from app import lesson_flow, main
from test_api import client, create, headers, lesson, start_quiz, quiz


def analytics_state():
    plan = lesson()
    state = lesson_flow.initial_state(plan)
    question = plan["diagnostic_quiz"][0]
    return plan, state, question


def test_unassessed_and_correct_selection_are_not_mastery():
    plan, state, question = analytics_state()
    assert all(item["status"] == "not_assessed" for item in main._concept_analytics(plan, state))
    state.update(diagnostic_complete=True, diagnostic=[{**question, "correct": True}])
    concept = next(item for item in main._concept_analytics(plan, state) if item["concept"] == question["concept"])
    assert concept["status"] == "developing" and concept["independent_checks"] == 0


def test_improvement_resolves_original_gap_and_summary_uses_current_evidence():
    plan, state, question = analytics_state()
    state.update(diagnostic_complete=True, diagnostic=[{**question, "correct": False, "confidence": "high", "misconception": "An earlier incorrect idea"}])
    records = [{"objective_id": question["objective_id"], "concept": question["concept"], "activity_id": f"fresh:{index}", "demonstrated": True,
        "category": "sound_reasoning", "response": f"Fresh reasoning {index}", "rationale": "Sound scenario reasoning", "assessment_source": "ai"} for index in range(2)]
    state["practice_history"] = records
    concepts = main._concept_analytics(plan, state)
    concept = next(item for item in concepts if item["concept"] == question["concept"])
    assert concept["status"] == "demonstrated" and concept["independent_checks"] == 2
    assert concept["earlier_misconceptions"] == ["An earlier incorrect idea"]
    summary = main._student_summary({"display_name": "Alex"}, {"quiz_score": 4, "learning_state": {"reflections": []}}, [], [], concepts)
    assert any(question["concept"] in item for item in summary["strengths"])
    assert not any(question["concept"] in item for item in summary["weaknesses"])


def test_supported_success_and_grader_failure_do_not_claim_understanding():
    plan, state, question = analytics_state()
    state["practice_history"] = [{"objective_id": question["objective_id"], "concept": question["concept"], "activity_id": "supported",
        "demonstrated": False, "assisted": True, "category": "sound_reasoning", "response": "Supported response", "rationale": "Sound with assistance"}]
    concept = main._concept_analytics(plan, state)[0]
    assert concept["status"] == "developing" and concept["independent_checks"] == 0 and concept["assisted_responses"] == 1
    state["practice_history"] = [{"objective_id": question["objective_id"], "concept": question["concept"], "activity_id": "unavailable",
        "demonstrated": False, "category": "grader_unavailable", "assessment_status": "grader_unavailable", "rationale": "Provider unavailable"}]
    concept = main._concept_analytics(plan, state)[0]
    assert concept["status"] == "not_assessed" and concept["grader_issue"] == "Provider unavailable"


def test_later_misconception_is_visible_even_after_earlier_successes():
    plan, state, question = analytics_state()
    state["practice_history"] = [{"objective_id": question["objective_id"], "concept": question["concept"],
        "activity_id": f"case:{index}", "demonstrated": True, "category": "sound_reasoning"} for index in range(2)]
    state["practice_history"].append({"objective_id": question["objective_id"], "concept": question["concept"],
        "activity_id": "new-error", "demonstrated": False, "category": "identifiable_misconception", "rationale": "A newly expressed misconception"})
    concept = main._concept_analytics(plan, state)[0]
    assert concept["independent_checks"] == 2
    assert concept["status"] == "needs_support"
    assert concept["next_action"] == "A newly expressed misconception"


def test_progress_and_student_detail_expose_concept_coverage_without_private_snapshot(client):
    aid = create(client)
    progress = client.get(f"/api/instructor/assignments/{aid}/progress", headers=headers("instructor-demo")).json()
    assert progress[0]["concept_analytics"] and "learning_state" not in progress[0]
    assert all(item["status"] == "not_assessed" for item in progress[0]["concept_analytics"])
    plan = lesson()
    start_quiz(client, aid)
    quiz(client, aid, plan)
    result = client.get(f"/api/instructor/assignments/{aid}/students/student-alex", headers=headers("instructor-demo"))
    assert result.status_code == 200
    assert result.json()["concept_analytics"]
    assert "student_explanation" in result.json()["quiz_results"][-1]
    assert "concepts" in result.json()["summary"]["overview"]
