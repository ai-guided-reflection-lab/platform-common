"""Platform-owned adaptive orchestration for legacy and generic plans."""

from __future__ import annotations

import re
from hashlib import sha256
from dataclasses import dataclass
from uuid import uuid4

from psycopg.types.json import Jsonb

from platform_app import engines
from platform_app.adaptive import (
    AssessmentTarget,
    GENERIC_POLICY_VERSION,
    PolicyContext,
    bounded_response_independence,
    choose_adaptive_action,
    derive_objective_progress,
)
from platform_app.schemas import (
    AdaptiveAction,
    AdaptiveDecision,
    AssessmentItem,
    AssessmentPrompt,
    AssessmentResult,
    AssessmentType,
    CompletenessState,
    CorrectnessState,
    EvidenceType,
    IndependenceLevel,
    LearningEvidence,
    LearningPlan,
    LearningObjective,
    ObjectiveProgress,
    ObjectiveStatus,
    RequiredTaskStatus,
    TutorConfig,
)

SELF_REPORT_RE = re.compile(r"\b(i already know|i know this|i understand this|this is easy)\b", re.I)
MINIMUM_PATH_RE = re.compile(r"\b(only have|just have|in a hurry|minimum|fastest|just get this done)\b", re.I)
LEGACY_CURIOUS_RE = re.compile(r"\b(inheritance|outside today|extra topic)\b", re.I)
SCOPED_EXPLORATION_RE = re.compile(r"\b(outside (?:the )?scope|extra topic|curious about)\b", re.I)
OBJECTIVE_REQUEST_RE = re.compile(r"\bobjective\s+([A-Za-z0-9_-]+)\b", re.I)
STUCK_RE = re.compile(r"\b(i don'?t know|no idea|stuck|not sure)\b", re.I)

INITIAL_DIAGNOSTIC_PHASE = "initial_diagnostic"
ADAPTIVE_LEARNING_PHASE = "adaptive_learning"
FINAL_DEMONSTRATION_PHASE = "final_demonstration"
REQUIRED_TASK_PHASE = "required_task"

PHASE_LABELS = {
    INITIAL_DIAGNOSTIC_PHASE: "Initial diagnostic",
    ADAPTIVE_LEARNING_PHASE: "Adaptive learning",
    FINAL_DEMONSTRATION_PHASE: "Final demonstration",
    REQUIRED_TASK_PHASE: "Required task",
}


def _legacy_diagnostics(plan: LearningPlan) -> list[AssessmentPrompt]:
    return [
        AssessmentPrompt(
            id="DIAG-1",
            objective_id="OBJ-1",
            concept_id="classes",
            assessment_type=AssessmentType.CONCEPTUAL,
            prompt="What is the difference between a class and an object?",
        ),
        AssessmentPrompt(
            id="DIAG-2",
            objective_id="OBJ-3",
            concept_id="object_interaction",
            assessment_type=AssessmentType.CODE_OUTPUT,
            code=(
                "class BankAccount:\n"
                "    def __init__(self, balance):\n"
                "        self.balance = balance\n\n"
                "account = BankAccount(100)\n"
                "print(account.balance)"
            ),
            prompt="What does this print, and why?",
        ),
        AssessmentPrompt(
            id="DIAG-3",
            objective_id="OBJ-3",
            concept_id="object_interaction",
            assessment_type=AssessmentType.DEBUGGING,
            code=(
                "class BankAccount:\n"
                "    def __init__(self, balance):\n"
                "        balance = balance\n\n"
                "account = BankAccount(100)\n"
                "print(account.balance)"
            ),
            prompt="What is wrong with this code, and how would you fix it?",
        ),
        AssessmentPrompt(
            id="DIAG-4",
            objective_id="OBJ-2",
            concept_id="methods",
            assessment_type=AssessmentType.CODE_CONSTRUCTION,
            prompt="Write a small Student class with a name attribute and a method that prints the student's name.",
        ),
        AssessmentPrompt(
            id="TASK-1",
            objective_id="OBJ-2",
            concept_id="methods",
            assessment_type=AssessmentType.CODE_CONSTRUCTION,
            prompt=plan.required_task.description,
        ),
    ]


RuntimeAssessment = AssessmentPrompt | AssessmentItem


def _task_assessment(plan: LearningPlan) -> AssessmentPrompt:
    """Build a rendering target; the first linked objective is only an anchor.

    Phase 2B records the submission without treating this target as a mastery
    assessment. Multi-objective task assessment belongs to the later explicit
    required-task workflow.
    """
    objective = next(
        item for item in plan.objectives if item.id == plan.required_task.objective_ids[0]
    )
    if objective.demonstration_requirements:
        assessment_type = objective.demonstration_requirements[0].assessment_types[0]
    else:
        assessment_type = objective.assessment_types[0]
    return AssessmentPrompt(
        id=plan.required_task.id,
        objective_id=objective.id,
        concept_id=objective.concept_id,
        assessment_type=assessment_type,
        prompt=plan.required_task.submission_prompt or plan.required_task.description,
    )


def runtime_assessments(plan: LearningPlan) -> list[RuntimeAssessment]:
    """Return immutable authored v2 targets or the exact Phase 1 sequence."""
    if plan.schema_version == 1:
        return _legacy_diagnostics(plan)
    return [*plan.diagnostics, *final_demonstration_targets(plan), _task_assessment(plan)]


