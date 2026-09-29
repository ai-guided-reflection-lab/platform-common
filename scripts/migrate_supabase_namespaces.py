"""Move the existing ClubALL tables into explicit, suffixed app namespaces.

The migration is transactional and idempotent. It never drops source data.
Run from the repository root after taking a Supabase backup.
"""

from __future__ import annotations

import os
import argparse
from pathlib import Path

import psycopg
from dotenv import load_dotenv
from psycopg import sql


ROOT = Path(__file__).resolve().parents[1]
load_dotenv(ROOT / ".env")

PLATFORM = os.getenv("PLATFORM_DB_SCHEMA", "platform")
SOCRATIC = os.getenv("SOCRATIC_DB_SCHEMA", "socratic_chat")
REFLECTIONS = os.getenv("REFLECTIONS_DB_SCHEMA", "reflections_app")

PLATFORM_TABLES = {
    "users": "users_platform",
    "email_verification_codes": "email_verification_codes_platform",
    "github_oauth_states": "github_oauth_states_platform",
    "github_login_codes": "github_login_codes_platform",
    "courses": "courses_platform",
    "course_memberships": "course_memberships_platform",
    "platform_assignments": "assignments_platform",
    "platform_recipients": "assignment_recipients_platform",
    "platform_attempts": "assignment_attempts_platform",
    "platform_migrations": "migrations_platform",
}

SOCRATIC_TABLES = {
    "conversations": "conversations_socratic_chat",
    "conversation_messages": "conversation_messages_socratic_chat",
    "conversation_state": "conversation_state_socratic_chat",
    "student_concept_progress": "student_concept_progress_socratic_chat",
    "mastery_assessments": "mastery_assessments_socratic_chat",
    "rag_files": "rag_files_socratic_chat",
    "document_chunks": "document_chunks_socratic_chat",
    "lti_sessions": "lti_sessions_socratic_chat",
}

REFLECTION_TABLES = {
    "students": "students_reflections_app",
    "modules": "modules_reflections_app",
    "module_configs": "module_configs_reflections_app",
    "conversations": "conversations_reflections_app",
    "reflection_analytics": "reflection_analytics_reflections_app",
}

CHECKPOINT_TABLES = {
    "checkpoint_migrations": "checkpoint_migrations_reflections_app",
    "checkpoints": "checkpoints_reflections_app",
    "checkpoint_blobs": "checkpoint_blobs_reflections_app",
    "checkpoint_writes": "checkpoint_writes_reflections_app",
}


def exists(cur, schema: str, table: str) -> bool:
    cur.execute("SELECT to_regclass(%s) IS NOT NULL", (f'"{schema}"."{table}"',))
    return bool(cur.fetchone()[0])


def move_and_rename(cur, source: str, target: str, old: str, new: str) -> None:
    if exists(cur, target, new):
        return
    if not exists(cur, source, old):
        return
    cur.execute(
        sql.SQL("ALTER TABLE {}.{} SET SCHEMA {}").format(
            sql.Identifier(source), sql.Identifier(old), sql.Identifier(target)
        )
    )
    if old != new:
        cur.execute(
            sql.SQL("ALTER TABLE {}.{} RENAME TO {}").format(
                sql.Identifier(target), sql.Identifier(old), sql.Identifier(new)
            )
        )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="execute every migration statement and then roll the transaction back",
    )
    args = parser.parse_args()
    database_url = os.getenv("DATABASE_URL", "")
    if not database_url:
        raise SystemExit("DATABASE_URL is required")

    with psycopg.connect(database_url, prepare_threshold=None) as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT pg_advisory_xact_lock(716340023)")
            for schema in (PLATFORM, SOCRATIC, REFLECTIONS):
                cur.execute(sql.SQL("CREATE SCHEMA IF NOT EXISTS {}").format(sql.Identifier(schema)))

            # Older ClubALL installs created pgvector while `cluball` was the
            # active schema. Move the relocatable extension to Supabase's
            # standard extension namespace so every app can resolve its types
            # and operator classes without retaining the legacy schema in its
            # search path.
            cur.execute(
                """
                SELECT namespace.nspname, extension.extrelocatable
                FROM pg_extension AS extension
                JOIN pg_namespace AS namespace ON namespace.oid = extension.extnamespace
                WHERE extension.extname = 'vector'
                """
            )
            vector_extension = cur.fetchone()
            if vector_extension == ("cluball", True):
                cur.execute("CREATE SCHEMA IF NOT EXISTS extensions")
                cur.execute("ALTER EXTENSION vector SET SCHEMA extensions")

            for old, new in PLATFORM_TABLES.items():
                move_and_rename(cur, "cluball", PLATFORM, old, new)
            for old, new in SOCRATIC_TABLES.items():
                move_and_rename(cur, "cluball", SOCRATIC, old, new)
            for old, new in REFLECTION_TABLES.items():
                move_and_rename(cur, "public", REFLECTIONS, old, new)
            for old, new in CHECKPOINT_TABLES.items():
                move_and_rename(cur, "public", REFLECTIONS, old, new)

            modules = sql.Identifier(REFLECTIONS, "modules_reflections_app")
            conversations = sql.Identifier(REFLECTIONS, "conversations_reflections_app")
            courses = sql.Identifier(PLATFORM, "courses_platform")
            users = sql.Identifier(PLATFORM, "users_platform")
            assignments = sql.Identifier(PLATFORM, "assignments_platform")

            if exists(cur, REFLECTIONS, "modules_reflections_app"):
                cur.execute(sql.SQL("ALTER TABLE {} ADD COLUMN IF NOT EXISTS course_id UUID").format(modules))
                cur.execute(sql.SQL(
                    "UPDATE {} m SET course_id=a.course_id FROM {} a "
                    "WHERE m.course_id IS NULL AND m.id=a.id::text"
                ).format(modules, assignments))
                cur.execute(sql.SQL(
                    "DO $$ BEGIN IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname='modules_reflections_app_course_fk') "
                    "THEN ALTER TABLE {} ADD CONSTRAINT modules_reflections_app_course_fk "
                    "FOREIGN KEY (course_id) REFERENCES {}(id); END IF; END $$"
                ).format(modules, courses))

            if exists(cur, REFLECTIONS, "conversations_reflections_app"):
                cur.execute(sql.SQL(
                    "ALTER TABLE {} ALTER COLUMN student_id DROP NOT NULL, "
                    "ADD COLUMN IF NOT EXISTS platform_user_id UUID, "
                    "ADD COLUMN IF NOT EXISTS course_id UUID"
                ).format(conversations))
                cur.execute(sql.SQL(
                    "DO $$ BEGIN IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname='conversations_reflections_app_user_fk') "
                    "THEN ALTER TABLE {} ADD CONSTRAINT conversations_reflections_app_user_fk "
                    "FOREIGN KEY (platform_user_id) REFERENCES {}(id); END IF; "
                    "IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname='conversations_reflections_app_course_fk') "
                    "THEN ALTER TABLE {} ADD CONSTRAINT conversations_reflections_app_course_fk "
                    "FOREIGN KEY (course_id) REFERENCES {}(id); END IF; END $$"
                ).format(conversations, users, conversations, courses))

        if args.dry_run:
            conn.rollback()
            print("Dry run succeeded; all database changes were rolled back.")
            return

    print("Database namespaces migrated successfully.")


if __name__ == "__main__":
    main()
