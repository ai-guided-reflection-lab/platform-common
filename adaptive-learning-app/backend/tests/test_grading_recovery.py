"""Provider failures are not student failures; demo checks and recovery stay bounded."""
import copy
import json
from pathlib import Path
from types import SimpleNamespace

import httpx
import pytest

from app import lesson_flow, openai_client
from app.lesson_content import configuration_issues
from app.schemas import LearningPlan


def memory_lesson():
    return json.loads((Path(__file__).parents[1] / "lessons/operating-system-processes.json").read_text(encoding="utf-8"))


def memory_activity(plan, level="foundational"):
    return next(a for a in plan["learning_assets"][0][level] if a["concept"] == "Process Memory Layout")


@pytest.fixture
def grader(monkeypatch):
    monkeypatch.setattr(openai_client, "AI_MODE", "openai")
    monkeypatch.setattr(openai_client, "OPENAI_API_KEY", "secret-test-key")
    monkeypatch.setattr(openai_client, "ALLOW_DEMO_FALLBACK", False)
    monkeypatch.setattr(openai_client, "_runtime_fallback", False)
    plan = memory_lesson()
    activity = memory_activity(plan)
    return lambda response="Network buffer is not part of process memory.": openai_client.assess_configured_response(
        response, activity["rubric"], plan["objectives"][0], plan["approved_material"], activity["prompt"])


def provider_reply(monkeypatch, body, status=200):
    monkeypatch.setattr(httpx.Client, "post", lambda *args, **kwargs: httpx.Response(
        status, request=httpx.Request("POST", "https://api.openai.com/v1/chat/completions"), json=body))


def envelope(value):
    return {"choices": [{"message": {"content": json.dumps(value)}}]}


def test_valid_ai_assessment_is_used(grader, monkeypatch):
    provider_reply(monkeypatch, envelope({"category": "sound_reasoning", "score": 0.91, "feedback": "Specific AI feedback"}))
    assert grader("A paraphrase without the demo evidence phrases") == {
        "status": "assessed", "source": "ai", "category": "sound_reasoning", "score": 0.91, "feedback": "Specific AI feedback"}


@pytest.mark.parametrize("status", [401, 403, 429, 500])
def test_provider_failure_is_unavailable_without_secret_logging(grader, monkeypatch, caplog, status):
    provider_reply(monkeypatch, {"error": {"code": "invalid_api_key", "message": "secret-test-key"}}, status)
    result = grader()
    assert result["status"] == result["category"] == "grader_unavailable"
    assert result["score"] is None
    assert "not been marked incorrect" in result["feedback"]
    assert "secret-test-key" not in json.dumps(result) + caplog.text
    assert f"http_status={status}" in caplog.text
    assert "source" not in result  # Even a phrase-matching response must not be graded.


def test_timeout_is_controlled(grader, monkeypatch, caplog):
    def timeout(*args, **kwargs):
        raise httpx.ReadTimeout("secret-test-key")
    monkeypatch.setattr(httpx.Client, "post", timeout)
    assert grader()["status"] == "grader_unavailable"
    assert "ReadTimeout" in caplog.text and "secret-test-key" not in caplog.text


@pytest.mark.parametrize("body", [
    {}, {"choices": []}, {"choices": [None]}, {"choices": [{}]},
    {"choices": [{"message": None}]}, {"choices": [{"message": {}}]},
    {"choices": [{"message": {"content": None}}]},
    {"choices": [{"message": {"content": "not JSON"}}]},
    envelope([]), envelope({"category": "invalid", "score": 1, "feedback": "ok"}),
    envelope({"category": [], "score": 1, "feedback": "ok"}),
    envelope({"category": "sound_reasoning", "feedback": "ok"}),
    *[envelope({"category": "sound_reasoning", "score": score, "feedback": "ok"})
      for score in (-1, 2, None, True, "bad", [], float("nan"), float("inf"))],
    envelope({"category": "sound_reasoning", "score": 1}),
    envelope({"category": "sound_reasoning", "score": 1, "feedback": {}}),
])
def test_malformed_ai_response_is_controlled(grader, monkeypatch, body):
    provider_reply(monkeypatch, body)
    result = grader()
    assert result["status"] == result["category"] == "grader_error"
    assert result["score"] is None


def test_malformed_provider_envelope_json_is_controlled(grader, monkeypatch):
    monkeypatch.setattr(httpx.Client, "post", lambda *args, **kwargs: httpx.Response(
        200, request=httpx.Request("POST", "https://example.invalid"), text="not JSON"))
    assert grader()["status"] == "grader_error"


def test_missing_credentials_and_global_fallback_are_not_demo(grader, monkeypatch):
    monkeypatch.setattr(openai_client, "OPENAI_API_KEY", "")
    assert grader()["status"] == "grader_unavailable"
    monkeypatch.setattr(openai_client, "OPENAI_API_KEY", "secret-test-key")
    monkeypatch.setattr(openai_client, "_runtime_fallback", True)
    assert grader()["status"] == "grader_unavailable"


def test_student_insufficient_evidence_is_distinct(grader, monkeypatch):
    provider_reply(monkeypatch, envelope({"category": "insufficient_evidence", "score": 0, "feedback": "Please explain the distinction."}))
    assert grader()["status"] == "student_insufficient_evidence"
    assert grader("")["status"] == "student_insufficient_evidence"


