import pytest
from fastapi import HTTPException

from platform_app import shared_rag


def test_ingest_uses_platform_embedding_configuration(monkeypatch):
    chunks = [{"text": "First section"}, {"text": "Second section"}]
    vectors = [[1.0, 0.0], [0.0, 1.0]]
    calls = []

    def pipeline(method, path, **kwargs):
        calls.append((method, path, kwargs))
        assert path == "/internal/platform/rag/parse"
        return {"chunks": chunks}

    monkeypatch.setattr(shared_rag, "pipeline", pipeline)
    monkeypatch.setattr(shared_rag, "create_embeddings", lambda texts: vectors)
    monkeypatch.setattr(shared_rag.db, "save_rag_file", lambda *_args, **_kwargs: "file-1")
    replace = lambda *args, **kwargs: calls.append(("replace", args, kwargs))
    monkeypatch.setattr(shared_rag.db, "replace_document_chunks", replace)

    result = shared_rag.ingest(
        "course-1",
        {"user_id": "instructor-1"},
        "lesson.docx",
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        b"document",
    )

    assert result["file_id"] == "file-1"
    assert result["chunk_count"] == 2
    assert [call[1] for call in calls if call[0] != "replace"] == [
        "/internal/platform/rag/parse",
    ]
    replace_call = next(call for call in calls if call[0] == "replace")
    assert replace_call[1][3] == chunks
    assert replace_call[1][4] == vectors


def test_pdf_ingest_does_not_require_shared_parser(monkeypatch):
    vectors = [[1.0, 0.0]]
    calls = []

    monkeypatch.setattr(
        shared_rag,
        "pipeline",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("PDF should be parsed in Platform"),
        ),
    )
    monkeypatch.setattr(
        shared_rag,
        "read_pdf_pages",
        lambda _path: [(1, "A readable lesson about requirements.")],
    )
    monkeypatch.setattr(shared_rag, "chunk_text", lambda text: [text])
    monkeypatch.setattr(shared_rag, "create_embeddings", lambda texts: vectors)
    monkeypatch.setattr(shared_rag.db, "save_rag_file", lambda *_args, **_kwargs: "file-1")
    monkeypatch.setattr(
        shared_rag.db,
        "replace_document_chunks",
        lambda *args, **kwargs: calls.append((args, kwargs)),
    )

    result = shared_rag.ingest(
        "course-1",
        {"user_id": "instructor-1"},
        "lesson.pdf",
        "application/pdf",
        b"pdf",
    )

    assert result["file_id"] == "file-1"
    assert result["chunk_count"] == 1
    assert calls[0][0][3][0]["page_number"] == 1
    assert calls[0][0][4] == vectors


@pytest.mark.parametrize("filename", ["lesson.html", "lesson.htm"])
def test_html_ingest_uses_local_semantic_parser(monkeypatch, filename):
    captured = []
    monkeypatch.setattr(
        shared_rag,
        "pipeline",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("Uploaded HTML should be parsed in Platform")
        ),
    )
    monkeypatch.setattr(shared_rag, "create_embeddings", lambda texts: [[0.1, 0.2] for _ in texts])
    monkeypatch.setattr(shared_rag.db, "save_rag_file", lambda *_args, **_kwargs: "file-1")
    monkeypatch.setattr(
        shared_rag.db,
        "replace_document_chunks",
        lambda *args, **kwargs: captured.append((args, kwargs)),
    )

    result = shared_rag.ingest(
        "course-1",
        {"user_id": "instructor-1"},
        filename,
        "text/html",
        b"<html><body><nav>Menu</nav><h1>Version control</h1>"
        b"<p>Version control records changes to files over time.</p></body></html>",
    )

    assert result["chunk_count"] > 0
    chunks = captured[0][0][3]
    assert any("Version control records changes" in chunk["text"] for chunk in chunks)
    assert all("Menu" not in chunk["text"] for chunk in chunks)
    assert any(chunk["metadata"]["section_path"] for chunk in chunks)
    assert captured[0][0][4] == [[0.1, 0.2] for _ in chunks]


def test_html_ingest_rejects_empty_document_before_storage(monkeypatch):
    monkeypatch.setattr(
        shared_rag.db,
        "save_rag_file",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("Empty HTML must not be saved")),
    )
    with pytest.raises(HTTPException, match="no readable text") as error:
        shared_rag.ingest(
            "course-1", {"user_id": "instructor-1"}, "empty.html", "text/html",
            b"<html><body><script>hidden</script></body></html>",
        )
    assert error.value.status_code == 422
