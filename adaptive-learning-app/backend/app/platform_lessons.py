"""Trusted bridge for common-platform course lessons; no demo identity headers."""
import json
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from .common_rag_api import service_access
from .db import connection, now
from .lesson_content import configuration_issues
from .schemas import LearningPlan

router = APIRouter(prefix="/internal/platform/lessons", dependencies=[Depends(service_access)])


class PrepareInput(BaseModel):
    material: str = Field(min_length=30, max_length=30000)
    filename: str = Field(min_length=1, max_length=300)
    focus: str = Field(default="", max_length=10000)


class Identity(BaseModel):
    id: str = Field(min_length=1, max_length=200)
    email: str = Field(min_length=3, max_length=320)
    display_name: str = Field(min_length=1, max_length=200)


class PublishInput(BaseModel):
    id: str
    title: str
    instructions: str = ""
    instructor: Identity
    students: list[Identity]
    learning_plan: LearningPlan
    chunks: list[dict] = Field(default_factory=list)


@router.post("/prepare")
def prepare(body: PrepareInput):
    from .main import _document_plan
    material = body.material
    if body.focus.strip():
        material = ("Instructor learning focus: " + body.focus + "\n\nCourse material:\n" + material)[:30000]
    return _document_plan(material, body.filename, allow_course_material_fallback=True)


def identity(conn, person, role):
    existing = conn.execute("SELECT id,role FROM users WHERE email=?", (person.email.strip().lower(),)).fetchone()
    if existing and existing["role"] != role:
        raise HTTPException(409, "This email already belongs to a different SDL role.")
    row = conn.execute("""INSERT INTO users(id,email,display_name,role) VALUES (?,?,?,?)
        ON CONFLICT(email) DO UPDATE SET display_name=excluded.display_name RETURNING id""",
        (person.id, person.email.strip().lower(), person.display_name, role)).fetchone()
    return row["id"]


@router.post("/publish")
def publish(body: PublishInput):
    plan = body.learning_plan.model_dump()
    plan["content_approved"] = True
    issues = configuration_issues(plan)
    if plan.get("flow_version") != 2 or issues:
        raise HTTPException(422, {"message": "Prepare and review a complete SDL lesson before publishing.", "issues": issues})
    with connection() as conn:
        owner = identity(conn, body.instructor, "instructor")
        existing = conn.execute("SELECT instructor_id,status FROM assignments WHERE id=?", (body.id,)).fetchone()
        if existing and existing["instructor_id"] != owner:
            raise HTTPException(409, "The lesson belongs to another instructor.")
        student_ids = [identity(conn, person, "student") for person in body.students]
        if not existing:
            conn.execute("""INSERT INTO assignments(id,instructor_id,title,instructions,status,learning_plan,created_at,published_at)
                VALUES (?,?,?,?,'published',?,?,?)""", (body.id, owner, body.title, body.instructions, json.dumps(plan), now(), now()))
            documents = {}
            for i, chunk in enumerate(body.chunks):
                source = chunk["document_id"]
                if source not in documents:
                    document_id = str(uuid4())
                    documents[source] = document_id
                    conn.execute("INSERT INTO documents(id,assignment_id,filename,content_type,path,created_at) VALUES (?,?,?,?,?,?)",
                                 (document_id, body.id, chunk["title"], "application/octet-stream", "", now()))
                metadata = {**chunk.get("metadata", {}), "source_document_id": source, "page_number": chunk.get("page_number")}
                conn.execute("INSERT INTO chunks(id,document_id,position,content,embedding,metadata) VALUES (?,?,?,?,?,?)",
                             (str(uuid4()), documents[source], i, chunk["text"], json.dumps(chunk["embedding"]), json.dumps(metadata)))
        # Idempotent retries grant only the platform's current course recipients.
        conn.execute("DELETE FROM recipients WHERE assignment_id=?", (body.id,))
        conn.executemany("INSERT INTO recipients(assignment_id,student_id) VALUES (?,?)", [(body.id, sid) for sid in set(student_ids)])
    return {"id": body.id, "status": "published"}


@router.get("/{assignment_id}/progress")
def progress(assignment_id: str):
    with connection() as conn:
        rows = conn.execute("""SELECT u.id AS student_id,u.display_name,u.email,
            coalesce(t.status,'not_started') AS progress,t.completed_at
            FROM recipients r JOIN users u ON u.id=r.student_id
            LEFT JOIN attempts t ON t.assignment_id=r.assignment_id AND t.student_id=r.student_id
            WHERE r.assignment_id=? ORDER BY u.display_name""", (assignment_id,)).fetchall()
    return [dict(row) for row in rows]
