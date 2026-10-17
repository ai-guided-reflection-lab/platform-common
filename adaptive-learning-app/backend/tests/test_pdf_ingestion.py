"""Real PDF parsing plus the existing RAG contract, without OpenAI calls."""
import io
import json
from contextlib import contextmanager
from types import SimpleNamespace

import pytest
from pypdf import PdfWriter
from pypdf.generic import DictionaryObject, NameObject, DecodedStreamObject

from test_api import client, create, headers  # reuse the isolated API/database fixture


def make_pdf(*, pages=1, table=False, encrypted=False):
    """Small reproducible academic PDFs; no fixture-generation dependency."""
    writer = PdfWriter()
    font = DictionaryObject({NameObject("/Type"): NameObject("/Font"),
                             NameObject("/Subtype"): NameObject("/Type1"),
                             NameObject("/BaseFont"): NameObject("/Helvetica")})
    font_ref = writer._add_object(font)
    for _ in range(pages):
        page = writer.add_blank_page(width=612, height=792)
        page[NameObject("/Resources")] = DictionaryObject({NameObject("/Font"): DictionaryObject({NameObject("/F1"): font_ref})})
        commands = []

        def text(value, x, y, size=12):
            escaped = value.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
            commands.append(f"BT /F1 {size} Tf 1 0 0 1 {x} {y} Tm ({escaped}) Tj ET")

        text("Operating Systems", 50, 740, 24)
        text("Process Management", 50, 700, 18)
        for y, line in zip(range(670, 560, -20), [
            "A process is a running instance of a program.",
            "The operating system schedules processes on the CPU.",
            "A ready process waits for CPU time. A blocked process waits for input.",
            "Scheduling makes it possible to share the processor fairly.",
            "Explain why a process waiting for input should release the CPU.",
        ]):
            text(line, 50, y)
        if table:
            for y in [530, 500, 470, 440]:
                commands.append(f"50 {y} m 560 {y} l S")
            for x in [50, 170, 440, 560]:
                commands.append(f"{x} 440 m {x} 530 l S")
            for y, row in [(510, ("State", "Description", "CPU")),
                           (480, ("Running", "Executing instructions", "Yes")),
                           (450, ("Blocked", "Waiting for input", "No"))]:
                for x, value in zip([60, 180, 450], row):
                    text(value, x, y)
        stream = DecodedStreamObject()
        stream.set_data("\n".join(commands).encode("ascii"))
        page[NameObject("/Contents")] = writer._add_object(stream)
    if encrypted:
        writer.encrypt("secret")
    output = io.BytesIO()
    writer.write(output)
    return output.getvalue()


def parse(tmp_path, **options):
    from app.resource_ingestion import ingest_resource
    path = tmp_path / "lecture.pdf"
    path.write_bytes(make_pdf(**options))
    return ingest_resource(path)


def test_academic_pdf_retains_context_and_sequential_positions(tmp_path):
    chunks = parse(tmp_path)
    assert chunks
    assert [chunk.position for chunk in chunks] == list(range(len(chunks)))
    combined = "\n".join(chunk.content for chunk in chunks)
    assert "running instance of a program" in combined
    assert "Process Management" in combined
    assert any("Process Management" in chunk.metadata.get("section", "") for chunk in chunks)
    assert all(chunk.metadata["source_type"] == "pdf" and chunk.metadata["pages"] == [1] for chunk in chunks)
    json.dumps([chunk.metadata for chunk in chunks])


def test_multi_page_pdf_has_one_based_physical_provenance(tmp_path):
    chunks = parse(tmp_path, pages=2)
    assert {page for chunk in chunks for page in chunk.metadata["pages"]} == {1, 2}
    assert any(chunk.metadata["pages"] == [1, 2] for chunk in chunks)


def test_pdf_table_preserves_column_row_relationships(tmp_path):
    chunks = parse(tmp_path, table=True)
    table_chunk = next(chunk for chunk in chunks if "Executing instructions" in chunk.content)
    assert all(value in table_chunk.content for value in ["State", "Description", "CPU", "Running", "Yes", "Blocked", "Waiting for input", "No"])
    lines = table_chunk.content.splitlines()
    assert any("Running" in line and "Executing instructions" in line and "Yes" in line for line in lines)
    assert any("Blocked" in line and "Waiting for input" in line and "No" in line for line in lines)
    assert table_chunk.metadata["pages"] == [1]


