from __future__ import annotations

import logging
from dataclasses import asdict
from pathlib import Path
import secrets
import smtplib
from time import monotonic
import uuid
from email.message import EmailMessage
from urllib.parse import quote, urlencode

import requests
from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from google.auth.transport import requests as google_requests
from google.oauth2 import id_token as google_id_token

from app import auth, db, settings
from app.answer_evaluation import (
    answer_evaluation_query,
    evaluate_student_answer,
    mastery_completion_answer,
    with_progress_status,
)
from app.classifier import MessageClassification, classify_message
from app.pipeline_logging import (
    begin_trace,
    debug_digest,
    debug_preview,
    end_trace,
    log_event,
    log_exception,
    set_conversation_id,
)
from app.rag import (
    RAG_DOCUMENT_SUFFIXES,
    generate_answer,
    generate_conversation_transition,
    ingest_file,
    ingest_text,
    retrieve,
    retrieve_overview,
    scan_raw_docs,
)
from app.schemas import (
    AuthorityUpdateRequest,
    AuthConfigResponse,
    AuthResponse,
    ChatRequest,
    ChatResponse,
    ConversationListResponse,
    ConversationResponse,
    CourseAccessRequestResponse,
    CourseAccessReviewRequest,
    CourseCreateRequest,
    CourseDeleteResponse,
    CourseListResponse,
    CourseMembership,
    CourseSummary,
    CurrentUserResponse,
    DatabaseStatus,
    EmailCodeRequest,
    EmailCodeResponse,
    GitHubAuthorizeResponse,
    GoogleAuthRequest,
    GoogleClientConfigResponse,
    IngestResponse,
    LoginRequest,
    OnboardingRequest,
    RagFileListResponse,
    RegisterRequest,
    SessionRefreshResponse,
    TextDocumentRequest,
    UserProfile,
)

