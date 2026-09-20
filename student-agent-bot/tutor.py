"""Socratic tutor with phased lesson flow."""

import re
from dataclasses import dataclass, field

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

from models import get_model, invoke_with_retry
from topics import get_topic

PHASES = ("reading", "checking", "practice", "complete")

RETURN_PATTERN = re.compile(
    r"\b(i'?m back|i am back|i'?m here|i am here|done reading|finished reading|"
    r"read it|read them|back now|ready to talk|let'?s talk|let'?s go|let us go|"
    r"i read it|i'?ve read|i have read|finished the (article|reading|link)|"
    r"ready to (start|continue)|ok(?:ay)?(?: i'?m)? ready|i skimmed|"
    r"went through it|done with the reading|i went through|read through)\b",
    re.IGNORECASE,
)
RECAP_PATTERN = re.compile(
    r"\b(i understood|one thing i|i('m| am) unsure|not sure about|"
    r"what i got|what clicked|still fuzzy|i learned that)\b",
    re.IGNORECASE,
)
PRACTICE_READY_PATTERN = re.compile(
    r"\b(let'?s practice|ready to practice|want to (try|practice|apply|build)|"
    r"try a scenario|let'?s (apply|build|try)|move to practice|"
    r"i'?m ready to (try|build|practice))\b",
    re.IGNORECASE,
)
BACK_READING_PATTERN = re.compile(
    r"\b(re-?read|read( it)? again|back to the (link|reading|article)s?|"
    r"go back to reading|skim again)\b",
    re.IGNORECASE,
)
BACK_TALK_PATTERN = re.compile(
    r"\b(still (vague|unclear|confused|fuzzy|lost)|go back to "
    r"(the )?(question|talk|discussion|check)|talk (it|this) through|"
    r"revisit that|can we (go back|revisit)|i don'?t get (that|the) earlier)\b",
    re.IGNORECASE,
)
BACK_PRACTICE_PATTERN = re.compile(
    r"\b(back to practice|return to (the )?practice|keep building|"
    r"continue (the )?exercise)\b",
    re.IGNORECASE,
)
WRAP_PATTERN = re.compile(
    r"\b(done with practice|finished (the )?(exercise|practice|build)|"
    r"that'?s my (diagram|answer|design)|i'?m done building)\b",
    re.IGNORECASE,
)
WANT_EXAMPLE_PATTERN = re.compile(
    r"\b(show (me )?(an |the )?(example|model|answer)|what would a complete "
    r"(one|version) look like|can i see (the|a) (model|worked) example)\b",
    re.IGNORECASE,
)
DONE_PATTERN = re.compile(
    r"\b(no doubts|all good|that'?s it|we'?re done|i'?m done|looks good|"
    r"no more questions)\b",
    re.IGNORECASE,
)
FINISH_PATTERN = re.compile(
    r"\b(no doubts|no more questions|that'?s all|i'?m good|all good|"
    r"nothing else|thanks(?: you)?|thank you|end session|all set|bye)\b",
    re.IGNORECASE,
)
IDK_PATTERN = re.compile(
    r"\b(i don'?t know|i dunno|no idea|not sure|idk|i have no idea)\b",
    re.IGNORECASE,
)

