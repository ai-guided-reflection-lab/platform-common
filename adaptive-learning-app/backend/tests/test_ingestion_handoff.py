"""Stage 4 handoff contract and integration hardening, without live embeddings."""
import io
import json
from contextlib import contextmanager
from pathlib import Path
from types import SimpleNamespace

import httpx
import pytest
from pptx import Presentation

from test_api import client, create, headers
from test_pdf_ingestion import make_pdf
from test_presentation_url_ingestion import ARTICLE, network, presentation


def url_resource(client, assignment, url):
    return client.post(f"/api/instructor/assignments/{assignment}/documents/url",
                       headers=headers("instructor-demo"), json={"url": url})


@pytest.mark.parametrize("kind", ["pdf", "pptx", "html", "pdf_url"])
def test_provenance_content_vectors_and_isolation_survive_retrieval(client, network, monkeypatch, kind):
    from app import rag, db, main
    routes, _ = network
    assignment = create(client, publish=False)
    foreign = create(client, publish=False)
    calls = []
    def embed(texts):
        vectors = [[0.0, 1.0] for _ in texts]
        vectors[-1] = [1.0, 0.0]
        calls.append((list(texts), vectors))
        return vectors
    monkeypatch.setattr(rag, "embed_texts", embed)
    if kind in {"pdf", "pptx"}:
        data = make_pdf(pages=12) if kind == "pdf" else presentation(slides=8)
        response = client.post(f"/api/instructor/assignments/{assignment}/documents",
                               headers=headers("instructor-demo"), files={"file": (f"lecture.{kind}", data)})
    else:
        url = "https://school.test/download" if kind == "pdf_url" else "https://school.test/article"
        routes[url] = httpx.Response(200, content=make_pdf() if kind == "pdf_url" else ARTICLE,
                                    headers={"content-type": "application/pdf" if kind == "pdf_url" else "text/html"})
        response = url_resource(client, assignment, url)
    assert response.status_code == 201, response.text
    document = response.json()["id"]
    texts, vectors = calls[0]
    with db.connection() as conn:
        rows = conn.execute("SELECT c.*,d.assignment_id FROM chunks c JOIN documents d ON d.id=c.document_id WHERE d.id=? ORDER BY c.position", (document,)).fetchall()
    assert texts == [row["content"] for row in rows]
    assert vectors == [json.loads(row["embedding"]) for row in rows]
    assert all(row["assignment_id"] == assignment for row in rows)
    foreign_response = client.post(f"/api/instructor/assignments/{foreign}/documents",
                                   headers=headers("instructor-demo"), files={"file": ("foreign.txt", b"Unrelated material with equally high similarity.")})
    assert foreign_response.status_code == 201
    monkeypatch.setattr(rag, "embed_texts", lambda texts: [[1.0, 0.0] for _ in texts])
    retrieved = rag.retrieve(assignment, "What is a process?")
    assert len(retrieved) == min(4, len(rows))
    assert all(item["document_id"] == document for item in retrieved)
    by_position = {row["position"]: row for row in rows}
    for item in retrieved:
        row = by_position[item["position"]]
        assert item["content"] == row["content"]
        assert item["metadata"] == json.loads(row["metadata"])
    if kind == "pdf":
        assert any(12 in item["metadata"]["pages"] for item in retrieved)
    elif kind == "pptx":
        assert retrieved[0]["metadata"]["slide"] == 8
    else:
        assert all(item["metadata"]["source_url"] == url for item in retrieved)
        if kind == "pdf_url":
            assert retrieved[0]["metadata"]["pages"] == [1]
    assert main._source_metadata(retrieved)[0]["metadata"] == retrieved[0]["metadata"]
    assert all(item["document_id"] == foreign_response.json()["id"] for item in rag.retrieve(foreign, "process"))


@pytest.mark.parametrize("kind", ["empty_pptx", "parser_pptx", "invalid_pdf_url", "empty_html", "missing_redirect"])
def test_additional_parse_failures_are_atomic(client, network, monkeypatch, kind):
    from app import rag, db, config
    routes, _ = network
    assignment = create(client, publish=False)
    if kind.endswith("pptx"):
        data = presentation()
        if kind == "empty_pptx":
            buffer = io.BytesIO()
            Presentation().save(buffer)
            data = buffer.getvalue()
        else:
            monkeypatch.setattr(rag, "ingest_resource", lambda path: (_ for _ in ()).throw(ValueError("parser failed")))
        response = client.post(f"/api/instructor/assignments/{assignment}/documents",
                               headers=headers("instructor-demo"), files={"file": ("lecture.pptx", data)})
    else:
        url = "https://school.test/resource"
        routes[url] = {
            "invalid_pdf_url": httpx.Response(200, content=b"%PDF-1.7\ncorrupt", headers={"content-type": "application/pdf"}),
            "empty_html": httpx.Response(200, content=b"<html><body><article><p></", headers={"content-type": "text/html"}),
            "missing_redirect": httpx.Response(302),
        }[kind]
        response = url_resource(client, assignment, url)
    assert response.status_code == 422, response.text
    assert response.json()["detail"]
    with db.connection() as conn:
        assert conn.execute("SELECT count(*) FROM documents").fetchone()[0] == 0
        assert conn.execute("SELECT count(*) FROM chunks").fetchone()[0] == 0
    assert not list(config.UPLOAD_DIR.iterdir())


