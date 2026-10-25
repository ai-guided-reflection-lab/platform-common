from __future__ import annotations

import json
import hashlib
import os
import re
import secrets
import shutil
import httpx
from pydantic import BaseModel
from contextlib import asynccontextmanager
from pathlib import Path
from uuid import uuid4

from fastapi import Depends, FastAPI, File, Header, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from .auth import current_user, require_instructor, require_student
from .config import AI_MODE, INSTRUCTOR_ORIGIN, STUDENT_ORIGIN, UPLOAD_DIR
from .db import (
    connection, initialize, now, row_dict, load_attempt_for_turn, save_lesson_turn,
    list_attempt_messages, load_attempt_progress_data, load_attempt_learning_state,
    reset_attempt_for_restart,
)
from .lesson_content import configuration_issues
from . import lesson_flow
from .learning_flow import place_student, select_diagnostic_questions
from .openai_client import assess_response, generate_learning_plan, infer_document_context, repair_learning_plan, runtime_ai_mode, tutor_reply
from .rag import add_document, add_url_document, retrieve, preview_document, preview_url_document
from .resource_discovery import discover_resources, read_resource_excerpts, verify_resources
from .schemas import (
    AssignmentInput,
    ResourceURLInput,
    GeneratePlanInput,
    DocumentDraftInput,
    LearningPlan,
    LearningTurn,
    MessageInput,
    PlatformStudentInput,
    QuizSubmission,
    StudyCompletion,
    TaskSubmission,
)


@asynccontextmanager
async def lifespan(_: FastAPI):
    initialize()
    yield