app = FastAPI(title="Socratic-Chat")

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ALLOWED_ORIGINS or ["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
async def startup() -> None:
    missing = []
    if settings.SCHOOL_GOOGLE_AUTH_ENABLED:
        if not settings.GOOGLE_CLIENT_ID:
            missing.append("GOOGLE_CLIENT_ID")
        if not settings.ALLOWED_GOOGLE_DOMAINS:
            missing.append("ALLOWED_GOOGLE_DOMAINS")
        if not settings.AUTH_SESSION_SECRET:
            missing.append("AUTH_SESSION_SECRET")
    if settings.REQUIRE_GITHUB_ACCOUNT:
        if not settings.GITHUB_CLIENT_ID:
            missing.append("GITHUB_CLIENT_ID")
        if not settings.GITHUB_CLIENT_SECRET:
            missing.append("GITHUB_CLIENT_SECRET")
        if not settings.GITHUB_CALLBACK_URL:
            missing.append("GITHUB_CALLBACK_URL")
    if missing:
        raise RuntimeError(f"Authentication is enabled, but {', '.join(missing)} is not configured.")
    db.init_db()


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/api/db/status", response_model=DatabaseStatus)
async def database_status() -> DatabaseStatus:
    connected, message = db.check_status()
    return DatabaseStatus(enabled=db.is_enabled(), connected=connected, message=message)


def _session_user_id(request: Request) -> str:
    return auth.current_user_id(request, required=True) or ""


def _current_user_id(request: Request) -> str:
    user_id = _session_user_id(request)
    user = db.get_user_by_id(user_id)
    if user is None:
        raise HTTPException(status_code=401, detail="Account was not found.")
    if not user.get("onboarding_complete"):
        raise HTTPException(status_code=403, detail="Complete your one-time account setup to continue.")
    if settings.REQUIRE_GITHUB_ACCOUNT and not db.user_has_github(user_id):
        raise HTTPException(status_code=403, detail="Connect your GitHub account to continue.")
    return user_id


def _require_authority(request: Request, highest_level: int) -> dict[str, object]:
    user_id = _current_user_id(request)
    user = db.get_user_by_id(user_id)
    if user is None:
        raise HTTPException(status_code=401, detail="Account was not found.")
    if int(user.get("authority_level", 2)) > highest_level:
        role = "administrator" if highest_level == 0 else "instructor"
        raise HTTPException(status_code=403, detail=f"This action requires {role} permission.")
    return user


def _require_course_access(request: Request, course_id: str, manage: bool = False) -> dict[str, object]:
    user_id = _current_user_id(request)
    user = db.get_user_by_id(user_id)
    if user is None:
        raise HTTPException(status_code=401, detail="Account was not found.")
    allowed = (
        db.user_manages_course(course_id, user_id)
        if manage
        else db.user_can_access_course(course_id, user_id)
    )
    if not allowed:
        detail = (
            "Only the instructor who manages this course can perform that action."
            if manage
            else "Your course access request must be approved before you can use this class."
        )
        raise HTTPException(status_code=403, detail=detail)
    return user


def _auth_response(user: dict[str, object]) -> AuthResponse:
    access_token, expires_in_seconds = auth.issue_session(str(user["user_id"]))
    return AuthResponse(
        user=user,
        access_token=access_token,
        expires_in_seconds=expires_in_seconds,
    )


@app.get("/api/auth/config", response_model=AuthConfigResponse)
async def auth_config() -> AuthConfigResponse:
    school_domain = sorted(settings.ALLOWED_GOOGLE_DOMAINS)[0] if settings.ALLOWED_GOOGLE_DOMAINS else None
    return AuthConfigResponse(
        email_verification_required=(
            settings.REQUIRE_EMAIL_VERIFICATION and not settings.SCHOOL_GOOGLE_AUTH_ENABLED
        ),
        auth_mode=settings.AUTH_MODE,
        password_auth_enabled=settings.ALLOW_PASSWORD_LOGIN,
        registration_enabled=not settings.SCHOOL_GOOGLE_AUTH_ENABLED,
        school_domain=school_domain,
        github_account_required=settings.REQUIRE_GITHUB_ACCOUNT,
        github_oauth_configured=bool(settings.GITHUB_CLIENT_ID and settings.GITHUB_CLIENT_SECRET),
    )


def _send_verification_email(email: str, code: str) -> None:
    if not settings.SMTP_HOST or not settings.SMTP_FROM_EMAIL:
        raise HTTPException(
            status_code=503,
            detail="Email verification is enabled, but SMTP is not configured.",
        )

    message = EmailMessage()
    message["Subject"] = "Your Socratic-Chat verification code"
    message["From"] = settings.SMTP_FROM_EMAIL
    message["To"] = email
    message.set_content(
        f"Your verification code is {code}.\n\n"
        f"This code expires in {settings.EMAIL_CODE_EXPIRY_MINUTES} minutes."
    )

    try:
        with smtplib.SMTP(settings.SMTP_HOST, settings.SMTP_PORT, timeout=15) as smtp:
            if settings.SMTP_USE_TLS:
                smtp.starttls()
            if settings.SMTP_USERNAME:
                smtp.login(settings.SMTP_USERNAME, settings.SMTP_PASSWORD)
            smtp.send_message(message)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Could not send verification email: {exc}") from exc


@app.post("/api/auth/send-verification-code", response_model=EmailCodeResponse)
async def send_verification_code(payload: EmailCodeRequest) -> EmailCodeResponse:
    if settings.SCHOOL_GOOGLE_AUTH_ENABLED:
        raise HTTPException(status_code=403, detail="Use your school Google account to sign in.")
    if not settings.REQUIRE_EMAIL_VERIFICATION:
        raise HTTPException(status_code=409, detail="Email verification is disabled.")
    if not db.is_enabled():
        raise HTTPException(status_code=503, detail="PostgreSQL is not connected.")

    code = f"{secrets.randbelow(1_000_000):06d}"
    db.save_email_verification_code(payload.email, code, settings.EMAIL_CODE_EXPIRY_MINUTES)
    _send_verification_email(payload.email, code)
    return EmailCodeResponse(
        message="Verification code sent. Please check your email.",
        expires_in_minutes=settings.EMAIL_CODE_EXPIRY_MINUTES,
    )


@app.post("/api/auth/register", response_model=AuthResponse)
async def register(payload: RegisterRequest) -> AuthResponse:
    if settings.SCHOOL_GOOGLE_AUTH_ENABLED:
        raise HTTPException(status_code=403, detail="Registration is limited to school Google accounts.")
    if not db.is_enabled():
        raise HTTPException(status_code=503, detail="PostgreSQL is not connected.")
    if settings.REQUIRE_EMAIL_VERIFICATION:
        if not payload.verification_code or not db.verify_email_code(payload.email, payload.verification_code):
            raise HTTPException(status_code=400, detail="Verification code is wrong or expired.")
    try:
        user = db.create_user(payload.username, payload.email, payload.password)
    except Exception as exc:
        detail = str(exc)
        if "users_username_key" in detail or "users_email_key" in detail or "duplicate key" in detail:
            raise HTTPException(status_code=409, detail="That username or email is already registered.") from exc
        raise
    return _auth_response(user)


@app.get("/api/auth/google/config", response_model=GoogleClientConfigResponse)
async def google_client_config() -> GoogleClientConfigResponse:
    hosted_domain = sorted(settings.ALLOWED_GOOGLE_DOMAINS)[0] if settings.ALLOWED_GOOGLE_DOMAINS else None
    return GoogleClientConfigResponse(client_id=settings.GOOGLE_CLIENT_ID, hosted_domain=hosted_domain)


def _verify_google_credential(credential: str) -> dict[str, str]:
    if not settings.GOOGLE_CLIENT_ID:
        raise HTTPException(status_code=503, detail="Google sign-in is not configured.")

    try:
        data = google_id_token.verify_oauth2_token(
            credential,
            google_requests.Request(),
            settings.GOOGLE_CLIENT_ID,
        )
    except Exception as exc:
        raise HTTPException(status_code=401, detail="Could not verify Google sign-in.") from exc

    if data.get("iss") not in {"accounts.google.com", "https://accounts.google.com"}:
        raise HTTPException(status_code=401, detail="Google sign-in issuer is invalid.")
    if data.get("email_verified") is not True:
        raise HTTPException(status_code=401, detail="Google email is not verified.")
    if not data.get("email") or not data.get("sub"):
        raise HTTPException(status_code=401, detail="Google sign-in response is missing account details.")

    hosted_domain = str(data.get("hd") or "").lower()
    if settings.SCHOOL_GOOGLE_AUTH_ENABLED and hosted_domain not in settings.ALLOWED_GOOGLE_DOMAINS:
        allowed = " or ".join(f"@{domain}" for domain in sorted(settings.ALLOWED_GOOGLE_DOMAINS))
        raise HTTPException(
            status_code=403,
            detail=(
                f"Please choose your UNC Charlotte Google account ({allowed}). "
                "Personal Google accounts cannot access Socratic-Chat."
            ),
        )

    return {
        "email": str(data["email"]),
        "sub": str(data["sub"]),
        "name": str(data.get("name") or str(data["email"]).split("@", 1)[0]),
    }


@app.post("/api/auth/google", response_model=AuthResponse)
async def google_auth(payload: GoogleAuthRequest) -> AuthResponse:
    if not db.is_enabled():
        raise HTTPException(status_code=503, detail="PostgreSQL is not connected.")

    profile = _verify_google_credential(payload.credential)
    user = db.find_or_create_google_user(profile["email"], profile["sub"], profile.get("name"))
    return _auth_response(user)


@app.post("/api/auth/login", response_model=AuthResponse)
async def login(payload: LoginRequest) -> AuthResponse:
    if not settings.ALLOW_PASSWORD_LOGIN:
        raise HTTPException(status_code=403, detail="ID and password sign-in is disabled.")
    if not db.is_enabled():
        raise HTTPException(status_code=503, detail="PostgreSQL is not connected.")
    user = db.authenticate_user(
        payload.identifier,
        payload.password,
        require_google=settings.SCHOOL_GOOGLE_AUTH_ENABLED,
    )
    if not user:
        detail = "Socratic-Chat ID/email or password is incorrect."
        if settings.SCHOOL_GOOGLE_AUTH_ENABLED:
            detail += " New users must complete Google verification first."
        raise HTTPException(status_code=401, detail=detail)
    return _auth_response(user)


@app.post("/api/auth/session/refresh", response_model=SessionRefreshResponse)
async def refresh_session(request: Request) -> SessionRefreshResponse:
    user_id = _session_user_id(request)
    access_token, expires_in_seconds = auth.issue_session(user_id)
    return SessionRefreshResponse(access_token=access_token, expires_in_seconds=expires_in_seconds)


@app.post("/api/auth/onboarding", response_model=CurrentUserResponse)
async def complete_account_setup(payload: OnboardingRequest, request: Request) -> CurrentUserResponse:
    user_id = _session_user_id(request)
    if payload.password != payload.password_confirmation:
        raise HTTPException(status_code=400, detail="Password and password confirmation must match.")
    try:
        user = db.complete_onboarding(user_id, payload.username, payload.password, payload.position)
    except ValueError as exc:
        detail = str(exc)
        status_code = 409 if "already" in detail.lower() or "in use" in detail.lower() else 400
        raise HTTPException(status_code=status_code, detail=detail) from exc
    return CurrentUserResponse(user=user)


@app.get("/api/auth/me", response_model=CurrentUserResponse)
async def current_user(request: Request) -> CurrentUserResponse:
    user_id = _session_user_id(request)
    user = db.get_user_by_id(user_id)
    if user is None:
        raise HTTPException(status_code=401, detail="Account was not found.")
    return CurrentUserResponse(user=user)


@app.get("/api/admin/instructor-requests", response_model=list[UserProfile])
async def instructor_requests(request: Request) -> list[dict[str, object]]:
    _require_authority(request, 0)
    return db.list_pending_instructor_requests()


@app.post("/api/admin/users/{user_id}/authority", response_model=CurrentUserResponse)
async def update_user_authority(
    user_id: str, payload: AuthorityUpdateRequest, request: Request
) -> CurrentUserResponse:
    admin = _require_authority(request, 0)
    if str(admin["user_id"]) == user_id:
        raise HTTPException(status_code=400, detail="Administrators cannot change their own authority here.")
    try:
        user = db.set_user_authority(user_id, payload.authority_level)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return CurrentUserResponse(user=user)


@app.get("/api/courses", response_model=CourseListResponse)
async def list_courses(request: Request) -> CourseListResponse:
    user_id = _current_user_id(request)
    return CourseListResponse(courses=db.list_courses_for_user(user_id))


@app.post("/api/courses", response_model=CourseSummary)
async def create_course(payload: CourseCreateRequest, request: Request) -> CourseSummary:
    instructor = _require_authority(request, 1)
    try:
        course = db.create_course(
            str(instructor["user_id"]),
            payload.course_code,
            payload.title,
            payload.description,
        )
    except Exception as exc:
        detail = str(exc)
        if "courses_instructor_id_course_code_key" in detail or "duplicate key" in detail:
            raise HTTPException(status_code=409, detail="You already have a course with that code.") from exc
        raise
    course["membership_role"] = "instructor"
    course["membership_status"] = "approved"
    return CourseSummary(**course)


@app.delete("/api/courses/{course_id}", response_model=CourseDeleteResponse)
async def delete_course(course_id: str, request: Request) -> CourseDeleteResponse:
    instructor = _require_authority(request, 1)
    deleted_course = db.delete_course(str(instructor["user_id"]), course_id)
    if deleted_course is None:
        raise HTTPException(status_code=404, detail="Course not found or you do not manage it.")
    return CourseDeleteResponse(
        **deleted_course,
        message=f"{deleted_course['course_code']} was permanently deleted.",
    )


@app.post("/api/courses/{course_id}/request-access", response_model=CourseAccessRequestResponse)
async def request_course_access(course_id: str, request: Request) -> CourseAccessRequestResponse:
    user_id = _current_user_id(request)
    try:
        membership = db.request_course_access(course_id, user_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    message = (
        "You already have access to this course."
        if membership["status"] == "approved"
        else "Access request sent to the instructor."
    )
    return CourseAccessRequestResponse(membership=membership, message=message)


@app.get("/api/instructor/access-requests", response_model=list[CourseMembership])
async def list_course_access_requests(request: Request, course_id: str | None = None) -> list[dict[str, object]]:
    instructor = _require_authority(request, 1)
    return db.list_pending_course_requests(str(instructor["user_id"]), course_id=course_id)


@app.post("/api/instructor/access-requests/{membership_id}/review", response_model=CourseMembership)
async def review_course_access_request(
    membership_id: str,
    payload: CourseAccessReviewRequest,
    request: Request,
) -> CourseMembership:
    instructor = _require_authority(request, 1)
    try:
        membership = db.review_course_request(
            str(instructor["user_id"]),
            membership_id,
            payload.decision,
            payload.rejection_reason,
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return CourseMembership(**membership)


@app.get("/api/instructor/enrolled-students", response_model=list[CourseMembership])
async def list_enrolled_course_students(request: Request, course_id: str) -> list[dict[str, object]]:
    instructor = _require_authority(request, 1)
    return db.list_approved_course_students(str(instructor["user_id"]), course_id)


@app.delete("/api/instructor/enrolled-students/{membership_id}", response_model=CourseMembership)
async def remove_enrolled_course_student(membership_id: str, request: Request) -> CourseMembership:
    instructor = _require_authority(request, 1)
    try:
        membership = db.remove_course_student(str(instructor["user_id"]), membership_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return CourseMembership(**membership)


@app.post("/api/auth/github/start", response_model=GitHubAuthorizeResponse)
async def github_start(request: Request) -> GitHubAuthorizeResponse:
    user_id = _session_user_id(request)
    if not settings.GITHUB_CLIENT_ID or not settings.GITHUB_CLIENT_SECRET or not settings.GITHUB_CALLBACK_URL:
        raise HTTPException(status_code=503, detail="GitHub sign-in is not configured.")
    state = db.create_github_oauth_state(user_id)
    query = urlencode(
        {
            "client_id": settings.GITHUB_CLIENT_ID,
            "redirect_uri": settings.GITHUB_CALLBACK_URL,
            "state": state,
        }
    )
    return GitHubAuthorizeResponse(authorize_url=f"https://github.com/login/oauth/authorize?{query}")


def _frontend_github_redirect(result: str) -> RedirectResponse:
    separator = "&" if "?" in settings.FRONTEND_URL else "?"
    return RedirectResponse(f"{settings.FRONTEND_URL}{separator}github={quote(result)}", status_code=303)


@app.get("/api/auth/github/callback")
async def github_callback(code: str = "", state: str = "", error: str = "") -> RedirectResponse:
    if error or not code or not state:
        return _frontend_github_redirect("cancelled")

    user_id = db.consume_github_oauth_state(state)
    if not user_id:
        return _frontend_github_redirect("invalid_state")

    try:
        token_response = requests.post(
            "https://github.com/login/oauth/access_token",
            data={
                "client_id": settings.GITHUB_CLIENT_ID,
                "client_secret": settings.GITHUB_CLIENT_SECRET,
                "code": code,
                "redirect_uri": settings.GITHUB_CALLBACK_URL,
            },
            headers={"Accept": "application/json"},
            timeout=15,
        )
        token_response.raise_for_status()
        access_token = token_response.json().get("access_token")
        if not access_token:
            return _frontend_github_redirect("token_error")

        profile_response = requests.get(
            "https://api.github.com/user",
            headers={
                "Accept": "application/vnd.github+json",
                "Authorization": f"Bearer {access_token}",
                "X-GitHub-Api-Version": "2022-11-28",
            },
            timeout=15,
        )
        profile_response.raise_for_status()
        profile = profile_response.json()
        github_id = int(profile["id"])
        github_username = str(profile["login"])
        db.link_github_account(user_id, github_id, github_username)
    except (KeyError, TypeError, ValueError, requests.RequestException):
        return _frontend_github_redirect("error")

    return _frontend_github_redirect("connected")


@app.get("/api/conversations", response_model=ConversationListResponse)
async def list_conversations(request: Request) -> ConversationListResponse:
    user_id = _current_user_id(request)
    if not db.is_enabled():
        return ConversationListResponse(conversations=[])
    course_id = request.query_params.get("course_id")
    if course_id:
        _require_course_access(request, course_id)
    return ConversationListResponse(
        conversations=db.list_conversations(user_id=user_id, course_id=course_id)
    )


@app.get("/api/conversations/{conversation_id}", response_model=ConversationResponse)
async def get_conversation(conversation_id: str, request: Request) -> ConversationResponse:
    user_id = _current_user_id(request)
    if not db.is_enabled():
        return ConversationResponse(conversation_id=conversation_id, messages=[])
    if not db.conversation_belongs_to(conversation_id, user_id):
        raise HTTPException(status_code=404, detail="Chat not found.")
    return ConversationResponse(conversation_id=conversation_id, messages=db.get_messages(conversation_id))


@app.delete("/api/conversations/{conversation_id}")
async def delete_conversation(conversation_id: str, request: Request) -> dict[str, bool]:
    user_id = _current_user_id(request)
    if not db.is_enabled():
        return {"deleted": False}
    if not db.conversation_belongs_to(conversation_id, user_id):
        return {"deleted": False}
    return {"deleted": db.delete_conversation(conversation_id)}


@app.get("/api/documents/files", response_model=RagFileListResponse)
async def list_uploaded_files(request: Request) -> RagFileListResponse:
    user_id = _current_user_id(request)
    if not db.is_enabled():
        return RagFileListResponse(files=[])
    conversation_id = request.query_params.get("conversation_id")
    try:
        files = db.list_rag_files(conversation_id=conversation_id, user_id=user_id)
    except TypeError:
        files = db.list_rag_files(conversation_id=conversation_id)
    return RagFileListResponse(files=files)


@app.get("/api/documents/files/{file_id}/download")
async def download_uploaded_file(file_id: str, request: Request) -> Response:
    user_id = _current_user_id(request)
    if not db.is_enabled():
        raise HTTPException(status_code=503, detail="PostgreSQL is not connected.")

    file = db.get_rag_file(file_id, user_id=user_id)
    if not file:
        raise HTTPException(status_code=404, detail="File not found.")

    filename = str(file["filename"])
    content_type = str(file["content_type"] or "application/octet-stream")
    quoted_filename = quote(filename)
    headers = {
        "Content-Disposition": f"attachment; filename*=UTF-8''{quoted_filename}",
        "Content-Length": str(file["file_size"]),
    }
    return Response(content=file["content"], media_type=content_type, headers=headers)


@app.post("/api/documents/text", response_model=IngestResponse)
async def add_text_document(payload: TextDocumentRequest, request: Request) -> IngestResponse:
    user = _require_authority(request, 1)
    content = payload.text.encode("utf-8")
    file_id = db.save_rag_file(
        payload.title, "text/plain; charset=utf-8", content, user_id=str(user["user_id"]),
    )
    if not file_id:
        raise HTTPException(status_code=503, detail="PostgreSQL is required to index documents.")
    doc_id, chunks_added = ingest_text(payload.title, payload.text, file_id=file_id)
    message = "Text added to the knowledge base." if chunks_added else "That text was already indexed."
    return IngestResponse(document_id=doc_id, chunks_added=chunks_added, documents_scanned=1, message=message)


@app.post("/api/documents/scan", response_model=IngestResponse)
async def scan_documents(request: Request) -> IngestResponse:
    _require_authority(request, 1)
    documents_scanned, chunks_added, skipped_files = scan_raw_docs()
    if documents_scanned == 0:
        message = "No .txt, .md, .pdf, .tex, .html, or .htm files found in backend/data/raw_docs."
    elif chunks_added == 0:
        message = "Documents were found, but no new chunks were added. They may already be indexed."
    else:
        message = "Documents scanned successfully."
    return IngestResponse(
        chunks_added=chunks_added,
        documents_scanned=documents_scanned,
        skipped_files=skipped_files,
        message=message,
    )


def _chat_title_from_uploads(files: list[object]) -> str:
    filenames: list[str] = []
    seen = set()
    for upload in files:
        filename = Path(getattr(upload, "filename", "") or "upload.txt").name
        if not filename or filename in seen:
            continue
        seen.add(filename)
        filenames.append(filename)

    if not filenames:
        return "Uploaded documents"

    if len(filenames) == 1:
        return filenames[0]

    return f"{filenames[0]} + {len(filenames) - 1} more"


@app.post("/api/documents/upload", response_model=IngestResponse)
async def upload_document(request: Request) -> IngestResponse:
    user = _require_authority(request, 1)
    user_id = str(user["user_id"])
    try:
        form = await request.form()
    except (AssertionError, RuntimeError) as exc:
        raise HTTPException(status_code=501, detail="Install python-multipart to upload files.") from exc

    files = form.getlist("files") or form.getlist("file")
    if not files:
        raise HTTPException(status_code=400, detail="Choose at least one file to upload.")

    conversation_id = form.get("conversation_id")
    chat_title = _chat_title_from_uploads(files)
    if conversation_id and db.is_enabled():
        db.ensure_conversation(str(conversation_id), chat_title, user_id=user_id)
        if hasattr(db, "set_conversation_title"):
            db.set_conversation_title(str(conversation_id), chat_title, user_id=user_id)

    settings.RAW_DOCS_DIR.mkdir(parents=True, exist_ok=True)
    chunks_added = 0
    documents_scanned = 0
    files_stored = 0
    skipped_files: list[str] = []

    store_suffixes = RAG_DOCUMENT_SUFFIXES | {".png", ".jpg", ".jpeg", ".gif", ".webp"}
    rag_suffixes = RAG_DOCUMENT_SUFFIXES

    for upload in files:
        filename = Path(getattr(upload, "filename", "") or "upload.txt").name
        suffix = Path(filename).suffix.lower()
        if suffix not in store_suffixes:
            skipped_files.append(filename)
            continue

        content = upload.file.read()
        target = settings.RAW_DOCS_DIR / filename
        target.write_bytes(content)

        file_id = None
        if db.is_enabled():
            file_id = db.save_rag_file(
                filename,
                getattr(upload, "content_type", "") or "application/octet-stream",
                content,
                str(conversation_id) if conversation_id else None,
                user_id=user_id,
            )
            files_stored += 1

        added = 0
        if suffix in rag_suffixes:
            if not file_id:
                raise HTTPException(status_code=503, detail="PostgreSQL is required to index documents.")
            _, added = ingest_file(
                target, str(conversation_id) if conversation_id else None, file_id=file_id,
            )
            documents_scanned += 1
        chunks_added += added

    if documents_scanned == 0:
        message = "No supported files were uploaded. Use .txt, .md, .pdf, .tex, .html, .htm, or common image files."
    elif chunks_added == 0:
        message = "Uploaded file(s) were already indexed."
    else:
        message = "Uploaded file(s) added to the knowledge base."

    return IngestResponse(
        chunks_added=chunks_added,
        documents_scanned=documents_scanned,
        files_stored=files_stored,
        skipped_files=skipped_files,
        message=message,
    )


@app.get("/api/courses/{course_id}/documents", response_model=RagFileListResponse)
async def list_course_documents(course_id: str, request: Request) -> RagFileListResponse:
    _require_course_access(request, course_id, manage=True)
    return RagFileListResponse(files=db.list_rag_files(course_id=course_id))


@app.post("/api/courses/{course_id}/documents/upload", response_model=IngestResponse)
async def upload_course_documents(course_id: str, request: Request) -> IngestResponse:
    instructor = _require_course_access(request, course_id, manage=True)
    instructor_id = str(instructor["user_id"])
    try:
        form = await request.form()
    except (AssertionError, RuntimeError) as exc:
        raise HTTPException(status_code=501, detail="Install python-multipart to upload files.") from exc

    files = form.getlist("files") or form.getlist("file")
    if not files:
        raise HTTPException(status_code=400, detail="Choose at least one file to upload.")

    chunks_added = 0
    documents_scanned = 0
    files_stored = 0
    skipped_files: list[str] = []
    supported_suffixes = RAG_DOCUMENT_SUFFIXES

    for upload in files:
        filename = Path(getattr(upload, "filename", "") or "upload.txt").name
        suffix = Path(filename).suffix.lower()
        if suffix not in supported_suffixes:
            skipped_files.append(filename)
            continue

        content = upload.file.read()
        upload_dir = settings.RAW_DOCS_DIR / course_id / secrets.token_hex(8)
        upload_dir.mkdir(parents=True, exist_ok=True)
        target = upload_dir / filename
        target.write_bytes(content)

        file_id = db.save_rag_file(
            filename,
            getattr(upload, "content_type", "") or "application/octet-stream",
            content,
            user_id=instructor_id,
            course_id=course_id,
        )
        if not file_id:
            raise HTTPException(status_code=503, detail="PostgreSQL is required to index documents.")
        _, added = ingest_file(target, course_id=course_id, file_id=file_id)
        chunks_added += added
        documents_scanned += 1
        files_stored += 1

    if documents_scanned == 0:
        message = "No course documents were uploaded. Use .txt, .md, .pdf, .tex, .html, or .htm files."
    elif chunks_added == 0:
        message = "The course documents were stored; matching content was already indexed."
    else:
        message = "Course documents were published to the student knowledge base."

    return IngestResponse(
        chunks_added=chunks_added,
        documents_scanned=documents_scanned,
        files_stored=files_stored,
        skipped_files=skipped_files,
        message=message,
    )


@app.delete("/api/courses/{course_id}/documents/{file_id}")
async def delete_course_document(course_id: str, file_id: str, request: Request) -> dict[str, object]:
    _require_course_access(request, course_id, manage=True)
    removed = db.delete_course_document(file_id, course_id)
    if removed is None:
        raise HTTPException(status_code=404, detail="Course document was not found.")
    return {
        "deleted": True,
        "filename": removed["filename"],
        "chunks_removed": int(removed.get("chunks_removed") or 0),
    }



def _unique_file_names(files: list[dict[str, object]]) -> list[str]:
    names: list[str] = []
    seen = set()
    for file in files:
        name = str(file.get("filename", "")).strip()
        if not name or name in seen:
            continue
        seen.add(name)
        names.append(name)
    return names


def _operational_context_answer(
    course: dict[str, object],
    files: list[dict[str, object]],
    classification: MessageClassification,
) -> str | None:
    request_type = classification.operational_request
    if request_type == "course_instructor":
        return f"The instructor for {course['course_code']} is {course['instructor_name']}."
    if request_type == "course_title":
        return f"This course is {course['course_code']}: {course['title']}."
    if request_type == "course_scope":
        names = _unique_file_names(files)
        document_text = ", ".join(names) if names else "no published documents yet"
        description = str(course.get("description") or "").strip()
        description_text = f" The course scope is: {description}" if description else ""
        return (
            f"I can answer questions about {course['course_code']}: {course['title']}."
            f"{description_text} Published materials: {document_text}."
        )
    if request_type in {"list_documents", "document_visibility", "system_status"}:
        names = _unique_file_names(files)
        if not names:
            return "No course documents are currently published."
        return f"Published course documents: {', '.join(names)}."
    return None




def _save_assistant_message(conversation_id: str, answer: str) -> None:
    log_event(11, "conversation_save_started", role="assistant")
    db.add_message(conversation_id, "assistant", answer)
    log_event(11, "conversation_saved", role="assistant")


def _ensure_course_conversation(
    requested_id: str | None,
    title: str,
    user_id: str,
    course_id: str,
) -> tuple[str, bool]:
    """Return a conversation in this user/course scope, replacing stale client IDs."""
    conversation_id = db.ensure_conversation(
        requested_id,
        title,
        user_id=user_id,
        course_id=course_id,
    )
    if db.conversation_belongs_to_course(conversation_id, user_id, course_id):
        return conversation_id, False

    return (
        db.ensure_conversation(
            None,
            title,
            user_id=user_id,
            course_id=course_id,
        ),
        True,
    )


async def _run_chat_pipeline(payload: ChatRequest, request: Request) -> ChatResponse:
    conversation_id = payload.conversation_id
    course_id = payload.course_id
    history = payload.history
    user_id = _current_user_id(request)
    pending: dict[str, object] | None = None
    user_message_id: int | None = None

    if not course_id:
        raise HTTPException(status_code=400, detail="Choose an approved course before opening the chatbot.")
    _require_course_access(request, course_id)
    log_event(2, "course_access_validated", course_id=course_id)

    if db.is_enabled():
        conversation_id, replaced_stale_id = _ensure_course_conversation(
            payload.conversation_id,
            payload.message,
            user_id,
            course_id,
        )
        set_conversation_id(conversation_id)
        log_event(
            3,
            "conversation_ready",
            database_enabled=True,
            replaced_stale_id=replaced_stale_id,
        )
        stored_history = db.get_messages(conversation_id, limit=None)
        history = stored_history or payload.history
        log_event(3, "history_loaded", messages=len(history), source="database" if stored_history else "request")
        saved_message_id = db.add_message(conversation_id, "user", payload.message)
        user_message_id = saved_message_id if isinstance(saved_message_id, int) else None
        log_event(3, "user_message_saved")
        pending = db.get_pending_clarification(conversation_id) if hasattr(db, "get_pending_clarification") else None
    else:
        log_event(3, "history_loaded", messages=len(history), source="request")

    log_event(4, "message_classification_started")
    classification = await classify_message(payload.message, history)
    log_event(
        4,
        "message_classification_completed",
        source=classification.source,
        route=classification.route,
        student_intent=classification.student_intent,
        question_type=classification.question_type,
        conversation_state=classification.conversation_state,
        dialogue_status=classification.dialogue_status,
        conversation_action=classification.conversation_action,
        has_substantive_claim=classification.has_substantive_claim,
        wants_to_continue=classification.wants_to_continue,
        target_concepts="|".join(classification.target_concepts) or "none",
        confidence=round(classification.confidence, 2),
        needs_clarification=classification.needs_clarification,
        direct_answer=classification.direct_answer is not None,
        operational_request=classification.operational_request,
        understanding_level=classification.understanding_level,
        support_level=classification.support_level,
        query_rewritten=bool(classification.rewritten_query and classification.rewritten_query != payload.message),
    )

    if db.is_enabled() and conversation_id and hasattr(db, "update_conversation_dialogue_state"):
        db.update_conversation_dialogue_state(
            conversation_id,
            classification.dialogue_status,
            classification.conversation_action,
            classification.target,
            classification.understanding_level,
            classification.support_level,
        )

    if classification.conversation_action in {"soft_close", "complete"}:
        log_event(4, "route_selected", route=classification.conversation_action)
        answer = await generate_conversation_transition(payload.message, history, classification)
        if db.is_enabled() and conversation_id:
            if hasattr(db, "clear_pending_clarification"):
                db.clear_pending_clarification(conversation_id)
            _save_assistant_message(conversation_id, answer)
        return ChatResponse(answer=answer, conversation_id=conversation_id or "local", sources=[])

    current_files = db.list_rag_files(course_id=course_id) if db.is_enabled() else []
    course = db.get_course(course_id) if db.is_enabled() else None
    log_event(3, "course_context_loaded", files=len(current_files), course_found=course is not None)
    operational_answer = _operational_context_answer(course, current_files, classification) if course else None
    if operational_answer:
        log_event(
            4,
            "route_selected",
            route="operational_context_answer",
            operational_request=classification.operational_request,
        )
        if db.is_enabled() and conversation_id:
            if hasattr(db, "clear_pending_clarification"):
                db.clear_pending_clarification(conversation_id)
            _save_assistant_message(conversation_id, operational_answer)
        return ChatResponse(answer=operational_answer, conversation_id=conversation_id or "local", sources=[])

    if pending:
        log_event(4, "route_selected", route="pending_clarification")
        combined_query = f"{pending['original_question']} {payload.message}".strip()
        debug_digest("combined_query", combined_query)
        if hasattr(db, "clear_pending_clarification"):
            db.clear_pending_clarification(conversation_id)
        sources = retrieve(
            combined_query,
            top_k=payload.top_k,
            conversation_id=conversation_id,
            course_id=course_id,
        )
        answer = await generate_answer(combined_query, history, sources)
        if answer.lower().startswith("i do not know from your uploaded notes"):
            sources = []
        _save_assistant_message(conversation_id, answer)
        return ChatResponse(answer=answer, conversation_id=conversation_id, sources=sources)

    if classification.needs_clarification:
        log_event(4, "route_selected", route="clarification_response")
        answer = classification.clarification_question or "Could you clarify what you want to know?"
        if db.is_enabled() and conversation_id:
            if hasattr(db, "set_pending_clarification"):
                db.set_pending_clarification(conversation_id, payload.message, classification.target)
            _save_assistant_message(conversation_id, answer)
        return ChatResponse(answer=answer, conversation_id=conversation_id or "local", sources=[])

    if classification.direct_answer:
        log_event(4, "route_selected", route="classified_direct_answer")
        answer = classification.direct_answer
        if db.is_enabled() and conversation_id:
            if hasattr(db, "clear_pending_clarification"):
                db.clear_pending_clarification(conversation_id)
            _save_assistant_message(conversation_id, answer)
        return ChatResponse(answer=answer, conversation_id=conversation_id or "local", sources=[])

    query = answer_evaluation_query(payload.message, history, classification)
    log_event(4, "route_selected", route="rag_generation")
    sources = retrieve(
        query,
        top_k=payload.top_k,
        conversation_id=conversation_id,
        course_id=course_id,
    )
    if (
        not sources
        and current_files
        and classification.operational_request == "document_overview"
    ):
        sources = retrieve_overview(
            conversation_id=conversation_id,
            top_k=payload.top_k,
            course_id=course_id,
        )
    concept_hint = classification.target
    if not concept_hint and db.is_enabled() and conversation_id:
        concept_hint = db.get_conversation_active_concept(conversation_id)
    evaluation = await evaluate_student_answer(
        payload.message,
        history,
        sources,
        classification,
        concept_hint=concept_hint,
    )
    if evaluation and db.is_enabled() and conversation_id and hasattr(db, "save_mastery_assessment"):
        progress_status = db.save_mastery_assessment(
            conversation_id,
            user_message_id,
            user_id,
            course_id,
            asdict(evaluation),
        )
        evaluation = with_progress_status(evaluation, progress_status)
        log_event(
            6,
            "concept_progress_updated",
            concept=evaluation.concept,
            status=progress_status,
            score=evaluation.total_score,
            understanding_improved=evaluation.understanding_improved,
            application=evaluation.application if evaluation.application is not None else "not_assessed",
        )

    if evaluation and evaluation.progress_status == "mastered":
        log_event(4, "route_selected", route="mastery_completed")
        answer = mastery_completion_answer(evaluation)
    else:
        answer = await generate_answer(
            payload.message,
            history,
            sources,
            classification=classification,
            evaluation=evaluation,
        )
    if answer.lower().startswith((
        "i do not know from your uploaded notes",
        "that topic is outside the currently published course documentation",
    )):
        sources = []

    if db.is_enabled() and conversation_id:
        if hasattr(db, "clear_pending_clarification"):
            db.clear_pending_clarification(conversation_id)
        _save_assistant_message(conversation_id, answer)

    return ChatResponse(answer=answer, conversation_id=conversation_id or "local", sources=sources)


@app.post("/api/chat", response_model=ChatResponse)
async def chat(payload: ChatRequest, request: Request) -> ChatResponse:
    trace_id = uuid.uuid4().hex
    tokens = begin_trace(trace_id, payload.conversation_id)
    started = monotonic()
    log_event(
        1,
        "chat_received",
        course_id=payload.course_id,
        message_chars=len(payload.message),
        request_history_messages=len(payload.history),
    )
    debug_digest("user_message", payload.message)
    try:
        response = await _run_chat_pipeline(payload, request)
        set_conversation_id(response.conversation_id)
        debug_preview("final_answer", response.answer)
        log_event(
            12,
            "response_returned",
            sources=len(response.sources),
            response_chars=len(response.answer),
            latency_ms=round((monotonic() - started) * 1000),
        )
        return response
    except HTTPException as error:
        log_event(
            "error",
            "chat_rejected",
            level=logging.WARNING,
            status_code=error.status_code,
            latency_ms=round((monotonic() - started) * 1000),
        )
        raise
    except Exception as error:
        log_exception(
            "error",
            "chat_failed",
            error,
            latency_ms=round((monotonic() - started) * 1000),
        )
        raise
    finally:
        end_trace(tokens)

app.mount("/", StaticFiles(directory=settings.FRONTEND_DIR, html=True), name="frontend")