TEACHER_CORE = """
## Role
You are a self-directed-learning coach for a freshman/sophomore undergraduate.
This may be their first course on this material. No industry, interview, or cert-prep tone.
The student thinks; you facilitate. Stay inside **this session's topic only**.
The learning goal is the session topic — do not change the topic.

## Voice
- Warm, brief, conversational. 2–4 sentences unless they asked you to define a term.
- One move per turn: acknowledge in a few words → one question. At most one question mark.
- Never stack two questions. Never ask them to "explain the difference" or "define both" —
  that produces a recap. Ask them to apply: pick A or B, or name one everyday situation
  using only terms they already used.
- Everyday language. If you analogize, keep it generic and familiar — do not import another course topic.
- Do not lecture, recap a textbook, or paste a complete worked solution during checking/practice.

## Method (self-directed)
- Elicit first from what THEY just said. Follow their understanding and their confusion.
- Never run a numbered quiz or a fixed list of check questions.
- After they attempt: praise the reasoning you can use, then correct only the one most important miss.
- Wrong or half-right answers are useful — do not restart the lesson or dump the full key.
- If they ask "what is X?", give a 1–2 sentence plain definition, then have them use it immediately.
- If they are stuck ("I don't know" / blank): ONE hint, simpler sub-question, or everyday analogy.
  After 2+ stalls on the same idea, a smaller nudge — still not the full answer.
- After reading, if they give a takeaway AND a doubt: the takeaway is the current work.
  The doubt is often a later, harder distinction — park it. First confirm they can APPLY
  the thing they said they understood (a concrete example or A vs B on THAT idea only).
  Do not open with the doubted idea until the takeaway holds up.
- Only then, if the foundation is solid, invite the parked doubt — still by applying it,
  not by defining it.

## Anti-loop (important)
- Never open a turn by repeating the definition you just gave.
- Never teach the doubted idea in the same message you ask about it.
- If the last two student messages are "I understood [your words] / still unsure…", they are
  parroting, not learning. Stop explaining. Demand a specific attempt or switch to practice.
- If something they thought they knew is still vague, stay there or go back with them. Do not force the next stage.
- Brand/product/vendor names: only if this topic is about them, or the student used them first.

## Handling different students
- Confused / mixed-up: they may state something wrong. Treat it as an attempt. Untangle one mix-up.
- Missing background: define the assumed word in one sentence, then ask them to try.
- Overconfident: do not rubber-stamp. Ask them to justify. If they skip a step, ask why that first,
  then decide together whether to rewind.

## Never
- Never answer your own eliciting question in the same message.
- Never give the full artifact, full list, or full diagram until they ask at wrap-up.
- Never copy the student's wording back as a lecture. Never switch topics.
"""

MAX_COMPLETE_FOLLOWUPS = 3

PHASE_LABELS = {
    "reading": "Read — then share one takeaway and one doubt",
    "checking": "Talk it through — questions from what you said",
    "practice": "Practice — pick a scenario, then build",
    "complete": "Wrap-up — you self-assess first",
    "ended": "Ended — transcript only",
}

NAV_LABELS = {
    "reading": "Re-read",
    "checking": "Talk it through",
    "practice": "Practice",
    "complete": "Wrap-up",
}


def session_status(session: "Session") -> str:
    if session.ended:
        return "ended"
    if session.phase == "complete":
        return "complete"
    return "active"


def practice_options_for(topic: dict) -> list[str]:
    raw = topic.get("practice_options")
    if isinstance(raw, list):
        options = [str(item).strip() for item in raw if str(item).strip()]
        if options:
            return options[:4]
    label = str(topic.get("practice_label") or "").strip()
    if label:
        return [label, "a campus app you actually use", "a small system you invent"]
    return ["a campus app you actually use", "a small system you invent", "the example from the reading"]


def _unlock(session: "Session", phase: str) -> None:
    if phase in PHASES and phase not in session.unlocked_phases:
        session.unlocked_phases.append(phase)


@dataclass
class Session:
    session_id: str
    topic_id: str
    provider: str
    personality: str = "confused"
    phase: str = "reading"
    messages: list[dict] = field(default_factory=list)
    practice_steps: int = 0
    practice_stage: int = 0
    awaiting_answer: bool = False
    ended: bool = False
    complete_followups: int = 0
    unlocked_phases: list[str] = field(default_factory=lambda: ["reading"])
    practice_scenario: str = ""
    shared_model_example: bool = False
    checking_turns: int = 0
    topic_snapshot: dict | None = None

    def to_public(self) -> dict:
        topic = (self.topic_snapshot or get_topic(self.topic_id))
        options = practice_options_for(topic)
        return {
            "session_id": self.session_id,
            "topic_id": self.topic_id,
            "topic_name": topic["name"],
            "provider": self.provider,
            "personality": self.personality,
            "phase": self.phase,
            "phase_label": PHASE_LABELS.get(self.phase, self.phase),
            "status": session_status(self),
            "practice_steps": self.practice_steps,
            "complete_followups": self.complete_followups,
            "complete_followups_remaining": max(
                0, MAX_COMPLETE_FOLLOWUPS - self.complete_followups
            ),
            "ended": self.ended,
            "messages": self.messages,
            "unlocked_phases": list(self.unlocked_phases),
            "practice_options": options,
            "practice_scenario": self.practice_scenario,
            "awaiting_scenario": self.phase == "practice" and not self.practice_scenario,
            "shared_model_example": self.shared_model_example,
            "nav": [
                {
                    "id": phase,
                    "label": NAV_LABELS[phase],
                    "current": self.phase == phase,
                    "unlocked": phase in self.unlocked_phases or phase == "reading",
                }
                for phase in PHASES
            ],
        }


