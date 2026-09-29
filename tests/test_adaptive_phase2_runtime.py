from datetime import datetime, timezone
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "Socratic-Chat/backend"))

from platform_app.adaptive import (
    AssessmentTarget,
    PolicyContext,
    choose_adaptive_action,
    derive_objective_progress,
    oop_learning_plan,
)
from platform_app.adaptive_runtime import (
    eligible_objectives,
    final_demonstration_targets,
    initial_diagnostic_targets,
    runtime_assessments,
    select_diagnostic,
    select_objective,
)
from platform_app.schemas import (
    AdaptiveAction,
    AssessmentType,
    CompletenessState,
    CorrectnessState,
    EvidenceType,
    IndependenceLevel,
    LearningEvidence,
    LearningPlan,
    ObjectiveProgress,
    ObjectiveStatus,
)


NOW = datetime(2026, 1, 1, tzinfo=timezone.utc)


def history_plan() -> LearningPlan:
    return LearningPlan.model_validate(
        {
            "schema_version": 2,
            "title": "Primary Source Analysis",
            "course_context": "History",
            "assignment_context": "Analyze and corroborate primary sources.",
            "concepts": [
                {"id": "sourcing", "name": "Sourcing"},
                {
                    "id": "corroboration",
                    "name": "Corroboration",
                    "prerequisite_ids": ["sourcing"],
                },
            ],
            "objectives": [
                {
                    "id": "HIST-SOURCE",
                    "concept_id": "sourcing",
                    "description": "Explain how author perspective affects a source.",
                    "success_criteria": ["Connects perspective to a specific claim."],
                    "required": True,
                    "assessment_types": ["explanation", "analysis", "application"],
                    "demonstration_requirements": [
                        {"id": "source_explanation", "assessment_types": ["explanation", "analysis"]},
                        {"id": "source_application", "assessment_types": ["application"]},
                    ],
                },
                {
                    "id": "HIST-CORROBORATE",
                    "concept_id": "corroboration",
                    "description": "Construct a corroborated interpretation.",
                    "success_criteria": ["Uses evidence from both sources."],
                    "required": True,
                    "assessment_types": ["analysis", "construction"],
                    "demonstration_requirements": [
                        {"id": "corroborated_claim", "assessment_types": ["construction"]}
                    ],
                },
            ],
            "diagnostics": [
                {
                    "id": "HIST-D1",
                    "objective_id": "HIST-SOURCE",
                    "assessment_type": "explanation",
                    "purpose": "diagnostic",
                    "prompt": "How might the author's position affect this account?",
                    "stimulus": "A factory owner describes working conditions.",
                    "evaluation_criteria": ["Identifies a relevant perspective."],
                },
                {
                    "id": "HIST-D2",
                    "objective_id": "HIST-SOURCE",
                    "assessment_type": "application",
                    "purpose": "diagnostic",
                    "prompt": "Apply sourcing to evaluate this claim.",
                    "evaluation_criteria": ["Uses the source context."],
                },
                {
                    "id": "HIST-D3",
                    "objective_id": "HIST-CORROBORATE",
                    "assessment_type": "construction",
                    "purpose": "diagnostic",
                    "prompt": "Construct one claim supported by both excerpts.",
                    "evaluation_criteria": ["Uses both excerpts."],
                },
            ],
            "required_task": {
                "id": "HIST-TASK",
                "title": "Source interpretation",
                "description": "Write a corroborated interpretation.",
                "submission_prompt": "Submit your interpretation.",
                "objective_ids": ["HIST-SOURCE", "HIST-CORROBORATE"],
            },
            "approved_resources": [],
            "scope": {"notes": "Use only the two approved excerpts."},
        }
    )


def progress(objective_id: str, concept_id: str, status: ObjectiveStatus) -> ObjectiveProgress:
    return ObjectiveProgress(objective_id=objective_id, concept_id=concept_id, status=status)