def initial_diagnostic_targets(plan: LearningPlan) -> list[AssessmentItem]:
    """Return every required objective's authored diagnostics in plan order."""
    required_ids = {objective.id for objective in plan.objectives if objective.required}
    return [
        diagnostic
        for objective in plan.objectives
        if objective.id in required_ids
        for diagnostic in plan.diagnostics
        if diagnostic.objective_id == objective.id
        and diagnostic.purpose == "diagnostic"
    ]


def final_demonstration_targets(plan: LearningPlan) -> list[AssessmentItem]:
    """Build one stable assessment target for each authored requirement group."""
    targets: list[AssessmentItem] = []
    occupied_ids = {item.id for item in plan.diagnostics} | {plan.required_task.id}
    for objective in plan.objectives:
        if not objective.required:
            continue
        for requirement in objective.demonstration_requirements:
            permitted = set(requirement.assessment_types)
            authored = next(
                (
                    item
                    for item in plan.diagnostics
                    if item.objective_id == objective.id
                    and item.assessment_type in permitted
                ),
                None,
            )
            assessment_type = (
                authored.assessment_type
                if authored is not None
                else requirement.assessment_types[0]
            )
            identity = sha256(
                f"{objective.id}:{requirement.id}".encode("utf-8")
            ).hexdigest()[:16]
            base_id = (
                f"FINAL-AUTHORED-{identity}"
                if authored is not None
                else f"generated-final-{identity}"
            )
            target_id = base_id
            suffix = 2
            while target_id in occupied_ids:
                target_id = f"{base_id}-{suffix}"
                suffix += 1
            occupied_ids.add(target_id)
            targets.append(
                AssessmentItem(
                    id=target_id,
                    objective_id=objective.id,
                    assessment_type=assessment_type,
                    purpose="formative",
                    prompt=(
                        authored.prompt
                        if authored is not None
                        else (
                            f"Independently demonstrate this objective with a "
                            f"{assessment_type.value} response: {objective.description}"
                        )
                    ),
                    stimulus=authored.stimulus if authored is not None else None,
                    stimulus_format=(
                        authored.stimulus_format if authored is not None else "plain_text"
                    ),
                    evaluation_criteria=(
                        authored.evaluation_criteria
                        if authored is not None
                        else (objective.success_criteria or [objective.description])
                    ),
                )
            )
    return targets


def select_diagnostic(plan: LearningPlan, objective_id: str) -> AssessmentItem:
    return next(
        item
        for item in plan.diagnostics
        if item.objective_id == objective_id and item.purpose == "diagnostic"
    )


def eligible_objectives(
    plan: LearningPlan,
    progress_items: list[ObjectiveProgress],
) -> list[LearningObjective]:
    """Apply concept prerequisites using platform-owned demonstrated states."""
    progress = {item.objective_id: item.status for item in progress_items}
    concept_required = {
        concept.id: [
            objective.id
            for objective in plan.objectives
            if objective.concept_id == concept.id and objective.required
        ]
        for concept in plan.concepts
    }
    concepts = {concept.id: concept for concept in plan.concepts}

    def eligible(objective: LearningObjective) -> bool:
        prerequisites = concepts[objective.concept_id].prerequisite_ids
        return all(
            all(
                progress.get(objective_id) == ObjectiveStatus.DEMONSTRATED
                for objective_id in concept_required[prerequisite_id]
            )
            for prerequisite_id in prerequisites
        )

    return [objective for objective in plan.objectives if eligible(objective)]


@dataclass(frozen=True)
class ObjectiveSelection:
    objective: LearningObjective
    request_accepted: bool


def select_objective(
    plan: LearningPlan,
    progress_items: list[ObjectiveProgress],
    requested_objective_id: str | None,
) -> ObjectiveSelection:
    """Select in plan order; accept student requests only when eligible and assessable."""
    eligible = eligible_objectives(plan, progress_items)
    eligible_ids = {item.id for item in eligible}
    diagnostic_ids = {
        item.objective_id for item in plan.diagnostics if item.purpose == "diagnostic"
    }
    if requested_objective_id in eligible_ids and requested_objective_id in diagnostic_ids:
        return ObjectiveSelection(_objective(plan, requested_objective_id), True)

    progress = {item.objective_id: item.status for item in progress_items}
    for objective in eligible:
        if objective.required and progress.get(objective.id) != ObjectiveStatus.DEMONSTRATED:
            return ObjectiveSelection(objective, False)
    for objective in eligible:
        if objective.id in diagnostic_ids:
            return ObjectiveSelection(objective, False)
    raise ValueError("The learning plan has no eligible objective with an authored diagnostic.")


def is_adaptive_assignment(assignment: dict) -> bool:
    if assignment.get("tool") != "student-agent":
        return False
    snapshot = assignment.get("snapshot") or {}
    config = snapshot.get("config", assignment.get("config", {}))
    return isinstance(config, dict) and config.get("learning_plan") is not None


def _config(assignment: dict) -> TutorConfig:
    return TutorConfig.model_validate((assignment.get("snapshot") or {}).get("config", assignment["config"]))


def _objective(plan: LearningPlan, objective_id: str):
    return next(item for item in plan.objectives if item.id == objective_id)


def _format_prompt(item: RuntimeAssessment) -> str:
    if isinstance(item, AssessmentItem):
        if not item.stimulus:
            return item.prompt
        if item.stimulus_format == "code":
            return f"```\n{item.stimulus}\n```\n\n{item.prompt}"
        return f"{item.stimulus}\n\n{item.prompt}"
    return f"```python\n{item.code}\n```\n\n{item.prompt}" if item.code else item.prompt


