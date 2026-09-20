"""Deterministic Phase 0 contracts for adaptive self-directed learning.

This module deliberately contains no conversational generation and no model
calls.  It converts observable evidence into objective progress and chooses a
structured next action that the tutor can render in Phase 1.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass

from platform_app.schemas import (
    AdaptiveAction,
    AdaptiveDecision,
    ClassObjectiveAnalytics,
    CompletenessState,
    CorrectnessState,
    EvidenceType,
    IndependenceLevel,
    LearningEvidence,
    LearningPlan,
    LearningObjective,
    ObjectiveProgress,
    ObjectiveStatus,
)


POLICY_VERSION = "adaptive-sdl-v1"
REMEDIATION_FAILURE_COUNT = 2

STUDENT_REQUESTABLE_ACTIONS = {
    AdaptiveAction.ASSESS,
    AdaptiveAction.EXPLAIN,
    AdaptiveAction.HINT,
    AdaptiveAction.PRACTICE,
    AdaptiveAction.CHALLENGE,
    AdaptiveAction.FOCUS_REQUIRED,
}


def effective_independence(evidence: LearningEvidence) -> IndependenceLevel:
    """Downgrade independence categorically when hints were used."""
    levels = [
        IndependenceLevel.GUIDED,
        IndependenceLevel.SUPPORTED,
        IndependenceLevel.INDEPENDENT,
    ]
    base = levels.index(evidence.independence)
    return levels[max(0, base - min(evidence.hints_used, 2))]


def bounded_response_independence(
    independence: IndependenceLevel,
    previous_action: AdaptiveAction | None,
) -> IndependenceLevel:
    """Prevent supported tutor turns from becoming independent evidence."""
    levels = [
        IndependenceLevel.GUIDED,
        IndependenceLevel.SUPPORTED,
        IndependenceLevel.INDEPENDENT,
    ]
    caps = {
        AdaptiveAction.EXPLAIN: IndependenceLevel.GUIDED,
        AdaptiveAction.REMEDIATE: IndependenceLevel.GUIDED,
        AdaptiveAction.PRACTICE: IndependenceLevel.SUPPORTED,
    }
    cap = caps.get(previous_action)
    if cap is None:
        return independence
    return levels[min(levels.index(independence), levels.index(cap))]


def _is_success(evidence: LearningEvidence) -> bool:
    return (
        evidence.correctness == CorrectnessState.CORRECT
        and evidence.completeness != CompletenessState.INCOMPLETE
    )


def _is_demonstration(evidence: LearningEvidence, objective: LearningObjective) -> bool:
    if evidence.evidence_type == EvidenceType.SELF_REPORT:
        return False
    return (
        evidence.assessment_type in objective.demonstration_assessment_types
        and evidence.correctness == CorrectnessState.CORRECT
        and evidence.completeness == CompletenessState.COMPLETE
        and effective_independence(evidence) == IndependenceLevel.INDEPENDENT
    )


def derive_objective_progress(
    objective: LearningObjective,
    evidence_items: list[LearningEvidence],
) -> ObjectiveProgress:
    """Derive a transparent status; assignment completion is not an input."""
    relevant = [item for item in evidence_items if item.objective_id == objective.id]
    observable = [item for item in relevant if item.evidence_type != EvidenceType.SELF_REPORT]
    independent = [item for item in observable if _is_demonstration(item, objective)]
    incorrect = [item for item in observable if item.correctness == CorrectnessState.INCORRECT]
    misconceptions = Counter(
        item.misconception_code for item in incorrect if item.misconception_code
    )

    if independent:
        status = ObjectiveStatus.DEMONSTRATED
    elif any(count >= REMEDIATION_FAILURE_COUNT for count in misconceptions.values()):
        status = ObjectiveStatus.NEEDS_REVIEW
    elif len(incorrect) >= REMEDIATION_FAILURE_COUNT:
        status = ObjectiveStatus.NEEDS_REVIEW
    elif any(_is_success(item) for item in observable):
        status = ObjectiveStatus.DEVELOPING
    elif observable:
        status = ObjectiveStatus.EMERGING
    else:
        status = ObjectiveStatus.NOT_OBSERVED

    return ObjectiveProgress(
        objective_id=objective.id,
        concept_id=objective.concept_id,
        status=status,
        evidence_count=len(relevant),
        independent_evidence_count=len(independent),
        attempts=len(observable),
        hints_used=sum(item.hints_used for item in relevant),
        last_updated_at=max((item.created_at for item in relevant), default=None),
    )


@dataclass(frozen=True)
class PolicyContext:
    objective_id: str
    progress: ObjectiveProgress
    evidence: tuple[LearningEvidence, ...] = ()
    requested_action: AdaptiveAction | None = None
    request_in_scope: bool = True
    student_stuck: bool = False
    needs_explanation: bool = False
    needs_practice: bool = False
    continue_assessment: bool = False
    required_work_remaining: bool = True
    prefer_challenge: bool = False
    minimum_path_requested: bool = False
    scoped_exploration_requested: bool = False


def _has_repeated_misconception(evidence: tuple[LearningEvidence, ...]) -> bool:
    codes = Counter(
        item.misconception_code
        for item in evidence
        if item.correctness == CorrectnessState.INCORRECT and item.misconception_code
    )
    return any(count >= REMEDIATION_FAILURE_COUNT for count in codes.values())


def _has_repeated_failure(evidence: tuple[LearningEvidence, ...]) -> bool:
    return sum(
        item.evidence_type != EvidenceType.SELF_REPORT
        and item.correctness == CorrectnessState.INCORRECT
        for item in evidence
    ) >= REMEDIATION_FAILURE_COUNT


def choose_adaptive_action(context: PolicyContext) -> AdaptiveDecision:
    """Select an action using application-owned, deterministic priorities."""
    def decision(action: AdaptiveAction, *reasons: str, resume: str | None = None):
        return AdaptiveDecision(
            action=action,
            objective_id=context.objective_id,
            reason_codes=list(reasons),
            policy_version=POLICY_VERSION,
            resume_objective_id=resume,
        )

    # A minimum-path request is an allowed request, but it focuses rather than
    # waives required evidence or task requirements.
    if context.minimum_path_requested:
        return decision(AdaptiveAction.FOCUS_REQUIRED, "student_requested_minimum_path", "requirements_still_apply")

    # Brief exploration retains the required objective as the return point.
    if context.scoped_exploration_requested:
        return decision(AdaptiveAction.EXPLAIN, "scoped_exploration", "return_to_required_objective", resume=context.objective_id)

    if context.requested_action in STUDENT_REQUESTABLE_ACTIONS and context.request_in_scope:
        return decision(context.requested_action, "explicit_in_scope_request")

    if _has_repeated_misconception(context.evidence):
        return decision(AdaptiveAction.REMEDIATE, "repeated_misconception")

    if _has_repeated_failure(context.evidence):
        return decision(AdaptiveAction.REMEDIATE, "repeated_incorrect_evidence")

    if context.student_stuck:
        return decision(AdaptiveAction.HINT, "student_stuck")

    if context.needs_explanation:
        return decision(AdaptiveAction.EXPLAIN, "incorrect_evidence")

    if context.needs_practice:
        return decision(AdaptiveAction.PRACTICE, "partial_evidence")

    if context.continue_assessment:
        return decision(AdaptiveAction.ASSESS, "diagnostic_sequence_continues")

    if context.progress.status == ObjectiveStatus.NOT_OBSERVED:
        return decision(AdaptiveAction.ASSESS, "insufficient_evidence")

    if context.progress.status == ObjectiveStatus.DEMONSTRATED:
        if context.prefer_challenge:
            return decision(AdaptiveAction.CHALLENGE, "objective_demonstrated", "student_ready_for_challenge")
        return decision(AdaptiveAction.ADVANCE, "objective_demonstrated")

    if context.required_work_remaining:
        return decision(AdaptiveAction.FOCUS_REQUIRED, "required_work_remaining")

    return decision(AdaptiveAction.PRACTICE, "continue_selected_activity")


def oop_learning_plan() -> LearningPlan:
    """Seeded Phase 1 plan; professor authoring remains future work."""
    return LearningPlan.model_validate(
        {
            "title": "Object-Oriented Programming",
            "course_context": "Introductory software engineering",
            "assignment_context": "Diagnose, practice, then complete the required BankAccount task.",
            "concepts": [
                {"id": "classes", "name": "Classes"},
                {"id": "objects", "name": "Objects"},
                {"id": "methods", "name": "Methods"},
                {"id": "object_interaction", "name": "Object interaction"},
            ],
            "objectives": [
                {
                    "id": "OBJ-1",
                    "concept_id": "classes",
                    "description": "Explain the difference between a class and an object.",
                    "required": True,
                    "assessment_types": ["conceptual", "application_scenario"],
                    "demonstration_assessment_types": ["conceptual", "application_scenario"],
                },
                {
                    "id": "OBJ-2",
                    "concept_id": "methods",
                    "description": "Create a class containing attributes and methods.",
                    "required": True,
                    "assessment_types": ["code_construction", "application_scenario"],
                    "demonstration_assessment_types": ["code_construction", "application_scenario"],
                },
                {
                    "id": "OBJ-3",
                    "concept_id": "object_interaction",
                    "description": "Read, debug, and reason about simple object-oriented code.",
                    "required": True,
                    "assessment_types": ["code_output", "debugging", "application_scenario"],
                    "demonstration_assessment_types": ["debugging", "application_scenario"],
                },
            ],
            "required_task": {
                "id": "TASK-1",
                "title": "Implement a BankAccount class",
                "description": "Write a BankAccount class with an appropriate balance attribute and deposit/withdraw methods.",
                "objective_ids": ["OBJ-1", "OBJ-2", "OBJ-3"],
            },
            "approved_resources": [],
            "scope_notes": "Inheritance may receive a brief preview; return to the required objectives afterward.",
        }
    )


def is_phase1_oop_plan(plan: LearningPlan) -> bool:
    """Allow resource selection without implying support for arbitrary plans."""
    return plan.model_dump(exclude={"approved_resources"}) == oop_learning_plan().model_dump(
        exclude={"approved_resources"}
    )


def summarize_class_objective(
    objective_id: str,
    concept_id: str,
    progress_items: list[ObjectiveProgress],
    evidence_items: list[LearningEvidence],
    decisions: list[AdaptiveDecision],
) -> ClassObjectiveAnalytics:
    """Aggregate learning signals without ranking or scoring individual students."""
    statuses = Counter(item.status for item in progress_items if item.objective_id == objective_id)
    misconceptions = Counter(
        item.misconception_code
        for item in evidence_items
        if item.objective_id == objective_id and item.misconception_code
    )
    return ClassObjectiveAnalytics(
        objective_id=objective_id,
        concept_id=concept_id,
        status_counts=dict(statuses),
        common_misconceptions=dict(misconceptions),
        remediation_count=sum(
            item.objective_id == objective_id and item.action == AdaptiveAction.REMEDIATE
            for item in decisions
        ),
        independent_demonstration_count=sum(
            item.objective_id == objective_id and item.independent_evidence_count > 0
            for item in progress_items
        ),
    )
