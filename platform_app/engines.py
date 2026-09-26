"""Adapters to existing learning engines. No client controls engine/session identity."""
import asyncio
import json
import os
from pathlib import Path
import re
from time import monotonic
import uuid

import httpx
from fastapi import HTTPException

from app import db, rag
from app.answer_evaluation import (
    answer_evaluation_query,
    evaluate_student_answer,
    mastery_completion_answer,
    with_progress_status,
)
from app.classifier import MessageClassification, classify_message
from app.pipeline_logging import begin_trace, debug_preview, end_trace, log_event, log_exception
from app.schemas import ChatMessage
from platform_app.schemas import ReflectionConfig, TutorConfig, Topic

ROOT = Path(__file__).resolve().parents[1]


def call(tool, method, path, **kwargs):
    env, default = ("REFLECTIONS_URL", "http://127.0.0.1:8002") if tool == "reflections" else ("TUTOR_URL", "http://127.0.0.1:8003")
    token = os.environ.get("PLATFORM_SERVICE_TOKEN", "")
    if not token:
        raise HTTPException(503, "Configure PLATFORM_SERVICE_TOKEN before using the learning services.")
    try:
        with httpx.Client(timeout=180, headers={"X-Platform-Service": token}) as client:
            response = client.request(method, os.getenv(env, default).rstrip("/") + path, **kwargs)
        if response.is_error:
            if response.status_code == 503:
                try:
                    code = response.json().get("code")
                except (ValueError, AttributeError):
                    code = None
                if code == "llm_authentication_failed":
                    raise HTTPException(503, "Reflections cannot connect to its AI provider because the API key is missing or invalid. Please contact your instructor or administrator.")
            # Preserve actionable validation errors, never expose remote traces or secrets.
            detail = response.json().get("detail", "") if response.status_code < 500 else ""
            raise HTTPException(422 if response.status_code < 500 else 502,
                                detail or f"The {tool} engine could not complete this action. Please retry.")
        return response.json()
    except (httpx.HTTPError, ValueError) as exc:
        raise HTTPException(503, f"The {tool} engine is unavailable. Please retry shortly.") from exc


def topic_templates():
    topics = [json.loads(p.read_text()) for p in sorted((ROOT / "student-agent-bot/data/topics/builtin").glob("*.json"))]
    return [Topic.model_validate({k: v for k, v in topic.items() if k in Topic.model_fields}).model_dump(mode="json") for topic in topics]


def publish_snapshot(assignment):
    config = assignment["config"]
    if assignment["tool"] == "socratic":
        files = db.list_rag_files(course_id=str(assignment["course_id"]))
        allowed = {str(f["document_id"]) for f in files if f.get("document_id")}
        chosen = set(config["document_ids"]) or allowed
        if not chosen or not chosen.issubset(allowed):
            raise HTTPException(422, "Select documents belonging to this course, or upload course materials first.")
        chunks = db.snapshot_document_chunks(str(assignment["course_id"]), sorted(chosen))
        if chosen - {c["document_id"] for c in chunks}:
            raise HTTPException(422, "Some course materials have no indexed content. Re-upload them before publishing.")
        course = db.get_course(str(assignment["course_id"])) or {}
        return {
            "config": config,
            "chunks": chunks,
            "course": {
                "course_code": course.get("course_code", ""),
                "title": course.get("title", ""),
                "description": course.get("description", ""),
            },
        }
    if assignment["tool"] == "reflections":
        cfg = ReflectionConfig.model_validate(config)
        cfg.validate_publish()
        module = call("reflections", "PUT", f"/internal/platform/modules/{assignment['id']}",
                      json={"name": assignment["title"], "course_id": str(assignment["course_id"]), "config": config})
        return {"config": config, "module_id": module["id"]}
    cfg = TutorConfig.model_validate(config)
    if cfg.topic is None:
        raise HTTPException(422, "Select or create a tutor topic before publishing.")
    return {"config": config}


