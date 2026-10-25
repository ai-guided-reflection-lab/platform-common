"""Real course authorization and assignment-row preservation; inference is mocked."""
from unittest.mock import Mock
from uuid import uuid4

from app import db, settings
from platform_app import reflection_copilot, store


def seed_document(course_id, professor, *, indexed=True):
    document_id = str(uuid4()) if indexed else None
    db.save_rag_file("Requirements.pdf", "application/pdf", b"test-only course content",
                     user_id=professor, course_id=course_id, document_id=document_id)
    return document_id


def test_proposal_does_not_create_or_update_assignments(client, roster, monkeypatch):
    document_id = seed_document(roster["course"], roster["prof"])
    draft = client.post("/api/platform/assignments", headers=roster["headers"]["prof"], json={
        "course_id": roster["course"], "tool": "reflections", "title": "Existing draft", "config": {},
    })
    assert draft.status_code == 201
    with store.connection() as conn:
        before = conn.execute("SELECT * FROM assignments_platform ORDER BY id").fetchall()
    inference = Mock(return_value={
        "proposal": {"title": "Proposed title", "instructions": "Reflect on verification.", "rationale": "Connects concepts to practice.",
                     "config": {"document_ids": [document_id], "required_topics": ["Testability"], "sub_topics": ["Verification"]}},
        "evidence": [{"document_id": document_id, "title": "Requirements.pdf", "excerpt": "Requirements should be verifiable."}],
    })
    monkeypatch.setattr(reflection_copilot, "propose", inference)
    payload = {"course_id": roster["course"], "document_ids": [document_id], "goal": "Reflect on verifiable requirements."}
    endpoint = "/api/platform/copilot/reflections/propose"
    for identity, status in [("student", 403), ("other_prof", 403), ("prof", 200)]:
        response = client.post(endpoint, headers=roster["headers"][identity], json=payload)
        assert response.status_code == status, response.text
    inference.assert_called_once()
    with store.connection() as conn:
        after = conn.execute("SELECT * FROM assignments_platform ORDER BY id").fetchall()
    assert after == before


def test_missing_and_cross_course_documents_never_reach_inference(client, roster, monkeypatch):
    other_course = str(uuid4())
    with store.connection() as conn:
        conn.execute("INSERT INTO courses_platform(id,course_code,title,instructor_id) VALUES (%s,%s,'Other course',%s)",
                     (other_course, f"OTHER-{uuid4().hex[:8]}", roster["other_prof"]))
    foreign = seed_document(other_course, roster["other_prof"])
    inference = Mock(side_effect=AssertionError("Unauthorized documents must not reach inference"))
    monkeypatch.setattr(reflection_copilot, "propose", inference)
    for document_id in (foreign, str(uuid4())):
        response = client.post("/api/platform/copilot/reflections/propose", headers=roster["headers"]["prof"], json={
            "course_id": roster["course"], "document_ids": [document_id], "goal": "Reflect on testable requirements.",
        })
        assert response.status_code == 422
    inference.assert_not_called()


def test_disabled_copilot_returns_safe_503_and_manual_draft_still_works(client, roster, monkeypatch):
    document_id = seed_document(roster["course"], roster["prof"])
    monkeypatch.setattr(settings, "PLATFORM_AGENT_PROVIDER", "ollama")
    monkeypatch.setattr(settings, "PLATFORM_AGENT_MODEL", "")
    response = client.post("/api/platform/copilot/reflections/propose", headers=roster["headers"]["prof"], json={
        "course_id": roster["course"], "document_ids": [document_id], "goal": "Reflect on testable requirements.",
    })
    assert response.status_code == 503
    assert "continue configuring Reflections manually" in response.json()["detail"]
    saved = client.post("/api/platform/assignments", headers=roster["headers"]["prof"], json={
        "course_id": roster["course"], "tool": "reflections", "title": "Manual reflection",
        "config": {"document_ids": [document_id], "sub_topics": ["Verify requirements"]},
    })
    assert saved.status_code == 201, saved.text

