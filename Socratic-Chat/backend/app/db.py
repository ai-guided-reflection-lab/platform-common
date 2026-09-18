from __future__ import annotations

import hashlib
import hmac
import re
import secrets
import uuid
from contextlib import contextmanager
from typing import Iterator

from app import settings
from app.schemas import ChatMessage


AUTHORITY_LABELS = {0: "admin", 1: "instructor", 2: "student"}


@contextmanager
def get_connection() -> Iterator[object]:
    if not settings.DATABASE_URL:
        raise RuntimeError("DATABASE_URL is not configured.")

    import psycopg

    with psycopg.connect(settings.DATABASE_URL) as conn:
        yield conn


def _hash_password(password: str, salt: bytes | None = None) -> tuple[str, str]:
    salt = salt or secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, 120_000)
    return salt.hex(), digest.hex()


def _password_matches(password: str, salt_hex: str, expected_hash: str) -> bool:
    _, candidate_hash = _hash_password(password, bytes.fromhex(salt_hex))
    return hmac.compare_digest(candidate_hash, expected_hash)


def is_enabled() -> bool:
    return bool(settings.DATABASE_URL)


def init_db() -> None:
    if not is_enabled():
        return

    with get_connection() as conn:
        with conn.cursor() as cur:

            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS users (
                    id UUID PRIMARY KEY,
                    username TEXT NOT NULL UNIQUE,
                    display_name TEXT,
                    email TEXT NOT NULL UNIQUE,
                    password_salt TEXT NOT NULL,
                    password_hash TEXT NOT NULL,
                    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                )
                """
            )
            cur.execute(
                """
                ALTER TABLE users
                ADD COLUMN IF NOT EXISTS auth_provider TEXT NOT NULL DEFAULT 'password'
                """
            )
            cur.execute(
                """
                ALTER TABLE users
                ADD COLUMN IF NOT EXISTS google_sub TEXT UNIQUE
                """
            )
            cur.execute(
                """
                ALTER TABLE users
                ADD COLUMN IF NOT EXISTS display_name TEXT
                """
            )
            cur.execute(
                """
                ALTER TABLE users
                ADD COLUMN IF NOT EXISTS github_id BIGINT UNIQUE
                """
            )
            cur.execute(
                """
                ALTER TABLE users
                ADD COLUMN IF NOT EXISTS github_username TEXT
                """
            )
            cur.execute(
                """
                ALTER TABLE users
                ADD COLUMN IF NOT EXISTS github_linked_at TIMESTAMPTZ
                """
            )
            cur.execute(
                """
                ALTER TABLE users
                ADD COLUMN IF NOT EXISTS authority_level SMALLINT NOT NULL DEFAULT 2
                """
            )
            cur.execute(
                """
                ALTER TABLE users
                ADD COLUMN IF NOT EXISTS requested_authority_level SMALLINT
                """
            )
            cur.execute(
                """
                ALTER TABLE users
                ADD COLUMN IF NOT EXISTS onboarding_completed_at TIMESTAMPTZ
                """
            )
            cur.execute(
                """
                DO $$
                BEGIN
                    IF NOT EXISTS (
                        SELECT 1 FROM pg_constraint WHERE conname = 'users_authority_level_check'
                    ) THEN
                        ALTER TABLE users
                        ADD CONSTRAINT users_authority_level_check
                        CHECK (authority_level IN (0, 1, 2));
                    END IF;
                END $$
                """
            )
            cur.execute(
                """
                DO $$
                BEGIN
                    IF NOT EXISTS (
                        SELECT 1 FROM pg_constraint WHERE conname = 'users_requested_authority_level_check'
                    ) THEN
                        ALTER TABLE users
                        ADD CONSTRAINT users_requested_authority_level_check
                        CHECK (requested_authority_level IS NULL OR requested_authority_level IN (1, 2));
                    END IF;
                END $$
                """
            )
            cur.execute(
                """
                UPDATE users
                SET onboarding_completed_at = created_at
                WHERE onboarding_completed_at IS NULL
                  AND auth_provider LIKE 'password%'
                """
            )
            cur.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_users_pending_authority
                ON users(requested_authority_level, created_at)
                WHERE requested_authority_level IS NOT NULL
                """
            )
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS email_verification_codes (
                    id UUID PRIMARY KEY,
                    email TEXT NOT NULL,
                    code_hash TEXT NOT NULL,
                    expires_at TIMESTAMPTZ NOT NULL,
                    used_at TIMESTAMPTZ,
                    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                )
                """
            )
            cur.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_email_verification_codes_email_created_at
                ON email_verification_codes(email, created_at DESC)
                """
            )
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS github_oauth_states (
                    state_hash TEXT PRIMARY KEY,
                    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                    expires_at TIMESTAMPTZ NOT NULL,
                    used_at TIMESTAMPTZ,
                    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                )
                """
            )
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS courses (
                    id UUID PRIMARY KEY,
                    course_code TEXT NOT NULL,
                    title TEXT NOT NULL,
                    description TEXT NOT NULL DEFAULT '',
                    instructor_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                    is_discoverable BOOLEAN NOT NULL DEFAULT TRUE,
                    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    UNIQUE (instructor_id, course_code)
                )
                """
            )
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS course_memberships (
                    id UUID PRIMARY KEY,
                    course_id UUID NOT NULL REFERENCES courses(id) ON DELETE CASCADE,
                    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                    course_role TEXT NOT NULL CHECK (course_role IN ('instructor', 'student')),
                    status TEXT NOT NULL CHECK (status IN ('pending', 'approved', 'rejected')),
                    requested_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    reviewed_at TIMESTAMPTZ,
                    reviewed_by UUID REFERENCES users(id) ON DELETE SET NULL,
                    rejection_reason TEXT,
                    UNIQUE (course_id, user_id)
                )
                """
            )
            cur.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_course_memberships_user_status
                ON course_memberships(user_id, status, course_id)
                """
            )
            cur.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_course_memberships_course_status
                ON course_memberships(course_id, status, requested_at)
                """
            )
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS conversations (
                    id UUID PRIMARY KEY,
                    title TEXT NOT NULL DEFAULT 'New conversation',
                    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                )
                """
            )

            cur.execute(
                """
                ALTER TABLE conversations
                ADD COLUMN IF NOT EXISTS user_id UUID REFERENCES users(id) ON DELETE CASCADE
                """
            )
            cur.execute(
                """
                ALTER TABLE conversations
                ADD COLUMN IF NOT EXISTS course_id UUID REFERENCES courses(id) ON DELETE CASCADE
                """
            )
            cur.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_conversations_user_id_updated_at
                ON conversations(user_id, updated_at DESC)
                """
            )
            cur.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_conversations_user_course_updated_at
                ON conversations(user_id, course_id, updated_at DESC)
                """
            )
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS conversation_messages (
                    id BIGSERIAL PRIMARY KEY,
                    conversation_id UUID NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
                    role TEXT NOT NULL CHECK (role IN ('system', 'user', 'assistant')),
                    content TEXT NOT NULL,
                    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                )
                """
            )
            cur.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_conversation_messages_conversation_id
                ON conversation_messages(conversation_id, created_at, id)
                """
            )
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS conversation_state (
                    conversation_id UUID PRIMARY KEY REFERENCES conversations(id) ON DELETE CASCADE,
                    pending_type TEXT NOT NULL,
                    original_question TEXT NOT NULL,
                    missing_target TEXT,
                    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                )
                """
            )
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS rag_files (
                    id UUID PRIMARY KEY,
                    conversation_id UUID REFERENCES conversations(id) ON DELETE CASCADE,
                    filename TEXT NOT NULL,
                    content_type TEXT NOT NULL DEFAULT 'application/octet-stream',
                    file_size BIGINT NOT NULL,
                    content BYTEA NOT NULL,
                    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                )
                """
            )
            cur.execute(
                """
                ALTER TABLE rag_files
                ADD COLUMN IF NOT EXISTS conversation_id UUID REFERENCES conversations(id) ON DELETE CASCADE
                """
            )
            cur.execute(
                """
                ALTER TABLE rag_files
                ADD COLUMN IF NOT EXISTS user_id UUID REFERENCES users(id) ON DELETE CASCADE
                """
            )
            cur.execute(
                """
                ALTER TABLE rag_files
                ADD COLUMN IF NOT EXISTS course_id UUID REFERENCES courses(id) ON DELETE CASCADE
                """
            )
            cur.execute(
                """
                ALTER TABLE rag_files
                ADD COLUMN IF NOT EXISTS document_id TEXT
                """
            )
            cur.execute(
                """
                ALTER TABLE rag_files
                ADD COLUMN IF NOT EXISTS is_published BOOLEAN NOT NULL DEFAULT TRUE
                """
            )
            cur.execute(
                """
                UPDATE rag_files rf
                SET user_id = c.user_id
                FROM conversations c
                WHERE rf.conversation_id = c.id
                  AND rf.user_id IS NULL
                  AND c.user_id IS NOT NULL
                """
            )
            cur.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_rag_files_created_at
                ON rag_files(created_at DESC)
                """
            )
            cur.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_rag_files_conversation_id
                ON rag_files(conversation_id, created_at DESC)
                """
            )
            cur.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_rag_files_user_id_created_at
                ON rag_files(user_id, created_at DESC)
                """
            )
            cur.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_rag_files_course_id_created_at
                ON rag_files(course_id, created_at DESC)
                """
            )
        conn.commit()