def _opening_message(topic_id: str, topic_snapshot: dict | None = None) -> str:
    topic = topic_snapshot or get_topic(topic_id)
    primary = topic["resource"]
    alt = topic["alt_resource"]
    return (
        f"Today we're working on **{topic['name']}**. That goal stays fixed — "
        f"you do the thinking, I'll coach with questions.\n\n"
        f"Pick **one** of these to skim (whichever looks more useful to you):\n\n"
        f"1. [{primary['title']}]({primary['url']})\n"
        f"2. [{alt['title']}]({alt['url']})\n\n"
        f"When you're back, tell me **one thing you understood** and **one thing you're "
        f"still unsure about**. No need to memorize the whole article."
    )


def create_session(session_id: str, topic_id: str, provider: str, personality: str, topic_snapshot: dict | None = None) -> Session:
    session = Session(
        session_id=session_id,
        topic_id=topic_id,
        provider=provider,
        personality=personality,
        phase="reading",
        topic_snapshot=topic_snapshot,
    )
    session.messages.append({"role": "assistant", "content": _opening_message(topic_id, topic_snapshot)})
    return session


def _history_for_llm(messages: list[dict], *, limit: int = 10) -> list:
    recent = messages[-limit:]
    out = []
    for msg in recent:
        if msg["role"] == "assistant":
            out.append(AIMessage(content=msg["content"]))
        else:
            out.append(HumanMessage(content=msg["content"]))
    return out


def _practice_stage_info(session: Session) -> tuple[dict | None, list[dict]]:
    topic = (session.topic_snapshot or get_topic(session.topic_id))
    stages = topic.get("practice_stages", [])
    if not stages or session.practice_stage >= len(stages):
        return None, stages
    return stages[session.practice_stage], stages


def _match_scenario(message: str, options: list[str]) -> str | None:
    text = message.strip().lower()
    if not text:
        return None
    for index, option in enumerate(options, start=1):
        if option.lower() in text or text in option.lower():
            return option
        ordinal = {1: "first", 2: "second", 3: "third", 4: "fourth"}.get(index)
        if re.search(rf"\b(option\s*{index}|{index}\b|{ordinal})\b", text):
            return option
    return None


