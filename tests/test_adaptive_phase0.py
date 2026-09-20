from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from platform_app.adaptive import (
    PolicyContext,
    choose_adaptive_action,
    derive_objective_progress,
    effective_independence,
    summarize_class_objective,
)
from platform_app.schemas import (
    AdaptiveAction,
    AssessmentType,
    AttemptLearningState,
    CompletenessState,
    CorrectnessState,
    EvidenceType,
    IndependenceLevel,
    LearningEvidence,
    LearningPlan,
    LearningObjective,
    ObjectiveStatus,
    RequiredTaskStatus,
    TutorConfig,
)


NOW = datetime(2026, 1, 1, tzinfo=timezone.utc)


def evidence(
    kind: EvidenceType,
    *,
    correctness: CorrectnessState,
    completeness: CompletenessState = CompletenessState.COMPLETE,
    independence: IndependenceLevel = IndependenceLevel.INDEPENDENT,
    hints: int = 0,
    assessment: AssessmentType | None = AssessmentType.CONCEPTUAL,
    misconception: str | None = None,
) -> LearningEvidence:
    return LearningEvidence(
        student_id="student-1",
        course_id="course-1",
        assignment_id="assignment-1",
        attempt_id="attempt-1",
        objective_id="OBJ-1",
        concept_id="classes_objects",
        evidence_type=kind,
        assessment_type=assessment,
        response="Observable student response",
        correctness=correctness,
        completeness=completeness,
        independence=independence,
        hints_used=hints,
        misconception_code=misconception,
        assessor_version="test-assessor-v1",
        created_at=NOW,
    )


def objective(*demonstration_types: AssessmentType) -> LearningObjective:
    allowed = list(dict.fromkeys([AssessmentType.CONCEPTUAL, *demonstration_types]))
    return LearningObjective(
        id="OBJ-1",
        concept_id="classes_objects",
        description="Explain and apply the difference between classes and objects.",
        assessment_types=allowed,
        demonstration_assessment_types=list(demonstration_types),
    )


def progress(items, *demonstration_types):
    return derive_objective_progress(objective(*demonstration_types), items)


def oop_plan() -> dict:
    return {
        "title": "Object-Oriented Programming",
        "course_context": "SE 101",
        "assignment_context": "Today's learning plan",
        "concepts": [
            {"id": "classes_objects", "name": "Classes and objects"},
            {
                "id": "object_interactions",
                "name": "Object interactions",
                "prerequisite_ids": ["classes_objects"],
            },
        ],
        "objectives": [
            {
                "id": "OBJ-1",
                "concept_id": "classes_objects",
                "description": "Explain the difference between a class and an object.",
                "required": True,
                "assessment_types": ["conceptual", "application_scenario"],
                "demonstration_assessment_types": ["application_scenario"],
            },
            {
                "id": "OBJ-2",
                "concept_id": "classes_objects",
                "description": "Create a class containing attributes and methods.",
                "required": True,
                "assessment_types": ["code_construction", "debugging"],
                "demonstration_assessment_types": ["code_construction"],
            },
            {
                "id": "OBJ-3",
                "concept_id": "object_interactions",
                "description": "Debug and reason about object interactions.",
                "required": False,
                "assessment_types": ["debugging", "application_scenario"],
                "demonstration_assessment_types": ["debugging"],
            },
        ],
        "required_task": {
            "id": "TASK-1",
            "title": "BankAccount",
            "description": "Implement a BankAccount class.",
            "objective_ids": ["OBJ-1", "OBJ-2"],
        },
        "approved_resources": [
            {"id": "oop-lecture", "title": "OOP lecture", "document_id": "doc-1"}
        ],
        "scope_notes": "Inheritance is optional preview material.",
    }


def test_learning_plan_extends_existing_tutor_config_without_replacing_topic():
    plan = LearningPlan.model_validate(oop_plan())
    config = TutorConfig(learning_plan=plan, provider="openai")
    assert config.learning_plan.objectives[1].id == "OBJ-2"
    assert config.topic is None


def test_evidence_contract_rejects_false_precision():
    with pytest.raises(ValidationError):
        evidence(EvidenceType.DIAGNOSTIC_RESPONSE, correctness=0.8)  # type: ignore[arg-type]