def _prompt_source(plan: LearningPlan, assessment: RuntimeAssessment) -> str:
    if plan.schema_version == 1:
        return "legacy"
    if assessment.id == plan.required_task.id:
        return "required_task"
    if assessment.id.startswith("generated-"):
        return "generated"
    return "authored"


def _assessment_concept_id(plan: LearningPlan, assessment: RuntimeAssessment) -> str:
    return _objective(plan, assessment.objective_id).concept_id


def _policy_context(
    plan: LearningPlan,
    assessment: RuntimeAssessment,
    progress: ObjectiveProgress,
    **kwargs,
) -> PolicyContext:
    prompt_source = _prompt_source(plan, assessment)
    return PolicyContext(
        objective_id=assessment.objective_id,
        progress=progress,
        target=AssessmentTarget(
            assessment=assessment,
            prompt_source=prompt_source,
            counts_as_assessment=prompt_source != "required_task",
        ),
        policy_version=GENERIC_POLICY_VERSION if plan.schema_version == 2 else "adaptive-sdl-v1",
        **kwargs,
    )


def _initialize_progress(conn, attempt: dict, assignment: dict, plan: LearningPlan) -> list[ObjectiveProgress]:
    for objective in plan.objectives:
        conn.execute(
            """INSERT INTO platform_objective_progress
               (attempt_id,student_id,course_id,assignment_id,objective_id,concept_id)
               VALUES (%s,%s,%s,%s,%s,%s) ON CONFLICT DO NOTHING""",
            (attempt["id"], attempt["student_id"], assignment["course_id"], assignment["id"], objective.id, objective.concept_id),
        )
    return _load_progress(conn, attempt["id"])


def _load_progress(conn, attempt_id) -> list[ObjectiveProgress]:
    rows = conn.execute(
        """SELECT objective_id,concept_id,status,evidence_count,independent_evidence_count,
                  attempts,hints_used,updated_at AS last_updated_at
           FROM platform_objective_progress WHERE attempt_id=%s ORDER BY objective_id""",
        (attempt_id,),
    ).fetchall()
    return [ObjectiveProgress.model_validate(row) for row in rows]


def _load_evidence(conn, attempt_id, objective_id) -> list[LearningEvidence]:
    rows = conn.execute(
        """SELECT student_id::text,course_id::text,assignment_id::text,attempt_id::text,
                  objective_id,concept_id,evidence_type,assessment_type,assessment_id,
                  assessment_origin,assessment_prompt,response,correctness,
                  completeness,independence,hints_used,misconception_code,misconception_detail,
                  assessor_version,created_at
           FROM platform_learning_evidence WHERE attempt_id=%s AND objective_id=%s ORDER BY created_at,id""",
        (attempt_id, objective_id),
    ).fetchall()
    return [LearningEvidence.model_validate(row) for row in rows]


def _save_evidence(conn, evidence: LearningEvidence) -> None:
    conn.execute(
        """INSERT INTO platform_learning_evidence
           (id,student_id,course_id,assignment_id,attempt_id,objective_id,concept_id,
            evidence_type,assessment_type,assessment_id,assessment_origin,assessment_prompt,
            response,correctness,completeness,independence,
            hints_used,misconception_code,misconception_detail,assessor_version,created_at)
           VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
        (uuid4(), evidence.student_id, evidence.course_id, evidence.assignment_id,
         evidence.attempt_id, evidence.objective_id, evidence.concept_id,
         evidence.evidence_type.value, evidence.assessment_type.value if evidence.assessment_type else None,
         evidence.assessment_id, evidence.assessment_origin, evidence.assessment_prompt,
         evidence.response, evidence.correctness.value, evidence.completeness.value,
         evidence.independence.value, evidence.hints_used, evidence.misconception_code,
         evidence.misconception_detail, evidence.assessor_version, evidence.created_at),
    )


def _save_progress(conn, attempt_id, progress: ObjectiveProgress) -> None:
    conn.execute(
        """UPDATE platform_objective_progress SET status=%s,evidence_count=%s,
           independent_evidence_count=%s,attempts=%s,hints_used=%s,updated_at=now()
           WHERE attempt_id=%s AND objective_id=%s""",
        (progress.status.value, progress.evidence_count, progress.independent_evidence_count,
         progress.attempts, progress.hints_used, attempt_id, progress.objective_id),
    )


def _save_decision(conn, attempt_id, decision: AdaptiveDecision) -> None:
    conn.execute(
        """INSERT INTO platform_adaptive_decisions
           (id,attempt_id,objective_id,action,assessment_type,assessment_id,prompt_source,
            reason_codes,policy_version,resume_objective_id)
           VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
        (uuid4(), attempt_id, decision.objective_id, decision.action.value,
         decision.assessment_type.value if decision.assessment_type else None,
         decision.assessment_id, decision.prompt_source, Jsonb(decision.reason_codes),
         decision.policy_version, decision.resume_objective_id),
    )


def _public_progress(items: list[ObjectiveProgress]) -> list[dict]:
    return [item.model_dump(mode="json") for item in items]


def student_learning_plan(plan: LearningPlan) -> dict:
    """Expose goals and task context without releasing the assessment key."""
    public = plan.model_dump(mode="json")
    public.pop("diagnostics", None)
    for objective in public["objectives"]:
        objective.pop("anticipated_misconceptions", None)
    return public


