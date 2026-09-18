from __future__ import annotations

from pathlib import Path
import secrets
import smtplib
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
from app.classifier import classify_message
from app.rag import (
    RAG_DOCUMENT_SUFFIXES,
    course_document_ids,
    delete_document,
    generate_answer,
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
    _require_authority(request, 1)
    doc_id, chunks_added = ingest_text(payload.title, payload.text)
    message = "Text added to the knowledge base." if chunks_added else "That text was already indexed."
    return IngestResponse(document_id=doc_id, chunks_added=chunks_added, documents_scanned=1, message=message)


@app.post("/api/documents/scan", response_model=IngestResponse)
async def scan_documents(request: Request) -> IngestResponse:
    _require_authority(request, 1)
    documents_scanned, chunks_added, skipped_files = scan_raw_docs()
    if documents_scanned == 0:
        message = "No .txt, .md, .pdf, or .tex files found in backend/data/raw_docs."
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

        if db.is_enabled():
            db.save_rag_file(
                filename,
                getattr(upload, "content_type", "") or "application/octet-stream",
                content,
                str(conversation_id) if conversation_id else None,
                user_id=user_id,
            )
            files_stored += 1

        added = 0
        if suffix in rag_suffixes:
            _, added = ingest_file(target, str(conversation_id) if conversation_id else None)
            documents_scanned += 1
        chunks_added += added

    if documents_scanned == 0:
        message = "No supported files were uploaded. Use .txt, .md, .pdf, .tex, or common image files."
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

        document_id, added = ingest_file(target, course_id=course_id)
        db.save_rag_file(
            filename,
            getattr(upload, "content_type", "") or "application/octet-stream",
            content,
            user_id=instructor_id,
            course_id=course_id,
            document_id=document_id,
        )
        chunks_added += added
        documents_scanned += 1
        files_stored += 1

    if documents_scanned == 0:
        message = "No course documents were uploaded. Use .txt, .md, .pdf, or .tex files."
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
    chunks_removed = 0
    if removed.get("document_id"):
        chunks_removed = delete_document(str(removed["document_id"]), course_id=course_id)
    return {"deleted": True, "filename": removed["filename"], "chunks_removed": chunks_removed}



def _normalise_text(message: str) -> str:
    return " ".join(message.lower().strip().split())


def _is_file_status_question(message: str) -> bool:
    text = _normalise_text(message)
    words = text.split()

    # Keep real content questions in the RAG path. For example:
    # "what is machine learning in this paper?" should retrieve from the PDF,
    # not merely report that a PDF exists.
    content_question_patterns = [
        "what is",
        "what are",
        "explain",
        "summarize",
        "define",
        "according to",
        "why",
        "how does",
        "how do",
        "compare",
    ]
    file_listing_patterns = [
        "what file",
        "what files",
        "which file",
        "which files",
        "what document",
        "what documents",
        "which document",
        "which documents",
        "what pdf",
        "which pdf",
        "file name",
        "filename",
        "name of the file",
        "what is the file name",
        "what's the file name",
        "which file name",
        "file we looked at",
        "file we are looking at",
        "what kind of list",
        "what kind of lists",
        "what list",
        "what lists",
    ]

    if any(pattern in text for pattern in content_question_patterns) and not any(
        pattern in text for pattern in file_listing_patterns
    ):
        return False

    status_patterns = [
        "do you have a document",
        "do you have any document",
        "do you have documents",
        "do you have a file",
        "do you have any file",
        "do you see a file",
        "do you see my file",
        "can you see the file",
        "can you see my file",
        "can you read the file",
        "what is the file name",
        "what's the file name",
        "what file are we looking at",
        "what file did i upload",
        "what files did i upload",
        "what documents did i upload",
        "which file did i upload",
        "which documents did i upload",
        "list uploaded files",
        "list my files",
        "show uploaded files",
        "show my documents",
        "show my files",
        "did i upload",
        "is there a file",
        "is there any file",
        "uploaded files",
        "uploaded documents",
        "for now",
    ]
    if any(pattern in text for pattern in status_patterns):
        return True

    file_words = {"file", "files", "document", "documents", "pdf", "paper", "papers"}
    list_words = {"list", "lists", "show", "see", "have", "uploaded"}
    if file_words.intersection(words) and list_words.intersection(words):
        return True

    # Short phrases like "privacy risks pdf" or "machine learning pdf?" are
    # usually the user checking which uploaded document the chatbot sees.
    if len(words) <= 5 and file_words.intersection(words):
        return True

    return False


def _is_start_study_request(message: str) -> bool:
    text = _normalise_text(message)
    study_words = ["study", "start", "learn", "review", "practice"]
    file_refs = ["this file", "this document", "this pdf", "uploaded file", "uploaded document", "the file"]
    return any(word in text for word in study_words) and any(ref in text for ref in file_refs)


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


def _restore_missing_course_chunks(course_id: str, files: list[dict[str, object]]) -> int:
    """Rebuild Render-local chunks from the durable PostgreSQL file copy."""
    indexed_ids = course_document_ids(course_id)
    restored_chunks = 0
    for file in files:
        expected_document_id = str(file.get("document_id") or "")
        if expected_document_id and expected_document_id in indexed_ids:
            continue

        filename = Path(str(file.get("filename") or "document.txt")).name
        if Path(filename).suffix.lower() not in RAG_DOCUMENT_SUFFIXES:
            continue
        stored = db.get_rag_file(str(file.get("file_id") or ""))
        if not stored:
            continue

        try:
            restore_dir = settings.RAW_DOCS_DIR / course_id / "restored" / secrets.token_hex(8)
            restore_dir.mkdir(parents=True, exist_ok=True)
            target = restore_dir / filename
            target.write_bytes(bytes(stored["content"]))
            _, added = ingest_file(target, course_id=course_id)
            restored_chunks += added
        except Exception:
            # A damaged document should not prevent the rest of the course chat
            # or the course metadata answers from working.
            continue
    return restored_chunks


def _course_context_answer(
    course: dict[str, object],
    files: list[dict[str, object]],
    message: str,
) -> str | None:
    text = _normalise_text(message).rstrip("?.!")
    instructor_questions = {
        "what is the professor name",
        "what's the professor name",
        "who is the professor",
        "what is the instructor name",
        "what's the instructor name",
        "who is the instructor",
        "who teaches this course",
    }
    course_title_questions = {
        "what is the course title",
        "what's the course title",
        "what is the class name",
        "what's the class name",
        "which course is this",
        "which class is this",
    }
    scope_questions = {
        "what do you know",
        "what you know",
        "what can i ask",
        "what can you answer",
        "what materials do you know",
    }

    if text in instructor_questions:
        return f"The instructor for {course['course_code']} is {course['instructor_name']}."
    if text in course_title_questions:
        return f"This course is {course['course_code']}: {course['title']}."
    if text in scope_questions:
        names = _unique_file_names(files)
        document_text = ", ".join(names) if names else "no published documents yet"
        description = str(course.get("description") or "").strip()
        description_text = f" The course scope is: {description}" if description else ""
        return (
            f"I can answer questions about {course['course_code']}: {course['title']}."
            f"{description_text} Published materials: {document_text}."
        )
    return None




def _small_status_answer(files: list[dict[str, object]], message: str) -> str | None:
    text = _normalise_text(message)
    status_patterns = [
        "is it going well",
        "it's going well",
        "is this working",
        "does it work",
        "are we good",
        "are you ready",
    ]
    if not any(pattern in text for pattern in status_patterns):
        return None

    names = _unique_file_names(files)
    if not names:
        return "Not yet. I do not see an uploaded file in this chat."

    if len(names) == 1:
        return f"Yes. I can see {names[0]} in this chat. Ask me a specific question about it, or ask for a summary."

    return f"Yes. I can see {len(names)} files in this chat: {', '.join(names[:5])}."

def _file_state_answer(files: list[dict[str, object]], message: str) -> str | None:
    wants_status = _is_file_status_question(message)
    wants_study_start = _is_start_study_request(message)
    if not wants_status and not wants_study_start:
        return None

    names = _unique_file_names(files)
    if not names:
        return "I do not see any uploaded files in this chat yet. Attach a .txt, .md, .pdf, or .tex file first."

    if len(names) == 1:
        return (
            f"Yes, I see your uploaded file: {names[0]}. "
            "We can start with a summary, key concepts, or practice questions. Which one do you prefer?"
        )

    preview = ", ".join(names[:5])
    return (
        f"Yes, I see these uploaded files: {preview}. "
        "Which one should we focus on first?"
    )



def _is_document_overview_question(message: str) -> bool:
    text = _normalise_text(message)
    overview_patterns = [
        "topic",
        "main topic",
        "main idea",
        "what is this about",
        "what's this about",
        "what is the document about",
        "what is this document about",
        "what is this paper about",
        "what's the paper about",
        "what is the title",
        "what's the title",
        "document title",
        "paper title",
        "summarize",
        "summary",
        "overview",
    ]
    return any(pattern in text for pattern in overview_patterns)


OFF_TOPIC_TERMS = {"messi", "ronaldo", "soccer", "football", "nba", "weather", "movie", "restaurant"}


def _off_topic_answer(message: str) -> str | None:
    words = set(_normalise_text(message).replace("?", "").split())
    if not words.intersection(OFF_TOPIC_TERMS):
        return None
    return (
        "That question is outside the uploaded documents for this chat, "
        "so I should not answer it from the RAG workspace."
    )


@app.post("/api/chat", response_model=ChatResponse)
async def chat(payload: ChatRequest, request: Request) -> ChatResponse:
    conversation_id = payload.conversation_id
    course_id = payload.course_id
    history = payload.history
    user_id = _current_user_id(request)

    if not course_id:
        raise HTTPException(status_code=400, detail="Choose an approved course before opening the chatbot.")
    _require_course_access(request, course_id)

    if db.is_enabled():
        conversation_id = db.ensure_conversation(
            payload.conversation_id,
            payload.message,
            user_id=user_id,
            course_id=course_id,
        )
        if not db.conversation_belongs_to_course(conversation_id, user_id, course_id):
            raise HTTPException(status_code=409, detail="This conversation belongs to a different course.")
        stored_history = db.get_messages(conversation_id, limit=8)
        history = stored_history or payload.history
        db.add_message(conversation_id, "user", payload.message)

        off_topic_answer = _off_topic_answer(payload.message)
        if off_topic_answer:
            if hasattr(db, "clear_pending_clarification"):
                db.clear_pending_clarification(conversation_id)
            db.add_message(conversation_id, "assistant", off_topic_answer)
            return ChatResponse(answer=off_topic_answer, conversation_id=conversation_id, sources=[])

        pending = db.get_pending_clarification(conversation_id) if hasattr(db, "get_pending_clarification") else None
        if pending:
            combined_query = f"{pending['original_question']} {payload.message}".strip()
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
            db.add_message(conversation_id, "assistant", answer)
            return ChatResponse(answer=answer, conversation_id=conversation_id, sources=sources)

    current_files = db.list_rag_files(course_id=course_id) if db.is_enabled() else []
    if current_files:
        _restore_missing_course_chunks(course_id, current_files)

    course = db.get_course(course_id) if db.is_enabled() else None
    course_answer = _course_context_answer(course, current_files, payload.message) if course else None
    if course_answer:
        if db.is_enabled() and conversation_id:
            if hasattr(db, "clear_pending_clarification"):
                db.clear_pending_clarification(conversation_id)
            db.add_message(conversation_id, "assistant", course_answer)
        return ChatResponse(answer=course_answer, conversation_id=conversation_id or "local", sources=[])

    file_state_answer = _file_state_answer(current_files, payload.message) or _small_status_answer(current_files, payload.message)
    if file_state_answer:
        if db.is_enabled() and conversation_id:
            if hasattr(db, "clear_pending_clarification"):
                db.clear_pending_clarification(conversation_id)
            db.add_message(conversation_id, "assistant", file_state_answer)
        return ChatResponse(answer=file_state_answer, conversation_id=conversation_id or "local", sources=[])

    classification = await classify_message(payload.message, history)

    if classification.needs_clarification:
        answer = classification.clarification_question or "Could you clarify what you want to know?"
        if db.is_enabled() and conversation_id:
            if hasattr(db, "set_pending_clarification"):
                db.set_pending_clarification(conversation_id, payload.message, classification.target)
            db.add_message(conversation_id, "assistant", answer)
        return ChatResponse(answer=answer, conversation_id=conversation_id or "local", sources=[])

    if classification.direct_answer:
        answer = classification.direct_answer
        if db.is_enabled() and conversation_id:
            if hasattr(db, "clear_pending_clarification"):
                db.clear_pending_clarification(conversation_id)
            db.add_message(conversation_id, "assistant", answer)
        return ChatResponse(answer=answer, conversation_id=conversation_id or "local", sources=[])

    query = classification.rewritten_query or payload.message
    sources = retrieve(
        query,
        top_k=payload.top_k,
        conversation_id=conversation_id,
        course_id=course_id,
    )
    if not sources and current_files and _is_document_overview_question(payload.message):
        sources = retrieve_overview(
            conversation_id=conversation_id,
            top_k=payload.top_k,
            course_id=course_id,
        )
    answer = await generate_answer(query, history, sources)
    if answer.lower().startswith("i do not know from your uploaded notes"):
        sources = []

    if db.is_enabled() and conversation_id:
        if hasattr(db, "clear_pending_clarification"):
            db.clear_pending_clarification(conversation_id)
        db.add_message(conversation_id, "assistant", answer)

    return ChatResponse(answer=answer, conversation_id=conversation_id or "local", sources=sources)

app.mount("/", StaticFiles(directory=settings.FRONTEND_DIR, html=True), name="frontend")
