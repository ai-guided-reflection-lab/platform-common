"""Public workspace API. UI components never depend on engine-specific identities."""
from pathlib import Path
import os
from uuid import UUID

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.responses import Response
from pydantic import BaseModel, Field
from app import db
from platform_app import engines, shared_rag, store
from platform_app.routes import user, professor, manage_course, get_assignment

router = APIRouter(prefix="/api/platform", tags=["workspace"])


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


@router.get("/context")
def course_context(course_id: UUID | None = None, account=Depends(user)):
    # Browser context chooses a view; approved membership remains authoritative.
    with store.connection() as conn:
        if course_id:
            row = conn.execute("""SELECT c.id AS course_id,c.course_code,c.title FROM courses_platform c
                JOIN course_memberships_platform m ON m.course_id=c.id
                WHERE c.id=%s AND m.user_id=%s AND m.status='approved'""", (course_id, account['user_id'])).fetchone()
        elif os.getenv('PLATFORM_LOCAL_COURSE_CODE') or os.getenv('MAIN_COMPARISON_MODE') == 'true':
            row = conn.execute("""SELECT c.id AS course_id,c.course_code,c.title FROM courses_platform c
                JOIN course_memberships_platform m ON m.course_id=c.id
                WHERE c.course_code=%s AND m.user_id=%s AND m.status='approved'
                ORDER BY c.created_at,c.id LIMIT 1""", (os.getenv('PLATFORM_LOCAL_COURSE_CODE') or os.getenv('LOCAL_COMPARISON_COURSE_CODE','SE101'), account['user_id'])).fetchone()
        else:
            row = None
    if not row:
        raise HTTPException(404, 'Open this tool from your Canvas course to access its assignments.')
    return row


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


def _student_material_files(assignment_id, account):
    with store.connection() as conn:
        item = get_assignment(conn, assignment_id, account)
    if item["tool"] != "self-directed-learning":
        raise HTTPException(404, "Assignment not found.")
    config = (item.get("snapshot") or {}).get("config", item["config"])
    selected = {str(value) for value in config.get("document_ids", [])}
    return [file for file in db.list_rag_files(limit=100000, course_id=str(item["course_id"]))
            if str(file.get("document_id")) in selected]


@router.get("/self-directed/assignments/{assignment_id}/materials")
def student_materials(assignment_id: UUID, account=Depends(user)):
    files = _student_material_files(assignment_id, account)
    return {"files": [{"id": file["file_id"], "filename": file["filename"]} for file in files]}


@router.get("/self-directed/assignments/{assignment_id}/materials/{file_id}")
def student_material_download(assignment_id: UUID, file_id: UUID, account=Depends(user)):
    if str(file_id) not in {str(file["file_id"]) for file in _student_material_files(assignment_id, account)}:
        raise HTTPException(404, "Document not found.")
    file = db.get_rag_file(str(file_id))
    if not file:
        raise HTTPException(404, "Document not found.")
    from urllib.parse import quote
    return Response(file["content"], media_type=file["content_type"], headers={
        "Content-Disposition": "attachment; filename*=UTF-8''" + quote(file["filename"]),
        "Cache-Control": "private, no-store",
    })


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
        focus = item["config"].get("prompt", "")
        questions = [q.strip() for q in item["config"].get("custom_questions", []) if q.strip()]
        if questions:
            focus += "\nInstructor sub-questions to address:\n" + "\n".join(questions)
        plan = shared_rag.pipeline("POST", "/internal/platform/lessons/prepare", json={"material": material, "filename": item["title"], "focus": focus, "starting_point": item["config"].get("starting_point", ""), "ending_point": item["config"].get("ending_point", "")})
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
