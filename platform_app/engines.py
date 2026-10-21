"""Adapters to existing learning engines. No client controls engine/session identity."""
import asyncio
from dataclasses import asdict, replace
import hashlib
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
    AnswerEvaluation,
    answer_evaluation_query,
    evaluate_student_answer,
    mastery_completion_answer,
    with_progress_status,
)
from app.classifier import MessageClassification, classify_message, _classification_from_observation
from app.pipeline_logging import begin_trace, debug_preview, end_trace, log_event, log_exception
from app.schemas import ChatMessage, Source
from app.term_resolution import resolve_term, TOKEN_PATTERN
from platform_app import debate
from platform_app.schemas import ReflectionConfig, TutorConfig, Topic

ROOT = Path(__file__).resolve().parents[1]


def call(tool, method, path, **kwargs):
    if tool != "reflections":
        raise HTTPException(404, "Unknown learning service.")
    env, default = "REFLECTIONS_URL", "http://127.0.0.1:8002"
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




def publish_snapshot(assignment):
    if not assignment["tool"]:
        raise HTTPException(422, "Choose an assigned chatbot before publishing.")
    config = assignment["config"]
    if assignment["tool"] == "aiducate":
        raise HTTPException(503, "AIducate has no connected backend yet. Save a draft for now.")
    if assignment["tool"] == "self-directed-learning":
        return {"config": config}
    if assignment["tool"] == "debate":
        files = db.list_rag_files(course_id=str(assignment["course_id"]))
        allowed = {str(f["document_id"]) for f in files if f.get("document_id")}
        selected = set(config["document_ids"])
        if not selected.issubset(allowed):
            raise HTTPException(422, "Select documents belonging to this course.")
        chosen = selected or allowed
        chunks = (
            db.snapshot_document_chunks(str(assignment["course_id"]), sorted(chosen))
            if chosen
            else []
        )
        if chosen - {c["document_id"] for c in chunks}:
            raise HTTPException(422, "Some course materials have no indexed content. Re-upload them before publishing.")
        return {"config": config, "chunks": chunks}
    if assignment["tool"] == "socratic":
        files = db.list_rag_files(course_id=str(assignment["course_id"]))
        allowed = {str(f["document_id"]) for f in files if f.get("document_id")}
        chosen = set(config["document_ids"]) or allowed
        if files and not allowed:
            raise HTTPException(422, "Your course files were uploaded but have not been indexed. Check the embedding service and reprocess the files before publishing.")
        if not chosen or not chosen.issubset(allowed):
            raise HTTPException(422, "Select documents belonging to this course, or upload course materials first.")
        chunks = db.snapshot_document_chunks(str(assignment["course_id"]), sorted(chosen))
        if chosen - {c["document_id"] for c in chunks}:
            raise HTTPException(422, "Some course materials have no indexed content. Re-upload them before publishing.")
        objective = None
        keywords = tuple(config.get("keywords") or ())
        if not keywords and not config.get("learning_objective_id"):
            raise HTTPException(422, "Add saved keywords to the assignment before publishing this Socratic assignment.")
        if not keywords and config.get("learning_objective_id"):
            objective = db.get_approved_learning_objective(str(assignment["course_id"]), str(config["learning_objective_id"]))
            if objective is None:
                raise HTTPException(422, "Select an approved learning objective belonging to this course.")
            if not objective.get("keywords"):
                raise HTTPException(422, "Add and save at least one keyword for the approved learning objective before publishing.")
            evidence_ids = set(objective.get("source_chunk_ids") or [])
            chunks = [chunk for chunk in chunks if str(chunk["chunk_id"]) in evidence_ids]
            if not chunks:
                raise HTTPException(422, "Include the objective's supporting document in the selected course materials.")
        course = db.get_course(str(assignment["course_id"])) or {}
        return {
            "config": config,
            "chunks": chunks,
            "learning_objective": objective,
            **({"approved_keywords": list(keywords)} if keywords else {}),
            "keyword_glossary": keyword_glossary(
                keywords or tuple(objective.get("keywords") or ()),
                chunks,
            ),
            "course": {
                "course_code": course.get("course_code", ""),
                "title": course.get("title", ""),
                "description": course.get("description", ""),
            },
        }
    if assignment["tool"] == "reflections":
        cfg = ReflectionConfig.model_validate(config)
        cfg.validate_publish()
        # Shared document selection is platform metadata. The existing Reflections
        # engine owns its own configuration schema and is unchanged by this adapter.
        reflection_config = {k: v for k, v in config.items() if k != "document_ids"}
        module = call("reflections", "PUT", f"/internal/platform/modules/{assignment['id']}",
                      json={"name": assignment["title"], "course_id": str(assignment["course_id"]), "config": reflection_config})
        return {"config": config, "module_id": module["id"]}
    raise HTTPException(404, "Unknown assignment tool.")