def start(assignment, attempt):
    snapshot = assignment["snapshot"]
    config = snapshot["config"]
    if assignment["tool"] == "socratic":
        return {"messages": [{"role": "assistant", "content": config["prompt"] or "What would you like to explore in the assigned materials?"}]}
    if assignment["tool"] == "reflections":
        if config["module_type"] == "milestone_based":
            return {"messages": [{"role": "assistant", "content": config["milestone_prompt"]}]}
        result = call("reflections", "POST", "/internal/platform/start", json={
            "session_id": str(attempt["id"]), "module_id": snapshot["module_id"],
            "student_id": str(attempt["student_id"]), "course_id": str(assignment["course_id"])})
        return {"messages": [{"role": "assistant", "content": result["greeting"]}], "total_questions": result["total_questions"], "question_index": 0}
    return call("student-agent", "POST", "/api/session/start", json={
        "session_id": str(attempt["id"]), "topic_id": config["topic"]["id"],
        "topic_snapshot": config["topic"], "provider": config["provider"], "personality": config["personality"]})


def _snapshot_titles(chunks):
    return list(dict.fromkeys(str(chunk["title"]) for chunk in chunks))


def _snapshot_context_answer(snapshot, classification: MessageClassification):
    request_type = classification.operational_request
    if request_type == "none":
        return None
    course = snapshot.get("course") or {}
    titles = _snapshot_titles(snapshot.get("chunks") or [])
    documents = ", ".join(titles) if titles else "no published documents"
    if request_type == "course_title":
        return f"This assignment belongs to {course.get('course_code', '')}: {course.get('title', '')}.".replace(" :", ":").strip()
    if request_type == "course_scope":
        description = str(course.get("description") or "").strip()
        return description or f"This assignment uses these published course documents: {documents}."
    if request_type in {"list_documents", "document_visibility", "system_status"}:
        return f"Published course documents for this assignment: {documents}."
    return None


def _update_snapshot_progress(state, evaluation):
    progress = dict(state.get("progress") or {})
    key = evaluation.concept.strip().lower()
    previous = progress.get(key)
    existing = None
    if previous:
        existing = (
            previous.get("estimated_mastery", evaluation.total_score),
            previous.get("evidence_count", 0),
            previous.get("status", "emerging"),
        )
    mastery, count, status = db._mastery_progress_update(
        existing,
        evaluation.total_score,
        evaluation.correctness,
        evaluation.application,
        evaluation.critical_misconception,
    )
    progress[key] = {
        "estimated_mastery": mastery,
        "evidence_count": count,
        "status": status,
        "critical_misconception": evaluation.critical_misconception,
    }
    state["progress"] = progress
    return with_progress_status(evaluation, status)


def _next_thinking_step(answer: str) -> str:
    sentences = [
        sentence.strip()
        for sentence in re.split(r"(?<=[.!?])\s+", answer.strip())
        if sentence.strip()
    ]
    return next(
        (sentence for sentence in reversed(sentences) if sentence.endswith("?")),
        answer.strip(),
    )


def _socratic_result(answer, sources, state, classification, score=None):
    concepts = [
        str(concept).strip()
        for concept in (*classification.target_concepts, classification.target or "")
        if str(concept).strip()
    ]
    state["next_thinking_step"] = _next_thinking_step(answer)
    state["keywords"] = list(dict.fromkeys(concepts))[:5]
    state["last_score"] = score
    return {
        "reply": answer,
        "sources": [source.model_dump() for source in sources],
        "socratic": state,
    }