@pytest.mark.parametrize("response", [
    "Network buffer is not part of the process memory layout because code, data, and heap are process memory sections.",
    "Network buffer is not part of process memory; it is managed separately by the OS/hardware.",
    "Code, data, and heap are process memory, while the network buffer is separate.",
    "Network buffer is the intended answer because code, data, and heap are standard sections of a process’s memory layout, while network buffers are not a standard section.",
    "Network buffer is not part of the process memory layout in this example. Code stores instructions, data stores variables, and the heap stores dynamically allocated memory, while the network buffer is managed separately by the OS or hardware.",
    "The network buffer belongs outside these process memory sections.",
    "A network buffer isn't part of process memory; the operating system manages it separately.",
])
def test_demo_memory_evidence_accepts_paraphrases(grader, monkeypatch, response):
    monkeypatch.setattr(openai_client, "AI_MODE", "demo")
    result = grader(response)
    assert result["category"] == "sound_reasoning"
    assert result["source"] == "demo_rubric"
    assert "limited phrase matching" in result["feedback"]


@pytest.mark.parametrize("response", [
    "code, data, heap are process memory", "Network buffer is part of process memory.",
    "Heap is not part of process memory.", "Network buffer.",
])
def test_demo_memory_requires_identifying_excluded_buffer(grader, monkeypatch, response):
    monkeypatch.setattr(openai_client, "AI_MODE", "demo")
    assert grader(response)["category"] != "sound_reasoning"


def test_memory_activities_test_memory_not_process_states():
    plan = memory_lesson()
    LearningPlan.model_validate(plan)
    assert configuration_issues({**plan, "content_approved": True}) == []
    assert not plan["content_approved"]
    for asset in plan["learning_assets"]:
        for level in ("foundational", "standard", "accelerated"):
            for activity in asset[level]:
                if activity["concept"] == "Process Memory Layout":
                    assert "heap" in json.dumps(activity["rubric"]).lower() or "network buffer" in activity["prompt"].lower()
                    assert not any(term in activity["prompt"].lower() for term in ("ready queue", "blocked", "scheduler", "disk read"))
    standard = memory_activity(plan, "standard")
    accelerated = memory_activity(plan, "accelerated")
    assert "four process memory sections" in standard["prompt"]
    assert "heap rather than" in accelerated["prompt"]
    objective = plan["objectives"][0]
    for activity, response in [
        (standard, "Code stores instructions; data stores global/static variables; heap is for dynamically allocated memory; stack stores function call information."),
        (accelerated, "The heap holds dynamically allocated memory. The stack contains function call information and is associated with returns. Code holds instructions and data holds the global configuration."),
    ]:
        assert openai_client._assess_local_rubric(response, activity["rubric"], objective)["category"] == "sound_reasoning"
        assert openai_client._assess_local_rubric("The process moves ready to running, then blocked and back to ready.", activity["rubric"], objective)["category"] != "sound_reasoning"


def practice_state():
    plan = memory_lesson()
    state = lesson_flow.initial_state(plan)
    state.update(target_objective="OBJ1", target_concept="Process Memory Layout", current_paths={"OBJ1": "standard"})
    lesson_flow.next_activity(plan, state, "OBJ1", "foundational")
    return plan, state


@pytest.mark.parametrize("exhausted", [False, True])
def test_three_revisions_recover_without_mastery(monkeypatch, exhausted):
    monkeypatch.setattr(openai_client, "AI_MODE", "demo")
    plan, state = practice_state()
    original_id = state["activity"]["id"]
    state["depth_checks"] = 1
    if exhausted:
        state["used_activities"] = [f"OBJ1:{level}:{index}" for level in ("foundational", "standard", "accelerated")
            for index, activity in enumerate(plan["learning_assets"][0][level]) if activity["concept"] == "Process Memory Layout"]
    for revision in range(lesson_flow.MAX_PRACTICE_REVISIONS):
        reply, record = lesson_flow.handle_practice(plan, state, SimpleNamespace(action="message", content="I think the code section is excluded."))
        if revision < lesson_flow.MAX_PRACTICE_REVISIONS - 1:
            assert state["activity"]["id"] == original_id
    assert "Worked example:" in reply
    assert record["substantial_support"] and not record["demonstrated"]
    assert state["demonstrated"] == [] and state["depth_checks"] == 0
    if exhausted:
        assert state["stage"] == "learning_choice" and state["choices"] == lesson_flow.CHOICES
        assert state["activity"] is None
    else:
        assert state["activity"]["id"] != original_id and not state["activity"]["assisted"]


def test_grader_failure_preserves_snapshot_and_does_not_count_as_revision(monkeypatch):
    plan, state = practice_state()
    snapshot = copy.deepcopy(state["lesson_snapshot"])
    monkeypatch.setattr(lesson_flow, "assess_configured_response", lambda *args: openai_client._assessment_issue("grader_unavailable"))
    reply, evidence = lesson_flow.handle_practice(plan, state, SimpleNamespace(action="message", content="My answer"))
    assert evidence is None and state["practice_history"][-1]["score"] is None
    assert state["practice_history"][-1]["revision"] == 0
    assert state["used_activities"] == [] and state["demonstrated"] == []
    assert state["stage"] == "learning_choice" and "not been marked incorrect" in reply
    assert state["lesson_snapshot"] == snapshot


def test_missing_demo_evidence_is_grader_unavailable(monkeypatch):
    monkeypatch.setattr(openai_client, "AI_MODE", "demo")
    result = openai_client.assess_configured_response("An answer", [{"description": "Explain it", "evidence_groups": []}], {}, "", "")
    assert result["status"] == "grader_unavailable" and result["score"] is None