def _hash_email_code(email: str, code: str) -> str:
    normalized_email = email.strip().lower()
    normalized_code = code.strip()
    return hashlib.sha256(f"{normalized_email}:{normalized_code}".encode("utf-8")).hexdigest()


def save_email_verification_code(email: str, code: str, expires_in_minutes: int = 10) -> None:
    init_db()
    normalized_email = email.strip().lower()
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO email_verification_codes (id, email, code_hash, expires_at)
                VALUES (%s, %s, %s, NOW() + (%s || ' minutes')::interval)
                """,
                (str(uuid.uuid4()), normalized_email, _hash_email_code(normalized_email, code), expires_in_minutes),
            )
        conn.commit()


def verify_email_code(email: str, code: str) -> bool:
    init_db()
    normalized_email = email.strip().lower()
    code_hash = _hash_email_code(normalized_email, code)
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT id
                FROM email_verification_codes
                WHERE email = %s
                  AND code_hash = %s
                  AND used_at IS NULL
                  AND expires_at > NOW()
                ORDER BY created_at DESC
                LIMIT 1
                """,
                (normalized_email, code_hash),
            )
            row = cur.fetchone()
            if row is None:
                return False

            cur.execute(
                """
                UPDATE email_verification_codes
                SET used_at = NOW()
                WHERE id = %s
                """,
                (row[0],),
            )
        conn.commit()

    return True


