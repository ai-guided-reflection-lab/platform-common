"""Public workspace API. UI components never depend on engine-specific identities."""
from pathlib import Path
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, Request
from fastapi.responses import Response
from pydantic import BaseModel, Field
from app import db
from platform_app import engines, shared_rag, store
from platform_app.routes import user, professor, manage_course, get_assignment

router = APIRouter(prefix="/api/platform", tags=["workspace"])


class TestRoleInput(BaseModel):
    role: str = Field(pattern="^(student|professor)$")


def local_test_access(request):
    import os
    from app import settings
    from psycopg.conninfo import conninfo_to_dict
    return (os.getenv("WIRING_TEST_MODE") == "true"
            and request.client.host in {"127.0.0.1", "::1"}
            and conninfo_to_dict(settings.DATABASE_URL).get("host") in {"127.0.0.1", "localhost", "::1"})


def test_account_session(role):
    from app.main import _auth_response
    with store.connection() as conn:
        row = conn.execute("SELECT id FROM users_platform WHERE username=%s", ("wiring-" + role,)).fetchone()
    if not row:
        raise HTTPException(503, "The local test account is unavailable.")
    return _auth_response(db.get_user_by_id(str(row["id"])))


@router.post("/testing/session")
def public_demo_session(body: TestRoleInput, request: Request):
    """Explicit opt-in public demo: shared disposable personas, local database only."""
    import os
    if os.getenv("WIRING_PUBLIC_DEMO") != "true" or not local_test_access(request):
        raise HTTPException(404, "Not found.")
    return test_account_session(body.role)


@router.post("/testing/role")
def testing_role(body: TestRoleInput, request: Request, account=Depends(user)):
    """Switch disposable personas only in the explicitly enabled localhost test stack."""
    if (not local_test_access(request)
            or account.get("username") not in {"wiring-professor", "wiring-student"}):
        raise HTTPException(403, "Sign in with the account for the workspace you want to open.")
    return test_account_session(body.role)


class CourseInput(BaseModel):
    title: str = Field(min_length=1, max_length=150)
    course_code: str = Field(min_length=1, max_length=70)
    description: str = Field(default="", max_length=10000)


class ProfileInput(BaseModel):
    display_name: str = Field(min_length=1, max_length=200)
    email: str = Field(min_length=3, max_length=320)


@router.put("/profile")
def update_profile(body: ProfileInput, account=Depends(user)):
    if body.email.strip().lower() != account["email"].strip().lower():
        raise HTTPException(422, "Change your sign-in email through account management so it can be verified.")
    with store.connection() as conn:
        conn.execute("UPDATE users_platform SET display_name=%s WHERE id=%s", (body.display_name.strip(), account["user_id"]))
    return {"display_name": body.display_name.strip()}


class JoinInput(BaseModel):
    code: str = Field(pattern=r"^[A-Za-z0-9]{8}$")


class RetrievalInput(BaseModel):
    course_id: UUID
    document_ids: list[str] = Field(min_length=1, max_length=100)
    query: str = Field(min_length=1, max_length=20000)
    limit: int = Field(default=4, ge=1, le=20)


class ChunksInput(BaseModel):
    course_id: UUID
    document_ids: list[str] = Field(min_length=1, max_length=100)
    offset: int = Field(default=0, ge=0)
    limit: int = Field(default=200, ge=1, le=1000)


def course_access(course_id, account):
    with store.connection() as conn:
        allowed = conn.execute("SELECT 1 FROM course_memberships_platform WHERE course_id=%s AND user_id=%s AND status='approved'", (course_id, account["user_id"])).fetchone()
    if not allowed:
        raise HTTPException(404, "Course not found.")


@router.get("/courses")
def courses(account=Depends(user)):
    rows = db.list_courses_for_user(str(account["user_id"]))
    # The legacy API intentionally omits join codes; expose them only in this scoped API.
    with store.connection() as conn:
        for row in rows:
            if row.get("membership_status") != "approved":
                continue
            detail = conn.execute("SELECT join_code FROM courses_platform WHERE id=%s", (row["course_id"],)).fetchone()
            row["join_code"] = detail["join_code"] if detail else None
    return {"courses": [r for r in rows if r.get("membership_status") == "approved"]}


@router.post("/courses", status_code=201)
def create_course(body: CourseInput, account=Depends(professor)):
    row = db.create_course(str(account["user_id"]), body.course_code, body.title, body.description)
    with store.connection() as conn:
        row["join_code"] = conn.execute("SELECT join_code FROM courses_platform WHERE id=%s", (row["course_id"],)).fetchone()["join_code"]
    return row