def _build_tutor_system(session: Session) -> str:
    topic = (session.topic_snapshot or get_topic(session.topic_id))
    options = practice_options_for(topic)
    options_text = "; ".join(options)

    stage, all_stages = (None, [])
    practice_hint = ""
    if session.phase == "practice":
        stage, all_stages = _practice_stage_info(session)
        if not session.practice_scenario:
            practice_hint = f"""
## Practice scenario (not chosen yet)
Offer these options and let the student pick ONE. Do not start building until they choose.
Options: {options_text}
They may also name their own similar scenario — then use that.
"""
        elif stage:
            order = " → ".join(s["label"] for s in all_stages)
            practice_hint = f"""
## Chosen scenario
{session.practice_scenario}

## Current practice stage: {stage['label']} (step {session.practice_stage + 1}/{len(all_stages)})
Stage focus: {stage['focus']}
Recommended build order: {order}
If they jump ahead, ask why that first — then rewind only if the current step is still vague.
Do NOT give the full solution yet.
"""
    else:
        all_stages = (session.topic_snapshot or get_topic(session.topic_id)).get("practice_stages", [])

    scenario_line = session.practice_scenario or "(not chosen yet)"

    return f"""You are coaching an undergrad through a self-directed lesson.

{TEACHER_CORE}

## This session
Topic (fixed): **{topic['name']}**
Simulated-student style (if they are using Simulate): {session.personality}
Practice scenario: {scenario_line}

## Current phase: {session.phase}
{PHASE_LABELS.get(session.phase, "")}

## Phase rules
- **reading**: They skim one link. Do NOT quiz. Wait for one takeaway + one doubt.
  If they only say "ready", ask for those two things.
- **checking**: Interactive Q&A from the conversation — especially what they said they
  understood (probe if it's solid) and what they said they are unsure about.
  No script, no "question 1 of 4". One question per turn. When they want to apply it,
  they can move to practice.
- **practice**: {topic['practice_prompt']}
  First they choose a scenario from the options (or invent a similar one). Then ONE
  guiding question per turn. Student proposes; you coach.
- **complete**: Do NOT dump the model answer first. Ask them to self-assess:
  what can they do now, and what is still fuzzy? Share this worked example ONLY if they ask:
  {topic['final_example']}
  They can jump back to talk/practice if something is still vague.
- **ended**: Session closed (should not reach here).
{practice_hint}

## Counters
Practice stage: {session.practice_stage + 1 if all_stages else 0}/{len(all_stages) if all_stages else 0}
Complete follow-ups used: {session.complete_followups}/{MAX_COMPLETE_FOLLOWUPS}
"""


def _close_from_complete(session: Session, reason: str = "finished") -> str:
    topic = (session.topic_snapshot or get_topic(session.topic_id))
    if reason == "finished":
        goodbye = (
            f"Awesome — sounds like you're all set on **{topic['name']}**! "
            "Session closed. Download your transcript anytime, or reset for a new topic."
        )
    else:
        goodbye = (
            f"We've covered your follow-up questions on **{topic['name']}**. "
            "Session closed — great work today!"
        )
    session.ended = True
    session.phase = "ended"
    return goodbye


def _apply_navigation_intent(session: Session, user_message: str) -> bool:
    """Return True if the message jumped phases."""
    if BACK_READING_PATTERN.search(user_message) and session.phase != "reading":
        session.phase = "reading"
        return True
    if (
        BACK_TALK_PATTERN.search(user_message)
        and session.phase in ("practice", "complete")
        and "checking" in session.unlocked_phases
    ):
        session.phase = "checking"
        return True
    if (
        BACK_PRACTICE_PATTERN.search(user_message)
        and session.phase in ("checking", "complete", "reading")
        and "practice" in session.unlocked_phases
    ):
        session.phase = "practice"
        return True
    return False


def _update_phase(session: Session, user_message: str) -> None:
    topic = (session.topic_snapshot or get_topic(session.topic_id))
    options = practice_options_for(topic)

    if _apply_navigation_intent(session, user_message):
        session.awaiting_answer = False
        return

    if session.phase == "reading" and (
        RETURN_PATTERN.search(user_message) or RECAP_PATTERN.search(user_message)
    ):
        session.phase = "checking"
        _unlock(session, "checking")
        _unlock(session, "practice")
        session.awaiting_answer = False
        return

    if session.phase == "checking":
        session.checking_turns += 1
        if PRACTICE_READY_PATTERN.search(user_message):
            session.phase = "practice"
            _unlock(session, "practice")
            session.awaiting_answer = False
        return

    if session.phase == "practice":
        if not session.practice_scenario:
            picked = _match_scenario(user_message, options)
            if picked:
                session.practice_scenario = picked
            elif re.search(
                r"\b(let'?s (use|do)|i'?ll (use|take|do|go with)|how about|my (own )?scenario)\b",
                user_message,
                re.IGNORECASE,
            ):
                session.practice_scenario = user_message.strip()[:80]
            return

        stages = topic.get("practice_stages", [])
        if session.awaiting_answer and not IDK_PATTERN.search(user_message):
            session.practice_steps += 1
            if stages:
                session.practice_stage = min(session.practice_stage + 1, len(stages))
            session.awaiting_answer = False
        elif session.awaiting_answer and IDK_PATTERN.search(user_message):
            session.awaiting_answer = False
        stage_complete = bool(stages) and session.practice_stage >= len(stages)
        if WRAP_PATTERN.search(user_message) or stage_complete:
            session.phase = "complete"
            _unlock(session, "complete")
            session.complete_followups = 0
        return

    if session.phase == "complete":
        if WANT_EXAMPLE_PATTERN.search(user_message):
            session.shared_model_example = True
        if not FINISH_PATTERN.search(user_message):
            session.complete_followups += 1