def _start_legacy(conn, assignment: dict, attempt: dict, cfg: TutorConfig, plan: LearningPlan) -> dict:
    progress = _initialize_progress(conn, attempt, assignment, plan)
    assessment = runtime_assessments(plan)[0]
    progress_by_id = {item.objective_id: item for item in progress}
    decision = choose_adaptive_action(
        _policy_context(plan, assessment, progress_by_id[assessment.objective_id])
    )
    _save_decision(conn, attempt["id"], decision)
    rendered = engines.call("student-agent", "POST", "/internal/platform/adaptive/start", json={
        "session_id": str(attempt["id"]),
        "provider": cfg.provider,
        "plan_title": plan.title,
        "decision": decision.model_dump(mode="json"),
        "objective": _objective(plan, assessment.objective_id).model_dump(mode="json"),
        "assessment_prompt": _format_prompt(assessment),
    })
    rendered.pop("nav", None)
    rendered.pop("practice_options", None)
    rendered.update({
        "adaptive": True,
        "learning_plan": student_learning_plan(plan),
        "objective_progress": _public_progress(progress),
        "current_objective_id": assessment.objective_id,
        "current_assessment_id": assessment.id,
        "latest_decision": decision.model_dump(mode="json"),
        "required_task_status": RequiredTaskStatus.NOT_STARTED.value,
    })
    return rendered


def _start_v2(conn, assignment: dict, attempt: dict, cfg: TutorConfig, plan: LearningPlan) -> dict:
    progress = _initialize_progress(conn, attempt, assignment, plan)
    assessments = initial_diagnostic_targets(plan)
    assessment = assessments[0]
    decision = _explicit_decision(
        AdaptiveAction.ASSESS,
        plan,
        assessment,
        "initial_diagnostic_started",
    )
    _save_decision(conn, attempt["id"], decision)
    rendered = engines.call("student-agent", "POST", "/internal/platform/adaptive/start", json={
        "session_id": str(attempt["id"]),
        "provider": cfg.provider,
        "plan_title": plan.title,
        "decision": decision.model_dump(mode="json"),
        "objective": _objective(plan, assessment.objective_id).model_dump(mode="json"),
        "assessment_prompt": _format_prompt(assessment),
    })
    rendered.pop("nav", None)
    rendered.pop("practice_options", None)
    rendered.update({
        "adaptive": True,
        "learning_plan": student_learning_plan(plan),
        "objective_progress": _public_progress(progress),
        "current_objective_id": assessment.objective_id,
        "current_assessment_id": assessment.id,
        "latest_decision": decision.model_dump(mode="json"),
        "required_task_status": RequiredTaskStatus.NOT_STARTED.value,
        "assessment_phase": INITIAL_DIAGNOSTIC_PHASE,
        "phase_label": PHASE_LABELS[INITIAL_DIAGNOSTIC_PHASE],
    })
    return rendered


def start(conn, assignment: dict, attempt: dict) -> dict:
    cfg = _config(assignment)
    plan = cfg.learning_plan
    assert plan is not None
    if plan.schema_version == 2:
        return _start_v2(conn, assignment, attempt, cfg, plan)
    return _start_legacy(conn, assignment, attempt, cfg, plan)


def _self_report_result(assessment: RuntimeAssessment) -> AssessmentResult:
    return AssessmentResult(
        objective_id=assessment.objective_id,
        assessment_type=assessment.assessment_type,
        correctness=CorrectnessState.PARTIAL,
        completeness=CompletenessState.INCOMPLETE,
        independence=IndependenceLevel.INDEPENDENT,
        rationale="The message is a self-report, not demonstrated evidence.",
        assessor_version="application-self-report-v1",
    )


def _required_task_result(assessment: RuntimeAssessment) -> AssessmentResult:
    """Acknowledge submission without interpreting it as objective evidence."""
    return AssessmentResult(
        objective_id=assessment.objective_id,
        assessment_type=assessment.assessment_type,
        correctness=CorrectnessState.CORRECT,
        completeness=CompletenessState.COMPLETE,
        independence=IndependenceLevel.INDEPENDENT,
        rationale="The required task was submitted; objective assessment is deferred.",
        assessor_version="application-required-task-v1",
    )


def _evidence_type(
    plan: LearningPlan,
    assessment: RuntimeAssessment,
    previous_action: str | None,
    self_report: bool,
) -> EvidenceType:
    if self_report:
        return EvidenceType.SELF_REPORT
    if assessment.id == plan.required_task.id:
        return EvidenceType.REQUIRED_TASK_SUBMISSION
    if previous_action in {AdaptiveAction.EXPLAIN.value, AdaptiveAction.HINT.value, AdaptiveAction.REMEDIATE.value}:
        return EvidenceType.GUIDED_RESPONSE
    if previous_action == AdaptiveAction.PRACTICE.value:
        return EvidenceType.PRACTICE_ATTEMPT
    return EvidenceType.DIAGNOSTIC_RESPONSE