def evidence(
    assessment_type: AssessmentType | None,
    *,
    independence: IndependenceLevel = IndependenceLevel.INDEPENDENT,
    evidence_type: EvidenceType = EvidenceType.DIAGNOSTIC_RESPONSE,
) -> LearningEvidence:
    return LearningEvidence(
        student_id="student",
        course_id="course",
        assignment_id="assignment",
        attempt_id="attempt",
        objective_id="HIST-SOURCE",
        concept_id="sourcing",
        evidence_type=evidence_type,
        assessment_type=assessment_type,
        response="Observable response",
        correctness=CorrectnessState.CORRECT,
        completeness=CompletenessState.COMPLETE,
        independence=independence,
        assessor_version="test-v2",
        created_at=NOW,
    )


def test_v2_uses_plan_order_authored_diagnostics_and_no_oop_identifiers():
    plan = history_plan()
    assessments = runtime_assessments(plan)
    initial = select_objective(plan, [], None)

    assert initial.objective.id == "HIST-SOURCE"
    assert select_diagnostic(plan, initial.objective.id).id == "HIST-D1"
    assert assessments[0].assessment_type == AssessmentType.EXPLANATION
    serialized = plan.model_dump_json()
    assert "BankAccount" not in serialized
    assert "OBJ-1" not in serialized
    assert "python" not in serialized.lower()


def test_v2_phase_targets_cover_authored_baseline_and_demonstration_requirements():
    plan = history_plan()

    baseline = initial_diagnostic_targets(plan)
    final = final_demonstration_targets(plan)

    assert [item.id for item in baseline] == ["HIST-D1", "HIST-D2", "HIST-D3"]
    assert [item.objective_id for item in final] == [
        "HIST-SOURCE",
        "HIST-SOURCE",
        "HIST-CORROBORATE",
    ]
    assert [item.assessment_type for item in final] == [
        AssessmentType.EXPLANATION,
        AssessmentType.APPLICATION,
        AssessmentType.CONSTRUCTION,
    ]
    assert all(item.purpose == "formative" for item in final)
    assert len({item.id for item in final}) == len(final)


def test_final_target_uses_requirement_type_when_no_authored_prompt_matches():
    data = history_plan().model_dump(mode="json")
    data["diagnostics"] = [
        item for item in data["diagnostics"] if item["id"] != "HIST-D2"
    ]
    plan = LearningPlan.model_validate(data)

    application_target = final_demonstration_targets(plan)[1]

    assert application_target.objective_id == "HIST-SOURCE"
    assert application_target.assessment_type == AssessmentType.APPLICATION
    assert application_target.id.startswith("generated-final-")
    assert "Independently demonstrate" in application_target.prompt


def test_prerequisites_and_student_objective_requests_are_application_validated():
    plan = history_plan()
    initial_progress = [
        progress("HIST-SOURCE", "sourcing", ObjectiveStatus.NOT_OBSERVED),
        progress("HIST-CORROBORATE", "corroboration", ObjectiveStatus.NOT_OBSERVED),
    ]

    assert [item.id for item in eligible_objectives(plan, initial_progress)] == ["HIST-SOURCE"]
    rejected = select_objective(plan, initial_progress, "HIST-CORROBORATE")
    assert rejected.objective.id == "HIST-SOURCE"
    assert rejected.request_accepted is False

    initial_progress[0] = progress("HIST-SOURCE", "sourcing", ObjectiveStatus.DEMONSTRATED)
    accepted = select_objective(plan, initial_progress, "HIST-CORROBORATE")
    assert accepted.objective.id == "HIST-CORROBORATE"
    assert accepted.request_accepted is True


def test_every_demonstration_requirement_group_must_be_satisfied():
    objective = history_plan().objectives[0]
    explanation = evidence(AssessmentType.EXPLANATION)
    application = evidence(AssessmentType.APPLICATION)

    assert derive_objective_progress(objective, [explanation]).status == ObjectiveStatus.DEVELOPING
    assert derive_objective_progress(objective, [explanation, application]).status == ObjectiveStatus.DEMONSTRATED


