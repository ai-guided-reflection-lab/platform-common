from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from .config import DATABASE_PATH, DATABASE_SCHEMA, DATABASE_URL, ensure_directories


SCHEMA = """
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS users (
    id TEXT PRIMARY KEY,
    email TEXT NOT NULL UNIQUE,
    display_name TEXT NOT NULL,
    role TEXT NOT NULL CHECK (role IN ('instructor', 'student'))
);

CREATE TABLE IF NOT EXISTS assignments (
    id TEXT PRIMARY KEY,
    instructor_id TEXT NOT NULL REFERENCES users(id),
    title TEXT NOT NULL,
    instructions TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL DEFAULT 'draft' CHECK (status IN ('draft', 'published', 'archived')),
    learning_plan TEXT NOT NULL,
    created_at TEXT NOT NULL,
    published_at TEXT
);

CREATE TABLE IF NOT EXISTS recipients (
    assignment_id TEXT NOT NULL REFERENCES assignments(id) ON DELETE CASCADE,
    student_id TEXT NOT NULL REFERENCES users(id),
    PRIMARY KEY (assignment_id, student_id)
);

CREATE TABLE IF NOT EXISTS documents (
    id TEXT PRIMARY KEY,
    assignment_id TEXT NOT NULL REFERENCES assignments(id) ON DELETE CASCADE,
    filename TEXT NOT NULL,
    content_type TEXT NOT NULL,
    path TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS chunks (
    id TEXT PRIMARY KEY,
    document_id TEXT NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    position INTEGER NOT NULL,
    content TEXT NOT NULL,
    embedding TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS attempts (
    id TEXT PRIMARY KEY,
    assignment_id TEXT NOT NULL REFERENCES assignments(id),
    student_id TEXT NOT NULL REFERENCES users(id),
    status TEXT NOT NULL DEFAULT 'in_progress' CHECK (status IN ('in_progress', 'completed')),
    current_objective INTEGER NOT NULL DEFAULT 0,
    required_task_status TEXT NOT NULL DEFAULT 'not_started',
    required_task_submission TEXT,
    phase TEXT NOT NULL DEFAULT 'study_resources',
    study_completed_at TEXT,
    quiz_answers TEXT NOT NULL DEFAULT '[]',
    quiz_score INTEGER,
    learning_path TEXT,
    learning_state TEXT NOT NULL DEFAULT '{}',
    started_at TEXT NOT NULL,
    completed_at TEXT,
    UNIQUE (assignment_id, student_id)
);

CREATE TABLE IF NOT EXISTS messages (
    id TEXT PRIMARY KEY,
    attempt_id TEXT NOT NULL REFERENCES attempts(id) ON DELETE CASCADE,
    role TEXT NOT NULL CHECK (role IN ('student', 'assistant')),
    content TEXT NOT NULL,
    sources TEXT NOT NULL DEFAULT '[]',
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS evidence (
    id TEXT PRIMARY KEY,
    attempt_id TEXT NOT NULL REFERENCES attempts(id) ON DELETE CASCADE,
    objective_id TEXT NOT NULL,
    response TEXT NOT NULL,
    score REAL NOT NULL,
    demonstrated INTEGER NOT NULL,
    rationale TEXT NOT NULL,
    created_at TEXT NOT NULL
);
"""


DEFAULT_PLAN = {
    "title": "Requirements Engineering",
    "course_context": "Introductory software engineering",
    "objectives": [
        {
            "id": "REQ-TYPES",
            "title": "Classify requirements",
            "description": "Distinguish functional from non-functional requirements and justify the classification.",
            "success_criteria": [
                "Correctly classifies behavior as functional",
                "Correctly classifies quality constraints as non-functional",
                "Justifies the classification",
            ],
            "diagnostic_prompt": "Classify each requirement as functional or non-functional and justify each choice: (1) The system shall email a receipt after payment. (2) Payment confirmation shall appear within two seconds.",
        },
        {
            "id": "REQ-QUALITY",
            "title": "Improve requirement quality",
            "description": "Identify ambiguity or missing details and rewrite a requirement so it is testable.",
            "success_criteria": [
                "Identifies the ambiguous wording",
                "Adds a measurable condition",
                "Produces a testable revision",
            ],
            "diagnostic_prompt": "Explain what is ambiguous in ‘The search page shall load quickly’ and rewrite it as a clear, testable requirement.",
        },
    ],
    "required_task": {
        "title": "Requirements review",
        "description": "Classify a short requirements set, identify quality problems, and submit improved wording.",
        "submission_prompt": "Submit your classified requirements, quality findings, and revised wording.",
    },
}


def now() -> str:
    return datetime.now(UTC).isoformat()


