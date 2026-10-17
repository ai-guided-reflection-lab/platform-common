from pathlib import Path

import httpx

from test_api import client, create, headers, lesson
from test_presentation_url_ingestion import network, ARTICLE


def test_url_preview_uses_article_parser_without_creating_assignment(client, network):
    routes, _ = network
    routes["https://school.test/article"] = httpx.Response(200, content=ARTICLE, headers={"content-type": "text/html"})
    result = client.post("/api/instructor/documents/url-preview", headers=headers("instructor-demo"), json={"url": "https://school.test/article"})
    assert result.status_code == 200, result.text
    assert "blocked process" in result.json()["text"].lower()
    assert "Navigation home" not in result.json()["text"]
    from app.db import connection
    with connection() as conn:
        assert conn.execute("SELECT count(*) AS n FROM documents").fetchone()["n"] == 0
    assert client.post("/api/instructor/documents/url-preview", headers=headers(), json={"url": "https://school.test/article"}).status_code == 403
    assert client.post("/api/instructor/documents/url-preview", headers=headers("instructor-demo"), json={"url": "http://localhost/private"}).status_code == 422


def test_published_copy_is_editable_and_sources_are_independent(client):
    from app.db import connection
    aid = create(client, publish=False)
    uploaded = client.post(f"/api/instructor/assignments/{aid}/documents", headers=headers("instructor-demo"), files={"file": ("notes.txt", b"Source teaching material for requirements and quality constraints.")})
    assert uploaded.status_code == 201
    original = client.post(f"/api/instructor/assignments/{aid}/publish", headers=headers("instructor-demo")).json()
    result = client.post(f"/api/instructor/assignments/{aid}/editable-copy", headers=headers("instructor-demo"))
    assert result.status_code == 201, result.text
    copy = result.json()
    assert copy["id"] != aid and copy["status"] == "draft"
    assert not copy["learning_plan"]["content_approved"]
    assert copy["documents"][0]["chunk_count"] == original["documents"][0]["chunk_count"]
    with connection() as conn:
        docs = conn.execute("SELECT * FROM documents ORDER BY created_at").fetchall()
        assert len({doc["path"] for doc in docs}) == 2
    plan = copy["learning_plan"]
    plan["diagnostic_quiz"][0]["question"] = "A revised quiz question?"
    body = {"title": copy["title"], "instructions": copy["instructions"], "student_ids": [s["id"] for s in copy["students"]], "learning_plan": plan}
    assert client.put(f"/api/instructor/assignments/{copy['id']}", headers=headers("instructor-demo"), json=body).status_code == 200
    assert client.put(f"/api/instructor/assignments/{aid}", headers=headers("instructor-demo"), json=body).status_code == 409
    unchanged = client.get(f"/api/instructor/assignments/{aid}", headers=headers("instructor-demo")).json()
    assert unchanged["learning_plan"] == original["learning_plan"]
    assert unchanged["access_code"] == original["access_code"]
    assert client.delete(f"/api/instructor/assignments/{copy['id']}/documents/{copy['documents'][0]['id']}", headers=headers("instructor-demo")).status_code == 204
    assert Path(docs[0]["path"]).exists()