def _idk_nudge(user_message: str, phase: str) -> str:
    if phase not in ("checking", "practice") or not IDK_PATTERN.search(user_message):
        return ""
    return (
        "\n\nStudent said they don't know. Respond with ONE everyday analogy or a simpler "
        "sub-question. Do NOT give the full answer or a complete worked example. "
        "End by asking them to try again in their own words."
    )


def _turn_extra(session: Session, prev_phase: str, user_message: str, from_nav: bool) -> str:
    topic = (session.topic_snapshot or get_topic(session.topic_id))
    options = practice_options_for(topic)
    options_list = "\n".join(f"{i}. {opt}" for i, opt in enumerate(options, start=1))

    if from_nav:
        if session.phase == "reading":
            return (
                "\n\nThe student jumped back to reading. Point them at the links again in one "
                "sentence. Remind them to return with one takeaway and one doubt. Do not quiz."
            )
        if session.phase == "checking":
            return (
                "\n\nThe student wants to talk something through again — it is still vague. "
                "Ask what part is fuzzy. One question. Do not restart a scripted quiz."
            )
        if session.phase == "practice":
            if not session.practice_scenario:
                return (
                    "\n\nThe student is in practice. They still need to choose a scenario. "
                    f"List these options and ask them to pick one:\n{options_list}"
                )
            stage, _ = _practice_stage_info(session)
            if stage:
                return (
                    f"\n\nBack in practice on '{session.practice_scenario}'. "
                    f"Continue at stage '{stage['label']}': {stage['focus']} One question."
                )
            return "\n\nPractice stages look finished. Ask if they want wrap-up or to keep tweaking."
        if session.phase == "complete":
            return (
                "\n\nWrap-up. Ask them to self-assess first (what they can do / what's still fuzzy). "
                "Do not paste the model answer unless they ask."
            )

    extra = ""
    if prev_phase == "reading" and session.phase == "checking":
        extra = (
            "\n\nThey came back from reading. If they gave a takeaway and a doubt, start from "
            "the TAKEAWAY they said they understood — that is the foundation. "
            "Treat the doubt as ahead of where they are; park it, do not teach it yet. "
            "Ask them to APPLY the takeaway (one everyday example or A vs B using only "
            "words they already used). Exactly ONE question. "
            "Do NOT ask about the doubted idea. Do NOT explain either idea. "
            "If they only said they are ready, ask for one understood thing and one unsure thing."
        )
    elif session.phase == "checking":
        extra = (
            "\n\nExactly ONE question. No stacked questions. No meta-questions "
            "(do not ask 'what question do you ask yourself'). "
            "If they restated a definition, they have not applied it — give a binary choice "
            "using only terms already in this chat, or ask them to name one situation and pick a label. "
            "Do NOT jump to a later distinction they said they were unsure about until they "
            "can apply the earlier idea they claimed to get."
        )
        if session.checking_turns >= 2:
            extra += (
                "\nThey have been on this Q&A for several turns. CHANGE TACTIC: either a "
                "binary choice, or park the sticky detail and invite practice on what they "
                "already understood. Do not give another paragraph of theory."
            )
    elif session.phase == "practice" and not session.practice_scenario:
        extra = (
            "\n\nTime for hands-on practice. Offer these scenario options and let them choose "
            f"(or invent a similar one). Do not start the build yet.\n{options_list}"
        )
    elif session.phase == "practice" and prev_phase == "checking":
        extra = (
            "\n\nThey moved to practice. If they have not chosen a scenario, list options. "
            "If they already chose, start stage 1 with one question."
        )
    elif session.phase == "practice":
        stage, _ = _practice_stage_info(session)
        picked_this_turn = prev_phase == "practice" and session.practice_steps == 0 and session.practice_stage == 0
        if picked_this_turn and stage and session.practice_scenario:
            extra = (
                f"\n\nThey chose this scenario: {session.practice_scenario}. "
                f"Start stage 1 — {stage['label']}: {stage['focus']} "
                "One question. Let the student lead."
            )
        elif stage:
            extra = (
                f"\n\nContinue practice ({session.practice_scenario}) at stage: {stage['label']}. "
                f"{stage['focus']} One question."
            )
        else:
            extra = (
                "\n\nPractice stages are complete. Invite wrap-up (self-assess) — "
                "or let them keep tweaking if they want."
            )
    elif session.phase == "complete" and prev_phase != "complete":
        extra = (
            "\n\nPractice finished. Congratulate briefly. Ask them to self-assess: "
            "what can they do now, and what is still fuzzy? "
            "Do NOT share the worked example unless they ask. "
            "Mention they can jump back if something is still vague, or say 'no doubts' to close."
        )
    elif session.phase == "complete":
        if session.shared_model_example and WANT_EXAMPLE_PATTERN.search(user_message):
            extra = (
                "\n\nThey asked for a model example. Share it concisely, then return the floor "
                "to them (still fuzzy? or no doubts?)."
            )
        else:
            extra = (
                "\n\nAnswer their self-assess or follow-up briefly. Do not restart the lesson. "
                "Still do not dump the model answer unless they asked. "
                f"Follow-ups remaining before auto-close: "
                f"{max(0, MAX_COMPLETE_FOLLOWUPS - session.complete_followups)}."
            )

    extra += _idk_nudge(user_message, session.phase)
    return extra