async def _socratic_message(assignment, attempt, content):
    snapshot = assignment["snapshot"]
    chunks = snapshot.get("chunks") or []
    history = [ChatMessage(**message) for message in attempt["messages"][-8:]]
    state = dict(attempt["engine_state"].get("socratic") or {})
    trace = begin_trace(uuid.uuid4().hex, str(attempt["id"]))
    started = monotonic()
    try:
        log_event(1, "assignment_chat_received", assignment_id=assignment["id"], message_chars=len(content))
        classification = await classify_message(content, history)
        log_event(
            4,
            "message_classification_completed",
            source=classification.source,
            route=classification.route,
            question_type=classification.question_type,
            dialogue_status=classification.dialogue_status,
            conversation_action=classification.conversation_action,
            target_concepts="|".join(classification.target_concepts) or "none",
        )
        state.update({
            "conversation_status": (
                "completed" if classification.conversation_action == "complete"
                else "paused" if classification.conversation_action == "soft_close"
                else "active"
            ),
            "dialogue_status": classification.dialogue_status,
            "active_concept": classification.target or state.get("active_concept"),
            "understanding_level": classification.understanding_level,
            "support_level": classification.support_level,
        })

        if classification.conversation_action in {"soft_close", "complete"}:
            answer = await rag.generate_conversation_transition(content, history, classification)
            state.pop("pending_clarification", None)
            return _socratic_result(answer, [], state, classification)

        operational = _snapshot_context_answer(snapshot, classification)
        if operational:
            state.pop("pending_clarification", None)
            return _socratic_result(operational, [], state, classification)

        pending = state.pop("pending_clarification", None)
        if pending:
            query = f"{pending['original_question']} {content}".strip()
        elif classification.needs_clarification:
            state["pending_clarification"] = {
                "original_question": content,
                "target": classification.target,
            }
            answer = classification.clarification_question or "Could you clarify what you want to know?"
            return _socratic_result(answer, [], state, classification)
        elif classification.direct_answer:
            return _socratic_result(classification.direct_answer, [], state, classification)
        else:
            query = answer_evaluation_query(content, history, classification)

        sources = rag.retrieve_snapshot(query, chunks, top_k=4)
        if not sources and classification.operational_request == "document_overview":
            sources = rag.snapshot_overview(chunks, top_k=4)

        evaluation = await evaluate_student_answer(
            content,
            history,
            sources,
            classification,
            concept_hint=state.get("active_concept"),
        )
        if evaluation:
            evaluation = _update_snapshot_progress(state, evaluation)
            log_event(
                6,
                "concept_progress_updated",
                concept=evaluation.concept,
                status=evaluation.progress_status,
                score=evaluation.total_score,
            )

        if evaluation and evaluation.progress_status == "mastered":
            answer = mastery_completion_answer(evaluation)
        else:
            answer = await rag.generate_answer(
                content,
                history,
                sources,
                classification=classification,
                evaluation=evaluation,
            )
        debug_preview("final_answer", answer)
        log_event(
            12,
            "assignment_response_returned",
            sources=len(sources),
            response_chars=len(answer),
            latency_ms=round((monotonic() - started) * 1000),
        )
        return _socratic_result(
            answer,
            sources,
            state,
            classification,
            evaluation.total_score if evaluation else None,
        )
    except Exception as error:
        log_exception(12, "assignment_pipeline_failed", error)
        raise
    finally:
        end_trace(trace)


def message(assignment, attempt, content, request_id):
    tool = assignment["tool"]
    cfg = assignment["snapshot"]["config"]
    if tool == "socratic":
        return asyncio.run(_socratic_message(assignment, attempt, content))
    if tool == "reflections":
        if cfg["module_type"] == "milestone_based":
            result = call(tool, "POST", "/api/rec-sys/milestone", json={
                "module_id": assignment["snapshot"]["module_id"], "student_name": str(attempt["student_id"]), "reflection": content})
            return {"reply": "Your reflection has been submitted.", "result": result, "completed": True}
        return call(tool, "POST", "/internal/platform/message", json={"session_id": str(attempt["id"]), "message": content, "request_id": request_id})
    return call(tool, "POST", "/internal/platform/action", json={"session_id": str(attempt["id"]), "action": "message", "value": content, "request_id": request_id})


def complete(assignment, attempt):
    tool = assignment["tool"]
    count = sum(m["role"] == "user" for m in attempt["messages"])
    if tool == "socratic":
        minimum = assignment["snapshot"]["config"]["minimum_messages"]
        if count < minimum:
            raise HTTPException(422, f"Send at least {minimum} message(s) before completing this assignment.")
        return {"message_count": count}
    if tool == "reflections":
        if assignment["snapshot"]["config"]["module_type"] == "milestone_based":
            raise HTTPException(422, "Submit your reflection to complete this assignment.")
        if not count:
            raise HTTPException(422, "Respond to the reflection before ending the session.")
        return call(tool, "POST", "/internal/platform/end", json={"session_id": str(attempt["id"])})
    if attempt["engine_state"].get("phase") != "complete" and not attempt["engine_state"].get("ended"):
        raise HTTPException(422, "Reach the tutor's wrap-up before completing this assignment.")
    return call(tool, "POST", "/api/session/end", json={"session_id": str(attempt["id"])})
