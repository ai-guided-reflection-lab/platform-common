import pytest
from psycopg.rows import tuple_row

from app import db, rag, settings
from platform_app import store


def test_empty_vector_index_can_adopt_qwen_dimensions(roster,monkeypatch):
    monkeypatch.setattr(settings,'EMBEDDING_DIMENSIONS',1024)
    with store.connection() as conn:
        conn.execute('CREATE TEMP TABLE chunks (embedding vector(1536)) ON COMMIT DROP')
        conn.execute('CREATE INDEX idx_document_chunks_embedding ON chunks USING hnsw (embedding vector_cosine_ops)')
        with conn.cursor() as cursor:
            cursor.row_factory=tuple_row
            db._ensure_embedding_dimensions(cursor)
        row=conn.execute("SELECT atttypmod FROM pg_attribute WHERE attrelid='chunks'::regclass AND attname='embedding'").fetchone()
        assert row['atttypmod']==1024


def test_existing_vectors_are_not_destroyed_by_dimension_change(roster,monkeypatch):
    monkeypatch.setattr(settings,'EMBEDDING_DIMENSIONS',1024)
    with store.connection() as conn:
        conn.execute('CREATE TEMP TABLE chunks (embedding vector(1536)) ON COMMIT DROP')
        conn.execute('INSERT INTO chunks VALUES (%s::vector)',('['+','.join(['0.1']*1536)+']',))
        with conn.cursor() as cursor:
            # The initializer normally uses tuple rows; retain that contract here.
            cursor.row_factory=tuple_row
            with pytest.raises(RuntimeError,match='no data was deleted'):db._ensure_embedding_dimensions(cursor)
        assert conn.execute('SELECT vector_dims(embedding) AS dimensions FROM chunks').fetchone()['dimensions']==1536


def test_hybrid_search_does_not_mix_embedding_models(roster,monkeypatch):
    monkeypatch.setattr(settings,'EMBEDDING_MODEL','current-model')
    for model in ['current-model','different-model']:
        fid=db.save_rag_file(model+'.txt','text/plain',b'Database records use keys.',course_id=roster['course'],user_id=roster['prof'])
        db.replace_document_chunks(fid,model,model,[{'text':'Database records use keys.'}],[[0.1]*1536],model,course_id=roster['course'])
    matches=db.hybrid_search_chunks('database records',[0.1]*1536,4,course_id=roster['course'])
    assert matches and {m['document_id'] for m in matches}=={'current-model'}


def test_course_upload_reports_embedding_failure_clearly(client,roster,monkeypatch,tmp_path):
    monkeypatch.setattr(settings,'RAW_DOCS_DIR',tmp_path)
    def fail(*_args,**_kwargs):raise rag.EmbeddingError('Ollama embedding model is unavailable. Start Ollama and retry.')
    monkeypatch.setattr('app.main.ingest_file',fail)
    response=client.post(f"/api/courses/{roster['course']}/documents/upload",headers=roster['headers']['prof'],files={'files':('small.txt',b'A short readable document.','text/plain')})
    assert response.status_code==503
    assert 'Start Ollama' in response.json()['detail']
