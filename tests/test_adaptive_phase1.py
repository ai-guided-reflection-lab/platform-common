from platform_app.adaptive import (
    PolicyContext,
    bounded_response_independence,
    choose_adaptive_action,
    is_phase1_oop_plan,
    oop_learning_plan,
)
from platform_app.schemas import (
    AdaptiveAction,
    AssessmentType,
    IndependenceLevel,
    ObjectiveProgress,
    ObjectiveStatus,
)


def progress(status=ObjectiveStatus.NOT_OBSERVED):
    return ObjectiveProgress(objective_id="OBJ-1", concept_id="classes", status=status)


def test_seeded_oop_plan_has_objective_specific_demonstrations_and_bank_account_task():
    plan = oop_learning_plan()
    objectives = {item.id: item for item in plan.objectives}

    assert objectives["OBJ-1"].demonstration_assessment_types == [
        AssessmentType.CONCEPTUAL,
        AssessmentType.APPLICATION_SCENARIO,
    ]
    assert AssessmentType.CODE_CONSTRUCTION in objectives["OBJ-2"].demonstration_assessment_types
    assert AssessmentType.CODE_OUTPUT not in objectives["OBJ-3"].demonstration_assessment_types
    assert AssessmentType.DEBUGGING in objectives["OBJ-3"].demonstration_assessment_types
    assert plan.required_task.id == "TASK-1"
    assert "BankAccount" in plan.required_task.description
    assert is_phase1_oop_plan(plan)

    changed = plan.model_copy(deep=True)
    changed.title = "A different plan"
    assert not is_phase1_oop_plan(changed)


def test_supported_actions_cannot_be_recorded_as_independent_evidence():
    assert bounded_response_independence(
        IndependenceLevel.INDEPENDENT, AdaptiveAction.EXPLAIN
    ) == IndependenceLevel.GUIDED
    assert bounded_response_independence(
        IndependenceLevel.INDEPENDENT, AdaptiveAction.REMEDIATE
    ) == IndependenceLevel.GUIDED
    assert bounded_response_independence(
        IndependenceLevel.INDEPENDENT, AdaptiveAction.PRACTICE
    ) == IndependenceLevel.SUPPORTED
    assert bounded_response_independence(
        IndependenceLevel.INDEPENDENT, AdaptiveAction.ASSESS
    ) == IndependenceLevel.INDEPENDENT


def test_policy_paths_keep_application_in_control():
    assert choose_adaptive_action(
        PolicyContext("OBJ-1", progress(), continue_assessment=True)
    ).action == AdaptiveAction.ASSESS
    assert choose_adaptive_action(
        PolicyContext("OBJ-1", progress(), needs_explanation=True)
    ).action == AdaptiveAction.EXPLAIN
    assert choose_adaptive_action(
        PolicyContext("OBJ-1", progress(), needs_practice=True)
    ).action == AdaptiveAction.PRACTICE
    assert choose_adaptive_action(
        PolicyContext("OBJ-1", progress(), minimum_path_requested=True)
    ).action == AdaptiveAction.FOCUS_REQUIRED

    exploration = choose_adaptive_action(
        PolicyContext("OBJ-1", progress(), scoped_exploration_requested=True)
    )
    assert exploration.action == AdaptiveAction.EXPLAIN
    assert exploration.resume_objective_id == "OBJ-1"


def test_mastery_and_required_task_completion_remain_separate_states():
    not_mastered = progress(ObjectiveStatus.NEEDS_REVIEW)
    decision = choose_adaptive_action(
        PolicyContext("OBJ-1", not_mastered, required_work_remaining=False)
    )
    assert decision.action == AdaptiveAction.PRACTICE
