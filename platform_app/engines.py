"""Adapters to existing learning engines. No client controls engine/session identity."""
import asyncio
import json
import os
from pathlib import Path

import httpx
from fastapi import HTTPException

from app import db, rag
from app.schemas import ChatMessage, Source
from platform_app.adaptive import is_phase1_oop_plan
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
        chunks = [c for c in rag.load_index() if c.get("course_id") == str(assignment["course_id"]) and c["document_id"] in chosen]
        if chosen - {c["document_id"] for c in chunks}:
            raise HTTPException(422, "Some course materials have no indexed content. Re-upload them before publishing.")
        return {"config": config, "chunks": chunks}
    if assignment["tool"] == "reflections":
        cfg = ReflectionConfig.model_validate(config)
        cfg.validate_publish()
        module = call("reflections", "PUT", f"/internal/platform/modules/{assignment['id']}",
                      json={"name": assignment["title"], "config": config})
        return {"config": config, "module_id": module["id"]}
    cfg = TutorConfig.model_validate(config)
    if cfg.learning_plan is not None:
        if not is_phase1_oop_plan(cfg.learning_plan):
            raise ValueError("Phase 1 supports only the seeded Object-Oriented Programming plan.")
        chosen = {item.document_id for item in cfg.learning_plan.approved_resources if item.document_id}
        chunks = []
        if chosen:
            files = db.list_rag_files(course_id=str(assignment["course_id"]))
            allowed = {str(f["document_id"]) for f in files if f.get("document_id")}
            if not chosen.issubset(allowed):
                raise HTTPException(422, "Every adaptive-plan document must belong to this course.")
            chunks = [c for c in rag.load_index() if c.get("course_id") == str(assignment["course_id"]) and c["document_id"] in chosen]
            if chosen - {c["document_id"] for c in chunks}:
                raise HTTPException(422, "Some adaptive-plan resources have no indexed content.")
        return {"config": config, "chunks": chunks}
    if cfg.topic is None:
        raise HTTPException(422, "Select a tutor topic or adaptive learning plan before publishing.")
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
            "session_id": str(attempt["id"]), "module_id": snapshot["module_id"], "student_id": str(attempt["student_id"])})
        return {"messages": [{"role": "assistant", "content": result["greeting"]}], "total_questions": result["total_questions"], "question_index": 0}
    return call("student-agent", "POST", "/api/session/start", json={
        "session_id": str(attempt["id"]), "topic_id": config["topic"]["id"],
        "topic_snapshot": config["topic"], "provider": config["provider"], "personality": config["personality"]})


def message(assignment, attempt, content, request_id):
    tool = assignment["tool"]
    cfg = assignment["snapshot"]["config"]
    if tool == "socratic":
        chunks = assignment["snapshot"]["chunks"]
        ranked = sorted(chunks, key=lambda c: rag.score(rag.tokenize(content), c.get("tokens", rag.tokenize(c["text"]))), reverse=True)[:4]
        sources = [Source(document_id=c["document_id"], chunk_id=c["chunk_id"], title=c["title"], text=c["text"],
                          score=rag.score(rag.tokenize(content), c.get("tokens", []))) for c in ranked]
        history = [ChatMessage(**m) for m in attempt["messages"][-8:]]
        answer = asyncio.run(rag.generate_answer(content, history, sources))
        return {"reply": answer, "sources": [s.model_dump() for s in sources]}
    if tool == "reflections":
        if cfg["module_type"] == "milestone_based":
            result = call(tool, "POST", "/api/rec-sys/milestone", json={
                "module_id": assignment["snapshot"]["module_id"], "student_name": str(attempt["student_id"]), "reflection": content})
            return {"reply": "Your reflection has been submitted.", "result": result, "completed": True}
        return call(tool, "POST", "/internal/platform/message", json={"session_id": str(attempt["id"]), "message": content, "request_id": request_id})
    return call(tool, "POST", "/internal/platform/action", json={"session_id": str(attempt["id"]), "action": "message", "value": content, "request_id": request_id})


def complete(assignment, attempt):
    tool = assignment["tool"]
    cfg = assignment["snapshot"]["config"]
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
    if cfg.get("learning_plan"):
        if attempt.get("required_task_status") != "completed":
            raise HTTPException(422, "Submit the required task before completing this assignment.")
        return {
            "required_task_status": "completed",
            "objective_progress": attempt["engine_state"].get("objective_progress", []),
        }
    if attempt["engine_state"].get("phase") != "complete" and not attempt["engine_state"].get("ended"):
        raise HTTPException(422, "Reach the tutor's wrap-up before completing this assignment.")
    return call(tool, "POST", "/api/session/end", json={"session_id": str(attempt["id"])})


def adaptive_rag_context(assignment, objective, decision, student_message):
    """Retrieve only from the immutable, approved assignment snapshot."""
    chunks = (assignment.get("snapshot") or {}).get("chunks", [])
    if not chunks:
        return []
    query = f"{objective.description} {decision.action.value} {student_message}"
    tokens = rag.tokenize(query)
    ranked = sorted(
        chunks,
        key=lambda item: rag.score(tokens, item.get("tokens", rag.tokenize(item["text"]))),
        reverse=True,
    )[:3]
    return [
        {"title": item["title"], "text": item["text"], "document_id": item["document_id"]}
        for item in ranked
        if rag.score(tokens, item.get("tokens", rag.tokenize(item["text"]))) > 0
    ]
