"""Chat service — manages in-memory session state and LLM calls."""

from __future__ import annotations

import json
import re
import uuid
from dataclasses import dataclass, field

from app.services.llm import LLMProvider
from app.services.prompts import build_reflection_prompt, build_question_generation_prompt


@dataclass
class Session:
    session_id: str
    student_id: str
    module_id: str
    config: dict
    messages: list[dict] = field(default_factory=list)
    questions: list[str] = field(default_factory=list)   # pre-generated questions
    question_idx: int = 0
    is_bonus_phase: bool = False
    wrong_subtopics: list[str] = field(default_factory=list)  # for adaptive bonus


# In-memory store — good enough for a single-process prototype.
_sessions: dict[str, Session] = {}


def _generate_questions(sub_topics: list[str], config: dict, llm: LLMProvider) -> list[str]:
    """Call LLM to generate one question per sub-topic."""
    if not sub_topics:
        return []
    prompt = build_question_generation_prompt(sub_topics, config)
    try:
        raw = llm.generate([{"role": "user", "content": prompt}])
        # Strip markdown fences if present
        text = re.sub(r"^```[a-z]*\n?", "", raw.strip(), flags=re.MULTILINE).strip("`").strip()
        questions = json.loads(text)
        if not isinstance(questions, list):
            raise ValueError("Not a list")
        # Ensure we have exactly one question per sub-topic
        result = []
        for i, topic in enumerate(sub_topics):
            if i < len(questions) and isinstance(questions[i], str) and questions[i].strip():
                result.append(questions[i].strip())
            else:
                result.append(f"What do you know about {topic}?")
        return result
    except Exception:
        return [f"What do you know about {topic}?" for topic in sub_topics]


def _parse_llm_json(raw: str) -> tuple[bool, str]:
    """Parse LLM JSON response {adequate: bool, reply: str}.

    Falls back gracefully if the LLM doesn't comply with JSON format.
    """
    try:
        text = re.sub(r"^```[a-z]*\n?", "", raw.strip(), flags=re.MULTILINE).strip("`").strip()
        data = json.loads(text)
        return bool(data.get("adequate", False)), str(data.get("reply", raw))
    except Exception:
        return False, raw


def start_session(
    student_id: str,
    module_id: str,
    config: dict,
    llm: LLMProvider,
    past_weak_areas: list[str] | None = None,
) -> tuple[str, str, int]:
    """Create a new chat session and return (session_id, greeting, total_questions)."""
    sub_topics = config.get("sub_topics", [])
    questions = _generate_questions(sub_topics, config, llm)

    system_prompt = build_reflection_prompt(config, questions, past_weak_areas or [])
    greeting = questions[0] if questions else "What did you learn this week?"

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "assistant", "content": greeting},
    ]

    session = Session(
        session_id=str(uuid.uuid4()),
        student_id=student_id,
        module_id=module_id,
        config=config,
        messages=messages,
        questions=questions,
        question_idx=0,
        is_bonus_phase=(len(questions) == 0),
    )
    _sessions[session.session_id] = session
    return session.session_id, greeting, len(questions)


def send_message(
    session_id: str,
    user_msg: str,
    llm: LLMProvider,
    time_remaining: int = 600,
) -> tuple[str, int, int, bool]:
    """Append user message, call LLM, return (reply, question_index, total_questions, is_bonus_phase)."""
    session = _sessions.get(session_id)
    if session is None:
        raise KeyError(f"Session {session_id} not found")

    total = len(session.questions)
    sub_topics = session.config.get("sub_topics", [])
    was_bonus = session.is_bonus_phase

    # Build content with context injections
    content = user_msg

    # Inject current question context so the LLM always knows exactly which question to evaluate
    if not session.is_bonus_phase and session.question_idx < total:
        current_q = session.questions[session.question_idx]
        content = f"[Q{session.question_idx + 1}/{total}: {current_q}] {content}"
    elif session.is_bonus_phase:
        bonus_ctx = "BONUS PHASE"
        if session.wrong_subtopics:
            bonus_ctx += f" - revisit weak areas: {', '.join(session.wrong_subtopics)}"
        content = f"[{bonus_ctx}] {content}"

    session.messages.append({"role": "user", "content": content})
    raw_reply = llm.generate(session.messages)

    # Parse JSON response
    adequate, reply = _parse_llm_json(raw_reply)

    # Track wrong subtopics for adaptive bonus
    if not adequate and not session.is_bonus_phase and session.question_idx < len(sub_topics):
        wrong_topic = sub_topics[session.question_idx]
        if wrong_topic not in session.wrong_subtopics:
            session.wrong_subtopics.append(wrong_topic)

    # Advance question index if adequate
    if adequate and not session.is_bonus_phase:
        session.question_idx += 1
        if session.question_idx >= total:
            session.is_bonus_phase = True
            session.question_idx = total

    # On transition to bonus phase: acknowledgment first, then intro, then first bonus question
    bonus_just_started = not was_bonus and session.is_bonus_phase
    if bonus_just_started:
        if session.wrong_subtopics:
            weak_str = ", ".join(session.wrong_subtopics)
            intro = f"Since you had some trouble with {weak_str}, let's chat more on that."
        else:
            intro = "Great work covering all the questions! Let's explore some deeper topics."

        # reply = LLM's acknowledgment of the last answer; append it + intro as one assistant turn
        transition = reply + " " + intro
        session.messages.append({"role": "assistant", "content": transition})

        # Synthetic trigger so the LLM asks the first real bonus question
        bonus_ctx = "BONUS PHASE"
        if session.wrong_subtopics:
            bonus_ctx += f" - revisit: {', '.join(session.wrong_subtopics)}"
        session.messages.append({"role": "user", "content": f"[{bonus_ctx}] (ready for first bonus question)"})
        raw_bonus = llm.generate(session.messages)
        _, bonus_q = _parse_llm_json(raw_bonus)
        session.messages.append({"role": "assistant", "content": bonus_q})

        full_reply = transition + "\n\n" + bonus_q
        return full_reply, session.question_idx, total, session.is_bonus_phase

    session.messages.append({"role": "assistant", "content": reply})
    return reply, session.question_idx, total, session.is_bonus_phase


def end_session(session_id: str) -> Session:
    """Pop and return the completed session."""
    session = _sessions.pop(session_id, None)
    if session is None:
        raise KeyError(f"Session {session_id} not found")
    return session


def format_transcript(messages: list[dict]) -> str:
    """Convert message list into a readable transcript string."""
    lines = []
    for msg in messages:
        role = msg["role"].upper()
        if role == "SYSTEM":
            continue
        lines.append(f"{role}: {msg['content']}")
    return "\n\n".join(lines)
