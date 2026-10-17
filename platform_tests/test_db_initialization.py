from app import db
from platform_app import store


def test_document_reads_do_not_repeat_ddl_inside_platform_transaction(database, monkeypatch):
    def unexpected_initialization():
        raise AssertionError("A normal document read must not rerun schema DDL")

    monkeypatch.setattr(db, "_initialize_db", unexpected_initialization)
    with store.connection() as conn:
        # A publication transaction reads these tables before taking its
        # document snapshot. Reinitialization would request conflicting locks.
        conn.execute("SELECT id FROM users_platform LIMIT 1")
        assert db.list_rag_files() == []