def check_status() -> tuple[bool, str]:
    if not is_enabled():
        return False, "DATABASE_URL is not configured."

    try:
        init_db()
        return True, "Connected to PostgreSQL."
    except Exception as exc:
        return False, str(exc)


def ensure_conversation(
    conversation_id: str | None,
    title: str = "New conversation",
    user_id: str | None = None,
    course_id: str | None = None,
) -> str:
    init_db()
    resolved_id = conversation_id or str(uuid.uuid4())

    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO conversations (id, title, user_id, course_id)
                VALUES (%s, %s, %s, %s)
                ON CONFLICT (id) DO UPDATE SET
                    updated_at = NOW(),
                    user_id = COALESCE(conversations.user_id, EXCLUDED.user_id),
                    course_id = COALESCE(conversations.course_id, EXCLUDED.course_id)
                """,
                (resolved_id, title[:120] or "New conversation", user_id, course_id),
            )
        conn.commit()

    return resolved_id


def set_conversation_title(conversation_id: str, title: str, user_id: str | None = None) -> None:
    init_db()
    clean_title = title.strip()[:120] or "New conversation"

    with get_connection() as conn:
        with conn.cursor() as cur:
            if user_id:
                cur.execute(
                    """
                    UPDATE conversations
                    SET title = %s,
                        updated_at = NOW()
                    WHERE id = %s
                      AND user_id = %s
                    """,
                    (clean_title, conversation_id, user_id),
                )
            else:
                cur.execute(
                    """
                    UPDATE conversations
                    SET title = %s,
                        updated_at = NOW()
                    WHERE id = %s
                    """,
                    (clean_title, conversation_id),
                )
        conn.commit()


def rename_uploaded_document_chats() -> int:
    init_db()
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                WITH first_files AS (
                    SELECT DISTINCT ON (conversation_id)
                        conversation_id,
                        filename
                    FROM rag_files
                    WHERE conversation_id IS NOT NULL
                    ORDER BY conversation_id, created_at ASC
                )
                UPDATE conversations c
                SET title = LEFT(first_files.filename, 120),
                    updated_at = NOW()
                FROM first_files
                WHERE c.id = first_files.conversation_id
                  AND c.title IN ('New conversation', 'Uploaded documents')
                """
            )
            updated = cur.rowcount
        conn.commit()

    return updated


def add_message(conversation_id: str, role: str, content: str) -> None:
    init_db()
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO conversation_messages (conversation_id, role, content)
                VALUES (%s, %s, %s)
                """,
                (conversation_id, role, content),
            )
            cur.execute(
                """
                UPDATE conversations
                SET updated_at = NOW()
                WHERE id = %s
                """,
                (conversation_id,),
            )
        conn.commit()


def get_messages(conversation_id: str, limit: int = 50) -> list[ChatMessage]:
    init_db()
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT role, content
                FROM conversation_messages
                WHERE conversation_id = %s
                ORDER BY created_at DESC, id DESC
                LIMIT %s
                """,
                (conversation_id, limit),
            )
            rows = cur.fetchall()

    return [ChatMessage(role=role, content=content) for role, content in reversed(rows)]


def list_conversations(
    limit: int = 50,
    user_id: str | None = None,
    course_id: str | None = None,
) -> list[dict[str, object]]:
    init_db()
    with get_connection() as conn:
        with conn.cursor() as cur:
            if user_id and course_id:
                cur.execute(
                    """
                    SELECT
                        c.id::text,
                        c.course_id::text,
                        c.title,
                        c.created_at::text,
                        c.updated_at::text,
                        COUNT(m.id)::int AS message_count
                    FROM conversations c
                    LEFT JOIN conversation_messages m ON m.conversation_id = c.id
                    WHERE c.user_id = %s AND c.course_id = %s
                    GROUP BY c.id, c.course_id, c.title, c.created_at, c.updated_at
                    HAVING COUNT(m.id) > 0
                    ORDER BY c.updated_at DESC
                    LIMIT %s
                    """,
                    (user_id, course_id, limit),
                )
            elif user_id:
                cur.execute(
                    """
                    SELECT
                        c.id::text,
                        c.course_id::text,
                        c.title,
                        c.created_at::text,
                        c.updated_at::text,
                        COUNT(m.id)::int AS message_count
                    FROM conversations c
                    LEFT JOIN conversation_messages m ON m.conversation_id = c.id
                    WHERE c.user_id = %s
                    GROUP BY c.id, c.course_id, c.title, c.created_at, c.updated_at
                    HAVING COUNT(m.id) > 0
                    ORDER BY c.updated_at DESC
                    LIMIT %s
                    """,
                    (user_id, limit),
                )
            else:
                cur.execute(
                    """
                    SELECT
                        c.id::text,
                        c.course_id::text,
                        c.title,
                        c.created_at::text,
                        c.updated_at::text,
                        COUNT(m.id)::int AS message_count
                    FROM conversations c
                    LEFT JOIN conversation_messages m ON m.conversation_id = c.id
                    GROUP BY c.id, c.course_id, c.title, c.created_at, c.updated_at
                    HAVING COUNT(m.id) > 0
                    ORDER BY c.updated_at DESC
                    LIMIT %s
                    """,
                    (limit,),
                )
            rows = cur.fetchall()

    return [
        {
            "conversation_id": row[0],
            "course_id": row[1],
            "title": row[2],
            "created_at": row[3],
            "updated_at": row[4],
            "message_count": row[5],
        }
        for row in rows
    ]


