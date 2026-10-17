from uuid import uuid4

from psycopg import sql
import pytest

from app import db, settings
from platform_app import store


def test_legacy_rename_preserves_files_vectors_and_chunk_identity(roster, monkeypatch):
    document_id = str(uuid4())
    file_id = db.save_rag_file('shared.txt', 'text/plain', b'Shared course material',
                              user_id=roster['prof'], course_id=roster['course'], document_id=document_id)
    vectors = [[1.0] + [0.0] * (settings.EMBEDDING_DIMENSIONS - 1)]
    db.replace_document_chunks(file_id, document_id, 'shared.txt',
                               [{'text':'Shared course material','metadata':{},'page_number':1}],
                               vectors, settings.embedding_model_name(), course_id=roster['course'])
    before = db.snapshot_document_chunks(roster['course'], [document_id])
    with store.connection() as conn:
        for current, legacy in [('chunks','document_chunks_socratic_chat'), ('documents','rag_files_socratic_chat')]:
            conn.execute(sql.SQL('ALTER TABLE {} RENAME TO {}').format(
                sql.Identifier(settings.SHARED_RAG_DB_SCHEMA, current), sql.Identifier(legacy)))
    original = settings.SHARED_RAG_DB_SCHEMA
    target = original + '_rag'
    try:
        with monkeypatch.context() as patch:
            patch.setattr(settings, 'SHARED_RAG_DB_SCHEMA', target)
            db.init_db()
            db.init_db()  # A second startup must leave the migrated data unchanged.
            assert db.get_rag_file(file_id)['content'] == b'Shared course material'
            assert db.snapshot_document_chunks(roster['course'], [document_id]) == before
    finally:
        # Restore the isolated fixture's shared tables for subsequent tests.
        with store.connection() as conn:
            for table in ('documents', 'chunks'):
                exists = conn.execute('SELECT to_regclass(%s)', (sql.Identifier(target, table).as_string(conn),)).fetchone()
                if next(iter(exists.values())):
                    conn.execute(sql.SQL('ALTER TABLE {} SET SCHEMA {}').format(sql.Identifier(target, table), sql.Identifier(original)))
            conn.execute(sql.SQL('DROP SCHEMA IF EXISTS {}').format(sql.Identifier(target)))


def test_conflicting_old_and_new_stores_are_not_silently_merged_or_deleted(database):
    legacy = sql.Identifier(settings.SOCRATIC_DB_SCHEMA, 'rag_files_socratic_chat')
    with store.connection() as conn:
        conn.execute(sql.SQL('CREATE TABLE {} (id uuid)').format(legacy))
    try:
        with pytest.raises(RuntimeError, match='Reconcile the two stores'):
            db.init_db()
    finally:
        with store.connection() as conn:
            conn.execute(sql.SQL('DROP TABLE {}').format(legacy))