def test_only_objective_approved_assessment_types_can_demonstrate():
    debugging = evidence(
        EvidenceType.DIAGNOSTIC_RESPONSE,
        correctness=CorrectnessState.CORRECT,
        assessment=AssessmentType.DEBUGGING,
    )
    assert progress([debugging], AssessmentType.CODE_CONSTRUCTION).status == ObjectiveStatus.DEVELOPING
    assert progress([debugging], AssessmentType.DEBUGGING).status == ObjectiveStatus.DEMONSTRATED


def test_self_report_does_not_establish_mastery():
    item = evidence(EvidenceType.SELF_REPORT, correctness=CorrectnessState.CORRECT)
    assert progress([item]).status == ObjectiveStatus.NOT_OBSERVED


def test_diagnostic_evidence_changes_the_adaptive_path():
    initial = progress([])
    weak = evidence(EvidenceType.DIAGNOSTIC_RESPONSE, correctness=CorrectnessState.INCORRECT)
    after = progress([weak])
    assert choose_adaptive_action(PolicyContext("OBJ-1", initial)).action == AdaptiveAction.ASSESS
    assert choose_adaptive_action(PolicyContext("OBJ-1", after)).action == AdaptiveAction.FOCUS_REQUIRED


def test_guided_success_is_developing_not_demonstrated():
    item = evidence(
        EvidenceType.GUIDED_RESPONSE,
        correctness=CorrectnessState.CORRECT,
        independence=IndependenceLevel.GUIDED,
    )
    assert progress([item]).status == ObjectiveStatus.DEVELOPING


def test_successful_independent_application_can_demonstrate_mastery():
    item = evidence(
        EvidenceType.INDEPENDENT_APPLICATION,
        correctness=CorrectnessState.CORRECT,
        assessment=AssessmentType.CODE_CONSTRUCTION,
    )
    assert progress([item], AssessmentType.CODE_CONSTRUCTION).status == ObjectiveStatus.DEMONSTRATED


def test_conceptual_explanation_alone_is_not_full_coding_mastery():
    item = evidence(
        EvidenceType.DIAGNOSTIC_RESPONSE,
        correctness=CorrectnessState.CORRECT,
        assessment=AssessmentType.CONCEPTUAL,
    )
    assert progress([item], AssessmentType.CODE_CONSTRUCTION).status == ObjectiveStatus.DEVELOPING


def test_repeated_incorrect_evidence_triggers_remediation():
    items = tuple(
        evidence(
            EvidenceType.DIAGNOSTIC_RESPONSE,
            correctness=CorrectnessState.INCORRECT,
            misconception="class_is_instance",
        )
        for _ in range(2)
    )
    state = progress(list(items))
    decision = choose_adaptive_action(PolicyContext("OBJ-1", state, evidence=items))
    assert state.status == ObjectiveStatus.NEEDS_REVIEW
    assert decision.action == AdaptiveAction.REMEDIATE
    assert decision.reason_codes == ["repeated_misconception"]


def test_repeated_incorrect_evidence_without_a_label_still_triggers_remediation():
    items = tuple(
        evidence(EvidenceType.PRACTICE_ATTEMPT, correctness=CorrectnessState.INCORRECT)
        for _ in range(2)
    )
    decision = choose_adaptive_action(
        PolicyContext("OBJ-1", progress(list(items)), evidence=items)
    )
    assert decision.action == AdaptiveAction.REMEDIATE
    assert decision.reason_codes == ["repeated_incorrect_evidence"]


def test_hints_reduce_independence_without_making_answer_incorrect():
    item = evidence(
        EvidenceType.INDEPENDENT_APPLICATION,
        correctness=CorrectnessState.CORRECT,
        independence=IndependenceLevel.INDEPENDENT,
        hints=2,
        assessment=AssessmentType.CODE_CONSTRUCTION,
    )
    assert item.correctness == CorrectnessState.CORRECT
    assert effective_independence(item) == IndependenceLevel.GUIDED
    assert progress([item], AssessmentType.CODE_CONSTRUCTION).status == ObjectiveStatus.DEVELOPING