def _process_message_legacy(
    conn,
    assignment: dict,
    attempt: dict,
    content: str,
    request_id: str,
    cfg: TutorConfig,
    plan: LearningPlan,
) -> dict:
    items = runtime_assessments(plan)
    current_id = attempt["engine_state"].get("current_assessment_id", items[0].id)
    index = next((i for i, item in enumerate(items) if item.id == current_id), 0)
    assessment = items[index]
    self_report = bool(SELF_REPORT_RE.search(content))
    if self_report:
        result = _self_report_result(assessment)
    else:
        result = AssessmentResult.model_validate(engines.call(
            "student-agent", "POST", "/internal/platform/adaptive/assess", json={
                "provider": cfg.provider,
                "objective": _objective(plan, assessment.objective_id).model_dump(mode="json"),
                "assessment": assessment.model_dump(mode="json"),
                "student_response": content,
            },
        ))

    previous_action = (attempt["engine_state"].get("latest_decision") or {}).get("action")
    evidence = LearningEvidence(
        student_id=str(attempt["student_id"]), course_id=str(assignment["course_id"]),
        assignment_id=str(assignment["id"]), attempt_id=str(attempt["id"]),
        objective_id=assessment.objective_id, concept_id=assessment.concept_id,
        evidence_type=_evidence_type(plan, assessment, previous_action, self_report),
        assessment_type=assessment.assessment_type, response=content,
        assessment_id=assessment.id,
        assessment_origin=_prompt_source(plan, assessment),
        assessment_prompt=_format_prompt(assessment),
        correctness=result.correctness, completeness=result.completeness,
        independence=bounded_response_independence(
            result.independence,
            AdaptiveAction(previous_action) if previous_action else None,
        ),
        hints_used=1 if previous_action == AdaptiveAction.HINT.value else 0,
        misconception_code=result.misconception_code,
        misconception_detail=result.misconception_detail,
        assessor_version=result.assessor_version,
    )
    _save_evidence(conn, evidence)
    objective = _objective(plan, assessment.objective_id)
    objective_evidence = _load_evidence(conn, attempt["id"], objective.id)
    updated = derive_objective_progress(objective, objective_evidence)
    _save_progress(conn, attempt["id"], updated)

    task_status = RequiredTaskStatus(attempt.get("required_task_status", "not_started"))
    if assessment.id == "TASK-1":
        task_status = RequiredTaskStatus.COMPLETED
    elif index >= len(items) - 2:
        task_status = RequiredTaskStatus.IN_PROGRESS

    successful = result.correctness == CorrectnessState.CORRECT
    if successful and not self_report and index < len(items) - 1:
        next_assessment = items[index + 1]
    else:
        next_assessment = assessment

    all_progress = _load_progress(conn, attempt["id"])
    progress_by_id = {item.objective_id: item for item in all_progress}
    all_required_demonstrated = all(
        progress_by_id[item.id].status.value == "demonstrated"
        for item in plan.objectives if item.required
    )
    decision = choose_adaptive_action(_policy_context(
        plan,
        assessment,
        updated,
        evidence=tuple(objective_evidence),
        student_stuck=bool(STUCK_RE.search(content)),
        needs_explanation=result.correctness == CorrectnessState.INCORRECT,
        needs_practice=result.correctness == CorrectnessState.PARTIAL and not self_report,
        continue_assessment=(
            successful
            and next_assessment.id != assessment.id
            and updated.status.value != "demonstrated"
        ),
        required_work_remaining=task_status != RequiredTaskStatus.COMPLETED,
        prefer_challenge=all_required_demonstrated,
        minimum_path_requested=bool(MINIMUM_PATH_RE.search(content)),
        scoped_exploration_requested=bool(LEGACY_CURIOUS_RE.search(content)),
    ))
    if successful and next_assessment.id != assessment.id:
        render_assessment = next_assessment
    else:
        render_assessment = assessment
    _save_decision(conn, attempt["id"], decision)
    conn.execute("UPDATE assignment_attempts_platform SET required_task_status=%s WHERE id=%s", (task_status.value, attempt["id"]))

    rag_context = engines.adaptive_rag_context(assignment, objective, decision, content)
    rendered = engines.call("student-agent", "POST", "/internal/platform/adaptive/render", json={
        "session_id": str(attempt["id"]), "request_id": request_id,
        "student_message": content, "provider": cfg.provider,
        "plan_title": plan.title, "decision": decision.model_dump(mode="json"),
        "objective": _objective(plan, render_assessment.objective_id).model_dump(mode="json"),
        "assessment_prompt": _format_prompt(render_assessment),
        "assessment_result": result.model_dump(mode="json"),
        "rag_context": rag_context,
    })
    # Navigation and phase progression belong to the legacy tutor flow. The
    # adaptive application owns those decisions and only accepts rendered text.
    rendered.pop("nav", None)
    rendered.pop("practice_options", None)
    rendered["sources"] = rag_context
    all_progress = _load_progress(conn, attempt["id"])
    rendered.update({
        "adaptive": True, "learning_plan": student_learning_plan(plan),
        "objective_progress": _public_progress(all_progress),
        "current_objective_id": render_assessment.objective_id,
        "current_assessment_id": render_assessment.id,
        "latest_decision": decision.model_dump(mode="json"),
        "required_task_status": task_status.value,
    })
    attempt["required_task_status"] = task_status.value
    return rendered


def _assessment_by_id(plan: LearningPlan, assessment_id: str) -> RuntimeAssessment:
    return next(item for item in runtime_assessments(plan) if item.id == assessment_id)


def _requirement_target(
    plan: LearningPlan,
    objective: LearningObjective,
    evidence_items: list[LearningEvidence],
    current_assessment_id: str,
) -> RuntimeAssessment:
    successful_types = {
        item.assessment_type
        for item in evidence_items
        if item.evidence_type != EvidenceType.SELF_REPORT
        and item.correctness == CorrectnessState.CORRECT
        and item.completeness == CompletenessState.COMPLETE
        and item.independence == IndependenceLevel.INDEPENDENT
        and item.hints_used == 0
    }
    unsatisfied = next(
        (
            requirement
            for requirement in objective.demonstration_requirements
            if not successful_types.intersection(requirement.assessment_types)
        ),
        None,
    )
    if unsatisfied is None:
        return _assessment_by_id(plan, current_assessment_id)
    authored = [
        item
        for item in plan.diagnostics
        if item.objective_id == objective.id
        and item.purpose == "diagnostic"
        and item.assessment_type in unsatisfied.assessment_types
    ]
    different = next((item for item in authored if item.id != current_assessment_id), None)
    if different:
        return different
    if authored:
        return authored[0]
    assessment_type = unsatisfied.assessment_types[0]
    return AssessmentPrompt(
        id=f"generated-{objective.id}-{assessment_type.value}",
        objective_id=objective.id,
        concept_id=objective.concept_id,
        assessment_type=assessment_type,
        prompt=(
            f"Demonstrate this objective with a {assessment_type.value} response: "
            f"{objective.description}"
        ),
    )