def _assignment_keywords(snapshot):
    if "approved_keywords" in snapshot:
        return tuple(snapshot["approved_keywords"])
    objective = snapshot.get("learning_objective") or {}
    return tuple(str(word).strip() for word in objective.get("keywords", []) if str(word).strip())


def _keyword_learning_topic(keywords):
    return "Instructor-approved topics: " + ", ".join(keywords)


def _keyword_opening(snapshot, keywords, question=None):
    """Start with a short example quoted from the published course snapshot."""
    focus = keywords[0]
    terms = [word.casefold() for word in re.findall(r"[a-z0-9]+", " ".join(keywords).casefold()) if len(word) >= 4]
    candidates = []
    for chunk in snapshot.get("chunks") or []:
        for sentence in re.split(r"(?<=[.!?])\s+|\n+", str(chunk.get("text") or "")):
            passage = " ".join(sentence.split())
            if not 35 <= len(passage) <= 320:
                continue
            words = re.findall(r"[a-z0-9]+", passage.casefold())
            overlap = sum(any(word.startswith(term) or term.startswith(word) for word in words) for term in terms)
            if not overlap:
                continue
            example_cue = bool(re.search(r"\b(?:example|when|suppose|imagine|if|team|student|developer|reviewer)\b", passage, re.I))
            candidates.append((example_cue, overlap, passage))
    opening = f"Let's begin with **{focus}**."
    if candidates:
        passage = max(candidates, key=lambda item: (item[0], item[1]))[2]
        opening += f"\n\nFor example, consider this from your course material: “{passage}”"
        follow_up = question or f"What is happening in this example, and how does it relate to {focus}?"
    else:
        opening += "\n\nWe'll explore this topic using your course materials."
        follow_up = question or f"What do you already know about {focus}?"
    opening += f"\n\n{follow_up}"
    return opening


def keyword_glossary(keywords, chunks):
    """Build short, course-grounded definitions for student-facing approved terms."""
    sentences = []
    for chunk in chunks:
        for sentence in re.split(r"(?<=[.!?])\s+|\n+", str(chunk.get("text") or "")):
            cleaned = " ".join(sentence.split())
            if 30 <= len(cleaned) <= 500:
                sentences.append(cleaned)
    result = []
    for keyword in keywords:
        term = str(keyword).strip()
        tokens = set(re.findall(r"[a-z0-9]+", term.lower()))
        if not tokens:
            continue
        candidates = []
        for sentence in sentences:
            lowered = sentence.lower()
            sentence_tokens = set(re.findall(r"[a-z0-9]+", lowered))
            overlap = len(tokens & sentence_tokens)
            if not overlap:
                continue
            exact = term.lower() in lowered
            definitional = bool(re.search(r"\b(?:is|are|means|refers to|describes)\b", lowered))
            candidates.append((
                exact,
                overlap == len(tokens),
                definitional,
                -abs(len(sentence) - 150),
                sentence,
            ))
        definition = max(candidates)[-1] if candidates else (
            f"{term} is an instructor-approved concept to recognize, explain, and apply in this assignment."
        )
        if len(definition) > 240:
            definition = definition[:237].rsplit(" ", 1)[0] + "…"
        result.append({"keyword": term, "definition": definition})
    return result


