import importlib.util
import sys
import types
from pathlib import Path
from uuid import uuid4

from fastapi.testclient import TestClient

from platform_app import adaptive_runtime, engines, store
from platform_app.adaptive import oop_learning_plan


def adaptive_assignment(client, roster, monkeypatch):
    plan = oop_learning_plan().model_dump(mode="json")
    body = {
        "course_id": roster["course"],
        "tool": "student-agent",
        "title": "Adaptive OOP",
        "instructions": "Complete the adaptive diagnostic and required task.",
        "audience": "selected",
        "recipient_ids": [roster["student"]],
        "config": {"provider": "openai", "personality": "confused", "learning_plan": plan},
    }
    created = client.post(
        "/api/platform/assignments", headers=roster["headers"]["prof"], json=body
    )
    assert created.status_code == 201, created.text
    assignment = created.json()
    monkeypatch.setattr(
        engines,
        "publish_snapshot",
        lambda item: {"config": item["config"], "chunks": []},
    )
    published = client.post(
        f"/api/platform/assignments/{assignment['id']}/publish",
        headers=roster["headers"]["prof"],
    )
    assert published.status_code == 200, published.text
    return assignment


def test_adaptive_detection_is_nonvalidating_until_runtime_selection():
    assert not adaptive_runtime.is_adaptive_assignment(
        {"tool": "reflections", "config": {"legacy": "value"}}
    )
    assert not adaptive_runtime.is_adaptive_assignment(
        {"tool": "student-agent", "config": {"legacy": "value"}}
    )
    assert adaptive_runtime.is_adaptive_assignment(
        {"tool": "student-agent", "config": {"learning_plan": {"invalid": "until runtime"}}}
    )


def test_publish_rejects_nonseeded_adaptive_plan(client, roster):
    plan = oop_learning_plan().model_dump(mode="json")
    plan["title"] = "An unsupported custom plan"
    created = client.post(
        "/api/platform/assignments",
        headers=roster["headers"]["prof"],
        json={
            "course_id": roster["course"],
            "tool": "student-agent",
            "title": "Unsupported adaptive plan",
            "audience": "selected",
            "recipient_ids": [roster["student"]],
            "config": {"provider": "openai", "learning_plan": plan},
        },
    )
    assert created.status_code == 201, created.text
    published = client.post(
        f"/api/platform/assignments/{created.json()['id']}/publish",
        headers=roster["headers"]["prof"],
    )
    assert published.status_code == 422, published.text
    assert "seeded Object-Oriented Programming plan" in published.json()["detail"]


def install_fake_tutor(monkeypatch):
    transcripts = {}
    assess_calls = []
    render_calls = []

    def result(response, objective, assessment_type):
        if "wrong" in response.lower():
            return {
                "objective_id": objective,
                "assessment_type": assessment_type,
                "correctness": "incorrect",
                "completeness": "complete",
                "independence": "independent",
                "misconception_code": "class_object_confusion",
                "misconception_detail": "The response conflates a class and an instance.",
                "rationale": "The demonstrated reasoning is incorrect.",
                "assessor_version": "test-assessor-v1",
            }
        if "partial" in response.lower():
            return {
                "objective_id": objective,
                "assessment_type": assessment_type,
                "correctness": "partial",
                "completeness": "partial",
                "independence": "independent",
                "misconception_code": None,
                "misconception_detail": None,
                "rationale": "Some relevant understanding is present.",
                "assessor_version": "test-assessor-v1",
            }
        return {
            "objective_id": objective,
            "assessment_type": assessment_type,
            "correctness": "correct",
            "completeness": "complete",
            "independence": "independent",
            "misconception_code": None,
            "misconception_detail": None,
            "rationale": "The response demonstrates the requested understanding.",
            "assessor_version": "test-assessor-v1",
        }

    def call(tool, method, path, **kwargs):
        assert tool == "student-agent"
        payload = kwargs["json"]
        if path.endswith("/adaptive/start"):
            transcripts[payload["session_id"]] = [
                {"role": "assistant", "content": payload["assessment_prompt"]}
            ]
            return {"messages": transcripts[payload["session_id"]].copy(), "phase": "checking"}
        if path.endswith("/adaptive/assess"):
            assess_calls.append(payload)
            assessment = payload["assessment"]
            return result(payload["student_response"], assessment["objective_id"], assessment["assessment_type"])
        if path.endswith("/adaptive/render"):
            render_calls.append(payload)
            transcript = transcripts[payload["session_id"]]
            transcript.extend([
                {"role": "user", "content": payload["student_message"]},
                {
                    "role": "assistant",
                    "content": f"{payload['decision']['action']}: {payload['assessment_prompt']}",
                },
            ])
            return {"messages": transcript.copy(), "phase": "checking", "nav": {"next": True}}
        raise AssertionError(path)

    monkeypatch.setattr(engines, "call", call)
    return assess_calls, render_calls