@pytest.mark.parametrize("kind", ["pptx", "html"])
def test_database_failure_after_chunk_inserts_rolls_back_and_cleans(client, network, monkeypatch, kind):
    from app import rag, db, config
    routes, _ = network
    assignment = create(client, publish=False)
    real_connection = db.connection
    @contextmanager
    def fail_after_insert():
        with real_connection() as conn:
            actual = conn.executemany
            def insert_then_fail(statement, parameters):
                actual(statement, parameters)
                raise RuntimeError("storage failed after chunks")
            conn.executemany = insert_then_fail
            yield conn
    monkeypatch.setattr(rag, "connection", fail_after_insert)
    if kind == "pptx":
        response = client.post(f"/api/instructor/assignments/{assignment}/documents",
                               headers=headers("instructor-demo"), files={"file": ("lecture.pptx", presentation())})
    else:
        routes["https://school.test/article"] = httpx.Response(200, content=ARTICLE, headers={"content-type": "text/html"})
        response = url_resource(client, assignment, "https://school.test/article")
    assert response.status_code == 500
    with db.connection() as conn:
        assert conn.execute("SELECT count(*) FROM documents").fetchone()[0] == 0
        assert conn.execute("SELECT count(*) FROM chunks").fetchone()[0] == 0
    assert not list(config.UPLOAD_DIR.iterdir())


def test_streaming_deadline_checked_before_buffer_fills(network, monkeypatch):
    from app import resource_ingestion as ingestion
    routes, _ = network
    clock = SimpleNamespace(value=0.0)
    monkeypatch.setattr(ingestion, "time", SimpleNamespace(monotonic=lambda: clock.value))
    class Trickle(httpx.SyncByteStream):
        def __iter__(self):
            for _ in range(5):
                clock.value += 8
                yield b"a"
        def close(self):
            self.closed = True
    stream = Trickle()
    routes["https://school.test/article"] = httpx.Response(200, stream=stream, headers={"content-type": "text/html"})
    with pytest.raises(ingestion.ResourceIngestionError, match="timed out"):
        ingestion.fetch_resource_url("https://school.test/article")
    assert clock.value == 24  # Stops on the first read past the deadline, not EOF.
    assert stream.closed


@pytest.mark.parametrize("suffix", ["pdf", "pptx", "html"])
def test_deletion_removes_file_chunks_and_retrieval(client, network, suffix):
    from app import db, rag
    routes, _ = network
    assignment = create(client, publish=False)
    if suffix == "html":
        routes["https://school.test/article"] = httpx.Response(200, content=ARTICLE, headers={"content-type": "text/html"})
        response = url_resource(client, assignment, "https://school.test/article")
    else:
        response = client.post(f"/api/instructor/assignments/{assignment}/documents", headers=headers("instructor-demo"),
                               files={"file": (f"lecture.{suffix}", make_pdf() if suffix == "pdf" else presentation())})
    assert response.status_code == 201, response.text
    doc_id = response.json()["id"]
    with db.connection() as conn:
        path = Path(conn.execute("SELECT path FROM documents WHERE id=?", (doc_id,)).fetchone()[0])
    assert path.is_file() and rag.retrieve(assignment, "process")
    endpoint = f"/api/instructor/assignments/{assignment}/documents/{doc_id}"
    assert client.delete(endpoint, headers=headers("instructor-demo")).status_code == 204
    assert not path.exists() and rag.retrieve(assignment, "process") == []
    with db.connection() as conn:
        assert conn.execute("SELECT count(*) FROM chunks WHERE document_id=?", (doc_id,)).fetchone()[0] == 0
    assert client.delete(endpoint, headers=headers("instructor-demo")).status_code == 404