def _concept_check(snapshot, answer_count):
    keywords = _assignment_keywords(snapshot)
    if not keywords:
        objective = snapshot.get("learning_objective") or {}
        objective_name = str(
            objective.get("title") or objective.get("objective") or ""
        ).strip()
        keywords = (objective_name,) if objective_name else ()
    glossary = snapshot.get("keyword_glossary") or keyword_glossary(
        keywords, snapshot.get("chunks") or []
    )
    if not glossary:
        return None
    target = glossary[(answer_count - 3) % len(glossary)]
    choices = [_concept_example(target)]
    choices.extend(
        _concept_example(item)
        for item in glossary
        if item["keyword"] != target["keyword"]
    )
    if len(choices) < 2:
        for chunk in snapshot.get("chunks") or []:
            for sentence in re.split(r"(?<=[.!?])\s+|\n+", str(chunk.get("text") or "")):
                candidate = " ".join(sentence.split())
                if (
                    40 <= len(candidate) <= 240
                    and target["keyword"].casefold() not in candidate.casefold()
                    and candidate not in choices
                ):
                    choices.append(
                        f"A team sees this in practice in the following situation: {candidate}"
                    )
                    break
            if len(choices) >= 2:
                break
    if len(choices) < 2:
        choices.append(
            "A team memorizes the name of the idea but never uses it to make a decision or solve a problem."
        )
    choices = choices[:3]
    correct = choices.pop(0)
    correct_position = hashlib.sha256(target["keyword"].encode()).digest()[0] % (
        len(choices) + 1
    )
    choices.insert(correct_position, correct)
    return {
        "id": f"after-{answer_count}-answers",
        "question": (
            f'Which situation is the best example of using "{target["keyword"]}" in practice?'
        ),
        "hint": (
            f'Look for the situation that applies "{target["keyword"]}" to a concrete task, '
            "not one that merely uses related vocabulary."
        ),
        "options": [
            {"id": f"option-{index + 1}", "text": text}
            for index, text in enumerate(choices)
        ],
    }


def _concept_example(glossary_item):
    term = str(glossary_item["keyword"]).strip()
    definition = " ".join(str(glossary_item["definition"]).split())
    clause = re.sub(rf"\b{re.escape(term)}\b", "", definition, count=1, flags=re.I)
    clause = clause.strip(" .:;-")
    relation = re.match(
        r"^(is|are|means|refers to|describes?|records?|creates?|combines?|identifies?|uses?)\b\s*",
        clause,
        flags=re.I,
    )
    if relation:
        verb = relation.group(1).casefold()
        remainder = clause[relation.end():].strip()
        gerunds = {
            "describe": "describing",
            "describes": "describing",
            "record": "recording",
            "records": "recording",
            "create": "creating",
            "creates": "creating",
            "combine": "combining",
            "combines": "combining",
            "identify": "identifying",
            "identifies": "identifying",
            "use": "using",
            "uses": "using",
        }
        clause = (
            remainder
            if verb in {"is", "are", "means", "refers to"}
            else f"{gerunds.get(verb, verb)} {remainder}".strip()
        )
    if not clause:
        clause = f"applying {term} to make a concrete decision"
    clause = clause[0].lower() + clause[1:]
    return f"A team sees this in practice when its work involves {clause}."


def start(assignment, attempt):
    snapshot = assignment["snapshot"]
    config = snapshot["config"]
    if assignment["tool"] == "debate":
        return {"messages": [{"role": "assistant", "content": config["opening_prompt"] or "Take a position on the scenario and explain your strongest reason."}]}
    if assignment["tool"] == "socratic":
        objective = snapshot.get("learning_objective")
        prompt = config.get("prompt", "").strip()
        state = {"pipeline_version": "local-socratic-v1", "phase": "teaching", "learning_topic": prompt or None}
        assignment_keywords = _assignment_keywords(snapshot)
        if "approved_keywords" in snapshot and assignment_keywords:
            # The example comes from frozen course evidence, never a hard-coded scenario.
            prompt = _keyword_opening(snapshot, assignment_keywords)
            state.update({"learning_topic": _keyword_learning_topic(assignment_keywords),
                          "stable_concept": ", ".join(assignment_keywords)[:120],
                          "active_concept": ", ".join(assignment_keywords)[:120],
                          "objective_keywords": list(assignment_keywords)})
        elif objective:
            # Newly published keyword objectives do not prescribe a fixed scenario.
            # Earlier published snapshots keep the opening the instructor published.
            opening = objective["diagnostic_question"] if "keywords" in objective else "\n\n".join(
                part for part in (objective.get("starting_scenario"), objective["diagnostic_question"]) if part
            )
            keywords = objective.get("keywords") or [objective.get("title") or objective["objective"]]
            prompt = prompt or (
                _keyword_opening(snapshot, keywords, objective["diagnostic_question"])
                if "keywords" in objective and snapshot.get("chunks")
                else opening
            )
            concept = ", ".join(keywords)[:120]
            state.update({"learning_topic": _keyword_learning_topic(keywords) if "keywords" in objective else objective["objective"], "original_question": objective["diagnostic_question"],
                          "stable_concept": concept, "active_concept": concept, "objective_keywords": keywords,
                          "learning_objective_id": objective["objective_id"]})
        return {"messages": ([{"role": "assistant", "content": prompt}] if prompt else []), "socratic": state}
    if assignment["tool"] == "debate":
        opening = config["opening_prompt"] or (
            "Take a position on the scenario and give your strongest reason. "
            "I will challenge your reasoning and help you strengthen it."
        )
        return {"messages": [{"role": "assistant", "content": opening}]}
    if assignment["tool"] == "reflections":
        if config["module_type"] == "milestone_based":
            return {"messages": [{"role": "assistant", "content": config["milestone_prompt"]}]}
        result = call("reflections", "POST", "/internal/platform/start", json={
            "session_id": str(attempt["id"]), "module_id": snapshot["module_id"],
            "student_id": str(attempt["student_id"]), "course_id": str(assignment["course_id"])})
        return {"messages": [{"role": "assistant", "content": result["greeting"]}], "total_questions": result["total_questions"], "question_index": 0}
    raise HTTPException(404, "Unknown assignment tool.")