app = FastAPI(
    title="Adaptive Learning Standalone API",
    version="1.0.0",
    lifespan=lifespan,
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[INSTRUCTOR_ORIGIN, STUDENT_ORIGIN, "http://localhost:5173", "http://localhost:5174"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class LabCode(BaseModel):
    code: str


@app.post("/api/lab/redeem")
def redeem_lab_code(body: LabCode, user=Depends(current_user)):
    from .lab import redeem
    return redeem(body.code, user)


class LabJoin(BaseModel):
    name: str


@app.post("/api/lab/sessions", status_code=201)
def join_lab(body: LabJoin):
    from .lab import create_session
    return create_session(body.name)


@app.get("/api/lab/session")
def lab_session(user=Depends(current_user)):
    if not user.get("lab_participant"):
        raise HTTPException(401, "A lab session is required.")
    return {"id": user["id"], "display_name": user["display_name"], "role": "student"}


@app.middleware("http")
async def platform_service_access(request, call_next):
    if os.getenv("ADAPTIVE_PLATFORM_ONLY", "false").lower() in {"true", "1", "yes"} and request.url.path.startswith("/api/") and request.url.path != "/api/health":
        token = os.getenv("PLATFORM_SERVICE_TOKEN", "")
        supplied = request.headers.get("X-Platform-Service", "")
        if not token or not secrets.compare_digest(supplied, token):
            return JSONResponse({"detail": "Use the signed-in platform to access this learning service."}, status_code=401)
    return await call_next(request)


def _plan(row: dict) -> dict:
    plan = json.loads(row["learning_plan"])
    plan.setdefault("flow_version", 1)
    return plan


def _assignment(assignment_id: str) -> dict:
    with connection() as conn:
        item = row_dict(conn.execute("SELECT * FROM assignments WHERE id=?", (assignment_id,)).fetchone())
    if item is None:
        raise HTTPException(404, "Assignment not found.")
    return item


def _instructor_assignment(assignment_id: str, user: dict) -> dict:
    require_instructor(user)
    item = _assignment(assignment_id)
    if item["instructor_id"] != user["id"]:
        raise HTTPException(404, "Assignment not found.")
    return item


def _student_assignment(assignment_id: str, user: dict) -> dict:
    require_student(user)
    if user.get("lab_participant"):
        from .lab import instructor_id
        with connection() as conn:
            item = conn.execute("SELECT a.* FROM assignments a JOIN lab_enrollments e ON e.assignment_id=a.id WHERE a.id=? AND a.status='published' AND a.instructor_id=? AND e.student_id=?",
                                (assignment_id, instructor_id(), user["id"])).fetchone()
            if item is None:
                raise HTTPException(404, "Assignment not found.")
            conn.execute("INSERT INTO recipients(assignment_id,student_id) VALUES (?,?) ON CONFLICT DO NOTHING",
                         (assignment_id, user["id"]))
        return dict(item)
    with connection() as conn:
        item = row_dict(
            conn.execute(
                """SELECT a.* FROM assignments a
                   JOIN recipients r ON r.assignment_id=a.id
                   WHERE a.id=? AND a.status='published' AND r.student_id=?""",
                (assignment_id, user["id"]),
            ).fetchone()
        )
    if item is None:
        raise HTTPException(404, "Assignment not found.")
    return item


def _assignment_public(item: dict, instructor_view: bool = False) -> dict:
    result = {key: value for key, value in item.items() if key != "learning_plan"}
    plan = _plan(item)
    question_bank = plan.get("diagnostic_quiz", [])
    diagnostic_questions = question_bank if plan.get("flow_version") == 2 else (select_diagnostic_questions(question_bank) if len(question_bank) >= 5 else [])
    plan = {**plan, "diagnostic_quiz": diagnostic_questions}
    if not instructor_view:
        public_quiz = [
            {key: value for key, value in question.items() if key not in {"correct_index", "explanation"}}
            for question in diagnostic_questions
        ]
        plan = {
            **plan,
            "objectives": [
                {key: value for key, value in objective.items() if key != "diagnostic_prompt"}
                for objective in plan["objectives"]
            ],
            "diagnostic_quiz": public_quiz,
        }
        plan.pop("learning_assets", None)
        if plan.get("flow_version") == 2:
            plan["diagnostic_quiz"] = []
            plan.pop("approved_material", None)
            for objective in plan["objectives"]:
                objective.pop("rubric", None)
                objective.pop("misconceptions", None)
    else:
        result["configuration_issues"] = configuration_issues(plan) if plan.get("flow_version") == 2 else ["This earlier lesson uses the previous flow. Configure and publish a new lesson to use the five-stage conversation."]
    result["learning_plan"] = plan
    return result


def _documents(assignment_id: str) -> list[dict]:
    with connection() as conn:
        rows = conn.execute(
            """SELECT d.id,d.filename,d.content_type,d.created_at,count(c.id) AS chunk_count
               FROM documents d LEFT JOIN chunks c ON c.document_id=d.id
               WHERE d.assignment_id=? GROUP BY d.id ORDER BY d.created_at""",
            (assignment_id,),
        ).fetchall()
    return [dict(row) for row in rows]


def _source_metadata(sources: list[dict]) -> list[dict]:
    """Expose one citation per document even when several chunks were retrieved."""
    result = []
    seen = set()
    for source in sources:
        if source["document_id"] in seen:
            continue
        seen.add(source["document_id"])
        result.append({key: value for key, value in source.items() if key != "content"})
    return result


def _objective_progress(attempt_id: str, plan: dict) -> list[dict]:
    with connection() as conn:
        evidence = load_attempt_progress_data(conn, attempt_id)
    latest = {row["objective_id"]: dict(row) for row in evidence}
    demonstrated_ids = set()
    if plan.get("flow_version") == 2:
        with connection() as conn:
            saved = load_attempt_learning_state(conn, attempt_id)
        if saved:
            coverage_state = json.loads(saved["learning_state"])
            lesson_flow.refresh_concept_progress(coverage_state.get("lesson_snapshot") or plan, coverage_state)
            demonstrated_ids = set(coverage_state["demonstrated"])
    return [
        {
            "objective_id": objective["id"],
            "title": objective["title"],
            "status": "demonstrated" if objective["id"] in demonstrated_ids or (plan.get("flow_version") != 2 and latest.get(objective["id"], {}).get("demonstrated")) else ("in_progress" if objective["id"] in latest else "not_started"),
            "score": latest.get(objective["id"], {}).get("score"),
            "rationale": latest.get(objective["id"], {}).get("rationale"),
        }
        for objective in plan["objectives"]
    ]


def _build_attempt_response(attempt: dict, plan: dict) -> dict:
    saved_state = json.loads(attempt.get("learning_state") or "{}")
    if saved_state.get("version") == 2:
        plan = saved_state["lesson_snapshot"]
    with connection() as conn:
        messages = [
            {**dict(row), "sources": json.loads(row["sources"])}
            for row in list_attempt_messages(conn, attempt["id"])
        ]
    current = attempt["current_objective"]
    result = {
        **attempt,
        "quiz_answers": json.loads(attempt.get("quiz_answers") or "[]"),
        "learning_state": json.loads(attempt.get("learning_state") or "{}"),
        "messages": messages,
        "objective_progress": _objective_progress(attempt["id"], plan),
        "current_objective_id": plan["objectives"][current]["id"] if current < len(plan["objectives"]) else None,
    }
    if saved_state.get("version") == 2:
        result["learning_state"] = lesson_flow.public_state(saved_state)
        result["quiz_results"] = [
            {"id": entry["question_id"], "question": entry["question"], "selected_index": entry["option_index"],
             "correct_index": entry["correct_index"], "correct": entry["correct"], "explanation": entry["explanation_of_answer"],
             "confidence": entry["confidence"], "reasoning": entry["reasoning"], "assistance_used": entry["assistance_used"]}
            for entry in saved_state["diagnostic"]
        ] if saved_state.get("diagnostic_complete") else []
        return result
    if attempt.get("quiz_score") is not None:
        answers = result["quiz_answers"]
        result["quiz_results"] = [
            {
                "id": question["id"],
                "selected_index": answers[index] if index < len(answers) else None,
                "correct_index": question["correct_index"],
                "correct": index < len(answers) and answers[index] == question["correct_index"],
                "explanation": question["explanation"],
            }
            for index, question in enumerate(plan.get("diagnostic_quiz", []))
        ]
    return result


# LEGACY lesson helpers; shared response/persistence helpers above serve both versions.
def _learning_asset(plan: dict, objective_id: str) -> dict | None:
    return next(
        (item for item in plan.get("learning_assets", []) if item["objective_id"] == objective_id),
        None,
    )


def _path_prompt(
    plan: dict,
    objective_index: int,
    learning_path: str,
    objective_paths: dict[str, str] | None = None,
) -> tuple[str, dict]:
    objective = plan["objectives"][objective_index]
    asset = _learning_asset(plan, objective["id"])
    paths = objective_paths or {}
    current_path = paths.get(objective["id"], learning_path)
    example = (
        f"Example: {asset['worked_example']}\n\n"
        + (f"Analogy: {asset['analogy']}\n\n" if asset.get("analogy") else "")
    ) if asset else ""
    state = {
        "mode": "demonstration",
        "practice_index": 0,
        "practice_level": None,
        "failures": 0,
        "current_path": current_path,
        "objective_paths": paths,
    }
    if current_path == "foundational" and asset:
        state.update(mode="practice", practice_level="foundational")
        prompt = (
            f"Let’s build the foundation first.\n\n{asset['explanation']}\n\n"
            f"{example}"
            f"Practice: {asset['foundational'][0]['prompt']}"
        )
        return prompt, state
    if current_path == "standard" and asset:
        state.update(mode="practice", practice_level="standard")
        return f"{example}Practice: {asset['standard'][0]['prompt']} Explain your reasoning with an example.", state
    if current_path == "accelerated" and asset:
        return f"Challenge: {asset['accelerated'][0]['prompt']}\n\n{example}Explain your reasoning with a different example.", state
    return objective["diagnostic_prompt"], state


def _concept_analytics(plan: dict, state: dict) -> list[dict]:
    """Summarize observed concept evidence, never inferred ability or personality."""
    import copy
    state = copy.deepcopy(state)
    lesson_flow.refresh_concept_progress(plan, state)
    results = []
    seen = set()
    for question in plan.get("diagnostic_quiz", []):
        oid, concept = question["objective_id"], question["concept"]
        if (oid, concept) in seen:
            continue
        seen.add((oid, concept))
        diagnostic = [item for item in state.get("diagnostic", []) if item.get("objective_id") == oid and item.get("concept") == concept] if state.get("diagnostic_complete") else []
        history = []
        for record in state.get("practice_history", []):
            recorded_concept = record.get("concept")
            if not recorded_concept:
                try:
                    _, level, index = record["activity_id"].rsplit(":", 2)
                    recorded_concept = lesson_flow.asset_for(plan, record["objective_id"])[level][int(index)]["concept"]
                except (KeyError, ValueError, IndexError, StopIteration):
                    continue
            if record.get("objective_id") == oid and recorded_concept == concept:
                history.append(record)
        assessed = [record for record in history if record.get("assessment_status") not in {"grader_unavailable", "grader_error"} and record.get("category") not in {"grader_unavailable", "grader_error"}]
        latest = assessed[-1] if assessed else None
        checks = state["concept_checks"].get(oid, {}).get(concept, 0)
        wrong = any(not entry.get("correct") for entry in diagnostic)
        diagnostic_gap = next((entry.get("reasoning", {}) for entry in diagnostic if entry.get("reasoning", {}).get("category") in {"partial_understanding", "identifiable_misconception"}), None)
        if latest and latest.get("category") != "sound_reasoning":
            status = "needs_support"
            next_action = latest.get("rationale") or "Ask for the missing reasoning in a fresh case."
        elif checks >= 2:
            status, next_action = "demonstrated", "Offer a transfer challenge or revisit another concept."
        elif latest or checks:
            status, next_action = "developing", "Use another distinct independent case to check this concept."
        elif wrong or diagnostic_gap:
            status = "needs_support"
            next_action = diagnostic_gap.get("feedback") if diagnostic_gap else "Use the approved counterexample, then check a fresh case." if any(entry.get("need") == "counterexample_revision" for entry in diagnostic) else "Explain this concept with a worked example, then check a fresh case."
        elif diagnostic:
            status, next_action = "developing", "Check the reasoning in fresh independent cases; a correct selection alone is not mastery."
        else:
            status, next_action = "not_assessed", "Collect a diagnostic answer or independent practice response."
        last_issue = history[-1] if history and history[-1].get("assessment_status") in {"grader_unavailable", "grader_error"} else None
        results.append({"objective_id": oid, "objective_title": lesson_flow.objective_for(plan, oid)["title"],
            "concept": concept, "status": status, "independent_checks": min(checks, 2),
            "practice_responses": len(history), "assisted_responses": sum(bool(record.get("assisted")) for record in history),
            "diagnostic_correct": sum(bool(entry.get("correct")) for entry in diagnostic), "diagnostic_total": len(diagnostic),
            "confident_errors": sum(not entry.get("correct") and entry.get("confidence") == "high" for entry in diagnostic),
            "earlier_misconceptions": list(dict.fromkeys(entry["misconception"] for entry in diagnostic if entry.get("misconception"))),
            "latest_category": latest.get("category") if latest else None,
            "latest_response": latest.get("response") if latest else None,
            "latest_feedback": latest.get("rationale") if latest else diagnostic_gap.get("feedback") if diagnostic_gap else None,
            "assessment_source": latest.get("assessment_source") if latest else None,
            "grader_issue": last_issue.get("rationale") if last_issue else None, "next_action": next_action})
    return results


def _student_summary(student: dict, attempt: dict, evidence: list[dict], quiz_results: list[dict], concepts=None) -> dict:
    state = attempt.get("learning_state", {})
    if state.get("bounded_flow"):
        assessment = state.get("application_assessment") or {}
        return {
            "overview": f"{student['display_name']}: {state['stage']}. First-attempt quiz score: {attempt.get('quiz_score')}/5.",
            "strengths": ["Completed the application submission."] if state["stage"] == "completed" else ["Application task not yet completed."],
            "weaknesses": [assessment.get("feedback") or "No application feedback yet."],
            "improvements": ["Review the application feedback against the instructor's ending outcomes."],
        }
    if concepts is not None:
        demonstrated = [item for item in concepts if item["status"] == "demonstrated"]
        gaps = [item for item in concepts if item["status"] == "needs_support"]
        developing = [item for item in concepts if item["status"] == "developing"]
        reflections = attempt.get("learning_state", {}).get("reflections", [])
        return {
            "overview": f"{student['display_name']} has demonstrated {len(demonstrated)} of {len(concepts)} concepts through independent practice. {len(gaps)} need support and {len(developing)} are developing. Diagnostic: {attempt.get('quiz_score') if attempt.get('quiz_score') is not None else 'not completed'}. {len(reflections)} reflections recorded.",
            "strengths": [item["concept"] + " — two distinct independent checks." for item in demonstrated] or ["Independent understanding has not yet been demonstrated."],
            "weaknesses": [item["concept"] + " — " + (item["latest_feedback"] or "The diagnostic identified a gap; fresh practice is needed.") for item in gaps] or ["No current assessed gaps; unassessed concepts still need evidence."],
            "improvements": [item["concept"] + " — " + item["next_action"] for item in [*gaps, *developing, *[c for c in concepts if c["status"] == "not_assessed"]]][:4] or ["Offer a transfer challenge to extend demonstrated understanding."],
        }
    demonstrated = {}
    completed_ids = {item["objective_id"] for item in attempt["objective_progress"] if item["status"] == "demonstrated"}
    needs_support = []
    for entry in evidence:
        if entry["demonstrated"] and entry["objective_id"] in completed_ids:
            demonstrated[entry["objective_id"]] = entry
        elif entry["rationale"] not in needs_support:
            needs_support.append(entry["rationale"])

    strengths = [
        f"Demonstrated {entry['objective_title']} with an assessment score of {round(entry['score'] * 100)}%."
        for entry in demonstrated.values()
    ]
    correct_questions = [result["question"] for result in quiz_results if result["correct"]]
    if correct_questions:
        strengths.append(
            f"Answered {len(correct_questions)} of {len(quiz_results)} diagnostic questions correctly."
        )

    incorrect = [result for result in quiz_results if not result["correct"]]
    weaknesses = [f"Diagnostic gap: {result['question']}" for result in incorrect[:3]]
    weaknesses.extend(
        f"Earlier response gap: {rationale}" for rationale in needs_support[: max(0, 3 - len(weaknesses))]
    )
    improvements = []
    for result in incorrect:
        suggestion = result["explanation"]
        if suggestion not in improvements:
            improvements.append(suggestion)
        if len(improvements) == 3:
            break
    if len(improvements) < 3:
        for rationale in needs_support:
            if rationale not in improvements:
                improvements.append(rationale)
            if len(improvements) == 3:
                break

    objective_count = len(attempt["objective_progress"])
    completed_count = sum(item["status"] == "demonstrated" for item in attempt["objective_progress"])
    final_note = "and submitted the final task" if attempt.get("required_task_submission") else "and has not submitted the final task yet"
    return {
        "overview": (
            f"{student['display_name']} scored {attempt.get('quiz_score', 0)}/5 on the diagnostic, "
            f"followed the {attempt.get('learning_path') or 'standard'} path, demonstrated "
            f"{completed_count} of {objective_count} objectives, {final_note}."
        ),
        "strengths": strengths or ["No demonstrated strengths are available yet."],
        "weaknesses": weaknesses or ["No specific learning gaps are currently recorded."],
        "improvements": improvements or ["Continue applying each concept to a new example and justify the reasoning."],
    }


from .common_rag_api import router as common_rag_router
app.include_router(common_rag_router)
from .platform_lessons import router as platform_lessons_router
app.include_router(platform_lessons_router)


@app.get("/api/health")
def health():
    return {"status": "ok", "ai_mode": runtime_ai_mode(), "configured_ai_mode": AI_MODE}


@app.post("/internal/platform/students/resolve")
def resolve_platform_student(
    body: PlatformStudentInput,
    x_platform_service: str | None = Header(default=None),
):
    expected = os.getenv("PLATFORM_SERVICE_TOKEN", "")
    if not expected or not x_platform_service or not secrets.compare_digest(expected, x_platform_service):
        raise HTTPException(401, "Valid platform service credentials are required.")
    with connection() as conn:
        row = conn.execute(
            """INSERT INTO users(id,email,display_name,role) VALUES (?,?,?,'student')
               ON CONFLICT (email) DO UPDATE SET display_name=excluded.display_name
               RETURNING id,email,display_name,role""",
            (body.platform_user_id, body.email.strip().lower(), body.display_name.strip()),
        ).fetchone()
    return dict(row)


@app.get("/api/demo/users")
def demo_users(role: str | None = None):
    with connection() as conn:
        if role:
            rows = conn.execute("SELECT * FROM users WHERE role=? ORDER BY display_name", (role,)).fetchall()
        else:
            rows = conn.execute("SELECT * FROM users ORDER BY role,display_name").fetchall()
    return [dict(row) for row in rows]


@app.get("/api/me")
def me(user=Depends(current_user)):
    return user


@app.get("/api/instructor/assignments")
def instructor_assignments(user=Depends(current_user)):
    require_instructor(user)
    with connection() as conn:
        rows = conn.execute(
            """SELECT a.*,
                 (SELECT count(*) FROM recipients r WHERE r.assignment_id=a.id) AS recipient_count,
                 (SELECT count(*) FROM attempts t WHERE t.assignment_id=a.id AND t.status='completed') AS completed_count
               FROM assignments a WHERE a.instructor_id=? ORDER BY a.created_at DESC""",
            (user["id"],),
        ).fetchall()
    from .lab import assignment_code
    items = []
    for row in rows:
        item = _assignment_public(dict(row), True)
        if row["status"] == "published":
            item["access_code"] = assignment_code(row["id"])
        items.append(item)
    return items


@app.post("/api/instructor/generate-plan")
def generate_plan(body: GeneratePlanInput, user=Depends(current_user)):
    require_instructor(user)
    try:
        topic = body.topic.strip()
        resources = [r.model_dump() for r in body.study_resources]
        generated = generate_learning_plan(topic, body.course_level.strip(),
            read_resource_excerpts(resources) if runtime_ai_mode() in {"openai", "groq"} else [],
            approved_material=body.approved_material, objective_descriptions=body.objective_descriptions,
            study_resources=resources, intended_difficulty=body.intended_difficulty,
            prerequisite_knowledge=body.prerequisite_knowledge)
        return LearningPlan.model_validate(generated)
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(502, f"The learning plan could not be generated: {exc}") from exc


@app.post("/api/instructor/documents/preview")
async def instructor_document_preview(file: UploadFile = File(...), user=Depends(current_user)):
    require_instructor(user)
    return await preview_document(file)


@app.post("/api/instructor/documents/url-preview")
async def instructor_url_preview(body: ResourceURLInput, user=Depends(current_user)):
    require_instructor(user)
    return await preview_url_document(body.url.strip())


def _document_plan(material: str, filename: str, *, starting_point: str = "", ending_point: str = "") -> dict:
    stage = "document setup"
    try:
        authoring_material = material
        if starting_point and ending_point:
            authoring_material = f"Instructor lesson boundaries — start: {starting_point}; end: {ending_point}\n\nCourse material:\n{material}"
        context = infer_document_context(authoring_material, filename)
        if ending_point:
            context["objective_descriptions"] = [ending_point]
        # A single optional lookup budget across topic and prerequisite readings.
        topic_candidates = discover_resources(context["topic"])
        prerequisite_topic = context.get("prerequisite_knowledge") or starting_point
        prerequisite_candidates = discover_resources(prerequisite_topic) if starting_point and ending_point else []
        candidates = topic_candidates[:2] + prerequisite_candidates[:1] if prerequisite_candidates else topic_candidates[:3]
        verified = verify_resources(candidates, context["topic"]) if candidates else []
        topic_titles = {item["title"] for item in topic_candidates}
        prerequisite_titles = {item["title"] for item in prerequisite_candidates}
        resources = [item for item in verified if item["title"] in topic_titles]
        prerequisite_resources = [item for item in verified if item["title"] in prerequisite_titles]
        stage = "lesson generation"
        plan = generate_learning_plan(context["topic"], context.get("course_level", "Undergraduate"),
            [], approved_material=material,
            objective_descriptions=context["objective_descriptions"], study_resources=resources,
            intended_difficulty=context.get("intended_difficulty", "Undergraduate"),
            prerequisite_knowledge=context.get("prerequisite_knowledge", "None"))
        reading_note = "Uploaded course material is the primary source. External readings are optional."
        if not resources:
            reading_note += " No supplemental topic readings were verified; review the generated lesson against the uploaded material and add optional links if desired."
        if starting_point and ending_point and not prerequisite_resources:
            reading_note += " No prerequisite links were verified. Review the prerequisite assumptions and add supporting course material if students need it."
        plan.update(material_first=True, study_resources=resources, supplemental_reading_note=reading_note)
        issues = configuration_issues({**plan, "content_approved": True})
        if issues:
            stage = "lesson validation repair"
            plan = repair_learning_plan(plan, issues)
            issues = configuration_issues({**plan, "content_approved": True})
        if issues:
            raise ValueError("The generated lesson needs another attempt: " + " ".join(issues))
        if starting_point and ending_point:
            plan.update(bounded_flow=True, starting_point=starting_point, ending_point=ending_point,
                        prerequisite_resources=prerequisite_resources,
                        application_rubric=plan["objectives"][0]["rubric"])
            plan = LearningPlan.model_validate(plan).model_dump()
        return plan
    except httpx.HTTPStatusError as exc:
        if exc.response.status_code == 413:
            detail = f"The {stage} request is too large for the configured AI provider. Retrying the same document will not reduce its size. Use a shorter document or a provider/model with a higher token allowance."
            try:
                provider_error = exc.response.json().get("error", {})
                message = provider_error.get("message", "")
                limit = re.search(r"\bLimit\s+(\d+)", message)
                requested = re.search(r"\bRequested\s+(\d+)", message)
                if limit and requested:
                    detail += f" Token allowance: {limit.group(1)}; requested: {requested.group(1)}."
            except (ValueError, AttributeError, TypeError):
                pass
        elif exc.response.status_code == 429:
            detail = f"The AI provider rate limit was reached during {stage}. Your document is still selected. Wait for the provider cooldown before trying again; the API key does not need changing."
        elif exc.response.status_code == 400:
            detail = exc.response.json().get("error", {}).get("message", "The AI provider rejected the draft request.")
        else:
            detail = f"The AI provider returned {exc.response.status_code}. Check the configured provider and retry."
        raise HTTPException(502, f"Could not prepare the document for review: {detail}") from exc
    except Exception as exc:
        raise HTTPException(502, f"Could not prepare the document for review: {exc}") from exc


@app.post("/api/instructor/document-draft")
def document_draft(body: DocumentDraftInput, user=Depends(current_user)):
    require_instructor(user)
    return _document_plan(body.material, body.filename)


@app.post("/api/instructor/assignments/{assignment_id}/prepare-review")
def prepare_document_review(assignment_id: str, user=Depends(current_user)):
    item = _instructor_assignment(assignment_id, user)
    if item["status"] != "draft":
        raise HTTPException(409, "Only a draft can be prepared for review.")
    material = _plan(item).get("approved_material", "")
    if len(material.strip()) < 30:
        raise HTTPException(422, "Upload a readable course document first.")
    documents = _documents(assignment_id)
    plan = _document_plan(material, documents[0]["filename"] if documents else item["title"])
    with connection() as conn:
        conn.execute("UPDATE assignments SET title=?,learning_plan=? WHERE id=?", (plan["title"], json.dumps(plan), assignment_id))
        count = conn.execute("SELECT count(*) AS total FROM recipients WHERE assignment_id=?", (assignment_id,)).fetchone()["total"]
        if not count:
            conn.executemany("INSERT INTO recipients(assignment_id,student_id) VALUES (?,?)", [(assignment_id, row["id"]) for row in conn.execute("SELECT id FROM users WHERE role='student'").fetchall()])
    return instructor_assignment_detail(assignment_id, user)


@app.post("/api/instructor/assignments", status_code=201)
def create_assignment(body: AssignmentInput, user=Depends(current_user)):
    require_instructor(user)
    assignment_id = str(uuid4())
    with connection() as conn:
        valid_students = {
            row["id"] for row in conn.execute("SELECT id FROM users WHERE role='student'").fetchall()
        }
        selected = set(body.student_ids)
        if not selected.issubset(valid_students):
            raise HTTPException(422, "Every recipient must be a demo student.")
        conn.execute(
            """INSERT INTO assignments(id,instructor_id,title,instructions,status,learning_plan,created_at)
               VALUES (?,?,?,?,?,?,?)""",
            (assignment_id, user["id"], body.title, body.instructions, "draft", body.learning_plan.model_dump_json(), now()),
        )
        conn.executemany(
            "INSERT INTO recipients(assignment_id,student_id) VALUES (?,?)",
            [(assignment_id, student_id) for student_id in body.student_ids],
        )
    return instructor_assignment_detail(assignment_id, user)


@app.get("/api/instructor/assignments/{assignment_id}")
def instructor_assignment_detail(assignment_id: str, user=Depends(current_user)):
    item = _instructor_assignment(assignment_id, user)
    with connection() as conn:
        recipients = [
            dict(row)
            for row in conn.execute(
                """SELECT u.id,u.display_name,u.email FROM recipients r
                   JOIN users u ON u.id=r.student_id WHERE r.assignment_id=? ORDER BY u.display_name""",
                (assignment_id,),
            ).fetchall()
        ]
    result = {**_assignment_public(item, True), "students": recipients, "documents": _documents(assignment_id)}
    if item["status"] == "published":
        from .lab import assignment_code
        result["access_code"] = assignment_code(assignment_id)
    return result


@app.post("/api/instructor/assignments/{assignment_id}/refresh-resources")
def refresh_assignment_resources(assignment_id: str, user=Depends(current_user)):
    item = _instructor_assignment(assignment_id, user)
    if item["status"] != "draft":
        raise HTTPException(409, "Published lesson resources are frozen. Prepare a new draft to change readings.")
    plan = _plan(item)
    topic = plan.get("topic") or plan.get("title") or item["title"]
    plan["study_resources"] = discover_resources(topic, limit=3)
    plan["content_approved"] = False
    validated = LearningPlan.model_validate(plan)
    with connection() as conn:
        conn.execute(
            "UPDATE assignments SET learning_plan=? WHERE id=?",
            (validated.model_dump_json(), assignment_id),
        )
    return instructor_assignment_detail(assignment_id, user)


@app.put("/api/instructor/assignments/{assignment_id}")
def update_assignment(assignment_id: str, body: AssignmentInput, user=Depends(current_user)):
    item = _instructor_assignment(assignment_id, user)
    if item["status"] != "draft":
        raise HTTPException(409, "Published assignments are read-only.")
    with connection() as conn:
        valid_students = {row["id"] for row in conn.execute("SELECT id FROM users WHERE role='student'")}
        if not set(body.student_ids).issubset(valid_students):
            raise HTTPException(422, "Every recipient must be a demo student.")
        conn.execute(
            "UPDATE assignments SET title=?,instructions=?,learning_plan=? WHERE id=?",
            (body.title, body.instructions, body.learning_plan.model_dump_json(), assignment_id),
        )
        conn.execute("DELETE FROM recipients WHERE assignment_id=?", (assignment_id,))
        conn.executemany(
            "INSERT INTO recipients(assignment_id,student_id) VALUES (?,?)",
            [(assignment_id, student_id) for student_id in body.student_ids],
        )
    return instructor_assignment_detail(assignment_id, user)


@app.post("/api/instructor/assignments/{assignment_id}/editable-copy", status_code=201)
def editable_assignment_copy(assignment_id: str, user=Depends(current_user)):
    item = _instructor_assignment(assignment_id, user)
    new_id = str(uuid4())
    plan = _plan(item)
    plan["content_approved"] = False
    copied_paths = []
    try:
        with connection() as conn:
            conn.execute("INSERT INTO assignments(id,instructor_id,title,instructions,status,learning_plan,created_at) VALUES (?,?,?,?,?,?,?)",
                         (new_id, user["id"], item["title"], item["instructions"], "draft", json.dumps(plan), now()))
            recipients = conn.execute("SELECT student_id FROM recipients WHERE assignment_id=?", (assignment_id,)).fetchall()
            conn.executemany("INSERT INTO recipients(assignment_id,student_id) VALUES (?,?)", [(new_id, row["student_id"]) for row in recipients])
            documents = conn.execute("SELECT * FROM documents WHERE assignment_id=?", (assignment_id,)).fetchall()
            for document in documents:
                document_id = str(uuid4())
                path = UPLOAD_DIR / (document_id + Path(document["path"]).suffix)
                copied_paths.append(path)
                shutil.copy2(document["path"], path)
                conn.execute("INSERT INTO documents(id,assignment_id,filename,content_type,path,created_at) VALUES (?,?,?,?,?,?)",
                             (document_id, new_id, document["filename"], document["content_type"], str(path), now()))
                chunks = conn.execute("SELECT * FROM chunks WHERE document_id=?", (document["id"],)).fetchall()
                conn.executemany("INSERT INTO chunks(id,document_id,position,content,embedding,metadata) VALUES (?,?,?,?,?,?)",
                    [(str(uuid4()), document_id, chunk["position"], chunk["content"], chunk["embedding"], chunk["metadata"]) for chunk in chunks])
    except Exception as exc:
        for path in copied_paths:
            path.unlink(missing_ok=True)
        raise HTTPException(500, "The editable copy could not be created. Please try again.") from exc
    return instructor_assignment_detail(new_id, user)


@app.post("/api/instructor/assignments/{assignment_id}/documents", status_code=201)
async def upload_document(assignment_id: str, file: UploadFile = File(...), user=Depends(current_user)):
    item = _instructor_assignment(assignment_id, user)
    if item["status"] != "draft":
        raise HTTPException(409, "Upload documents before publishing the assignment.")
    return await add_document(assignment_id, file)


@app.post("/api/instructor/assignments/{assignment_id}/documents/url", status_code=201)
async def upload_url_document(assignment_id: str, body: ResourceURLInput, user=Depends(current_user)):
    item = _instructor_assignment(assignment_id, user)
    if item["status"] != "draft":
        raise HTTPException(409, "Upload documents before publishing the assignment.")
    return await add_url_document(assignment_id, body.url.strip())


@app.delete("/api/instructor/assignments/{assignment_id}/documents/{document_id}", status_code=204)
def delete_document(assignment_id: str, document_id: str, user=Depends(current_user)):
    item = _instructor_assignment(assignment_id, user)
    if item["status"] != "draft":
        raise HTTPException(409, "Published assignment documents are frozen.")
    with connection() as conn:
        row = conn.execute("SELECT path FROM documents WHERE id=? AND assignment_id=?", (document_id, assignment_id)).fetchone()
        if row is None:
            raise HTTPException(404, "Document not found.")
        conn.execute("DELETE FROM documents WHERE id=?", (document_id,))
    Path(row["path"]).unlink(missing_ok=True)


@app.post("/api/instructor/assignments/{assignment_id}/publish")
def publish_assignment(assignment_id: str, user=Depends(current_user)):
    item = _instructor_assignment(assignment_id, user)
    if item["status"] == "published":
        return instructor_assignment_detail(assignment_id, user)
    plan = _plan(item)
    issues = configuration_issues(plan)
    if plan.get("flow_version") != 2:
        issues.insert(0, "Configure this draft for the current five-stage learning flow.")
    if issues:
        raise HTTPException(422, {"message": "Complete the lesson configuration before publishing.", "issues": issues})
    with connection() as conn:
        recipients = conn.execute("SELECT count(*) AS n FROM recipients WHERE assignment_id=?", (assignment_id,)).fetchone()["n"]
        if recipients == 0:
            raise HTTPException(422, "Select at least one student before publishing.")
        conn.execute("UPDATE assignments SET status='published',published_at=? WHERE id=?", (now(), assignment_id))
    return instructor_assignment_detail(assignment_id, user)


@app.get("/api/instructor/assignments/{assignment_id}/progress")
def assignment_progress(assignment_id: str, user=Depends(current_user)):
    item = _instructor_assignment(assignment_id, user)
    plan = _plan(item)
    with connection() as conn:
        rows = conn.execute(
            """SELECT u.id AS student_id,u.display_name,u.email,t.id AS attempt_id,t.status,
                      t.current_objective,t.required_task_status,t.phase,t.study_completed_at,
                      t.quiz_score,t.learning_path,t.started_at,t.completed_at,t.learning_state
               FROM recipients r JOIN users u ON u.id=r.student_id
               LEFT JOIN attempts t ON t.assignment_id=r.assignment_id AND t.student_id=r.student_id
               WHERE r.assignment_id=? ORDER BY u.display_name""",
            (assignment_id,),
        ).fetchall()
    result = []
    for row in rows:
        public = dict(row)
        saved_state = json.loads(public.pop("learning_state", None) or "{}")
        if plan.get("flow_version") == 2:
            analytics_plan = saved_state.get("lesson_snapshot") or plan
            public["concept_analytics"] = _concept_analytics(analytics_plan, saved_state or lesson_flow.initial_state(analytics_plan))
        public["objective_progress"] = _objective_progress(row["attempt_id"], plan) if row["attempt_id"] else []
        result.append(public)
    return result


@app.get("/api/instructor/assignments/{assignment_id}/students/{student_id}")
def instructor_student_evidence(
    assignment_id: str,
    student_id: str,
    user=Depends(current_user),
):
    item = _instructor_assignment(assignment_id, user)
    plan = _plan(item)
    with connection() as conn:
        student = row_dict(conn.execute(
            """SELECT u.id,u.display_name,u.email FROM recipients r
               JOIN users u ON u.id=r.student_id
               WHERE r.assignment_id=? AND r.student_id=?""",
            (assignment_id, student_id),
        ).fetchone())
        if student is None:
            raise HTTPException(404, "Student is not assigned to this assignment.")
        attempt = row_dict(conn.execute(
            "SELECT * FROM attempts WHERE assignment_id=? AND student_id=?",
            (assignment_id, student_id),
        ).fetchone())
        evidence_rows = [] if attempt is None else [
            dict(row)
            for row in conn.execute(
                "SELECT * FROM evidence WHERE attempt_id=? ORDER BY created_at,id",
                (attempt["id"],),
            ).fetchall()
        ]

    if attempt is None:
        return {"student": student, "attempt": None, "evidence": [], "quiz_results": []}

    saved_state = json.loads(attempt["learning_state"])
    if saved_state.get("version") == 2:
        plan = saved_state["lesson_snapshot"]

    objective_titles = {objective["id"]: objective["title"] for objective in plan["objectives"]}
    evidence = [
        {
            **row,
            "demonstrated": bool(row["demonstrated"]),
            "objective_title": objective_titles.get(row["objective_id"], row["objective_id"]),
        }
        for row in evidence_rows
    ]
    if saved_state.get("version") == 2:
        quiz_results = []
        if saved_state.get("diagnostic_complete"):
            for index, entry in enumerate(saved_state["diagnostic"]):
                question = plan["diagnostic_quiz"][index]
                quiz_results.append({**entry, "id": question["id"], "difficulty": question["difficulty"],
                    "selected_index": entry["option_index"], "selected_answer": question["options"][entry["option_index"]] if entry["option_index"] is not None else "I don't know",
                    "correct_answer": question["options"][question["correct_index"]], "student_explanation": entry.get("explanation"), "explanation": question["explanation"]})
        public_attempt = _build_attempt_response(attempt, plan)
        public_attempt.pop("quiz_results", None)
        concepts = _concept_analytics(plan, saved_state)
        return {"student": student, "attempt": public_attempt, "evidence": evidence, "quiz_results": quiz_results,
                "concept_analytics": concepts,
                "summary": _student_summary(student, public_attempt, evidence, quiz_results, concepts), "required_task": plan["required_task"]}
    answers = json.loads(attempt.get("quiz_answers") or "[]")
    question_bank = plan.get("diagnostic_quiz", [])
    diagnostic_questions = (
        select_diagnostic_questions(question_bank) if question_bank else []
    )
    quiz_results = [
        {
            "id": question["id"],
            "question": question["question"],
            "difficulty": question["difficulty"],
            "selected_index": answers[index] if index < len(answers) else None,
            "selected_answer": question["options"][answers[index]] if index < len(answers) else None,
            "correct_index": question["correct_index"],
            "correct_answer": question["options"][question["correct_index"]],
            "correct": index < len(answers) and answers[index] == question["correct_index"],
            "explanation": question["explanation"],
        }
        for index, question in enumerate(diagnostic_questions)
    ]
    public_attempt = _build_attempt_response(attempt, plan)
    public_attempt.pop("quiz_results", None)
    return {
        "student": student,
        "attempt": public_attempt,
        "evidence": evidence,
        "quiz_results": quiz_results,
        "summary": _student_summary(student, public_attempt, evidence, quiz_results),
        "required_task": plan["required_task"],
    }


@app.get("/api/student/assignments")
def student_assignments(user=Depends(current_user)):
    require_student(user)
    if user.get("lab_participant"):
        from .lab import instructor_id
        with connection() as conn:
            rows = conn.execute(
                """SELECT a.*,t.status AS attempt_status,t.current_objective,t.required_task_status,
                          t.phase,t.quiz_score,t.learning_path
                   FROM assignments a JOIN lab_enrollments e ON e.assignment_id=a.id AND e.student_id=?
                   LEFT JOIN attempts t ON t.assignment_id=a.id AND t.student_id=e.student_id
                   WHERE a.status='published' AND a.instructor_id=? ORDER BY a.published_at DESC""",
                (user["id"], instructor_id())).fetchall()
        return [_assignment_public(dict(row)) for row in rows]
    with connection() as conn:
        rows = conn.execute(
            """SELECT a.*,t.status AS attempt_status,t.current_objective,t.required_task_status,
                      t.phase,t.quiz_score,t.learning_path
               FROM recipients r JOIN assignments a ON a.id=r.assignment_id
               LEFT JOIN attempts t ON t.assignment_id=a.id AND t.student_id=r.student_id
               WHERE r.student_id=? AND a.status='published' ORDER BY a.published_at DESC""",
            (user["id"],),
        ).fetchall()
    return [_assignment_public(dict(row)) for row in rows]


@app.get("/api/student/assignments/{assignment_id}")
def student_assignment_detail(assignment_id: str, user=Depends(current_user)):
    item = _student_assignment(assignment_id, user)
    result = _assignment_public(item)
    result["documents"] = [{key: value for key, value in doc.items() if key != "content_type"} for doc in _documents(assignment_id)]
    return result


@app.get("/api/student/assignments/{assignment_id}/attempt")
def get_attempt(assignment_id: str, user=Depends(current_user)):
    item = _student_assignment(assignment_id, user)
    with connection() as conn:
        attempt = row_dict(conn.execute("SELECT * FROM attempts WHERE assignment_id=? AND student_id=?", (assignment_id, user["id"])).fetchone())
    return _build_attempt_response(attempt, _plan(item)) if attempt else None


@app.post("/api/student/assignments/{assignment_id}/start")
def start_attempt(assignment_id: str, user=Depends(current_user)):
    item = _student_assignment(assignment_id, user)
    plan = _plan(item)
    if plan.get("flow_version") == 2:
        with connection() as conn:
            if not conn.postgres:
                conn.execute("BEGIN IMMEDIATE")
            attempt = row_dict(conn.execute("SELECT * FROM attempts WHERE assignment_id=? AND student_id=?", (assignment_id, user["id"])).fetchone())
            if attempt is None:
                if configuration_issues(plan):
                    raise HTTPException(409, "Your instructor needs to finish configuring this lesson before you can start.")
                attempt_id = str(uuid4())
                state = lesson_flow.initial_state(plan)
                inserted = conn.execute("INSERT INTO attempts(id,assignment_id,student_id,phase,learning_state,started_at) VALUES (?,?,?,?,?,?) ON CONFLICT(assignment_id,student_id) DO NOTHING", (attempt_id, assignment_id, user["id"], "welcome", json.dumps(state), now()))
                if inserted.rowcount:
                    conn.execute("INSERT INTO messages(id,attempt_id,role,content,created_at) VALUES (?,?,?,?,?)", (str(uuid4()), attempt_id, "assistant", lesson_flow.welcome(plan, user["display_name"]), now()))
                attempt = row_dict(conn.execute("SELECT * FROM attempts WHERE assignment_id=? AND student_id=?", (assignment_id, user["id"])).fetchone())
            else:
                state = json.loads(attempt.get("learning_state") or "{}")
                # Older-V2 compatibility: preserve the existing chooser upgrade.
                if state.get("version") == 2 and state.get("diagnostic_complete") and not state.get("choice_flow_version"):
                    state["choice_flow_version"] = 1
                    awaiting_choice = state.get("stage") == "adaptive_learning" and not state.get("selected_format")
                    if awaiting_choice:
                        state.update(stage="learning_choice", choices=list(lesson_flow.CHOICES), activity=None, depth_checks=0)
                        concept = state.get("target_concept", "the concept highlighted by your quiz")
                        conn.execute("INSERT INTO messages(id,attempt_id,role,content,created_at) VALUES (?,?,?,?,?)", (str(uuid4()), attempt["id"], "assistant", f"Let's focus on {concept}. How would you like to work on it? Choose an approach below; then we'll go deeper one question at a time.", now()))
                    conn.execute("UPDATE attempts SET phase=?,learning_state=? WHERE id=?", (state["stage"], json.dumps(state), attempt["id"]))
                    attempt = row_dict(conn.execute("SELECT * FROM attempts WHERE id=?", (attempt["id"],)).fetchone())
        return _build_attempt_response(attempt, plan)
    with connection() as conn:
        attempt = row_dict(conn.execute("SELECT * FROM attempts WHERE assignment_id=? AND student_id=?", (assignment_id, user["id"])).fetchone())
        if attempt is None:
            if not plan.get("study_resources"):
                raise HTTPException(409, "Credible study links are unavailable. Ask your instructor to refresh this assignment's resources.")
            attempt_id = str(uuid4())
            if plan.get("study_resources"):
                phase = "study_resources"
            elif plan.get("diagnostic_quiz"):
                phase = "diagnostic_quiz"
            else:
                phase = "adaptive_learning"
            conn.execute(
                "INSERT INTO attempts(id,assignment_id,student_id,phase,started_at) VALUES (?,?,?,?,?)",
                (attempt_id, assignment_id, user["id"], phase, now()),
            )
            if phase == "adaptive_learning":
                first_prompt = plan["objectives"][0]["diagnostic_prompt"]
                conn.execute(
                    "INSERT INTO messages(id,attempt_id,role,content,created_at) VALUES (?,?,?,?,?)",
                    (str(uuid4()), attempt_id, "assistant", first_prompt, now()),
                )
            attempt = row_dict(conn.execute("SELECT * FROM attempts WHERE id=?", (attempt_id,)).fetchone())
    return _build_attempt_response(attempt, plan)


@app.post("/api/student/assignments/{assignment_id}/restart")
def restart_attempt(assignment_id: str, user=Depends(current_user)):
    """Restart this student's V2 attempt for testing, after explicit UI confirmation."""
    item = _student_assignment(assignment_id, user)
    plan = _plan(item)
    if plan.get("flow_version") != 2:
        raise HTTPException(409, "Restart is available for current V2 lessons only.")
    if configuration_issues(plan):
        raise HTTPException(409, "Your instructor needs to finish configuring this lesson before you can restart it.")
    with connection() as conn:
        if not conn.postgres:
            conn.execute("BEGIN IMMEDIATE")
        attempt = load_attempt_for_turn(conn, assignment_id, user["id"])
        if attempt is None:
            raise HTTPException(409, "Open the lesson before restarting it.")
        restarted_at = now()
        state = lesson_flow.initial_state(plan)
        reset_attempt_for_restart(
            conn, attempt["id"], learning_state=json.dumps(state),
            welcome_message=lesson_flow.welcome(plan, user["display_name"]),
            started_at=restarted_at,
        )
        attempt = row_dict(conn.execute("SELECT * FROM attempts WHERE id=?", (attempt["id"],)).fetchone())
    return _build_attempt_response(attempt, plan)


@app.post("/api/student/assignments/{assignment_id}/learning-turn")
def learning_turn(assignment_id: str, body: LearningTurn, user=Depends(current_user)):
    # CURRENT V2 — 1. FastAPI validates LearningTurn and identifies the student.
    # 2. Check assignment access.
    item = _student_assignment(assignment_id, user)
    if not body.content.strip() and body.action in {"message", "choice"}:
        raise HTTPException(422, "Write a response before sending.")
    fingerprint = hashlib.sha256(json.dumps(body.model_dump(), sort_keys=True).encode()).hexdigest()
    # 3. Load the attempt under the existing transaction and lock.
    with connection() as conn:
        if not conn.postgres:
            conn.execute("BEGIN IMMEDIATE")
        attempt = load_attempt_for_turn(conn, assignment_id, user["id"])
        if not attempt:
            raise HTTPException(409, "Open the lesson before sending a response.")
        if attempt["status"] == "completed" and body.turn_id not in json.loads(attempt["learning_state"]).get("events", {}):
            raise HTTPException(409, "This session is complete.")
        state = json.loads(attempt["learning_state"])
        if state.get("version") != 2:
            raise HTTPException(409, "This earlier session uses the previous learning flow. Open a newly configured lesson.")
        # 4. Check duplicate turn IDs before running the lesson again.
        events = state.get("events", {})
        if body.turn_id in events:
            if events[body.turn_id] != fingerprint:
                raise HTTPException(409, "This response identifier was already used for a different message.")
        else:
            # 5. Retrieve context only when the existing help check requests it.
            sources = []
            if state["stage"] in {"welcome", "study_resources", "adaptive_learning"} and lesson_flow.is_help(body.content):
                sources = retrieve(assignment_id, body.content)
                state["study_context"] = sources
            # 6. Let lesson_flow.py make all current lesson decisions.
            try:
                updated, reply, evidence = lesson_flow.process_lesson_turn(state, body)
            except ValueError as exc:
                raise HTTPException(409, str(exc)) from exc
            # 7. Save the decided result and transport metadata atomically.
            updated.pop("study_context", None)
            feedback = updated.get("quiz_feedback", [])
            message_count = conn.execute(
                "SELECT count(*) AS n FROM messages WHERE attempt_id=?", (attempt["id"],)
            ).fetchone()["n"]
            if feedback and feedback[-1]["turn_id"] == body.turn_id:
                feedback[-1]["message_index"] = message_count
            if updated["lesson_snapshot"].get("bounded_flow") and updated["stage"] == "diagnostic_quiz":
                question_id = updated["lesson_snapshot"]["diagnostic_quiz"][updated["quiz_index"]]["id"]
                fallback_position = message_count if attempt["phase"] == "diagnostic_quiz" and body.question_id == question_id else message_count + 2
                first_answer = next((entry["message_index"] for entry in feedback if entry["question_id"] == question_id), fallback_position)
                updated.setdefault("quiz_question_positions", {}).setdefault(question_id, first_answer)
            updated["events"] = {**events, body.turn_id: fingerprint}
            snapshot = updated["lesson_snapshot"]
            target = updated.get("target_objective")
            current_index = next((i for i, objective in enumerate(snapshot["objectives"]) if objective["id"] == target), 0)
            selected_path = updated.get("current_paths", {}).get(target)
            quiz_answers = json.dumps([entry["option_index"] for entry in updated["diagnostic"]]) if updated.get("diagnostic_complete") else attempt["quiz_answers"]
            study_time = now() if state["stage"] == "study_resources" and updated["stage"] == "diagnostic_quiz" else attempt.get("study_completed_at")
            attempt_values = (
                updated["stage"], json.dumps(updated), current_index, quiz_answers,
                updated.get("quiz_score"), selected_path, study_time,
            )
            student_message = body.content.strip() or (f"Option {chr(65 + body.option_index)}; confidence: {body.confidence or 'not reported'}; explanation: {body.explanation or 'not reported'}" if body.option_index is not None else body.action)
            save_lesson_turn(
                conn, attempt["id"], attempt_values=attempt_values,
                student_message=student_message, reply=reply,
                sources_json=json.dumps(_source_metadata(sources)), evidence=evidence,
            )
            state = updated
        if attempt["status"] != "completed" and state.get("stage") == "completed" and state.get("application_submission"):
            conn.execute("UPDATE attempts SET status='completed',required_task_status='completed',required_task_submission=?,completed_at=? WHERE id=?",
                         (state["application_submission"], now(), attempt["id"]))
        attempt = row_dict(conn.execute("SELECT * FROM attempts WHERE id=?", (attempt["id"],)).fetchone())
    # 8. Build the public response after the transaction commits.
    return _build_attempt_response(attempt, _plan(item))


# LEGACY endpoints below: V2 lessons use learning_turn() instead.
@app.post("/api/student/assignments/{assignment_id}/study-complete")
def complete_study_phase(
    assignment_id: str,
    body: StudyCompletion,
    user=Depends(current_user),
):
    item = _student_assignment(assignment_id, user)
    plan = _plan(item)
    if plan.get("flow_version") == 2:
        raise HTTPException(409, "Reply in the current lesson conversation to continue.")
    ready = body.message.strip().lower()
    accepted = bool(re.search(r"\b(done|finished|studied|ready|completed)\b", ready)) or any(phrase in ready for phrase in ("i'm back", "im back", "let's continue", "lets continue"))
    if any(phrase in ready for phrase in ("not done", "not finished", "not ready", "haven't", "have not", "didn't", "did not", "not studied", "not completed", "still studying")):
        accepted = False
    if not accepted:
        raise HTTPException(422, "Tell us you have finished studying before starting the quiz.")
    with connection() as conn:
        attempt = row_dict(conn.execute(
            "SELECT * FROM attempts WHERE assignment_id=? AND student_id=?",
            (assignment_id, user["id"]),
        ).fetchone())
        if attempt is None:
            raise HTTPException(409, "Start the assignment first.")
        if attempt["phase"] == "study_resources":
            next_phase = "diagnostic_quiz" if plan.get("diagnostic_quiz") else "adaptive_learning"
            conn.execute(
                "UPDATE attempts SET phase=?,study_completed_at=? WHERE id=?",
                (next_phase, now(), attempt["id"]),
            )
            conn.execute("INSERT INTO messages(id,attempt_id,role,content,created_at) VALUES (?,?,?,?,?)",
                         (str(uuid4()), attempt["id"], "student", body.message.strip(), now()))
            if next_phase == "diagnostic_quiz":
                conn.execute("INSERT INTO messages(id,attempt_id,role,content,created_at) VALUES (?,?,?,?,?)",
                             (str(uuid4()), attempt["id"], "assistant", "Now let's take a short quiz to assess your understanding: five multiple-choice questions, from basics to challenge.", now()))
            if next_phase == "adaptive_learning":
                prompt, state = _path_prompt(plan, 0, "standard")
                conn.execute("UPDATE attempts SET learning_state=? WHERE id=?", (json.dumps(state), attempt["id"]))
                conn.execute("INSERT INTO messages(id,attempt_id,role,content,created_at) VALUES (?,?,?,?,?)",
                             (str(uuid4()), attempt["id"], "assistant", prompt, now()))
        attempt = row_dict(conn.execute("SELECT * FROM attempts WHERE id=?", (attempt["id"],)).fetchone())
    return _build_attempt_response(attempt, plan)


@app.post("/api/student/assignments/{assignment_id}/quiz")
def submit_quiz(
    assignment_id: str,
    body: QuizSubmission,
    user=Depends(current_user),
):
    item = _student_assignment(assignment_id, user)
    plan = _plan(item)
    if plan.get("flow_version") == 2:
        raise HTTPException(409, "Answer the current diagnostic question, one at a time.")
    try:
        questions = select_diagnostic_questions(plan.get("diagnostic_quiz", []))
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from exc
    if len(body.answers) != len(questions):
        raise HTTPException(409, "This assignment does not have a five-question diagnostic.")
    if any(answer < 0 or answer > 3 for answer in body.answers):
        raise HTTPException(422, "Every quiz answer must select one of four options.")
    placement = place_student(
        questions,
        body.answers,
        [objective["id"] for objective in plan["objectives"]],
    )
    score = placement.correct_count
    learning_path = placement.learning_path
    prompt, state = _path_prompt(
        plan, 0, learning_path, placement.objective_paths
    )
    intro = (
        f"You scored {score} out of 5. Your starting path is {learning_path}.\n\n{prompt}"
    )
    with connection() as conn:
        attempt = row_dict(conn.execute(
            "SELECT * FROM attempts WHERE assignment_id=? AND student_id=?",
            (assignment_id, user["id"]),
        ).fetchone())
        if attempt is None:
            raise HTTPException(409, "Start the assignment first.")
        if attempt["phase"] != "diagnostic_quiz":
            raise HTTPException(409, "The diagnostic quiz is not currently available.")
        conn.execute(
            """UPDATE attempts SET phase='adaptive_learning',quiz_answers=?,quiz_score=?,
               learning_path=?,learning_state=? WHERE id=?""",
            (json.dumps(body.answers), score, learning_path, json.dumps(state), attempt["id"]),
        )
        conn.execute(
            "INSERT INTO messages(id,attempt_id,role,content,created_at) VALUES (?,?,?,?,?)",
            (str(uuid4()), attempt["id"], "assistant", intro, now()),
        )
        attempt = row_dict(conn.execute("SELECT * FROM attempts WHERE id=?", (attempt["id"],)).fetchone())
    return _build_attempt_response(attempt, plan)


@app.post("/api/student/assignments/{assignment_id}/messages")
def send_message(assignment_id: str, body: MessageInput, user=Depends(current_user)):
    item = _student_assignment(assignment_id, user)
    plan = _plan(item)
    if plan.get("flow_version") == 2:
        raise HTTPException(409, "Use the current lesson conversation to send this response.")
    with connection() as conn:
        attempt = row_dict(conn.execute("SELECT * FROM attempts WHERE assignment_id=? AND student_id=?", (assignment_id, user["id"])).fetchone())
    if attempt is None:
        raise HTTPException(409, "Start the assignment before sending a message.")
    if attempt["status"] == "completed":
        raise HTTPException(409, "This assignment is already complete.")
    if attempt["phase"] != "adaptive_learning":
        raise HTTPException(409, "Complete the current learning phase before sending a response.")

    index = attempt["current_objective"]
    state = json.loads(attempt.get("learning_state") or "{}")
    learning_path = attempt.get("learning_path") or "standard"
    next_phase = "adaptive_learning"
    if index >= len(plan["objectives"]):
        reply = f"You have demonstrated all learning objectives. {plan['required_task']['submission_prompt']}"
        assessment = None
        sources = retrieve(assignment_id, body.content)
        next_phase = "required_task"
    else:
        objective = plan["objectives"][index]
        asset = _learning_asset(plan, objective["id"])
        sources = retrieve(assignment_id, body.content)
        assessment = assess_response(objective, body.content)
        # A request for help is a Q&A turn, never evidence of mastery.
        help_request = body.content.strip().endswith("?") or any(
            phrase in body.content.lower() for phrase in ("give me a hint", "can you explain", "help me", "give an example", "another example", "analogy")
        )
        if help_request:
            assessment = {**assessment, "demonstrated": False}
        mode = state.get("mode", "demonstration")
        next_index = index

        if help_request:
            reply = tutor_reply(objective, body.content, assessment, sources, None)
            if asset and runtime_ai_mode() not in {"openai", "groq"}:
                reply = (
                    f"Example: {asset['worked_example']}\n\n"
                    + (f"Analogy: {asset['analogy']}\n\n" if asset.get("analogy") else "")
                    + f"{objective['diagnostic_prompt']} Explain what happens in your example and why."
                )
        elif mode == "practice" and asset:
            practice_level = state.get("practice_level") or "foundational"
            practice = asset[practice_level]
            practice_index = min(int(state.get("practice_index", 0)), len(practice) - 1)
            move_to_demonstration = assessment["demonstrated"] or practice_index + 1 >= len(practice)
            assessment = {**assessment, "demonstrated": False}
            if move_to_demonstration:
                state = {
                    **state,
                    "mode": "demonstration",
                    "practice_index": practice_index,
                    "practice_level": None,
                    "failures": 0,
                }
                reply = (
                    f"Now try an independent explanation so we can check your understanding.\n\n"
                    f"{objective['diagnostic_prompt']} Use a concrete example and explain why it fits."
                )
            else:
                next_item = practice[practice_index + 1]
                state = {**state, "practice_index": practice_index + 1}
                reply = (
                    f"{assessment['rationale']}\n\nHint: {next_item['hint']}\n\n"
                    f"Try this: {next_item['prompt']}"
                )
        else:
            if assessment["demonstrated"]:
                next_index = index + 1
                if next_index < len(plan["objectives"]):
                    next_prompt, state = _path_prompt(
                        plan,
                        next_index,
                        learning_path,
                        state.get("objective_paths", {}),
                    )
                    reply = tutor_reply(objective, body.content, assessment, sources, next_prompt)
                else:
                    next_phase = "required_task"
                    state = {
                        **state,
                        "mode": "complete",
                        "practice_index": 0,
                        "practice_level": None,
                        "failures": 0,
                    }
                    reply = tutor_reply(objective, body.content, assessment, sources, None)
                    reply += f"\n\nYou have demonstrated every objective. {plan['required_task']['submission_prompt']}"
            else:
                failures = int(state.get("failures", 0)) + 1
                if failures >= 2 and asset:
                    first_practice = asset["foundational"][0]
                    state = {
                        **state,
                        "mode": "practice",
                        "practice_index": 0,
                        "practice_level": "foundational",
                        "failures": 0,
                    }
                    reply = (
                        f"{assessment['rationale']}\n\nLet’s strengthen the foundation before you try again. "
                        f"{asset['explanation']}\n\nWorked example: {asset['worked_example']}\n\n"
                        + (f"Analogy: {asset['analogy']}\n\n" if asset.get("analogy") else "")
                        +
                        f"Practice: {first_practice['prompt']}\nHint: {first_practice['hint']}"
                    )
                else:
                    state = {**state, "mode": "demonstration", "failures": failures}
                    reply = tutor_reply(objective, body.content, assessment, sources, None)

    created = now()
    with connection() as conn:
        conn.execute(
            "INSERT INTO messages(id,attempt_id,role,content,created_at) VALUES (?,?,?,?,?)",
            (str(uuid4()), attempt["id"], "student", body.content, created),
        )
        conn.execute(
            "INSERT INTO messages(id,attempt_id,role,content,sources,created_at) VALUES (?,?,?,?,?,?)",
            (str(uuid4()), attempt["id"], "assistant", reply, json.dumps(_source_metadata(sources)), now()),
        )
        if assessment is not None:
            conn.execute(
                """INSERT INTO evidence(id,attempt_id,objective_id,response,score,demonstrated,rationale,created_at)
                   VALUES (?,?,?,?,?,?,?,?)""",
                (str(uuid4()), attempt["id"], objective["id"], body.content, assessment["score"], int(assessment["demonstrated"]), assessment["rationale"], created),
            )
            if assessment["demonstrated"]:
                conn.execute(
                    """UPDATE attempts SET current_objective=?,required_task_status=?,
                       phase=?,learning_state=? WHERE id=?""",
                    (
                        next_index,
                        "not_started" if next_index < len(plan["objectives"]) else "ready",
                        next_phase,
                        json.dumps(state),
                        attempt["id"],
                    ),
                )
            else:
                conn.execute(
                    "UPDATE attempts SET learning_state=? WHERE id=?",
                    (json.dumps(state), attempt["id"]),
                )
        attempt = row_dict(conn.execute("SELECT * FROM attempts WHERE id=?", (attempt["id"],)).fetchone())
    return _build_attempt_response(attempt, plan)


@app.post("/api/student/assignments/{assignment_id}/submit-task")
def submit_task(assignment_id: str, body: TaskSubmission, user=Depends(current_user)):
    item = _student_assignment(assignment_id, user)
    plan = _plan(item)
    if plan.get("flow_version") == 2:
        raise HTTPException(409, "Reflect in the lesson conversation, then choose further learning or pause.")
    if not body.content.strip():
        raise HTTPException(422, "Write your final response before submitting.")
    with connection() as conn:
        attempt = row_dict(conn.execute("SELECT * FROM attempts WHERE assignment_id=? AND student_id=?", (assignment_id, user["id"])).fetchone())
        if attempt is None:
            raise HTTPException(409, "Start the assignment first.")
        if attempt["phase"] != "required_task" or attempt["current_objective"] < len(plan["objectives"]):
            raise HTTPException(422, "Demonstrate every required objective before submitting the task.")
        conn.execute(
            """UPDATE attempts SET status='completed',required_task_status='completed',
               required_task_submission=?,completed_at=?,phase='completed' WHERE id=?""",
            (body.content, now(), attempt["id"]),
        )
        conn.execute(
            "INSERT INTO messages(id,attempt_id,role,content,created_at) VALUES (?,?,?,?,?)",
            (str(uuid4()), attempt["id"], "student", f"Required task submission:\n{body.content}", now()),
        )
        conn.execute(
            "INSERT INTO messages(id,attempt_id,role,content,created_at) VALUES (?,?,?,?,?)",
            (str(uuid4()), attempt["id"], "assistant", f"Thank you, {user['display_name']}! Your final write-up has been saved. Today's session is complete.", now()),
        )
        attempt = row_dict(conn.execute("SELECT * FROM attempts WHERE id=?", (attempt["id"],)).fetchone())
    return _build_attempt_response(attempt, plan)