def install_in_process_tutor(monkeypatch, tmp_path):
    """Route platform calls through the real tutor API, isolating only the LLM."""
    tutor_root = Path(__file__).resolve().parents[1] / "student-agent-bot"
    monkeypatch.syspath_prepend(str(tutor_root))

    # The platform test environment deliberately does not install tutor model
    # providers. Supply only the external-LLM seam needed to import the real
    # tutor API and exercise its durable session boundary.
    messages = types.ModuleType("langchain_core.messages")
    class Message:
        def __init__(self, content=""):
            self.content = content
    messages.AIMessage = messages.HumanMessage = messages.SystemMessage = Message
    langchain_core = types.ModuleType("langchain_core")
    langchain_core.messages = messages
    monkeypatch.setitem(sys.modules, "langchain_core", langchain_core)
    monkeypatch.setitem(sys.modules, "langchain_core.messages", messages)
    models = types.ModuleType("models")
    models.PROVIDERS = {
        "openai": {"label": "OpenAI", "env_key": "OPENAI_API_KEY"},
        "groq": {"label": "Groq", "env_key": "GROQ_API_KEY"},
    }
    models.get_model = lambda provider: None
    models.invoke_with_retry = lambda *args, **kwargs: None
    monkeypatch.setitem(sys.modules, "models", models)
    assessor = types.ModuleType("adaptive_assessor")
    assessor.assess_response = lambda *args, **kwargs: None
    monkeypatch.setitem(sys.modules, "adaptive_assessor", assessor)
    firecrawl = types.ModuleType("firecrawl")
    firecrawl.FirecrawlApp = type("FirecrawlApp", (), {})
    firecrawl.ScrapeOptions = type("ScrapeOptions", (), {})
    monkeypatch.setitem(sys.modules, "firecrawl", firecrawl)
    spec = importlib.util.spec_from_file_location("phase1_tutor_app", tutor_root / "app.py")
    tutor_app = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(tutor_app)
    tutor_app.sessions = tutor_app.SessionStore(tmp_path / "adaptive-sessions.sqlite3")

    assess_calls = []
    render_calls = []

    def assess(provider, objective, assessment, response):
        assess_calls.append(response)
        return {
            "objective_id": assessment["objective_id"],
            "assessment_type": assessment["assessment_type"],
            "correctness": "incorrect" if "wrong" in response.lower() else "correct",
            "completeness": "complete",
            "independence": "independent",
            "misconception_code": "task_error" if "wrong" in response.lower() else None,
            "misconception_detail": "The task contains an error." if "wrong" in response.lower() else None,
            "rationale": "Deterministic external-LLM test double.",
            "assessor_version": "test-assessor-v1",
        }

    def render(session, decision, objective, prompt, **kwargs):
        render_calls.append(decision["action"])
        if kwargs.get("student_message"):
            session.messages.append({"role": "user", "content": kwargs["student_message"]})
        session.messages.append({"role": "assistant", "content": f"{decision['action']}: {prompt}"})

    tutor_app.assess_response = assess
    tutor_app.render_adaptive_action = render
    tutor_client = TestClient(
        tutor_app.app, headers={"X-Platform-Service": "test-only-platform-service-secret"}
    )

    def call(tool, method, path, **kwargs):
        response = tutor_client.request(method, path, **kwargs)
        assert response.status_code == 200, response.text
        return response.json()

    monkeypatch.setattr(engines, "call", call)
    return assess_calls, render_calls


def send(client, roster, assignment_id, message, request_id=None):
    response = client.post(
        f"/api/platform/assignments/{assignment_id}/messages",
        headers=roster["headers"]["student"],
        json={"message": message, "request_id": request_id or str(uuid4())},
    )
    assert response.status_code == 200, response.text
    return response.json()


def start(client, roster, assignment_id):
    response = client.post(
        f"/api/platform/assignments/{assignment_id}/start",
        headers=roster["headers"]["student"],
    )
    assert response.status_code == 200, response.text
    return response.json()