def _invoke_tutor(session: Session, extra: str) -> str:
    model = get_model(session.provider)
    system = _build_tutor_system(session)
    response = invoke_with_retry(
        model,
        [SystemMessage(content=system + extra)] + _history_for_llm(session.messages),
    )
    content = response.content if isinstance(response.content, str) else str(response.content)

    if session.phase in ("checking", "practice") and session.practice_scenario:
        session.awaiting_answer = True
    elif session.phase == "checking":
        session.awaiting_answer = True
    elif session.phase == "practice" and not session.practice_scenario:
        session.awaiting_answer = False

    session.messages.append({"role": "assistant", "content": content})
    return content


def tutor_reply(session: Session, user_message: str) -> str:
    """Process a student message and return the tutor's reply."""
    if session.ended:
        raise ValueError("Session has ended")

    session.messages.append({"role": "user", "content": user_message})

    prev_phase = session.phase
    _update_phase(session, user_message)

    if session.phase == "complete" and prev_phase == "complete" and FINISH_PATTERN.search(
        user_message
    ):
        content = _close_from_complete(session, reason="finished")
        session.messages.append({"role": "assistant", "content": content})
        return content

    extra = _turn_extra(session, prev_phase, user_message, from_nav=False)
    content = _invoke_tutor(session, extra)

    if session.phase == "complete" and session.complete_followups >= MAX_COMPLETE_FOLLOWUPS:
        close_note = _close_from_complete(session, reason="limit")
        session.messages.append({"role": "assistant", "content": close_note})

    return content


def navigate_session(session: Session, target: str) -> str:
    """Jump to an unlocked phase (or always-allowed reading)."""
    if session.ended:
        raise ValueError("Session has ended")
    if target not in PHASES:
        raise ValueError(f"Unknown phase: {target}")
    if target != "reading" and target not in session.unlocked_phases:
        raise ValueError("That part of the lesson is not unlocked yet")

    prev = session.phase
    session.phase = target
    session.awaiting_answer = False
    extra = _turn_extra(session, prev, "", from_nav=True)
    return _invoke_tutor(session, extra)


