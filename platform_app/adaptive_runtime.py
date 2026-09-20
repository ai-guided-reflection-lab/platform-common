"""Phase 1 orchestration for one platform-owned adaptive tutor flow."""

from __future__ import annotations

import re
from uuid import uuid4

from psycopg.types.json import Jsonb

from platform_app import engines
from platform_app.adaptive import (
    PolicyContext,
    bounded_response_independence,
    choose_adaptive_action,
    derive_objective_progress,
)
from platform_app.schemas import (
    AdaptiveAction,
    AdaptiveDecision,
    AssessmentPrompt,
    AssessmentResult,
    AssessmentType,
    CompletenessState,
    CorrectnessState,
    EvidenceType,
    IndependenceLevel,
    LearningEvidence,
    LearningPlan,
    ObjectiveProgress,
    RequiredTaskStatus,
    TutorConfig,
)

SELF_REPORT_RE = re.compile(r"\b(i already know|i know this|i understand this|this is easy)\b", re.I)
MINIMUM_PATH_RE = re.compile(r"\b(only have|just have|in a hurry|minimum|fastest|just get this done)\b", re.I)
CURIOUS_RE = re.compile(r"\b(inheritance|outside today|extra topic)\b", re.I)
STUCK_RE = re.compile(r"\b(i don'?t know|no idea|stuck|not sure)\b", re.I)


def diagnostics(plan: LearningPlan) -> list[AssessmentPrompt]:
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


def _format_prompt(item: AssessmentPrompt) -> str:
    return f"```python\n{item.code}\n```\n\n{item.prompt}" if item.code else item.prompt


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
                  objective_id,concept_id,evidence_type,assessment_type,response,correctness,
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
            evidence_type,assessment_type,response,correctness,completeness,independence,
            hints_used,misconception_code,misconception_detail,assessor_version,created_at)
           VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
        (uuid4(), evidence.student_id, evidence.course_id, evidence.assignment_id,
         evidence.attempt_id, evidence.objective_id, evidence.concept_id,
         evidence.evidence_type.value, evidence.assessment_type.value if evidence.assessment_type else None,
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
           (id,attempt_id,objective_id,action,reason_codes,policy_version,resume_objective_id)
           VALUES (%s,%s,%s,%s,%s,%s,%s)""",
        (uuid4(), attempt_id, decision.objective_id, decision.action.value,
         Jsonb(decision.reason_codes), decision.policy_version, decision.resume_objective_id),
    )


def _public_progress(items: list[ObjectiveProgress]) -> list[dict]:
    return [item.model_dump(mode="json") for item in items]


def start(conn, assignment: dict, attempt: dict) -> dict:
    cfg = _config(assignment)
    plan = cfg.learning_plan
    assert plan is not None
    progress = _initialize_progress(conn, attempt, assignment, plan)
    assessment = diagnostics(plan)[0]
    decision = choose_adaptive_action(PolicyContext(assessment.objective_id, progress[0]))
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
        "learning_plan": plan.model_dump(mode="json"),
        "objective_progress": _public_progress(progress),
        "current_objective_id": assessment.objective_id,
        "current_assessment_id": assessment.id,
        "latest_decision": decision.model_dump(mode="json"),
        "required_task_status": RequiredTaskStatus.NOT_STARTED.value,
    })
    return rendered


def _self_report_result(assessment: AssessmentPrompt) -> AssessmentResult:
    return AssessmentResult(
        objective_id=assessment.objective_id,
        assessment_type=assessment.assessment_type,
        correctness=CorrectnessState.PARTIAL,
        completeness=CompletenessState.INCOMPLETE,
        independence=IndependenceLevel.INDEPENDENT,
        rationale="The message is a self-report, not demonstrated evidence.",
        assessor_version="application-self-report-v1",
    )


def _evidence_type(
    assessment: AssessmentPrompt,
    previous_action: str | None,
    self_report: bool,
) -> EvidenceType:
    if self_report:
        return EvidenceType.SELF_REPORT
    if assessment.id == "TASK-1":
        return EvidenceType.REQUIRED_TASK_SUBMISSION
    if previous_action in {AdaptiveAction.EXPLAIN.value, AdaptiveAction.HINT.value, AdaptiveAction.REMEDIATE.value}:
        return EvidenceType.GUIDED_RESPONSE
    if previous_action == AdaptiveAction.PRACTICE.value:
        return EvidenceType.PRACTICE_ATTEMPT
    return EvidenceType.DIAGNOSTIC_RESPONSE


def process_message(conn, assignment: dict, attempt: dict, content: str, request_id: str) -> dict:
    cfg = _config(assignment)
    plan = cfg.learning_plan
    assert plan is not None
    items = diagnostics(plan)
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
        evidence_type=_evidence_type(assessment, previous_action, self_report),
        assessment_type=assessment.assessment_type, response=content,
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
    decision = choose_adaptive_action(PolicyContext(
        objective_id=assessment.objective_id,
        progress=updated,
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
        scoped_exploration_requested=bool(CURIOUS_RE.search(content)),
    ))
    if successful and next_assessment.id != assessment.id:
        render_assessment = next_assessment
    else:
        render_assessment = assessment
    _save_decision(conn, attempt["id"], decision)
    conn.execute("UPDATE platform_attempts SET required_task_status=%s WHERE id=%s", (task_status.value, attempt["id"]))

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
    all_progress = _load_progress(conn, attempt["id"])
    rendered.update({
        "adaptive": True, "learning_plan": plan.model_dump(mode="json"),
        "objective_progress": _public_progress(all_progress),
        "current_objective_id": render_assessment.objective_id,
        "current_assessment_id": render_assessment.id,
        "latest_decision": decision.model_dump(mode="json"),
        "required_task_status": task_status.value,
    })
    attempt["required_task_status"] = task_status.value
    return rendered