def delete_conversation(conversation_id: str) -> bool:
    init_db()
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM rag_files WHERE conversation_id = %s", (conversation_id,))
            cur.execute(
                """
                DELETE FROM conversations
                WHERE id = %s
                """,
                (conversation_id,),
            )
            deleted = cur.rowcount > 0
        conn.commit()

    return deleted


def save_rag_file(
    filename: str,
    content_type: str,
    content: bytes,
    conversation_id: str | None = None,
    user_id: str | None = None,
    course_id: str | None = None,
    document_id: str | None = None,
) -> str | None:
    if not is_enabled():
        return None

    init_db()
    file_id = str(uuid.uuid4())
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO rag_files (
                    id, conversation_id, user_id, course_id, document_id,
                    filename, content_type, file_size, content
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    file_id, conversation_id, user_id, course_id, document_id,
                    filename, content_type or "application/octet-stream", len(content), content,
                ),
            )
        conn.commit()

    return file_id


def list_rag_files(
    limit: int = 50,
    conversation_id: str | None = None,
    user_id: str | None = None,
    course_id: str | None = None,
) -> list[dict[str, object]]:
    init_db()
    with get_connection() as conn:
        with conn.cursor() as cur:
            conditions: list[str] = []
            params: list[object] = []

            if conversation_id:
                conditions.append("rf.conversation_id = %s")
                params.append(conversation_id)

            if user_id:
                conditions.append("(rf.user_id = %s OR c.user_id = %s)")
                params.extend([user_id, user_id])

            if course_id:
                conditions.append("rf.course_id = %s")
                params.append(course_id)

            where_clause = f"WHERE {' AND '.join(conditions)}" if conditions else ""
            cur.execute(
                f"""
                SELECT rf.id::text, rf.document_id, rf.filename, rf.content_type, rf.file_size, rf.created_at::text
                FROM rag_files rf
                LEFT JOIN conversations c ON c.id = rf.conversation_id
                {where_clause}
                ORDER BY rf.created_at DESC
                LIMIT %s
                """,
                (*params, limit),
            )
            rows = cur.fetchall()

    return [
        {
            "file_id": row[0],
            "document_id": row[1],
            "filename": row[2],
            "content_type": row[3],
            "file_size": row[4],
            "created_at": row[5],
        }
        for row in rows
    ]


def get_rag_file(file_id: str, user_id: str | None = None) -> dict[str, object] | None:
    init_db()
    with get_connection() as conn:
        with conn.cursor() as cur:
            conditions = ["rf.id = %s"]
            params: list[object] = [file_id]

            if user_id:
                conditions.append("(rf.user_id = %s OR c.user_id = %s)")
                params.extend([user_id, user_id])

            where_clause = " AND ".join(conditions)
            cur.execute(
                f"""
                SELECT rf.id::text, rf.filename, rf.content_type, rf.file_size, rf.content
                FROM rag_files rf
                LEFT JOIN conversations c ON c.id = rf.conversation_id
                WHERE {where_clause}
                """,
                tuple(params),
            )
            row = cur.fetchone()

    if row is None:
        return None

    return {
        "file_id": row[0],
        "filename": row[1],
        "content_type": row[2],
        "file_size": row[3],
        "content": bytes(row[4]),
    }


def conversation_belongs_to(conversation_id: str, user_id: str | None) -> bool:
    if not user_id:
        return True
    init_db()
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT 1
                FROM conversations
                WHERE id = %s AND user_id = %s
                """,
                (conversation_id, user_id),
            )
            return cur.fetchone() is not None


def conversation_belongs_to_course(conversation_id: str, user_id: str, course_id: str) -> bool:
    init_db()
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT 1
                FROM conversations
                WHERE id = %s AND user_id = %s AND course_id = %s
                """,
                (conversation_id, user_id, course_id),
            )
            return cur.fetchone() is not None


def create_course(instructor_id: str, course_code: str, title: str, description: str = "") -> dict[str, object]:
    init_db()
    course_id = str(uuid.uuid4())
    membership_id = str(uuid.uuid4())
    normalized_code = " ".join(course_code.upper().split())
    clean_title = " ".join(title.split())
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO courses (id, course_code, title, description, instructor_id)
                VALUES (%s, %s, %s, %s, %s)
                """,
                (course_id, normalized_code, clean_title, description.strip(), instructor_id),
            )
            cur.execute(
                """
                INSERT INTO course_memberships (id, course_id, user_id, course_role, status, reviewed_at, reviewed_by)
                VALUES (%s, %s, %s, 'instructor', 'approved', NOW(), %s)
                """,
                (membership_id, course_id, instructor_id, instructor_id),
            )
        conn.commit()
    return get_course(course_id) or {}


def get_course(course_id: str) -> dict[str, object] | None:
    init_db()
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT
                    c.id::text,
                    c.course_code,
                    c.title,
                    c.description,
                    c.instructor_id::text,
                    COALESCE(NULLIF(u.display_name, ''), u.username),
                    (SELECT COUNT(*)::int FROM rag_files rf WHERE rf.course_id = c.id AND rf.is_published),
                    (SELECT COUNT(*)::int FROM course_memberships cm WHERE cm.course_id = c.id AND cm.status = 'pending')
                FROM courses c
                JOIN users u ON u.id = c.instructor_id
                WHERE c.id = %s
                """,
                (course_id,),
            )
            row = cur.fetchone()
    if row is None:
        return None
    return {
        "course_id": row[0],
        "course_code": row[1],
        "title": row[2],
        "description": row[3] or "",
        "instructor_id": row[4],
        "instructor_name": row[5],
        "membership_role": None,
        "membership_status": None,
        "document_count": row[6],
        "pending_request_count": row[7],
    }