def test_completion_can_be_true_while_mastery_is_not_demonstrated():
    developing = progress([
        evidence(EvidenceType.GUIDED_RESPONSE, correctness=CorrectnessState.CORRECT)
    ])
    state = AttemptLearningState(
        assignment_completed=True,
        required_task_status=RequiredTaskStatus.COMPLETED,
        objectives=[developing],
    )
    assert state.assignment_completed is True
    assert state.required_task_status == RequiredTaskStatus.COMPLETED
    assert state.objectives[0].status == ObjectiveStatus.DEVELOPING


def test_policy_is_deterministic():
    context = PolicyContext("OBJ-1", progress([]))
    assert choose_adaptive_action(context) == choose_adaptive_action(context)


def test_advanced_and_struggling_students_receive_different_paths():
    strong = evidence(
        EvidenceType.DIAGNOSTIC_RESPONSE,
        correctness=CorrectnessState.CORRECT,
        assessment=AssessmentType.APPLICATION_SCENARIO,
    )
    weak = evidence(EvidenceType.DIAGNOSTIC_RESPONSE, correctness=CorrectnessState.INCORRECT)
    advanced = choose_adaptive_action(
        PolicyContext(
            "OBJ-1",
            progress([strong], AssessmentType.APPLICATION_SCENARIO),
            evidence=(strong,),
            prefer_challenge=True,
        )
    )
    struggling = choose_adaptive_action(
        PolicyContext("OBJ-1", progress([weak]), evidence=(weak,), student_stuck=True)
    )
    assert advanced.action == AdaptiveAction.CHALLENGE
    assert struggling.action == AdaptiveAction.HINT


def test_overconfident_self_report_cannot_bypass_diagnostic_evidence():
    claim = evidence(EvidenceType.SELF_REPORT, correctness=CorrectnessState.CORRECT)
    weak = evidence(EvidenceType.DIAGNOSTIC_RESPONSE, correctness=CorrectnessState.INCORRECT)
    state = progress([claim, weak])
    assert state.status == ObjectiveStatus.EMERGING
    assert choose_adaptive_action(PolicyContext("OBJ-1", state, evidence=(claim, weak))).action != AdaptiveAction.ADVANCE


def test_student_cannot_request_advance_without_evidence():
    decision = choose_adaptive_action(
        PolicyContext("OBJ-1", progress([]), requested_action=AdaptiveAction.ADVANCE)
    )
    assert decision.action == AdaptiveAction.ASSESS


def test_minimum_effort_request_focuses_required_work_without_waiving_requirements():
    decision = choose_adaptive_action(
        PolicyContext("OBJ-1", progress([]), minimum_path_requested=True)
    )
    assert decision.action == AdaptiveAction.FOCUS_REQUIRED
    assert "requirements_still_apply" in decision.reason_codes


def test_curiosity_gets_scoped_explanation_then_returns_to_required_objective():
    decision = choose_adaptive_action(
        PolicyContext("OBJ-1", progress([]), scoped_exploration_requested=True)
    )
    assert decision.action == AdaptiveAction.EXPLAIN
    assert decision.resume_objective_id == "OBJ-1"
    assert "return_to_required_objective" in decision.reason_codes


def test_class_analytics_aggregate_learning_signals_without_student_ranking():
    strong = evidence(
        EvidenceType.INDEPENDENT_APPLICATION,
        correctness=CorrectnessState.CORRECT,
        assessment=AssessmentType.CODE_CONSTRUCTION,
    )
    misses = [
        evidence(
            EvidenceType.DIAGNOSTIC_RESPONSE,
            correctness=CorrectnessState.INCORRECT,
            misconception="class_is_instance",
        )
        for _ in range(2)
    ]
    demonstrated = progress([strong], AssessmentType.CODE_CONSTRUCTION)
    needs_review = progress(misses)
    remediation = choose_adaptive_action(
        PolicyContext("OBJ-1", needs_review, evidence=tuple(misses))
    )
    summary = summarize_class_objective(
        "OBJ-1",
        "classes_objects",
        [demonstrated, needs_review],
        [strong, *misses],
        [remediation],
    )
    assert summary.status_counts[ObjectiveStatus.DEMONSTRATED] == 1
    assert summary.status_counts[ObjectiveStatus.NEEDS_REVIEW] == 1
    assert summary.common_misconceptions["class_is_instance"] == 2
    assert summary.remediation_count == 1
    assert summary.independent_demonstration_count == 1
