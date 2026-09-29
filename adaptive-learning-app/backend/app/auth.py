from __future__ import annotations

from fastapi import Header, HTTPException

from .db import connection, row_dict


def current_user(x_demo_user: str | None = Header(default=None)) -> dict:
    if not x_demo_user:
        raise HTTPException(401, "Choose a demo user first.")
    with connection() as conn:
        user = row_dict(conn.execute("SELECT * FROM users WHERE id=?", (x_demo_user,)).fetchone())
    if user is None:
        raise HTTPException(401, "Unknown demo user.")
    return user


def instructor(user: dict = None) -> dict:
    user = user or current_user()
    if user["role"] != "instructor":
        raise HTTPException(403, "Instructor access required.")
    return user


def require_instructor(user: dict) -> None:
    if user["role"] != "instructor":
        raise HTTPException(403, "Instructor access required.")


def require_student(user: dict) -> None:
    if user["role"] != "student":
        raise HTTPException(403, "Student access required.")