def list_courses_for_user(user_id: str) -> list[dict[str, object]]:
    init_db()
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT
                    c.id::text,
                    c.course_code,
                    c.title,
                    c.description,
                    c.instructor_id::text,
                    COALESCE(NULLIF(instructor.display_name, ''), instructor.username),
                    cm.course_role,
                    cm.status,
                    (SELECT COUNT(*)::int FROM rag_files rf WHERE rf.course_id = c.id AND rf.is_published),
                    (SELECT COUNT(*)::int FROM course_memberships pending WHERE pending.course_id = c.id AND pending.status = 'pending')
                FROM courses c
                JOIN users instructor ON instructor.id = c.instructor_id
                LEFT JOIN course_memberships cm
                    ON cm.course_id = c.id AND cm.user_id = %s
                WHERE c.is_discoverable OR c.instructor_id = %s OR cm.user_id IS NOT NULL
                ORDER BY
                    CASE cm.status WHEN 'approved' THEN 0 WHEN 'pending' THEN 1 WHEN 'rejected' THEN 2 ELSE 3 END,
                    c.course_code,
                    c.title
                """,
                (user_id, user_id),
            )
            rows = cur.fetchall()
    return [
        {
            "course_id": row[0],
            "course_code": row[1],
            "title": row[2],
            "description": row[3] or "",
            "instructor_id": row[4],
            "instructor_name": row[5],
            "membership_role": row[6],
            "membership_status": row[7],
            "document_count": row[8],
            "pending_request_count": row[9],
        }
        for row in rows
    ]


def _course_membership_profile(row: tuple[object, ...] | None) -> dict[str, object] | None:
    if row is None:
        return None
    return {
        "membership_id": row[0],
        "course_id": row[1],
        "user_id": row[2],
        "display_name": row[3],
        "email": row[4],
        "course_role": row[5],
        "status": row[6],
        "requested_at": row[7],
    }


def get_course_membership(course_id: str, user_id: str) -> dict[str, object] | None:
    init_db()
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT
                    cm.id::text,
                    cm.course_id::text,
                    cm.user_id::text,
                    COALESCE(NULLIF(u.display_name, ''), u.username),
                    u.email,
                    cm.course_role,
                    cm.status,
                    cm.requested_at::text
                FROM course_memberships cm
                JOIN users u ON u.id = cm.user_id
                WHERE cm.course_id = %s AND cm.user_id = %s
                """,
                (course_id, user_id),
            )
            row = cur.fetchone()
    return _course_membership_profile(row)


def user_can_access_course(course_id: str, user_id: str) -> bool:
    membership = get_course_membership(course_id, user_id)
    return bool(membership and membership["status"] == "approved")


def user_manages_course(course_id: str, user_id: str) -> bool:
    membership = get_course_membership(course_id, user_id)
    return bool(
        membership
        and membership["course_role"] == "instructor"
        and membership["status"] == "approved"
    )


def request_course_access(course_id: str, user_id: str) -> dict[str, object]:
    init_db()
    membership_id = str(uuid.uuid4())
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT instructor_id::text, is_discoverable FROM courses WHERE id = %s",
                (course_id,),
            )
            course = cur.fetchone()
            if course is None or not course[1]:
                raise ValueError("Course was not found.")
            if course[0] == user_id:
                raise ValueError("The course instructor already has access.")
            cur.execute(
                """
                INSERT INTO course_memberships (id, course_id, user_id, course_role, status)
                VALUES (%s, %s, %s, 'student', 'pending')
                ON CONFLICT (course_id, user_id) DO UPDATE SET
                    status = CASE
                        WHEN course_memberships.status = 'approved' THEN 'approved'
                        ELSE 'pending'
                    END,
                    requested_at = CASE
                        WHEN course_memberships.status = 'approved' THEN course_memberships.requested_at
                        ELSE NOW()
                    END,
                    reviewed_at = CASE
                        WHEN course_memberships.status = 'approved' THEN course_memberships.reviewed_at
                        ELSE NULL
                    END,
                    reviewed_by = CASE
                        WHEN course_memberships.status = 'approved' THEN course_memberships.reviewed_by
                        ELSE NULL
                    END,
                    rejection_reason = NULL
                """,
                (membership_id, course_id, user_id),
            )
        conn.commit()
    membership = get_course_membership(course_id, user_id)
    if membership is None:
        raise RuntimeError("Course request could not be saved.")
    return membership


