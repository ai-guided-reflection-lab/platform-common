from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient


@pytest.fixture
def rag_service(monkeypatch):
    from app import common_rag_api, openai_client
    monkeypatch.setenv("PLATFORM_SERVICE_TOKEN", "rag-test-service")
    monkeypatch.setattr(openai_client, "OPENAI_API_KEY", "not-a-real-key")
    monkeypatch.setattr(openai_client, "runtime_ai_mode", lambda: "openai")
    requests = []

    class Provider:
        def __init__(self, **kwargs): pass
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def post(self, url, **kwargs):
            payload = kwargs["json"]
            requests.append(payload)
            dimensions = payload["dimensions"]
            return SimpleNamespace(
                raise_for_status=lambda: None,
                json=lambda: {"data": [{"index": i, "embedding": [1.0] + [0.0] * (dimensions - 1)} for i in range(len(payload["input"]))]},
            )

    monkeypatch.setattr(openai_client.httpx, "Client", Provider)
    app = FastAPI()
    app.include_router(common_rag_api.router)
    with TestClient(app) as client:
        yield client, requests, common_rag_api.OPENAI_EMBEDDING_MODEL


def test_shared_embeddings_preserve_dimensions_and_batch(rag_service):
    client, requests, model = rag_service
    response = client.post("/internal/platform/rag/embeddings", headers={"X-Platform-Service": "rag-test-service"}, json={"texts": ["course material"] * 130, "model": model, "dimensions": 128})
    assert response.status_code == 200, response.text
    assert [len(item["input"]) for item in requests] == [64, 64, 2]
    assert all(item["dimensions"] == 128 for item in requests)
    assert len(response.json()["embeddings"]) == 130
    assert all(len(vector) == 128 for vector in response.json()["embeddings"])


def test_rag_service_rejects_untrusted_callers_and_model_mismatch(rag_service):
    client, requests, model = rag_service
    body = {"texts": ["course material"], "model": model, "dimensions": 128}
    assert client.post("/internal/platform/rag/embeddings", json=body).status_code == 401
    assert client.post("/internal/platform/rag/embeddings", headers={"X-Platform-Service": "wrong"}, json=body).status_code == 401
    response = client.post("/internal/platform/rag/embeddings", headers={"X-Platform-Service": "rag-test-service"}, json={**body, "model": "other-model"})
    assert response.status_code == 409
    assert requests == []


def test_shared_search_preserves_citations_without_exposing_vectors(rag_service):
    client, requests, model = rag_service
    chunk = {"chunk_id": "chunk-1", "document_id": "document-1", "course_id": "course-1", "text": "Course material", "title": "Course notes", "embedding": [1.0, 0.0]}
    response = client.post("/internal/platform/rag/search", headers={"X-Platform-Service": "rag-test-service"}, json={"query": "Course question", "chunks": [chunk], "limit": 1, "model": model, "dimensions": 2})
    assert response.status_code == 200, response.text
    selected = response.json()["chunks"][0]
    assert selected["chunk_id"] == "chunk-1"
    assert selected["course_id"] == "course-1"
    assert selected["score"] == 1.0
    assert "embedding" not in selected


def test_shared_pdf_parse_uses_lightweight_page_extraction(rag_service, monkeypatch):
    from app import common_rag_api

    class Page:
        def extract_text(self):
            return "A readable course page about requirements and design."

    monkeypatch.setattr(common_rag_api, "_pdf_pages", lambda _path: [Page()])
    monkeypatch.setattr(
        common_rag_api,
        "parse_resource",
        lambda _path: pytest.fail("PDF upload should not load Docling"),
    )
    client, _requests, _model = rag_service
    response = client.post(
        "/internal/platform/rag/parse",
        headers={"X-Platform-Service": "rag-test-service"},
        files={"file": ("lesson.pdf", b"pdf", "application/pdf")},
    )

    assert response.status_code == 200, response.text
    assert response.json()["chunks"][0]["page_number"] == 1
    assert "requirements and design" in response.json()["chunks"][0]["text"]
