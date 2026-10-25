"""Compatibility entry point for the first Reflections vertical slice.

New authoring uses platform_app.copilot and the generic proposal endpoint.
Both entry points share the same bounded local orchestrator and retrieval code.
"""
from openai import OpenAI
from fastapi import HTTPException
from platform_app import shared_rag
from platform_app.copilot.orchestrator import propose as run


def propose(body, documents, *, authorize=None):
    try:
        return run(body, documents, legacy=True, client_factory=OpenAI, authorize=authorize)
    except HTTPException as exc:
        if exc.status_code == 503:
            exc.detail = exc.detail.replace("configuring the assignment manually", "configuring Reflections manually")
        raise