def list_pending_course_requests(instructor_id: str, course_id: str | None = None) -> list[dict[str, object]]:
    init_db()
    params: list[object] = [instructor_id]
    course_filter = ""
    if course_id:
        course_filter = "AND cm.course_id = %s"
        params.append(course_id)
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                f"""
                SELECT
                    cm.id::text,
                    cm.course_id::text,
                    cm.user_id::text,
                    COALESCE(NULLIF(u.display_name, ''), u.username),
                    u.email,
                    cm.course_role,
                    cm.status,
                    cm.requested_at::text
                FROM course_memberships cm
                JOIN courses c ON c.id = cm.course_id
                JOIN users u ON u.id = cm.user_id
                WHERE c.instructor_id = %s
                  AND cm.course_role = 'student'
                  AND cm.status = 'pending'
                  {course_filter}
                ORDER BY cm.requested_at ASC
                """,
                tuple(params),
            )
            rows = cur.fetchall()
    return [_course_membership_profile(row) for row in rows if row is not None]


def list_approved_course_students(instructor_id: str, course_id: str) -> list[dict[str, object]]:
    init_db()
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT
                    cm.id::text,
                    cm.course_id::text,
                    cm.user_id::text,
                    COALESCE(NULLIF(u.display_name, ''), u.username),
                    u.email,
                    cm.course_role,
                    cm.status,
                    cm.requested_at::text
                FROM course_memberships cm
                JOIN courses c ON c.id = cm.course_id
                JOIN users u ON u.id = cm.user_id
                WHERE c.instructor_id = %s
                  AND cm.course_id = %s
                  AND cm.course_role = 'student'
                  AND cm.status = 'approved'
                ORDER BY COALESCE(NULLIF(u.display_name, ''), u.username), u.email
                """,
                (instructor_id, course_id),
            )
            rows = cur.fetchall()
    return [_course_membership_profile(row) for row in rows if row is not None]


def remove_course_student(instructor_id: str, membership_id: str) -> dict[str, object]:
    init_db()
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                DELETE FROM course_memberships cm
                USING courses c, users u
                WHERE cm.id = %s
                  AND cm.course_id = c.id
                  AND cm.user_id = u.id
                  AND c.instructor_id = %s
                  AND cm.course_role = 'student'
                  AND cm.status = 'approved'
                RETURNING
                    cm.id::text,
                    cm.course_id::text,
                    cm.user_id::text,
                    COALESCE(NULLIF(u.display_name, ''), u.username),
                    u.email,
                    cm.course_role,
                    cm.status,
                    cm.requested_at::text
                """,
                (membership_id, instructor_id),
            )
            removed = cur.fetchone()
        conn.commit()
    membership = _course_membership_profile(removed)
    if membership is None:
        raise ValueError("Approved student was not found for one of your courses.")
    return membership


def review_course_request(
    instructor_id: str,
    membership_id: str,
    decision: str,
    rejection_reason: str | None = None,
) -> dict[str, object]:
    if decision not in {"approved", "rejected"}:
        raise ValueError("Decision must be approved or rejected.")
    init_db()
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE course_memberships cm
                SET status = %s,
                    reviewed_at = NOW(),
                    reviewed_by = %s,
                    rejection_reason = %s
                FROM courses c
                WHERE cm.id = %s
                  AND cm.course_id = c.id
                  AND c.instructor_id = %s
                  AND cm.course_role = 'student'
                RETURNING cm.course_id::text, cm.user_id::text
                """,
                (decision, instructor_id, rejection_reason, membership_id, instructor_id),
            )
            updated = cur.fetchone()
        conn.commit()
    if updated is None:
        raise ValueError("Access request was not found for one of your courses.")
    membership = get_course_membership(updated[0], updated[1])
    if membership is None:
        raise RuntimeError("Updated membership could not be loaded.")
    return membership


def delete_course_document(file_id: str, course_id: str) -> dict[str, object] | None:
    init_db()
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                DELETE FROM rag_files
                WHERE id = %s AND course_id = %s
                RETURNING document_id, filename
                """,
                (file_id, course_id),
            )
            row = cur.fetchone()
        conn.commit()
    if row is None:
        return None
    return {"document_id": row[0], "filename": row[1]}


def _user_profile(row: tuple[object, ...] | None) -> dict[str, object] | None:
    if row is None:
        return None
    authority_level = int(row[6]) if len(row) > 6 and row[6] is not None else 2
    requested_authority = int(row[7]) if len(row) > 7 and row[7] is not None else None
    onboarding_complete = bool(row[8]) if len(row) > 8 else False
    role_status = "onboarding_required"
    if onboarding_complete:
        role_status = "pending" if requested_authority == 1 and authority_level > 1 else "active"
    return {
        "user_id": str(row[0]),
        "username": str(row[1]),
        "email": str(row[2]),
        "display_name": str(row[3]) if row[3] else str(row[1]),
        "github_connected": row[4] is not None,
        "github_username": str(row[5]) if row[5] else None,
        "authority_level": authority_level,
        "role": AUTHORITY_LABELS.get(authority_level, "student"),
        "requested_role": "instructor" if requested_authority == 1 else None,
        "role_status": role_status,
        "onboarding_complete": onboarding_complete,
    }


USER_PROFILE_COLUMNS = """
    id::text, username, email, display_name, github_id, github_username,
    authority_level, requested_authority_level, onboarding_completed_at
"""


