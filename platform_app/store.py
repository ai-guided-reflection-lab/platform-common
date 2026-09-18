"""Platform persistence, migrations, and cross-worker attempt serialization."""
from contextlib import contextmanager
from pathlib import Path

import psycopg
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from app import settings


@contextmanager
def connection():
    with psycopg.connect(settings.DATABASE_URL, row_factory=dict_row) as conn:
        yield conn


def migrate():
    with connection() as conn:
        conn.execute("SELECT pg_advisory_xact_lock(716340001)")
        conn.execute("CREATE TABLE IF NOT EXISTS platform_migrations (name TEXT PRIMARY KEY, applied_at TIMESTAMPTZ DEFAULT now())")
        for path in sorted((Path(__file__).parent / "migrations").glob("*.sql")):
            if not conn.execute("SELECT 1 FROM platform_migrations WHERE name = %s", (path.name,)).fetchone():
                conn.execute(path.read_text())
                conn.execute("INSERT INTO platform_migrations(name) VALUES (%s)", (path.name,))


def save_attempt(conn, attempt):
    conn.execute("""UPDATE platform_attempts SET status=%s, engine_state=%s, messages=%s,
        result=%s, processed_requests=%s, updated_at=now(),
        completed_at=CASE WHEN %s='completed' THEN coalesce(completed_at, now()) ELSE NULL END
        WHERE id=%s""", (attempt["status"], Jsonb(attempt["engine_state"]), Jsonb(attempt["messages"]),
        Jsonb(attempt["result"]), Jsonb(attempt["processed_requests"]), attempt["status"], attempt["id"]))


@contextmanager
def locked_attempt(assignment_id, student_id):
    # A transaction-scoped lock works across workers, including first-time starts.
    with connection() as conn:
        conn.execute("SELECT pg_advisory_xact_lock(hashtextextended(%s, 0))", (f"{assignment_id}:{student_id}",))
        attempt = conn.execute("SELECT * FROM platform_attempts WHERE assignment_id=%s AND student_id=%s FOR UPDATE",
                               (assignment_id, student_id)).fetchone()
        yield conn, attempt
