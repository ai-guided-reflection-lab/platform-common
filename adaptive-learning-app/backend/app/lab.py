"""Optional participant sessions for local lab pilots."""
import hashlib
import os
import secrets
from uuid import uuid4

from fastapi import HTTPException
from .db import connection, now


def enabled():
    return os.getenv("ADAPTIVE_LAB_MODE", "false").lower() in {"true", "1", "yes"}


def instructor_id():
    return os.getenv("ADAPTIVE_LAB_INSTRUCTOR_ID", "instructor-demo")


def create_session(name):
    if not enabled():
        raise HTTPException(404, "Lab testing is unavailable.")
    name = name.strip()
    if not 1 <= len(name) <= 80:
        raise HTTPException(422, "Enter a name between 1 and 80 characters.")
    student_id, token = str(uuid4()), secrets.token_urlsafe(32)
    with connection() as conn:
        conn.execute("INSERT INTO users(id,email,display_name,role) VALUES (?,?,?,'student')",
                     (student_id, f"{student_id}@lab.invalid", name))
        conn.execute("INSERT INTO lab_sessions(token_hash,student_id,created_at) VALUES (?,?,?)",
                     (hashlib.sha256(token.encode()).hexdigest(), student_id, now()))
    return {"token": token, "user": {"id": student_id, "display_name": name, "role": "student"}}


def resolve(token):
    if not enabled() or not token:
        raise HTTPException(401, "Enter your name to join the lab.")
    with connection() as conn:
        row = conn.execute("SELECT u.* FROM lab_sessions s JOIN users u ON u.id=s.student_id WHERE s.token_hash=?",
                           (hashlib.sha256(token.encode()).hexdigest(),)).fetchone()
    if row is None:
        raise HTTPException(401, "Your lab session is unavailable. Enter your name again.")
    return {**dict(row), "lab_participant": True}


def assignment_code(assignment_id):
    with connection() as conn:
        for _ in range(10):
            conn.execute("INSERT INTO lab_codes(assignment_id,code) VALUES (?,?) ON CONFLICT DO NOTHING",
                         (assignment_id, secrets.token_hex(5).upper()))
            saved = conn.execute("SELECT code FROM lab_codes WHERE assignment_id=?", (assignment_id,)).fetchone()
            if saved:
                return saved["code"]
        raise HTTPException(503, "Could not create an assignment code. Please try again.")


def redeem(code, user):
    if not user.get("lab_participant"):
        raise HTTPException(401, "Enter your name first.")
    with connection() as conn:
        item = conn.execute("""SELECT a.id,a.title FROM lab_codes c JOIN assignments a ON a.id=c.assignment_id
                            WHERE c.code=? AND a.status='published' AND a.instructor_id=?""",
                            (code.strip().upper(), instructor_id())).fetchone()
        if item is None:
            raise HTTPException(404, "That code is invalid or the assignment is no longer available.")
        for table in ("lab_enrollments", "recipients"):
            conn.execute(f"INSERT INTO {table}(assignment_id,student_id) VALUES (?,?) ON CONFLICT DO NOTHING",
                         (item["id"], user["id"]))
    return {"assignment_id": item["id"], "title": item["title"]}