def get_user_by_id(user_id: str) -> dict[str, object] | None:
    init_db()
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT {USER_PROFILE_COLUMNS}
                FROM users
                WHERE id = %s
                """.format(USER_PROFILE_COLUMNS=USER_PROFILE_COLUMNS),
                (user_id,),
            )
            row = cur.fetchone()
    return _user_profile(row)


def get_user_by_email(email: str) -> dict[str, object] | None:
    init_db()
    normalized_email = email.strip().lower()
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT {USER_PROFILE_COLUMNS}
                FROM users
                WHERE lower(email) = %s
                """.format(USER_PROFILE_COLUMNS=USER_PROFILE_COLUMNS),
                (normalized_email,),
            )
            row = cur.fetchone()

    return _user_profile(row)


def get_user_by_google_sub(google_sub: str) -> dict[str, object] | None:
    init_db()
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT {USER_PROFILE_COLUMNS}
                FROM users
                WHERE google_sub = %s
                """.format(USER_PROFILE_COLUMNS=USER_PROFILE_COLUMNS),
                (google_sub,),
            )
            row = cur.fetchone()

    return _user_profile(row)


def user_has_github(user_id: str) -> bool:
    user = get_user_by_id(user_id)
    return bool(user and user["github_connected"])


def link_github_account(user_id: str, github_id: int, github_username: str) -> dict[str, object]:
    init_db()
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT id::text
                FROM users
                WHERE github_id = %s AND id <> %s
                """,
                (github_id, user_id),
            )
            if cur.fetchone() is not None:
                raise ValueError("That GitHub account is already linked to another user.")

            cur.execute(
                """
                UPDATE users
                SET github_id = %s,
                    github_username = %s,
                    github_linked_at = NOW()
                WHERE id = %s
                """,
                (github_id, github_username, user_id),
            )
            if cur.rowcount != 1:
                raise ValueError("School account was not found.")
        conn.commit()

    user = get_user_by_id(user_id)
    if user is None:
        raise ValueError("School account was not found.")
    return user


def create_github_oauth_state(user_id: str, expires_in_minutes: int = 10) -> str:
    init_db()
    state = secrets.token_urlsafe(32)
    state_hash = hashlib.sha256(state.encode("utf-8")).hexdigest()
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO github_oauth_states (state_hash, user_id, expires_at)
                VALUES (%s, %s, NOW() + (%s * INTERVAL '1 minute'))
                """,
                (state_hash, user_id, expires_in_minutes),
            )
        conn.commit()
    return state


def consume_github_oauth_state(state: str) -> str | None:
    init_db()
    state_hash = hashlib.sha256(state.encode("utf-8")).hexdigest()
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE github_oauth_states
                SET used_at = NOW()
                WHERE state_hash = %s
                  AND used_at IS NULL
                  AND expires_at > NOW()
                RETURNING user_id::text
                """,
                (state_hash,),
            )
            row = cur.fetchone()
        conn.commit()
    return str(row[0]) if row else None


def _unique_username(cur: object, desired: str) -> str:
    base = "".join(ch for ch in desired.strip().lower() if ch.isalnum() or ch in {"_", "-", "."})
    base = (base or "google_user")[:60]
    candidate = base
    suffix = 1
    while True:
        cur.execute("SELECT 1 FROM users WHERE lower(username) = %s", (candidate.lower(),))
        if cur.fetchone() is None:
            return candidate
        suffix += 1
        candidate = f"{base[:54]}{suffix}"


def find_or_create_google_user(email: str, google_sub: str, name: str | None = None) -> dict[str, object]:
    init_db()
    normalized_email = email.strip().lower()
    display_name = (name or normalized_email.split("@", 1)[0]).strip()[:120]

    existing = get_user_by_google_sub(google_sub) or get_user_by_email(normalized_email)
    if existing:
        is_configured_admin = normalized_email in settings.ADMIN_EMAILS
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    UPDATE users
                    SET google_sub = COALESCE(google_sub, %s),
                        display_name = COALESCE(NULLIF(%s, ''), display_name, username),
                        authority_level = CASE WHEN %s THEN 0 ELSE authority_level END,
                        requested_authority_level = CASE WHEN %s THEN NULL ELSE requested_authority_level END,
                        auth_provider = CASE
                            WHEN auth_provider = 'password' THEN 'password_google'
                            ELSE auth_provider
                        END
                    WHERE id = %s
                    """,
                    (google_sub, display_name, is_configured_admin, is_configured_admin, existing["user_id"]),
                )
            conn.commit()
        refreshed = get_user_by_id(str(existing["user_id"]))
        return refreshed or existing

    user_id = str(uuid.uuid4())
    salt, password_hash = _hash_password(secrets.token_urlsafe(32))
    desired_username = display_name

    authority_level = 0 if normalized_email in settings.ADMIN_EMAILS else 2
    with get_connection() as conn:
        with conn.cursor() as cur:
            username = _unique_username(cur, desired_username)
            cur.execute(
                """
                INSERT INTO users (
                    id, username, display_name, email, password_salt, password_hash,
                    auth_provider, google_sub, authority_level
                )
                VALUES (%s, %s, %s, %s, %s, %s, 'google', %s, %s)
                """,
                (user_id, username, display_name, normalized_email, salt, password_hash, google_sub, authority_level),
            )
        conn.commit()
    user = get_user_by_id(user_id)
    if user is None:
        raise RuntimeError("Google account could not be created.")
    return user


def complete_onboarding(user_id: str, username: str, password: str, position: str) -> dict[str, object]:
    init_db()
    normalized_username = username.strip()
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{2,79}", normalized_username):
        raise ValueError("Username must start with a letter or number and use only letters, numbers, ., _, or -.")

    requested_authority = 1 if position == "instructor" else None
    salt, password_hash = _hash_password(password)

    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT onboarding_completed_at, authority_level
                FROM users
                WHERE id = %s
                FOR UPDATE
                """,
                (user_id,),
            )
            row = cur.fetchone()
            if row is None:
                raise ValueError("Account was not found.")
            if row[0] is not None:
                raise ValueError("Account setup has already been completed.")

            cur.execute(
                """
                SELECT 1 FROM users
                WHERE lower(username) = lower(%s) AND id <> %s
                """,
                (normalized_username, user_id),
            )
            if cur.fetchone() is not None:
                raise ValueError("That username is already in use.")

            is_admin = int(row[1]) == 0
            cur.execute(
                """
                UPDATE users
                SET username = %s,
                    password_salt = %s,
                    password_hash = %s,
                    auth_provider = CASE
                        WHEN auth_provider = 'google' THEN 'google_password'
                        ELSE auth_provider
                    END,
                    requested_authority_level = CASE
                        WHEN %s THEN NULL::SMALLINT
                        ELSE %s::SMALLINT
                    END,
                    onboarding_completed_at = NOW()
                WHERE id = %s
                """,
                (normalized_username, salt, password_hash, is_admin, requested_authority, user_id),
            )
        conn.commit()

    user = get_user_by_id(user_id)
    if user is None:
        raise ValueError("Account was not found.")
    return user