def test_scanned_pdf_uses_configured_docling_ocr(tmp_path):
    import pypdfium2
    from app.resource_ingestion import ingest_resource
    document = pypdfium2.PdfDocument(make_pdf())
    page = document[0]
    bitmap = page.render(scale=2)
    path = tmp_path / "scan.pdf"
    try:
        bitmap.to_pil().save(path, "PDF", resolution=144)
    finally:
        bitmap.close()
        page.close()
        document.close()
    chunks = ingest_resource(path)
    content = " ".join(chunk.content for chunk in chunks).lower()
    assert "running instance of a program" in content
    assert all(chunk.metadata["pages"] == [1] for chunk in chunks)


def test_chunk_token_budget_is_configurable(tmp_path, monkeypatch):
    import tiktoken
    from app import resource_ingestion
    monkeypatch.setattr(resource_ingestion, "PDF_CHUNK_MAX_TOKENS", 40)
    chunks = parse(tmp_path)
    assert len(chunks) > 1
    encoding = tiktoken.encoding_for_model(resource_ingestion.OPENAI_EMBEDDING_MODEL)
    assert all(len(encoding.encode(chunk.content)) <= 40 for chunk in chunks)


def test_pdf_upload_embeddings_storage_and_assignment_isolation(client, monkeypatch):
    from app import db, rag
    seen = []

    def embeddings(texts):
        seen.append(list(texts))
        return [[1.0, 0.0] for _ in texts]

    monkeypatch.setattr(rag, "embed_texts", embeddings)
    # The PDF path must never pass structured chunks through character splitting.
    monkeypatch.setattr(rag, "split_text", lambda text: pytest.fail("PDF used legacy chunking"))
    aid = create(client, publish=False)
    other = create(client, publish=False)
    response = client.post(f"/api/instructor/assignments/{aid}/documents", headers=headers("instructor-demo"),
                           files={"file": ("lecture.pdf", make_pdf(table=True), "application/pdf")})
    assert response.status_code == 201, response.text
    with db.connection() as conn:
        rows = conn.execute("SELECT * FROM chunks WHERE document_id=? ORDER BY position", (response.json()["id"],)).fetchall()
    assert seen[0] == [row["content"] for row in rows]
    assert all(json.loads(row["metadata"])["pages"] == [1] for row in rows)
    retrieved = rag.retrieve(aid, "Which process is using the CPU?")
    assert retrieved and len(retrieved) <= 4
    assert all(set(item) == {"document_id", "filename", "content", "score", "position", "metadata"} for item in retrieved)
    assert all(item["metadata"]["pages"] == [1] for item in retrieved)
    assert rag.retrieve(other, "Which process is using the CPU?") == []


@pytest.mark.parametrize("kind", ["invalid", "empty", "encrypted", "parser", "partial", "chunker", "embedding", "database"])
def test_failed_pdf_upload_leaves_no_records_or_files(client, monkeypatch, kind):
    from app import db, rag, resource_ingestion
    aid = create(client, publish=False)
    payload = b"not a PDF" if kind == "invalid" else make_pdf(encrypted=kind == "encrypted")
    if kind == "empty":
        writer = PdfWriter()
        writer.add_blank_page(width=612, height=792)
        output = io.BytesIO()
        writer.write(output)
        payload = output.getvalue()
    if kind == "parser":
        def fail(*args):
            raise ValueError("Parser failed")
        monkeypatch.setattr(rag, "ingest_resource", fail)
    if kind == "partial":
        from docling.datamodel.base_models import ConversionStatus
        converter = SimpleNamespace(convert=lambda path: SimpleNamespace(status=ConversionStatus.PARTIAL_SUCCESS))
        monkeypatch.setattr(resource_ingestion, "_pdf_converter", lambda: converter)
    if kind == "chunker":
        from docling.chunking import HybridChunker
        monkeypatch.setattr(HybridChunker, "chunk", lambda *args, **kwargs: (_ for _ in ()).throw(ValueError("Chunker failed")))
    if kind == "embedding":
        def fail(texts):
            raise RuntimeError("Embedding failed")
        monkeypatch.setattr(rag, "embed_texts", fail)
    if kind == "database":
        real_connection = db.connection

        @contextmanager
        def failing_connection():
            with real_connection() as conn:
                original = conn.executemany

                def fail(statement, parameters):
                    original(statement, parameters)
                    raise RuntimeError("Database failed after inserting chunks")

                conn.executemany = fail
                yield conn

        monkeypatch.setattr(rag, "connection", failing_connection)
    response = client.post(f"/api/instructor/assignments/{aid}/documents", headers=headers("instructor-demo"),
                           files={"file": ("lecture.pdf", payload, "application/pdf")})
    assert response.status_code == (502 if kind == "embedding" else 500 if kind == "database" else 422), response.text
    with db.connection() as conn:
        assert conn.execute("SELECT count(*) AS n FROM documents WHERE assignment_id=?", (aid,)).fetchone()["n"] == 0
        assert conn.execute("SELECT count(*) AS n FROM chunks").fetchone()["n"] == 0
    assert list(rag.UPLOAD_DIR.iterdir()) == []