def _next_required_objective(
    plan: LearningPlan,
    progress_items: list[ObjectiveProgress],
) -> LearningObjective | None:
    statuses = {item.objective_id: item.status for item in progress_items}
    for objective in eligible_objectives(plan, progress_items):
        if objective.required and statuses.get(objective.id) != ObjectiveStatus.DEMONSTRATED:
            return objective
    return None


def _explicit_decision(
    action: AdaptiveAction,
    plan: LearningPlan,
    assessment: RuntimeAssessment,
    *reason_codes: str,
    resume_objective_id: str | None = None,
) -> AdaptiveDecision:
    prompt_source = _prompt_source(plan, assessment)
    return AdaptiveDecision(
        action=action,
        objective_id=assessment.objective_id,
        assessment_type=(
            None if prompt_source == "required_task" else assessment.assessment_type
        ),
        assessment_id=assessment.id,
        prompt_source=prompt_source,
        reason_codes=list(reason_codes),
        policy_version=GENERIC_POLICY_VERSION,
        resume_objective_id=resume_objective_id,
    )


def _learning_decision(
    plan: LearningPlan,
    target: RuntimeAssessment,
    progress: ObjectiveProgress,
    evidence_items: list[LearningEvidence],
    content: str,
) -> AdaptiveDecision:
    """Enter/resume the normal policy from persisted baseline evidence."""
    latest = evidence_items[-1] if evidence_items else None
    successful = latest is not None and latest.correctness == CorrectnessState.CORRECT
    return choose_adaptive_action(_policy_context(
        plan,
        target,
        progress,
        evidence=() if successful else tuple(evidence_items),
        student_stuck=bool(STUCK_RE.search(content)),
        needs_explanation=(
            latest is not None and latest.correctness == CorrectnessState.INCORRECT
        ),
        needs_practice=(
            latest is not None and latest.correctness == CorrectnessState.PARTIAL
        ),
        continue_assessment=(
            successful and progress.status != ObjectiveStatus.DEMONSTRATED
        ),
        required_work_remaining=True,
        minimum_path_requested=bool(MINIMUM_PATH_RE.search(content)),
        scoped_exploration_requested=bool(SCOPED_EXPLORATION_RE.search(content)),
    ))


def _independent_target_success(
    evidence: LearningEvidence,
    target: RuntimeAssessment,
) -> bool:
    return (
        evidence.evidence_type != EvidenceType.SELF_REPORT
        and evidence.assessment_type == target.assessment_type
        and evidence.correctness == CorrectnessState.CORRECT
        and evidence.completeness == CompletenessState.COMPLETE
        and evidence.independence == IndependenceLevel.INDEPENDENT
        and evidence.hints_used == 0
    )


def _render_v2(
    conn,
    assignment: dict,
    attempt: dict,
    cfg: TutorConfig,
    plan: LearningPlan,
    content: str,
    request_id: str,
    assessment: RuntimeAssessment,
    decision: AdaptiveDecision,
    result: AssessmentResult | None,
    task_status: RequiredTaskStatus,
    assessment_phase: str | None = None,
) -> dict:
    phase = assessment_phase or attempt["engine_state"].get(
        "assessment_phase", ADAPTIVE_LEARNING_PHASE
    )
    _save_decision(conn, attempt["id"], decision)
    conn.execute(
        "UPDATE assignment_attempts_platform SET required_task_status=%s WHERE id=%s",
        (task_status.value, attempt["id"]),
    )
    objective = _objective(plan, assessment.objective_id)
    rag_context = engines.adaptive_rag_context(assignment, objective, decision, content)
    rendered = engines.call("student-agent", "POST", "/internal/platform/adaptive/render", json={
        "session_id": str(attempt["id"]),
        "request_id": request_id,
        "student_message": content,
        "provider": cfg.provider,
        "plan_title": plan.title,
        "decision": decision.model_dump(mode="json"),
        "objective": objective.model_dump(mode="json"),
        "assessment_prompt": _format_prompt(assessment),
        "assessment_result": result.model_dump(mode="json") if result else None,
        "rag_context": rag_context,
    })
    rendered.pop("nav", None)
    rendered.pop("practice_options", None)
    rendered["sources"] = rag_context
    rendered.update({
        "adaptive": True,
        "learning_plan": student_learning_plan(plan),
        "objective_progress": _public_progress(_load_progress(conn, attempt["id"])),
        "current_objective_id": assessment.objective_id,
        "current_assessment_id": assessment.id,
        "latest_decision": decision.model_dump(mode="json"),
        "required_task_status": task_status.value,
        "assessment_phase": phase,
        "phase_label": PHASE_LABELS[phase],
    })
    attempt["required_task_status"] = task_status.value
    return rendered


