"""Recover safe subtopic generation requests after a sleeping service wakes."""
from time import monotonic, sleep

import httpx
from fastapi import HTTPException


def request_reflections(client, method, base_url, path, **kwargs):
    response = client.request(method, base_url + path, **kwargs)
    # Subtopic generation does not persist anything. Never replay chat turns,
    # publication, or other writes whose first response might have been lost.
    safe_to_replay = method.upper() == "POST" and path == "/api/modules/subtopics/generate"
    gateway_failure = response.status_code in {502, 504} or (
        response.status_code == 503 and "json" not in response.headers.get("content-type", "").lower()
    )
    if not safe_to_replay or not gateway_failure:
        return response

    # Probe the side-effect-free endpoint while Render starts the free instance.
    # JSON readiness prevents a hosting-provider loading page from passing.
    deadline = monotonic() + 90
    while monotonic() < deadline:
        ready = False
        try:
            health = client.get(base_url + "/health", timeout=min(10, deadline - monotonic()))
            ready = health.status_code == 200 and health.json().get("status") == "ok"
        except (httpx.HTTPError, ValueError, AttributeError):
            pass
        if ready:
            return client.request(method, base_url + path, **kwargs)
        remaining = deadline - monotonic()
        if remaining > 0:
            sleep(min(3, remaining))
    raise HTTPException(503, "Reflections is still starting. Please wait a moment and try again; you do not need to redeploy it.")