def _snapshot_titles(chunks):
    return list(dict.fromkeys(str(chunk["title"]) for chunk in chunks))


def _snapshot_context_answer(snapshot, classification: MessageClassification):
    request_type = classification.operational_request
    if request_type == "none":
        return None
    course = snapshot.get("course") or {}
    titles = _snapshot_titles(snapshot.get("chunks") or [])
    keywords = _assignment_keywords(snapshot)
    documents = ", ".join(titles) if titles else "no published documents"
    if request_type == "course_title":
        return f"This assignment belongs to {course.get('course_code', '')}: {course.get('title', '')}.".replace(" :", ":").strip()
    if request_type == "course_scope" and keywords:
        return "This assignment focuses on: " + ", ".join(keywords) + "."
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
    state["next_thinking_step"] = _next_thinking_step(answer) if "?" in answer else ""
    state["keywords"] = list(state["objective_keywords"]) if state.get("objective_keywords") else list(dict.fromkeys([state["stable_concept"]] + concepts if state.get("stable_concept") else concepts))[:5]
    state["last_score"] = score
    return {
        "reply": answer,
        "sources": [source.model_dump() for source in sources],
        "socratic": state,
    }


async def public_socratic_message(content, history, engine_state, learning_topic=None):
    """Run the Socratic teaching pipeline without private course retrieval."""
    state = dict(engine_state or {})
    classification = await classify_message(content, history, learning_topic=learning_topic)
    topic = learning_topic or (
        " ".join(content.split())[:500]
        if classification.route == "learning"
        else "General learning discussion"
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
        return _socratic_result(answer, [], state, classification), topic

    pending = state.pop("pending_clarification", None)
    if pending:
        query = f"{pending['original_question']} {content}".strip()
    elif classification.needs_clarification:
        state["pending_clarification"] = {
            "original_question": content,
            "target": classification.target,
        }
        answer = classification.clarification_question or "What part would you like to understand more clearly?"
        return _socratic_result(answer, [], state, classification), topic
    elif classification.direct_answer:
        return _socratic_result(classification.direct_answer, [], state, classification), topic
    else:
        query = answer_evaluation_query(content, history, classification)

    sources = [
        Source(
            document_id="public-learning-topic",
            chunk_id="public-learning-topic:0",
            title="Learner-selected topic",
            text=f"The learner's chosen learning objective is: {topic}",
            score=1.0,
        )
    ]
    evaluation = await evaluate_student_answer(
        content,
        history,
        sources,
        classification,
        concept_hint=state.get("active_concept"),
        evidence_scope="general",
    )
    if evaluation:
        evaluation = _update_snapshot_progress(state, evaluation)

    if evaluation and evaluation.progress_status == "mastered":
        answer = mastery_completion_answer(evaluation)
    else:
        answer = await rag.generate_answer(
            query,
            history,
            sources,
            classification=classification,
            evaluation=evaluation,
            learning_topic=topic,
            grounding_mode="general",
        )
    return (
        _socratic_result(
            answer,
            sources,
            state,
            classification,
            evaluation.total_score if evaluation else None,
        ),
        topic,
    )


async def _socratic_message(
    assignment,
    attempt,
    content,
    clarification_index=None,
    concept_check_option=None,
):
    """Adapt local-socratic-chat's teaching sequence to a frozen assignment."""
    snapshot = assignment["snapshot"]
    chunks = snapshot.get("chunks") or []
    keywords = _assignment_keywords(snapshot)
    scope_options = {"allowed_keywords": keywords} if keywords else {}
    history = [ChatMessage(**message) for message in attempt["messages"]]
    # The old adapter seeded a generic greeting. It must not disguise the
    # learner's first question as an answer to a diagnostic tutor question.
    if history and history[0].content == "What would you like to explore in the assigned materials?":
        history = history[1:]
    state = dict(attempt["engine_state"].get("socratic") or {})
    state.setdefault("pipeline_version", "local-socratic-v1")
    concept_check = state.get("concept_check")
    student_message = content
    if concept_check_option is not None:
        if not concept_check:
            raise HTTPException(422, "This concept check is no longer available.")
        options = concept_check.get("options") or []
        if not 0 <= concept_check_option < len(options):
            raise HTTPException(422, "Choose one of the available concept-check options.")
        selected_option = options[concept_check_option]
        student_message = (
            f"{selected_option['text']}\n\nMy reason: {content}"
        )
        content = (
            f"I selected this option for the concept check: {selected_option['text']}\n"
            f"My reasoning: {content}"
        )
        state["concept_check_response"] = {
            "id": concept_check["id"],
            "question": concept_check["question"],
            "selected_option": selected_option,
            "reason": content.split("My reasoning: ", 1)[1],
        }
        state["concept_check_completed"] = True
        state.pop("concept_check", None)
    elif concept_check:
        raise HTTPException(
            409, "Choose an option and explain your reason before continuing."
        )
    if state.get("phase") in {"awaiting_reflection", "ready_to_submit"}:
        raise HTTPException(409, "Write your learning summary, then submit this assignment.")
    trace = begin_trace(uuid.uuid4().hex, str(attempt["id"]))
    started = monotonic()
    try:
        topic = _keyword_learning_topic(keywords) if keywords else state.get("learning_topic")
        if keywords:
            # Reload the full authoritative list even for an attempt started before this update.
            state.update({"objective_keywords": list(keywords), "learning_topic": topic,
                          "stable_concept": ", ".join(keywords)[:120], "active_concept": ", ".join(keywords)[:120]})
        if not topic:
            topic = next((m.content for m in history if m.role == "user"), None)
        pending = state.get("pending_clarification")
        interpreted = content
        if clarification_index is not None:
            options = (pending or {}).get("options", [])
            if not 0 <= clarification_index < len(options):
                raise HTTPException(422, "This clarification choice is no longer available.")
            interpreted = options[clarification_index]["resolved_message"]
        log_event(1, "assignment_chat_received", assignment_id=assignment["id"], message_chars=len(content), pipeline_version="local-socratic-v1")
        classification = await classify_message(interpreted, history, learning_topic=topic, **scope_options)
        if keywords:
            state["keyword_scope_match"] = classification.keyword_scope_match
            log_event(4, "assignment_keyword_scope_checked", approved_keywords=list(keywords),
                      keyword_scope_match=classification.keyword_scope_match)
            if classification.conversation_action not in {"soft_close", "complete"}:
                if classification.keyword_scope_match is None:
                    raise HTTPException(503, "I couldn’t check this question against the assignment’s approved topics. Please try again.")
                if not classification.keyword_scope_match:
                    state["clarification_options"] = []
                    state.pop("pending_clarification", None)
                    return _socratic_result("This assignment focuses on " + ", ".join(keywords)
                        + ". Ask about one of those topics so we can continue.", [], state, classification)
        if clarification_index is not None:
            classification = replace(_classification_from_observation(
                message_role=options[clarification_index]["message_role"],
                concepts=classification.target_concepts,
                rewritten_query=classification.rewritten_query or interpreted,
                source="student_clarification_choice",
            ), keyword_scope_match=classification.keyword_scope_match)
        if topic and classification.message_role == "topic_change" and not keywords:
            return _socratic_result("This chat is focused on its original topic. Start a new chat to explore a different topic.", [], state, classification)
        if classification.route == "learning" and not classification.needs_clarification:
            topic = topic or " ".join(content.split())[:500]
            state["learning_topic"] = topic
            if "approved_keywords" in snapshot and not state.get("original_question"):
                state["original_question"] = content
            if not state.get("stable_concept"):
                state["stable_concept"] = state.get("active_concept") or classification.target or topic
            state["active_concept"] = state["stable_concept"]
        stable = state.get("stable_concept") or state.get("active_concept")
        state.update({"phase": "teaching", "message_role": classification.message_role,
                      "dialogue_status": classification.dialogue_status, "conversation_action": classification.conversation_action,
                      "conversation_status": "active", "clarification_options": []})
        state["classification"] = {
            "approved_keywords": list(keywords), "keyword_scope_match": classification.keyword_scope_match,
            "message_role": classification.message_role, "route": classification.route,
            "dialogue_status": classification.dialogue_status, "conversation_action": classification.conversation_action,
            "assessment_candidate": classification.assessment_candidate,
            "target_concepts": list(classification.target_concepts), "retrieval_query": classification.rewritten_query,
        }
        log_event(4, "message_classification_completed", **state["classification"])
        if classification.conversation_action in {"soft_close", "complete"}:
            state["conversation_status"] = "paused"
            return _socratic_result(await rag.generate_conversation_transition(content, history, classification), [], state, classification)
        operational = _snapshot_context_answer(snapshot, classification)
        if operational:
            return _socratic_result(operational, [], state, classification)
        if classification.needs_clarification:
            choices = [option.model_dump() for option in classification.clarification_options]
            state["pending_clarification"] = {"original_question": content, "options": choices}
            state["clarification_options"] = choices
            return _socratic_result(classification.clarification_question or "What would you like me to clarify?", [], state, classification)
        if classification.direct_answer:
            return _socratic_result(classification.direct_answer, [], state, classification)
        query = answer_evaluation_query(interpreted, history, classification, stable_concept=stable)
        if pending:
            query = f"{pending['original_question']} {query}".strip()
            state.pop("pending_clarification", None)
        vocabulary = list(dict.fromkeys(TOKEN_PATTERN.findall("\n".join(str(chunk.get("text", "")) for chunk in chunks))))[:12000]
        resolution = await resolve_term(content, history, None, str(attempt["id"]), document_terms=vocabulary)
        extras = [topic] if topic else []
        if resolution:
            extras.append(re.sub(rf"\b{re.escape(resolution.original_term)}\b", resolution.selected_term, query, flags=re.I))
        for subquery in classification.retrieval_subqueries[:2]:
            extras.append(subquery if not stable or stable.casefold() in subquery.casefold() else f"{stable} {subquery}")
        if keywords:
            # No unanchored student/model query may retrieve another topic independently.
            anchor = ", ".join(keywords)
            query = f"Instructor-approved keywords: {anchor}\nLearning question: {query}"
            extras = [f"Instructor-approved keywords: {anchor}\nLearning question: {extra}" for extra in extras]
        sources = _retrieve_assignment_sources(query, chunks, extras)
        if not sources and classification.operational_request == "document_overview":
            sources = rag.snapshot_overview(chunks, top_k=4)
        # Selecting an interpretation is not evidence of subject understanding.
        evaluation = None if pending else await evaluate_student_answer(content, history, sources, classification, concept_hint=stable, **scope_options)
        assessment = None
        if evaluation:
            if stable and evaluation.concept != stable:
                evaluation = replace(evaluation, concept=stable)
            evaluation = _update_snapshot_progress(state, evaluation)
            assessment = asdict(evaluation)
            state["latest_assessment"] = assessment
            log_event(6, "concept_progress_updated", concept=evaluation.concept, score=evaluation.total_score,
                      status=evaluation.progress_status, critical_misconception=evaluation.critical_misconception)
        answer_count = int(state.get("answered_question_count") or 0)
        if evaluation and classification.assessment_candidate:
            answer_count += 1
            state["answered_question_count"] = answer_count
        should_show_concept_check = (
            answer_count >= 3
            and not state.get("concept_check_completed")
            and not state.get("concept_check")
        )
        if evaluation and evaluation.ready_to_complete and not should_show_concept_check:
            state["phase"] = "awaiting_reflection"
            state["checkpoint"] = {"original_question": state.get("original_question") or topic or evaluation.concept, "latest_answer": content, "evaluation": assessment}
            answer = "Before I give final feedback, summarize what you learned in your own words. Use our example to explain the original question."
        else:
            generation_message = (f"Regarding my earlier message ({pending['original_question']}): {interpreted}"
                                  if pending else interpreted)
            answer = await rag.generate_answer(generation_message, history, sources, classification=classification,
                evaluation=evaluation, learning_topic=topic, stable_concept=stable,
                term_resolution=(resolution.original_term, resolution.selected_term) if resolution else None, **scope_options)
        result = _socratic_result(answer, sources, state, classification, evaluation.total_score if evaluation else None)
        if should_show_concept_check:
            state["concept_check"] = _concept_check(snapshot, answer_count)
        if concept_check_option is not None:
            result["student_message"] = student_message
        if assessment:
            result["assessment"] = assessment
        log_event(12, "assignment_response_returned", phase=state["phase"], sources=len(sources), latency_ms=round((monotonic()-started)*1000))
        return result
    except Exception as error:
        log_exception(12, "assignment_pipeline_failed", error)
        raise
    finally:
        end_trace(trace)


def _retrieve_assignment_sources(query, chunks, extra_queries=()):
    queries = list(dict.fromkeys([query, *(str(q) for q in extra_queries if q)]))[:4]
    # All searches remain inside the instructor-published assignment snapshot.
    ranked = [rag.retrieve_snapshot(q, chunks, top_k=4) for q in queries]
    result, seen = [], set()
    for rank in range(4):
        for matches in ranked:
            if rank < len(matches) and matches[rank].chunk_id not in seen:
                result.append(matches[rank]); seen.add(matches[rank].chunk_id)
                if len(result) == 4:
                    return result
    return result


async def _socratic_reflection(assignment, attempt, reflection):
    state = dict(attempt["engine_state"].get("socratic") or {})
    if state.get("completion_summary"):
        return {"socratic": state}
    checkpoint = state.get("checkpoint")
    if state.get("phase") != "awaiting_reflection" or not checkpoint:
        raise HTTPException(409, "Finish the teaching sequence before writing your summary.")
    trace = begin_trace(uuid.uuid4().hex, str(attempt["id"]))
    try:
        history = [ChatMessage(**message) for message in attempt["messages"]]
        keywords = _assignment_keywords(assignment["snapshot"])
        scope_options = {"allowed_keywords": keywords} if keywords else {}
        anchor = "Instructor-approved keywords: " + ", ".join(keywords) + "\n" if keywords else ""
        sources = _retrieve_assignment_sources(anchor + checkpoint["original_question"], assignment["snapshot"].get("chunks") or [], [anchor + reflection])
        summary = await rag.generate_completion_summary(checkpoint["original_question"], checkpoint["latest_answer"],
            history, sources, AnswerEvaluation(**checkpoint["evaluation"]), reflection, **scope_options)
        state.update({"phase": "ready_to_submit", "student_reflection": reflection, "completion_summary": summary.model_dump()})
        log_event(12, "assignment_summary_returned", phase="ready_to_submit")
        return {"socratic": state, "reply": summary.final_comment}
    finally:
        end_trace(trace)


def reflect(assignment, attempt, reflection):
    if assignment["tool"] != "socratic":
        raise HTTPException(422, "This assignment does not use a Socratic learning summary.")
    return asyncio.run(_socratic_reflection(assignment, attempt, reflection))

def message(
    assignment,
    attempt,
    content,
    request_id,
    clarification_index=None,
    concept_check_option=None,
):
    tool = assignment["tool"]
    cfg = assignment["snapshot"]["config"]
    if tool == "debate":
        return {"reply": asyncio.run(debate.generate_reply(cfg["scenario"], attempt["messages"], content))}
    if tool == "socratic":
        return asyncio.run(
            _socratic_message(
                assignment,
                attempt,
                content,
                clarification_index,
                concept_check_option,
            )
        )
    if tool == "debate":
        chunks = assignment["snapshot"].get("chunks") or []
        sources = rag.retrieve_snapshot(
            f"{cfg['scenario']}\n\nStudent argument: {content}", chunks, top_k=4
        ) if chunks else []
        reply = asyncio.run(
            debate.generate_reply(
                cfg["scenario"], attempt["messages"], content, sources=sources
            )
        )
        return {
            "reply": reply,
            "sources": [source.model_dump() for source in sources],
        }
    if tool == "reflections":
        if cfg["module_type"] == "milestone_based":
            result = call(tool, "POST", "/api/rec-sys/milestone", json={
                "module_id": assignment["snapshot"]["module_id"], "student_name": str(attempt["student_id"]), "reflection": content})
            return {"reply": "Your reflection has been submitted.", "result": result, "completed": True}
        return call(tool, "POST", "/internal/platform/message", json={"session_id": str(attempt["id"]), "message": content, "request_id": request_id})
    raise HTTPException(404, "Unknown assignment tool.")


def complete(assignment, attempt):
    tool = assignment["tool"]
    count = sum(m["role"] == "user" for m in attempt["messages"])
    if tool == "socratic":
        state = attempt["engine_state"].get("socratic") or {}
        if state.get("phase") != "ready_to_submit" or not state.get("completion_summary"):
            raise HTTPException(422, "Finish the teaching sequence and write your own learning summary before submitting.")
        return {"message_count": count, "completion_summary": state["completion_summary"], "student_reflection": state.get("student_reflection", "")}
    if tool == "debate":
        minimum = assignment["snapshot"]["config"]["minimum_messages"]
        if count < minimum:
            raise HTTPException(
                422,
                f"Send at least {minimum} message(s) before completing this assignment.",
            )
        return {"message_count": count}
    if tool == "reflections":
        if assignment["snapshot"]["config"]["module_type"] == "milestone_based":
            raise HTTPException(422, "Submit your reflection to complete this assignment.")
        if not count:
            raise HTTPException(422, "Respond to the reflection before ending the session.")
        return call(tool, "POST", "/internal/platform/end", json={"session_id": str(attempt["id"])})
    raise HTTPException(404, "Unknown assignment tool.")


def self_directed_call(student_id: str, method: str, path: str, **kwargs):
    """Call the standalone SDL service while the platform retains authentication."""
    base = os.getenv("SELF_DIRECTED_LEARNING_URL", "http://127.0.0.1:8100").rstrip("/")
    headers = {"X-Demo-User": student_id}
    token = os.environ.get("PLATFORM_SERVICE_TOKEN", "")
    if token:
        headers["X-Platform-Service"] = token
    try:
        with httpx.Client(timeout=180, headers=headers) as client:
            response = client.request(method, base + path, **kwargs)
        if response.is_error:
            detail = response.json().get("detail", "") if response.status_code < 500 else ""
            raise HTTPException(
                response.status_code if response.status_code < 500 else 502,
                detail or "Self-Directed Learning could not complete this action. Please retry.",
            )
        return response.json()
    except HTTPException:
        raise
    except (httpx.HTTPError, ValueError) as exc:
        raise HTTPException(503, "Self-Directed Learning is unavailable. Please retry shortly.") from exc


_student_identity_cache = {}


def resolve_self_directed_student(account: dict) -> str:
    base = os.getenv("SELF_DIRECTED_LEARNING_URL", "http://127.0.0.1:8100").rstrip("/")
    token = os.environ.get("PLATFORM_SERVICE_TOKEN", "")
    if not token:
        raise HTTPException(503, "The platform service connection is not configured.")
    # Cache only the cross-service identity mapping. Enrollment and assignment
    # permissions are still checked by the route on every request.
    identity_key = (base, token, str(account["user_id"]), account["email"], account.get("display_name"), account["username"])
    cached_identity = _student_identity_cache.get(identity_key)
    if cached_identity and cached_identity[1] > monotonic():
        return cached_identity[0]
    try:
        with httpx.Client(timeout=30, headers={"X-Platform-Service": token}) as client:
            response = client.post(
                base + "/internal/platform/students/resolve",
                json={
                    "platform_user_id": str(account["user_id"]),
                    "email": account["email"],
                    "display_name": account.get("display_name") or account["username"],
                },
            )
        if response.is_error:
            detail = response.json().get("detail", "") if response.status_code < 500 else ""
            raise HTTPException(
                response.status_code if response.status_code < 500 else 502,
                detail or "The student profile could not be connected to Self-Directed Learning.",
            )
        student_id = str(response.json()["id"])
        if len(_student_identity_cache) >= 500:
            _student_identity_cache.clear()
        _student_identity_cache[identity_key] = (student_id, monotonic() + 300)
        return student_id
    except HTTPException:
        raise
    except (httpx.HTTPError, KeyError, ValueError) as exc:
        raise HTTPException(503, "Self-Directed Learning is unavailable. Please retry shortly.") from exc