def list_pending_instructor_requests() -> list[dict[str, object]]:
    init_db()
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT {USER_PROFILE_COLUMNS}
                FROM users
                WHERE requested_authority_level = 1
                  AND authority_level = 2
                  AND onboarding_completed_at IS NOT NULL
                ORDER BY created_at ASC
                """.format(USER_PROFILE_COLUMNS=USER_PROFILE_COLUMNS)
            )
            rows = cur.fetchall()
    return [profile for row in rows if (profile := _user_profile(row)) is not None]


def set_user_authority(user_id: str, authority_level: int) -> dict[str, object]:
    if authority_level not in {1, 2}:
        raise ValueError("Authority level must be instructor (1) or student (2).")
    init_db()
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE users
                SET authority_level = %s,
                    requested_authority_level = NULL
                WHERE id = %s
                  AND authority_level <> 0
                """,
                (authority_level, user_id),
            )
            if cur.rowcount != 1:
                raise ValueError("User was not found or is an administrator.")
        conn.commit()

    user = get_user_by_id(user_id)
    if user is None:
        raise ValueError("Account was not found.")
    return user


def create_user(username: str, email: str, password: str) -> dict[str, object]:
    init_db()
    user_id = str(uuid.uuid4())
    salt, password_hash = _hash_password(password)
    normalized_email = email.strip().lower()
    normalized_username = username.strip()

    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO users (
                    id, username, display_name, email, password_salt, password_hash,
                    onboarding_completed_at
                )
                VALUES (%s, %s, %s, %s, %s, %s, NOW())
                """,
                (user_id, normalized_username, normalized_username, normalized_email, salt, password_hash),
            )
        conn.commit()
    user = get_user_by_id(user_id)
    if user is None:
        raise RuntimeError("Account could not be created.")
    return user


def authenticate_user(
    identifier: str,
    password: str,
    require_google: bool = False,
) -> dict[str, object] | None:
    init_db()
    normalized = identifier.strip().lower()
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT id::text, username, email, password_salt, password_hash
                FROM users
                WHERE (lower(email) = %s OR lower(username) = %s)
                  AND (
                    NOT %s
                    OR (google_sub IS NOT NULL AND onboarding_completed_at IS NOT NULL)
                  )
                """,
                (normalized, normalized, require_google),
            )
            row = cur.fetchone()

    if row is None:
        return None
    if not _password_matches(password, row[3], row[4]):
        return None
    return get_user_by_id(str(row[0]))


def set_pending_clarification(conversation_id: str, original_question: str, missing_target: str | None = None) -> None:
    init_db()
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO conversation_state (conversation_id, pending_type, original_question, missing_target)
                VALUES (%s, 'clarification', %s, %s)
                ON CONFLICT (conversation_id) DO UPDATE SET
                    pending_type = EXCLUDED.pending_type,
                    original_question = EXCLUDED.original_question,
                    missing_target = EXCLUDED.missing_target,
                    created_at = NOW()
                """,
                (conversation_id, original_question, missing_target),
            )
        conn.commit()


def get_pending_clarification(conversation_id: str) -> dict[str, str | None] | None:
    init_db()
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT original_question, missing_target
                FROM conversation_state
                WHERE conversation_id = %s
                  AND pending_type = 'clarification'
                """,
                (conversation_id,),
            )
            row = cur.fetchone()

    if row is None:
        return None
    return {"original_question": row[0], "missing_target": row[1]}


def clear_pending_clarification(conversation_id: str) -> None:
    init_db()
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                DELETE FROM conversation_state
                WHERE conversation_id = %s
                """,
                (conversation_id,),
            )
        conn.commit()
