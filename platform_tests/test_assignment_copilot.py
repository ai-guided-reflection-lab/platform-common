"""Real course scope, proposal loop, explicit save and reopen in isolated PostgreSQL."""
import json
from types import SimpleNamespace
from unittest.mock import Mock
from uuid import uuid4

import pytest
from openai.types.chat import ChatCompletionMessage

from app import db, settings
from platform_app import shared_rag, store
from platform_app.copilot import orchestrator
from platform_unit_tests.test_assignment_copilot import final


@pytest.mark.parametrize("activity", ["reflections", "socratic", "self-directed-learning", "debate"])
def test_proposal_does_not_write_then_instructor_saves_and_reopens(client, roster, monkeypatch, activity):
    course = roster["course"]
    document_id = str(uuid4())
    db.save_rag_file("OS.pdf", "application/pdf", b"test course material", user_id=roster["prof"],
                     course_id=course, document_id=document_id)
    calls = [dict(id=name, type="function", function={"name": name, "arguments": json.dumps(args)}) for name, args in [
        ("get_course_context", {"course_id": course}), ("list_activity_capabilities", {}),
        ("search_course_materials", {"course_id": course, "query": "processes and threads"}),
    ]]
    responses = iter([ChatCompletionMessage(role="assistant", tool_calls=calls),
                      ChatCompletionMessage(role="assistant", content=json.dumps(final(activity)))])
    model = Mock()
    model.__enter__ = Mock(return_value=model)
    model.__exit__ = Mock(return_value=False)
    model.chat.completions.create.side_effect = lambda **kwargs: SimpleNamespace(choices=[SimpleNamespace(message=next(responses))])
    monkeypatch.setattr(orchestrator, "OpenAI", Mock(return_value=model))
    monkeypatch.setattr(settings, "PLATFORM_AGENT_PROVIDER", "ollama")
    monkeypatch.setattr(settings, "PLATFORM_AGENT_MODEL", "test-model")
    monkeypatch.setattr(settings, "PLATFORM_AGENT_API_BASE_URL", "http://localhost:11434/v1")
    monkeypatch.setattr(shared_rag, "search", Mock(return_value={"chunks": [
        {"document_id": document_id, "text": "Threads share their process address space."}]}))
    with store.connection() as conn:
        before = conn.execute("SELECT * FROM assignments_platform ORDER BY id").fetchall()
    body = {"course_id": course, "request_id": str(uuid4()), "document_ids": [document_id],
            "goal": "Help students distinguish processes from threads.", "current": {"tool": activity}}
    endpoint = "/api/platform/copilot/propose"
    for identity, status in [("student", 403), ("other_prof", 403), ("prof", 200)]:
        result = client.post(endpoint, headers=roster["headers"][identity], json=body)
        assert result.status_code == status, result.text
    with store.connection() as conn:
        assert conn.execute("SELECT * FROM assignments_platform ORDER BY id").fetchall() == before
    proposed = result.json()["proposal"]
    assert proposed["config"]["document_ids"] == [document_id]
    proposed["instructions"] += "\n\nLearning objectives:\n" + "\n".join(f"- {value}" for value in proposed.pop("objectives"))
    proposed.pop("rationale")
    saved = client.post("/api/platform/assignments", headers=roster["headers"]["prof"], json={"course_id": course, **proposed})
    assert saved.status_code == 201, saved.text
    reopened = client.get(f"/api/platform/assignments/{saved.json()['id']}", headers=roster["headers"]["prof"])
    assert reopened.json()["status"] == "draft"
    assert reopened.json()["config"] == proposed["config"]
    assert "Learning objectives:" in reopened.json()["instructions"]


def test_foreign_document_and_capability_access_checked_before_model(client, roster, monkeypatch):
    inference = Mock(side_effect=AssertionError("No inference before authorization"))
    monkeypatch.setattr(orchestrator, "propose", inference)
    body = {"course_id": roster["course"], "document_ids": [str(uuid4())], "goal": "Distinguish processes from threads."}
    response = client.post("/api/platform/copilot/propose", headers=roster["headers"]["prof"], json=body)
    assert response.status_code == 422
    for identity, status in [("student", 403), ("other_prof", 403), ("prof", 200)]:
        result = client.get(f"/api/platform/copilot/capabilities?course_id={roster['course']}", headers=roster["headers"][identity])
        assert result.status_code == status
    inference.assert_not_called()