def test_resource_access_and_duplicate_submission_contract(client, network):
    from app import db
    routes, calls = network
    assignment = create(client, publish=False)
    with db.connection() as conn:
        conn.execute("INSERT INTO users VALUES (?,?,?,?)", ("other-instructor", "other@example.test", "Other", "instructor"))
    endpoint = f"/api/instructor/assignments/{assignment}/documents/url"
    assert client.post(endpoint, json={"url": "https://school.test/article"}).status_code == 401
    assert client.post(endpoint, headers=headers("other-instructor"), json={"url": "https://school.test/article"}).status_code == 404
    assert client.post(endpoint, headers=headers("instructor-demo"), json={"url": ""}).status_code == 422
    assert not calls
    routes["https://school.test/article"] = httpx.Response(200, content=ARTICLE, headers={"content-type": "text/html"})
    first = url_resource(client, assignment, "https://school.test/article")
    # Each explicit successful submission is intentionally a separate resource.
    routes["https://school.test/article"] = httpx.Response(200, content=ARTICLE, headers={"content-type": "text/html"})
    second = url_resource(client, assignment, "https://school.test/article")
    assert first.status_code == second.status_code == 201
    assert first.json()["id"] != second.json()["id"]
    with db.connection() as conn:
        assert conn.execute("SELECT count(*) FROM documents WHERE assignment_id=?", (assignment,)).fetchone()[0] == 2


@pytest.mark.parametrize("suffix", ["pdf", "pptx"])
def test_upload_ownership_authentication_and_frozen_assignment(client, suffix):
    from app import db, config
    assignment = create(client, publish=False)
    published = create(client)
    with db.connection() as conn:
        conn.execute("INSERT INTO users VALUES (?,?,?,?)", ("other-instructor", "other@example.test", "Other", "instructor"))
    for identity, target, status in [(None, assignment, 401), ("student-alex", assignment, 403),
                                     ("other-instructor", assignment, 404), ("instructor-demo", published, 409)]:
        result = client.post(f"/api/instructor/assignments/{target}/documents", headers=headers(identity) if identity else {},
                             files={"file": (f"lecture.{suffix}", b"must never reach parsing")})
        assert result.status_code == status
    assert not list(config.UPLOAD_DIR.iterdir())


def test_pdf_preview_stays_lightweight_and_has_no_storage_side_effects(client, monkeypatch):
    from app import rag, db
    monkeypatch.setattr(rag, "ingest_resource", lambda path: pytest.fail("Preview initialized Docling"))
    result = client.post("/api/instructor/documents/preview", headers=headers("instructor-demo"),
                         files={"file": ("lecture.pdf", make_pdf())})
    assert result.status_code == 200 and "running instance" in result.json()["text"]
    with db.connection() as conn:
        assert conn.execute("SELECT count(*) FROM documents").fetchone()[0] == 0


def test_preview_missing_presentation_dependency_is_service_error(client, monkeypatch):
    from app import rag
    monkeypatch.setattr(rag, "extract_text", lambda path: (_ for _ in ()).throw(ImportError("python-pptx missing")))
    result = client.post("/api/instructor/documents/preview", headers=headers("instructor-demo"), files={"file": ("lecture.pptx", presentation())})
    assert result.status_code == 503 and "dependencies" in result.json()["detail"]


@pytest.mark.parametrize("host", ["127.0.0.1", "10.1.2.3", "172.16.0.1", "192.168.1.1", "169.254.169.254", "[::1]", "[fc00::1]"])
def test_literal_private_addresses_are_rejected_without_http(host):
    from app.resource_ingestion import _validate_resource_url, ResourceIngestionError
    with pytest.raises(ResourceIngestionError, match="Private"):
        _validate_resource_url(f"http://{host}/resource")


def test_redirect_requests_use_remaining_download_budget(monkeypatch):
    from app import resource_ingestion as ingestion
    clock = SimpleNamespace(value=0.0)
    budgets = []
    monkeypatch.setattr(ingestion, "time", SimpleNamespace(monotonic=lambda: clock.value))
    monkeypatch.setattr(ingestion, "_validate_resource_url", lambda url: None)
    class Client:
        def __init__(self, **kwargs):
            assert kwargs["follow_redirects"] is False and kwargs["trust_env"] is False
        def __enter__(self):
            return self
        def __exit__(self, *args):
            pass
        @contextmanager
        def stream(self, method, url, **kwargs):
            budgets.append(kwargs["timeout"])
            if len(budgets) == 1:
                clock.value = 12
                yield httpx.Response(302, headers={"location": "/article"})
            else:
                yield httpx.Response(200, content=ARTICLE, headers={"content-type": "text/html"})
    monkeypatch.setattr(ingestion, "httpx", SimpleNamespace(Client=Client, HTTPError=httpx.HTTPError, TimeoutException=httpx.TimeoutException))
    data, mime, final = ingestion.fetch_resource_url("https://school.test/start")
    assert budgets == [20, 8] and mime == "text/html" and data == ARTICLE
    assert final == "https://school.test/article"
