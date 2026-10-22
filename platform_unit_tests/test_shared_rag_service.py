import httpx
import pytest
from fastapi import HTTPException

from platform_app import shared_rag


def mock_client(monkeypatch, handler):
    real_client = httpx.Client
    monkeypatch.setattr(
        shared_rag.httpx,
        "Client",
        lambda **kwargs: real_client(transport=httpx.MockTransport(handler), **kwargs),
    )


def test_pipeline_waits_for_sdl_cold_start(monkeypatch):
    calls = []

    def handler(request):
        calls.append((request.method, request.url.path))
        if len(calls) == 1:
            return httpx.Response(200, text="Application loading", headers={"content-type": "text/html"})
        if request.url.path == "/api/health":
            return httpx.Response(200, json={"status": "ok"})
        return httpx.Response(200, json={"chunks": []})

    mock_client(monkeypatch, handler)
    monkeypatch.setattr(shared_rag.time, "sleep", lambda seconds: None)
    monkeypatch.setenv("PLATFORM_SERVICE_TOKEN", "test-token")
    monkeypatch.setenv("SELF_DIRECTED_LEARNING_URL", "https://sdl.example.test")

    assert shared_rag.pipeline("POST", "/internal/platform/rag/search", json={"query": "test"}) == {"chunks": []}
    assert calls == [
        ("GET", "/api/health"),
        ("GET", "/api/health"),
        ("POST", "/internal/platform/rag/search"),
    ]


def test_pipeline_preserves_sdl_error_detail(monkeypatch):
    def handler(request):
        if request.url.path == "/api/health":
            return httpx.Response(200, json={"status": "ok"})
        return httpx.Response(502, json={"detail": "The AI provider rate limit was reached."})

    mock_client(monkeypatch, handler)
    monkeypatch.setenv("PLATFORM_SERVICE_TOKEN", "test-token")
    with pytest.raises(HTTPException) as error:
        shared_rag.pipeline("POST", "/internal/platform/lessons/prepare", json={})
    assert error.value.status_code == 502
    assert error.value.detail == "The AI provider rate limit was reached."


def test_pipeline_reports_wrong_sdl_url(monkeypatch):
    def handler(request):
        return httpx.Response(404)

    mock_client(monkeypatch, handler)
    monkeypatch.setenv("PLATFORM_SERVICE_TOKEN", "test-token")
    with pytest.raises(HTTPException) as error:
        shared_rag.pipeline("POST", "/internal/platform/lessons/prepare", json={})
    assert error.value.status_code == 503
    assert "URL" in error.value.detail


def test_pipeline_reports_sdl_still_starting(monkeypatch):
    mock_client(monkeypatch, lambda request: httpx.Response(200, text="Application loading"))
    with httpx.Client() as client:
        with pytest.raises(HTTPException) as error:
            shared_rag._wait_for_service(client, "https://sdl.example.test", timeout=0)
    assert error.value.status_code == 503
    assert "still starting" in error.value.detail