def test_advanced_path_persists_evidence_progress_decisions_and_completes_task(
    client, roster, monkeypatch, tmp_path
):
    assignment = adaptive_assignment(client, roster, monkeypatch)
    assess_calls, render_calls = install_in_process_tutor(monkeypatch, tmp_path)
    state = start(client, roster, assignment["id"])
    assert state["engine_state"]["latest_decision"]["action"] == "ASSESS"

    request_id = str(uuid4())
    state = send(client, roster, assignment["id"], "strong conceptual answer", request_id)
    assert state["engine_state"]["current_assessment_id"] == "DIAG-2"
    assert state["engine_state"]["latest_decision"]["action"] == "ADVANCE"
    duplicate = send(client, roster, assignment["id"], "strong conceptual answer", request_id)
    assert duplicate["messages"] == state["messages"]
    assert len(render_calls) == 2  # initial ASSESS plus one idempotent response render

    state = send(client, roster, assignment["id"], "strong output reasoning")
    assert state["engine_state"]["current_assessment_id"] == "DIAG-3"
    assert state["engine_state"]["latest_decision"]["action"] == "ASSESS"
    state = send(client, roster, assignment["id"], "strong debugging reasoning")
    assert state["engine_state"]["current_assessment_id"] == "DIAG-4"
    state = send(client, roster, assignment["id"], "strong Student class construction")
    assert state["engine_state"]["current_assessment_id"] == "TASK-1"
    state = send(client, roster, assignment["id"], "wrong required task submission")
    assert state["required_task_status"] == "completed"
    assert "nav" not in state["engine_state"]
    assert len(assess_calls) == 5

    completed = client.post(
        f"/api/platform/assignments/{assignment['id']}/complete",
        headers=roster["headers"]["student"],
    )
    assert completed.status_code == 200, completed.text
    assert completed.json()["status"] == "completed"
    assert completed.json()["result"]["required_task_status"] == "completed"

    with store.connection() as conn:
        counts = conn.execute(
            """SELECT
                 (SELECT count(*) FROM platform_learning_evidence WHERE assignment_id=%s) AS evidence,
                 (SELECT count(*) FROM platform_adaptive_decisions d JOIN platform_attempts a ON a.id=d.attempt_id WHERE a.assignment_id=%s) AS decisions,
                 (SELECT count(*) FROM platform_objective_progress WHERE assignment_id=%s) AS progress""",
            (assignment["id"], assignment["id"], assignment["id"]),
        ).fetchone()
    assert counts == {"evidence": 5, "decisions": 6, "progress": 3}


def test_struggling_overconfident_minimum_and_curiosity_paths(client, roster, monkeypatch):
    assess_calls, _ = install_fake_tutor(monkeypatch)

    struggling = adaptive_assignment(client, roster, monkeypatch)
    start(client, roster, struggling["id"])
    first = send(client, roster, struggling["id"], "wrong answer")
    practice = send(client, roster, struggling["id"], "partial answer")
    second = send(client, roster, struggling["id"], "wrong again")
    assert first["engine_state"]["latest_decision"]["action"] == "EXPLAIN"
    assert practice["engine_state"]["latest_decision"]["action"] == "PRACTICE"
    assert second["engine_state"]["latest_decision"]["action"] == "REMEDIATE"
    with store.connection() as conn:
        support = conn.execute(
            """SELECT evidence_type,independence FROM platform_learning_evidence
               WHERE assignment_id=%s ORDER BY created_at,id""",
            (struggling["id"],),
        ).fetchall()
    assert support[1] == {"evidence_type": "guided_response", "independence": "guided"}
    assert support[2] == {"evidence_type": "practice_attempt", "independence": "supported"}

    overconfident = adaptive_assignment(client, roster, monkeypatch)
    start(client, roster, overconfident["id"])
    before = len(assess_calls)
    claim = send(client, roster, overconfident["id"], "I already know this")
    assert len(assess_calls) == before
    assert claim["engine_state"]["latest_decision"]["action"] == "ASSESS"
    assert claim["engine_state"]["objective_progress"][0]["status"] == "not_observed"

    minimum = adaptive_assignment(client, roster, monkeypatch)
    start(client, roster, minimum["id"])
    focused = send(client, roster, minimum["id"], "I only have ten minutes; give me the minimum")
    assert focused["engine_state"]["latest_decision"]["action"] == "FOCUS_REQUIRED"

    curious = adaptive_assignment(client, roster, monkeypatch)
    start(client, roster, curious["id"])
    explored = send(client, roster, curious["id"], "Can you explain inheritance?")
    decision = explored["engine_state"]["latest_decision"]
    assert decision["action"] == "EXPLAIN"
    assert decision["resume_objective_id"] == "OBJ-1"

    analytics = client.get(
        f"/api/platform/assignments/{struggling['id']}/learning-analytics",
        headers=roster["headers"]["prof"],
    )
    assert analytics.status_code == 200, analytics.text
    assert analytics.json()["misconceptions"][0]["occurrences"] == 2
    assert analytics.json()["remediation"][0]["decisions"] == 1