@pytest.mark.parametrize("suffix", ["txt", "md"])
def test_text_formats_keep_legacy_content_and_chunking(client, monkeypatch, suffix):
    from app import db, rag
    aid = create(client, publish=False)
    content = "# Course\n\n" + "Processes share CPU time. " * 100
    expected = rag.split_text(content)
    monkeypatch.setattr(rag, "ingest_resource", lambda path: pytest.fail("Text used Docling"))
    response = client.post(f"/api/instructor/assignments/{aid}/documents", headers=headers("instructor-demo"),
                           files={"file": (f"course.{suffix}", content.encode())})
    assert response.status_code == 201, response.text
    with db.connection() as conn:
        rows = conn.execute("SELECT content,metadata FROM chunks WHERE document_id=? ORDER BY position", (response.json()["id"],)).fetchall()
    assert [row["content"] for row in rows] == expected
    assert all(json.loads(row["metadata"]) == {} for row in rows)


def test_existing_chunk_table_migration_preserves_data(client):
    from app import db
    aid = create(client, publish=False)
    with db.connection() as conn:
        conn.execute("DROP TABLE chunks")
        conn.execute("CREATE TABLE chunks (id TEXT PRIMARY KEY,document_id TEXT,position INTEGER,content TEXT,embedding TEXT)")
        conn.execute("INSERT INTO documents VALUES (?,?,?,?,?,?)", ("old-doc", aid, "old.txt", "text/plain", "unused", db.now()))
        conn.execute("INSERT INTO chunks VALUES (?,?,?,?,?)", ("old-chunk", "old-doc", 0, "Existing course content", "[1,0]"))
    db.initialize()
    db.initialize()  # migration remains idempotent
    with db.connection() as conn:
        row = conn.execute("SELECT * FROM chunks WHERE id='old-chunk'").fetchone()
    assert row["content"] == "Existing course content"
    assert row["embedding"] == "[1,0]"
    assert json.loads(row["metadata"]) == {}


def test_postgres_metadata_migration_uses_schema_scoped_column_lookup(client, monkeypatch):
    from app import db
    calls = []

    class ReachedSeeding(Exception):
        pass

    class Result:
        def __init__(self, rows):
            self.rows = rows

        def fetchall(self):
            return self.rows

    class Connection:
        postgres = True

        def executescript(self, statement):
            pass

        def execute(self, statement, parameters=()):
            calls.append((statement, parameters))
            if "table_name='attempts'" in statement:
                return Result([{"column_name": name} for name in (
                    "phase", "study_completed_at", "quiz_answers", "quiz_score", "learning_path", "learning_state")])
            if "table_name='chunks'" in statement:
                return Result([{"column_name": "content"}])
            return Result([])

        def executemany(self, statement, parameters):
            raise ReachedSeeding

    @contextmanager
    def connection():
        yield Connection()

    monkeypatch.setattr(db, "connection", connection)
    with pytest.raises(ReachedSeeding):
        db.initialize()
    assert any("table_name='chunks'" in sql and parameters == (db.DATABASE_SCHEMA,) for sql, parameters in calls)
    assert ("ALTER TABLE chunks ADD COLUMN metadata TEXT NOT NULL DEFAULT '{}'", ()) in calls