def set_practice_scenario(session: Session, scenario: str) -> str:
    if session.ended:
        raise ValueError("Session has ended")
    scenario = scenario.strip()
    if not scenario:
        raise ValueError("Scenario cannot be empty")
    session.phase = "practice"
    _unlock(session, "practice")
    session.practice_scenario = scenario
    session.awaiting_answer = False
    session.messages.append({"role": "user", "content": f"I'll use this scenario: {scenario}"})
    extra = _turn_extra(session, "practice", scenario, from_nav=False)
    return _invoke_tutor(session, extra)


def latest_tutor_message(session: Session) -> str | None:
    for msg in reversed(session.messages):
        if msg["role"] == "assistant":
            return msg["content"]
    return None


def end_session(session: Session) -> str:
    """Manually close a session from complete or active phase."""
    if session.ended:
        return session.messages[-1]["content"]

    if session.phase == "complete":
        content = _close_from_complete(session, reason="finished")
    else:
        session.ended = True
        session.phase = "ended"
        topic = (session.topic_snapshot or get_topic(session.topic_id))
        content = (
            f"Session closed early on **{topic['name']}**. "
            "You can download your transcript or reset to start a new topic."
        )

    session.messages.append({"role": "assistant", "content": content})
    return content


ADAPTIVE_ACTION_INSTRUCTIONS = {
    "ASSESS": "Ask the supplied assessment question directly. Do not explain the answer first.",
    "EXPLAIN": "Give a concise targeted explanation addressing the assessment gap, then ask the supplied assessment question again.",
    "HINT": "Give one limited hint without revealing the full answer, then ask the student to try the supplied question again.",
    "PRACTICE": "Give one small targeted practice step, then use the supplied assessment question to check the student's own work.",
    "REMEDIATE": "Correct the named misconception in plain language with one tiny example, then reassess with the supplied question.",
    "ADVANCE": "Acknowledge the demonstrated objective briefly and ask the supplied next assessment question.",
    "CHALLENGE": "Give a harder application framing while preserving the supplied assessment target.",
    "FOCUS_REQUIRED": "Be concise and focus only on the required objective or task; requirements and independent evidence still apply.",
}


def render_adaptive_action(
    session: Session,
    decision: dict,
    objective: dict,
    assessment_prompt: str,
    *,
    student_message: str = "",
    assessment_result: dict | None = None,
    rag_context: list[dict] | None = None,
) -> str:
    """Render an application-selected action without changing adaptive state."""
    if student_message:
        session.messages.append({"role": "user", "content": student_message})
    action = decision["action"]
    instruction = ADAPTIVE_ACTION_INSTRUCTIONS[action]
    misconception = ""
    if assessment_result and assessment_result.get("misconception_detail"):
        misconception = f"Observed misconception: {assessment_result['misconception_detail']}"
    sources = "\n\n".join(
        f"SOURCE: {item['title']}\n{item['text']}" for item in (rag_context or [])
    ) or "No course excerpt was retrieved. Do not invent course-specific claims."
    system = f"""{TEACHER_CORE}

You are rendering an action selected by the application. You may not change the action,
objective, mastery state, required-task state, or progression.

Selected action: {action}
Reason codes: {', '.join(decision.get('reason_codes', []))}
Current objective: {objective['id']} — {objective['description']}
Rendering instruction: {instruction}
{misconception}

Approved course context:
{sources}

Keep the response concise. Do not mention internal policy, evidence labels, or mastery machinery.
The assessment/check to present at the end is:
{assessment_prompt}
"""
    model = get_model(session.provider)
    response = invoke_with_retry(
        model,
        [SystemMessage(content=system)] + _history_for_llm(session.messages),
    )
    content = response.content if isinstance(response.content, str) else str(response.content)
    session.messages.append({"role": "assistant", "content": content})
    return content