def _process_message_v2(
    conn,
    assignment: dict,
    attempt: dict,
    content: str,
    request_id: str,
    cfg: TutorConfig,
    plan: LearningPlan,
) -> dict:
    progress_items = _load_progress(conn, attempt["id"])
    current_id = attempt["engine_state"].get("current_assessment_id")
    if not current_id:
        selected = select_objective(plan, progress_items, None).objective
        current_id = select_diagnostic(plan, selected.id).id
    current = _assessment_by_id(plan, current_id)
    task_status = RequiredTaskStatus(attempt.get("required_task_status", "not_started"))
    phase = attempt["engine_state"].get("assessment_phase")
    if phase is None:
        # Existing v2 attempts predate explicit phase sequencing and resume on
        # their existing target rather than restarting baseline diagnostics.
        phase = (
            REQUIRED_TASK_PHASE
            if current.id == plan.required_task.id
            else ADAPTIVE_LEARNING_PHASE
        )

    objective_request = OBJECTIVE_REQUEST_RE.search(content)
    if objective_request and phase == ADAPTIVE_LEARNING_PHASE:
        requested_id = objective_request.group(1)
        selection = select_objective(plan, progress_items, requested_id)
        if selection.request_accepted:
            target = select_diagnostic(plan, selection.objective.id)
            decision = _explicit_decision(
                AdaptiveAction.ASSESS,
                plan,
                target,
                "explicit_eligible_objective_request",
            )
        else:
            target = current
            decision = _explicit_decision(
                AdaptiveAction.FOCUS_REQUIRED,
                plan,
                target,
                "ineligible_objective_request",
                "return_to_current_objective",
            )
        return _render_v2(
            conn, assignment, attempt, cfg, plan, content, request_id,
            target, decision, None, task_status, phase,
        )

    task_submission = current.id == plan.required_task.id
    self_report = not task_submission and bool(SELF_REPORT_RE.search(content))
    objective = _objective(plan, current.objective_id)
    if task_submission:
        result = _required_task_result(current)
    elif self_report:
        result = _self_report_result(current)
    else:
        result = AssessmentResult.model_validate(engines.call(
            "student-agent", "POST", "/internal/platform/adaptive/assess", json={
                "provider": cfg.provider,
                "objective": objective.model_dump(mode="json"),
                "assessment": current.model_dump(mode="json"),
                "student_response": content,
            },
        ))

    previous_action = (attempt["engine_state"].get("latest_decision") or {}).get("action")
    evidence = LearningEvidence(
        student_id=str(attempt["student_id"]),
        course_id=str(assignment["course_id"]),
        assignment_id=str(assignment["id"]),
        attempt_id=str(attempt["id"]),
        objective_id=current.objective_id,
        concept_id=objective.concept_id,
        evidence_type=_evidence_type(plan, current, previous_action, self_report),
        assessment_type=None if task_submission else current.assessment_type,
        assessment_id=current.id,
        assessment_origin=_prompt_source(plan, current),
        assessment_prompt=_format_prompt(current),
        response=content,
        correctness=result.correctness,
        completeness=result.completeness,
        independence=bounded_response_independence(
            result.independence,
            AdaptiveAction(previous_action) if previous_action else None,
        ),
        hints_used=1 if previous_action == AdaptiveAction.HINT.value else 0,
        misconception_code=result.misconception_code,
        misconception_detail=result.misconception_detail,
        assessor_version=result.assessor_version,
    )
    _save_evidence(conn, evidence)
    objective_evidence = _load_evidence(conn, attempt["id"], objective.id)
    updated = derive_objective_progress(objective, objective_evidence)
    _save_progress(conn, attempt["id"], updated)

    if task_submission:
        task_status = RequiredTaskStatus.COMPLETED

    progress_items = _load_progress(conn, attempt["id"])

    if phase == INITIAL_DIAGNOSTIC_PHASE:
        diagnostics = initial_diagnostic_targets(plan)
        index = next(i for i, item in enumerate(diagnostics) if item.id == current.id)
        if index + 1 < len(diagnostics):
            target = diagnostics[index + 1]
            decision = _explicit_decision(
                AdaptiveAction.ASSESS,
                plan,
                target,
                "initial_diagnostic_continues",
            )
            return _render_v2(
                conn, assignment, attempt, cfg, plan, content, request_id,
                target, decision, result, task_status, INITIAL_DIAGNOSTIC_PHASE,
            )

        next_objective = _next_required_objective(plan, progress_items)
        if next_objective is not None:
            next_evidence = _load_evidence(conn, attempt["id"], next_objective.id)
            target = _requirement_target(
                plan,
                next_objective,
                next_evidence,
                select_diagnostic(plan, next_objective.id).id,
            )
            next_progress = next(
                item for item in progress_items if item.objective_id == next_objective.id
            )
            decision = _learning_decision(
                plan, target, next_progress, next_evidence, content
            )
            return _render_v2(
                conn, assignment, attempt, cfg, plan, content, request_id,
                target, decision, result, task_status, ADAPTIVE_LEARNING_PHASE,
            )

        target = final_demonstration_targets(plan)[0]
        decision = _explicit_decision(
            AdaptiveAction.ASSESS,
            plan,
            target,
            "initial_diagnostic_complete",
            "final_demonstration_started",
        )
        return _render_v2(
            conn, assignment, attempt, cfg, plan, content, request_id,
            target, decision, result, task_status, FINAL_DEMONSTRATION_PHASE,
        )

    if phase == FINAL_DEMONSTRATION_PHASE:
        targets = final_demonstration_targets(plan)
        index = next(i for i, item in enumerate(targets) if item.id == current.id)
        if _independent_target_success(evidence, current):
            if index + 1 < len(targets):
                target = targets[index + 1]
                decision = _explicit_decision(
                    AdaptiveAction.ASSESS,
                    plan,
                    target,
                    "final_requirement_demonstrated",
                    "final_demonstration_continues",
                )
                return _render_v2(
                    conn, assignment, attempt, cfg, plan, content, request_id,
                    target, decision, result, task_status, FINAL_DEMONSTRATION_PHASE,
                )
            target = _task_assessment(plan)
            task_status = RequiredTaskStatus.IN_PROGRESS
            decision = _explicit_decision(
                AdaptiveAction.FOCUS_REQUIRED,
                plan,
                target,
                "final_demonstration_complete",
                "required_task_remaining",
            )
            return _render_v2(
                conn, assignment, attempt, cfg, plan, content, request_id,
                target, decision, result, task_status, REQUIRED_TASK_PHASE,
            )

        if self_report:
            decision = _explicit_decision(
                AdaptiveAction.ASSESS,
                plan,
                current,
                "final_demonstration_requires_observed_response",
            )
            return _render_v2(
                conn, assignment, attempt, cfg, plan, content, request_id,
                current, decision, result, task_status, FINAL_DEMONSTRATION_PHASE,
            )

        successful_response = (
            result.correctness == CorrectnessState.CORRECT and not self_report
        )
        decision = choose_adaptive_action(_policy_context(
            plan,
            current,
            updated,
            evidence=() if successful_response else tuple(objective_evidence),
            student_stuck=bool(STUCK_RE.search(content)),
            needs_explanation=result.correctness == CorrectnessState.INCORRECT,
            needs_practice=(
                result.correctness == CorrectnessState.PARTIAL and not self_report
            ),
            continue_assessment=successful_response,
            required_work_remaining=True,
            minimum_path_requested=bool(MINIMUM_PATH_RE.search(content)),
            scoped_exploration_requested=bool(SCOPED_EXPLORATION_RE.search(content)),
        ))
        return _render_v2(
            conn, assignment, attempt, cfg, plan, content, request_id,
            current, decision, result, task_status, FINAL_DEMONSTRATION_PHASE,
        )

    if phase == REQUIRED_TASK_PHASE:
        decision = _explicit_decision(
            AdaptiveAction.CHALLENGE,
            plan,
            current,
            "required_task_submitted",
        )
        return _render_v2(
            conn, assignment, attempt, cfg, plan, content, request_id,
            current, decision, result, task_status, REQUIRED_TASK_PHASE,
        )

    target = current
    if result.correctness == CorrectnessState.CORRECT and not self_report:
        if updated.status == ObjectiveStatus.DEMONSTRATED:
            next_objective = _next_required_objective(plan, progress_items)
            if next_objective:
                target = select_diagnostic(plan, next_objective.id)
            elif task_status != RequiredTaskStatus.COMPLETED and current.id != plan.required_task.id:
                target = final_demonstration_targets(plan)[0]
                decision = _explicit_decision(
                    AdaptiveAction.ASSESS,
                    plan,
                    target,
                    "required_objectives_demonstrated",
                    "final_demonstration_started",
                )
                return _render_v2(
                    conn, assignment, attempt, cfg, plan, content, request_id,
                    target, decision, result, task_status, FINAL_DEMONSTRATION_PHASE,
                )
            else:
                target = current
        else:
            target = _requirement_target(
                plan, objective, objective_evidence, current.id
            )

    successful_response = (
        result.correctness == CorrectnessState.CORRECT and not self_report
    )
    needs_independent_reassessment = (
        successful_response
        and updated.status != ObjectiveStatus.DEMONSTRATED
        and (
            target.id != current.id
            or evidence.completeness != CompletenessState.COMPLETE
            or evidence.independence != IndependenceLevel.INDEPENDENT
        )
    )
    # A correct guided/supported response ends the active remediation streak,
    # but remains in learner history and cannot demonstrate the objective. The
    # next turn is an explicit reassessment with no support-derived cap.
    policy_evidence = () if successful_response else tuple(objective_evidence)

    context = _policy_context(
        plan,
        target,
        updated,
        evidence=policy_evidence,
        student_stuck=bool(STUCK_RE.search(content)),
        needs_explanation=result.correctness == CorrectnessState.INCORRECT,
        needs_practice=(
            result.correctness == CorrectnessState.PARTIAL and not self_report
        ),
        continue_assessment=(
            needs_independent_reassessment
        ),
        required_work_remaining=task_status != RequiredTaskStatus.COMPLETED,
        prefer_challenge=(
            updated.status == ObjectiveStatus.DEMONSTRATED
            and _next_required_objective(plan, progress_items) is None
            and task_status == RequiredTaskStatus.COMPLETED
        ),
        minimum_path_requested=bool(MINIMUM_PATH_RE.search(content)),
        scoped_exploration_requested=bool(SCOPED_EXPLORATION_RE.search(content)),
    )
    decision = choose_adaptive_action(context)
    return _render_v2(
        conn, assignment, attempt, cfg, plan, content, request_id,
        target, decision, result, task_status, ADAPTIVE_LEARNING_PHASE,
    )


def process_message(conn, assignment: dict, attempt: dict, content: str, request_id: str) -> dict:
    cfg = _config(assignment)
    plan = cfg.learning_plan
    assert plan is not None
    if plan.schema_version == 2:
        return _process_message_v2(
            conn, assignment, attempt, content, request_id, cfg, plan
        )
    return _process_message_legacy(
        conn, assignment, attempt, content, request_id, cfg, plan
    )
