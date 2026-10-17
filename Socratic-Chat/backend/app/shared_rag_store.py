"""Move legacy RAG tables into the shared namespace without copying or deleting rows."""
from psycopg import sql

from app import settings


def migrate_legacy_tables(conn):
    conn.execute("SELECT pg_advisory_xact_lock(716340041)")
    source = settings.SOCRATIC_DB_SCHEMA
    target = settings.SHARED_RAG_DB_SCHEMA
    pairs = (("rag_files_socratic_chat", "documents"),
             ("document_chunks_socratic_chat", "chunks"))
    for old, new in pairs:
        legacy = sql.Identifier(source, old).as_string(conn)
        shared = sql.Identifier(target, new).as_string(conn)
        exists = conn.execute("SELECT to_regclass(%s),to_regclass(%s)", (legacy, shared)).fetchone()
        # This connection normally uses tuple rows during initialization.
        values = list(exists.values()) if isinstance(exists, dict) else exists
        if not values[0]:
            continue
        if values[1]:
            raise RuntimeError(f"Both {legacy} and {shared} exist. Reconcile the two stores before migrating; no data was changed.")
        if source != target:
            conn.execute(sql.SQL("ALTER TABLE {} SET SCHEMA {}").format(sql.Identifier(source, old), sql.Identifier(target)))
        conn.execute(sql.SQL("ALTER TABLE {} RENAME TO {}").format(sql.Identifier(target, old), sql.Identifier(new)))