@router.post("/courses/join")
def join_course(body: JoinInput, account=Depends(user)):
    if int(account["authority_level"]) <= 1:
        raise HTTPException(403, "Sign in with a student account to join a course.")
    with store.connection() as conn:
        course = conn.execute("SELECT * FROM courses_platform WHERE join_code=%s", (body.code.upper(),)).fetchone()
        if not course:
            raise HTTPException(404, "That course code was not found.")
        conn.execute("""INSERT INTO course_memberships_platform(id,course_id,user_id,course_role,status,reviewed_at)
            VALUES (%s,%s,%s,'student','approved',now()) ON CONFLICT(course_id,user_id)
            DO UPDATE SET status='approved',course_role='student',reviewed_at=now()""", (uuid4(), course["id"], account["user_id"]))
        conn.execute("""INSERT INTO assignment_recipients_platform(assignment_id,student_id)
            SELECT id,%s FROM assignments_platform WHERE course_id=%s AND status='published' AND audience='course'
            ON CONFLICT DO NOTHING""", (account["user_id"], course["id"]))
        lessons = conn.execute("SELECT * FROM assignments_platform WHERE course_id=%s AND status='published' AND audience='course' AND tool='self-directed-learning'", (course["id"],)).fetchall()
        # Retry is idempotent. Keep enrollment and recipient grants atomic on service failure.
        for lesson in lessons:
            owner = db.get_user_by_id(str(course["instructor_id"]))
            publish_sdl(conn, lesson, owner)
    return {"course_id": str(course["id"]), "title": course["title"]}


@router.get("/courses/{course_id}/documents")
def documents(course_id: UUID, account=Depends(user)):
    course_access(course_id, account)
    return {"files": db.list_rag_files(limit=100000, course_id=str(course_id))}


@router.post("/courses/{course_id}/documents/upload")
def upload(course_id: UUID, files: list[UploadFile] = File(...), account=Depends(professor)):
    manage_course(course_id, account)
    if len(files) > 50:
        raise HTTPException(422, "Upload up to 50 documents at a time.")
    result = []
    try:
        for file in files:
            content = file.file.read(10 * 1024 * 1024 + 1)
            if len(content) > 10 * 1024 * 1024:
                raise HTTPException(413, "Documents must be 10 MB or smaller.")
            result.append(shared_rag.ingest(course_id, account, Path((file.filename or "document").replace("\\", "/")).name, file.content_type or "application/octet-stream", content))
    except Exception:
        # A failed batch must not leave hidden partial uploads behind.
        if result:
            with store.connection() as conn:
                conn.execute("DELETE FROM documents WHERE id=ANY(%s::uuid[])", ([f["id"] for f in result],))
        raise
    return {"files": result}


@router.get("/courses/{course_id}/documents/{file_id}/download")
def download(course_id: UUID, file_id: UUID, account=Depends(user)):
    course_access(course_id, account)
    files = db.list_rag_files(limit=100000, course_id=str(course_id))
    if str(file_id) not in {f["file_id"] for f in files}:
        raise HTTPException(404, "Document not found.")
    file = db.get_rag_file(str(file_id))
    from urllib.parse import quote
    return Response(file["content"], media_type=file["content_type"], headers={"Content-Disposition": "attachment; filename*=UTF-8''" + quote(file["filename"])})


@router.post("/rag/search")
def retrieve(body: RetrievalInput, account=Depends(user)):
    course_access(body.course_id, account)
    return shared_rag.search(body.course_id, body.document_ids, body.query, body.limit)


@router.post("/rag/chunks")
def chunks(body: ChunksInput, account=Depends(user)):
    course_access(body.course_id, account)
    rows = shared_rag.course_chunks(body.course_id, body.document_ids)
    page = rows[body.offset:body.offset + body.limit]
    following = body.offset + len(page)
    return {"chunks": [{k: v for k, v in row.items() if k != "embedding"} for row in page],
            "total": len(rows), "next_offset": following if following < len(rows) else None}


@router.post("/assignments/{assignment_id}/prepare-sdl")
def prepare_sdl(assignment_id: UUID, account=Depends(professor)):
    with store.connection() as conn:
        item = get_assignment(conn, assignment_id, account, manage=True, lock=True)
        if item["tool"] != "self-directed-learning" or item["status"] != "draft":
            raise HTTPException(409, "Prepare an SDL draft before publishing.")
        rows = shared_rag.course_chunks(item["course_id"], item["config"]["document_ids"])
        material = "\n\n".join(row["text"] for row in rows)[:30000]
        if len(material.strip()) < 30:
            raise HTTPException(422, "Select readable, indexed documents before preparing the lesson.")
        plan = shared_rag.pipeline("POST", "/internal/platform/lessons/prepare", json={"material": material, "filename": item["title"], "focus": item["config"].get("prompt", "")})
        config = {**item["config"], "learning_plan": plan}
        from psycopg.types.json import Jsonb
        conn.execute("UPDATE assignments_platform SET config=%s,updated_at=now() WHERE id=%s", (Jsonb(config), assignment_id))
    return {"learning_plan": plan}


def publish_sdl(conn, item, account):
    students = conn.execute("""SELECT u.id AS user_id,u.email,u.display_name,u.username FROM users_platform u
        JOIN assignment_recipients_platform r ON r.student_id=u.id WHERE r.assignment_id=%s""", (item["id"],)).fetchall()
    # SDL uses its own lesson engine and tables; the shared assignment UUID links them.
    payload = {"id": str(item["id"]), "title": item["title"], "instructions": item["instructions"],
               "instructor": {"id": str(account["user_id"]), "email": account["email"], "display_name": account.get("display_name") or account["username"]},
               "students": [{"id": str(s["user_id"]), "email": s["email"], "display_name": s["display_name"] or s["username"]} for s in students],
               "learning_plan": item["config"].get("learning_plan", {}),
               "chunks": shared_rag.course_chunks(item["course_id"], item["config"]["document_ids"])}
    return shared_rag.pipeline("POST", "/internal/platform/lessons/publish", json=payload)
