"""Coverage and diagnostic support must survive format choices and saved state."""
from types import SimpleNamespace
from contextlib import contextmanager
import json

import pytest

from app import lesson_flow
from test_grading_recovery import practice_state


def test_two_cases_complete_only_their_concept(monkeypatch):
    plan, state = practice_state()
    monkeypatch.setattr(lesson_flow, "assess_configured_response", lambda *args: {
        "category": "sound_reasoning", "score": 1, "feedback": "Supported reasoning"})
    monkeypatch.setattr(lesson_flow, "tutor_reply", lambda *args: args[-1])
    for index in range(2):
        lesson_flow.handle_practice(plan, state, SimpleNamespace(action="message", content=f"Independent scenario reasoning {index}"))
    assert state["concept_checks"]["OBJ1"]["Process Memory Layout"] == 2
    assert "Process Memory Layout" in state["demonstrated_concepts"]
    assert "OBJ1" not in state["demonstrated"]
    assert state["stage"] == "reflection"


def test_saved_coverage_requires_distinct_unassisted_cases():
    plan, state = practice_state()
    state["demonstrated"] = ["OBJ1"]  # Old broad completion is reconciled.
    state["practice_history"] = [
        {"objective_id": "OBJ1", "concept": "Process Memory Layout", "activity_id": "same", "demonstrated": True},
        {"objective_id": "OBJ1", "concept": "Process Memory Layout", "activity_id": "same", "demonstrated": True},
        {"objective_id": "OBJ1", "concept": "Process Memory Layout", "activity_id": "hinted", "demonstrated": True, "assisted": True},
    ]
    lesson_flow.refresh_concept_progress(plan, state)
    assert state["concept_checks"]["OBJ1"]["Process Memory Layout"] == 1
    assert state["demonstrated"] == []
    for question in plan["diagnostic_quiz"]:
        if question["objective_id"] == "OBJ1":
            for index in range(2):
                state["practice_history"].append({"objective_id": "OBJ1", "concept": question["concept"],
                    "activity_id": f"{question['id']}:{index}", "demonstrated": True})
    lesson_flow.refresh_concept_progress(plan, state)
    assert "OBJ1" in state["demonstrated"]


@pytest.mark.parametrize("choice", lesson_flow.CHOICES)
@pytest.mark.parametrize("need,marker,assisted", [
    ("counterexample_revision", "Counterexample:", True),
    ("reasoning_probe", "explain the relationship", False),
    ("confidence_building", "reported low confidence", False),
])
def test_required_support_precedes_every_format(choice, need, marker, assisted):
    plan, state = practice_state()
    question = next(q for q in plan["diagnostic_quiz"] if q["concept"] == state["target_concept"])
    state["diagnostic"] = [{"question_id": question["id"], "need": need}]
    reply = lesson_flow.handle_choice(plan, state, choice)
    assert marker in reply
    assert state["activity"]["assisted"] is assisted
    assert state["selected_format"] == choice
    assert state["selected_followup"] == need
    assert state["diagnostic_followups_delivered"] == [question["id"]]


def test_shared_progress_does_not_promote_one_success(monkeypatch):
    from app import main
    plan, state = practice_state()
    state["practice_history"] = [{"objective_id": "OBJ1", "concept": "Process Memory Layout",
        "activity_id": "one-case", "demonstrated": True}]
    @contextmanager
    def connection():
        yield None
    monkeypatch.setattr(main, "connection", connection)
    monkeypatch.setattr(main, "load_attempt_progress_data", lambda *args: [
        {"objective_id": "OBJ1", "demonstrated": True, "score": 1, "rationale": "One successful case"}])
    monkeypatch.setattr(main, "load_attempt_learning_state", lambda *args: {"learning_state": json.dumps(state)})
    progress = main._objective_progress("attempt", plan)
    assert next(item for item in progress if item["objective_id"] == "OBJ1")["status"] == "in_progress"
