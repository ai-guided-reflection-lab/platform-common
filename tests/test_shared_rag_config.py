import pytest
from fastapi import HTTPException

from platform_app import shared_rag


def test_document_pipeline_requires_explicit_service_url(monkeypatch):
    monkeypatch.setenv("PLATFORM_SERVICE_TOKEN", "test-token")
    monkeypatch.delenv("SELF_DIRECTED_LEARNING_URL", raising=False)

    with pytest.raises(HTTPException) as error:
        shared_rag.pipeline("POST", "/internal/platform/rag/parse")

    assert error.value.status_code == 503
    assert "SELF_DIRECTED_LEARNING_URL" in error.value.detail