class DatabaseConnection:
    """Small compatibility layer so application queries work with SQLite or PostgreSQL."""

    def __init__(self, raw: Any, postgres: bool = False):
        self.raw = raw
        self.postgres = postgres

    def _sql(self, statement: str) -> str:
        return statement.replace("?", "%s") if self.postgres else statement

    def execute(self, statement: str, parameters: tuple | list = ()):
        return self.raw.execute(self._sql(statement), parameters)

    def executemany(self, statement: str, parameters):
        if self.postgres:
            cursor = self.raw.cursor()
            cursor.executemany(self._sql(statement), parameters)
            return cursor
        return self.raw.executemany(self._sql(statement), parameters)

    def executescript(self, script: str) -> None:
        if not self.postgres:
            self.raw.executescript(script)
            return
        for statement in script.split(";"):
            statement = statement.strip()
            if statement and not statement.upper().startswith("PRAGMA"):
                self.raw.execute(statement)


@contextmanager
def connection():
    ensure_directories()
    if DATABASE_URL:
        try:
            import psycopg
            from psycopg.rows import dict_row
        except ImportError as exc:
            raise RuntimeError("PostgreSQL support requires psycopg. Install backend requirements.") from exc
        raw = psycopg.connect(DATABASE_URL, row_factory=dict_row, prepare_threshold=None)
        if not DATABASE_SCHEMA.replace("_", "").isalnum():
            raw.close()
            raise RuntimeError("DATABASE_SCHEMA may contain only letters, numbers, and underscores.")
        raw.execute(f'CREATE SCHEMA IF NOT EXISTS "{DATABASE_SCHEMA}"')
        raw.execute(f'SET search_path TO "{DATABASE_SCHEMA}"')
        conn = DatabaseConnection(raw, postgres=True)
    else:
        raw = sqlite3.connect(DATABASE_PATH)
        raw.row_factory = sqlite3.Row
        raw.execute("PRAGMA foreign_keys = ON")
        conn = DatabaseConnection(raw)
    try:
        yield conn
        raw.commit()
    except Exception:
        raw.rollback()
        raise
    finally:
        raw.close()


def initialize() -> None:
    ensure_directories()
    with connection() as conn:
        conn.executescript(SCHEMA)
        if conn.postgres:
            columns = {
                row["column_name"]
                for row in conn.execute(
                    "SELECT column_name FROM information_schema.columns WHERE table_schema=? AND table_name='attempts'",
                    (DATABASE_SCHEMA,),
                ).fetchall()
            }
        else:
            columns = {row["name"] for row in conn.execute("PRAGMA table_info(attempts)").fetchall()}
        migrations = {
            "phase": "ALTER TABLE attempts ADD COLUMN phase TEXT NOT NULL DEFAULT 'adaptive_learning'",
            "study_completed_at": "ALTER TABLE attempts ADD COLUMN study_completed_at TEXT",
            "quiz_answers": "ALTER TABLE attempts ADD COLUMN quiz_answers TEXT NOT NULL DEFAULT '[]'",
            "quiz_score": "ALTER TABLE attempts ADD COLUMN quiz_score INTEGER",
            "learning_path": "ALTER TABLE attempts ADD COLUMN learning_path TEXT",
            "learning_state": "ALTER TABLE attempts ADD COLUMN learning_state TEXT NOT NULL DEFAULT '{}'",
        }
        for name, statement in migrations.items():
            if name not in columns:
                conn.execute(statement)
        conn.executemany(
            "INSERT INTO users(id,email,display_name,role) VALUES (?,?,?,?) ON CONFLICT DO NOTHING",
            [
                ("instructor-demo", "instructor@demo.local", "Dr. Taylor", "instructor"),
                ("student-alex", "alex@demo.local", "Alex Morgan", "student"),
                ("student-jordan", "jordan@demo.local", "Jordan Lee", "student"),
            ],
        )
        existing = conn.execute("SELECT 1 FROM assignments LIMIT 1").fetchone()
        if existing is None:
            assignment_id = str(uuid4())
            conn.execute(
                """INSERT INTO assignments
                   (id,instructor_id,title,instructions,status,learning_plan,created_at,published_at)
                   VALUES (?,?,?,?,?,?,?,?)""",
                (
                    assignment_id,
                    "instructor-demo",
                    "Requirements Engineering Practice",
                    "Work through the diagnostic questions, use the tutor feedback, and submit the final requirements review.",
                    "published",
                    json.dumps(DEFAULT_PLAN),
                    now(),
                    now(),
                ),
            )
            conn.executemany(
                "INSERT INTO recipients(assignment_id,student_id) VALUES (?,?)",
                [(assignment_id, "student-alex"), (assignment_id, "student-jordan")],
            )


def row_dict(row: sqlite3.Row | dict | None) -> dict | None:
    return dict(row) if row is not None else None