def test_unsupported_guided_and_self_report_evidence_cannot_demonstrate():
    objective = history_plan().objectives[0]
    unsupported = evidence(AssessmentType.PREDICTION)
    guided = evidence(AssessmentType.APPLICATION, independence=IndependenceLevel.GUIDED)
    self_report = evidence(
        AssessmentType.APPLICATION,
        evidence_type=EvidenceType.SELF_REPORT,
    )
    explanation = evidence(AssessmentType.EXPLANATION)

    for item in (unsupported, guided, self_report):
        assert derive_objective_progress(objective, [explanation, item]).status != ObjectiveStatus.DEMONSTRATED


def test_multi_objective_required_task_submission_does_not_grant_mastery():
    plan = history_plan()
    submission = evidence(
        None,
        evidence_type=EvidenceType.REQUIRED_TASK_SUBMISSION,
    )

    source_progress = derive_objective_progress(plan.objectives[0], [submission])
    corroboration_progress = derive_objective_progress(plan.objectives[1], [submission])

    assert plan.required_task.objective_ids == ["HIST-SOURCE", "HIST-CORROBORATE"]
    assert source_progress.status == ObjectiveStatus.DEVELOPING
    assert corroboration_progress.status == ObjectiveStatus.NOT_OBSERVED
    assert source_progress.independent_evidence_count == 0
    assert corroboration_progress.independent_evidence_count == 0


def test_generic_actions_preserve_auditable_assessment_targeting():
    plan = history_plan()
    source_assessment = select_diagnostic(plan, "HIST-SOURCE")
    corroboration_assessment = select_diagnostic(plan, "HIST-CORROBORATE")
    current = progress("HIST-SOURCE", "sourcing", ObjectiveStatus.EMERGING)
    base = dict(
        objective_id="HIST-SOURCE",
        progress=current,
        target=AssessmentTarget(
            assessment=source_assessment,
            prompt_source="authored",
        ),
    )

    explain = choose_adaptive_action(PolicyContext(**base, needs_explanation=True))
    practice = choose_adaptive_action(PolicyContext(**base, needs_practice=True))
    remediate = choose_adaptive_action(
        PolicyContext(
            **base,
            evidence=(
                evidence(AssessmentType.EXPLANATION),
                LearningEvidence.model_validate(
                    {
                        **evidence(AssessmentType.EXPLANATION).model_dump(),
                        "correctness": "incorrect",
                        "misconception_code": "source_bias",
                    }
                ),
                LearningEvidence.model_validate(
                    {
                        **evidence(AssessmentType.EXPLANATION).model_dump(),
                        "correctness": "incorrect",
                        "misconception_code": "source_bias",
                    }
                ),
            ),
        )
    )
    advance = choose_adaptive_action(
        PolicyContext(
            **{
                **base,
                "target": AssessmentTarget(
                    assessment=corroboration_assessment,
                    prompt_source="authored",
                ),
                "progress": progress(
                    "HIST-SOURCE", "sourcing", ObjectiveStatus.DEMONSTRATED
                ),
            },
        )
    )

    assert explain.action == AdaptiveAction.EXPLAIN
    assert practice.action == AdaptiveAction.PRACTICE
    assert remediate.action == AdaptiveAction.REMEDIATE
    assert advance.action == AdaptiveAction.ADVANCE
    for decision in (explain, practice, remediate):
        assert decision.assessment_id == "HIST-D1"
        assert decision.assessment_type == AssessmentType.EXPLANATION
        assert decision.prompt_source == "authored"
        assert decision.objective_id == "HIST-SOURCE"
    assert advance.objective_id == "HIST-CORROBORATE"
    assert advance.assessment_id == "HIST-D3"
    assert advance.assessment_type == AssessmentType.CONSTRUCTION


def test_legacy_oop_plan_keeps_phase1_compatibility_diagnostics():
    plan = oop_learning_plan()
    assessments = runtime_assessments(plan)

    assert plan.schema_version == 1
    assert assessments[0].id == "DIAG-1"
    assert assessments[-1].id == "TASK-1"
    assert "BankAccount" in assessments[-1].prompt
