"""Simulated student — only used when the user clicks the button."""

from langchain_core.messages import SystemMessage

from models import get_model, invoke_with_retry
from personalities import get_personality_prompt
from topics import get_topic
from tutor import Session, _practice_stage_info, latest_tutor_message, practice_options_for


def simulate_student_reply(session: Session) -> str:
    tutor_msg = latest_tutor_message(session)
    if not tutor_msg:
        return (
            "I read the first link. I think I get the main idea, but I'm still unsure "
            "how the pieces actually fit together."
        )
    if len(tutor_msg) > 1600:
        tutor_msg = tutor_msg[:1600] + "…"

    personality_prompt = get_personality_prompt(session.personality)
    model = get_model(session.provider)
    topic = get_topic(session.topic_id)
    options = practice_options_for(topic)

    stage_hint = ""
    if session.phase == "reading":
        stage_hint = (
            "\nYou just finished (or should finish) the reading. Reply with ONE thing you "
            "understood and ONE thing you are still unsure about — not only 'ready'."
        )
    elif session.phase == "checking":
        stage_hint = (
            "\nAnswer with a concrete guess: pick A or B, or name one everyday situation "
            "using only words the tutor already used. You may get it backwards. "
            "Do NOT define both terms. Do NOT recap the tutor. "
            "Do NOT write 'I understood X. I'm still unsure about Y'."
        )
    elif session.phase == "practice":
        if not session.practice_scenario:
            listed = ", ".join(options)
            stage_hint = (
                f"\nPick ONE practice scenario by name from: {listed}. "
                "Do not start the full build yet."
            )
        else:
            stage, stages = _practice_stage_info(session)
            if stage:
                order = " → ".join(s["label"] for s in stages)
                stage_hint = (
                    f"\nChosen scenario: {session.practice_scenario}. "
                    f"Practice stage now: {stage['label']}. Build order: {order}. "
                    "If overconfident, you might jump ahead — otherwise stay on the current step. "
                    "If an earlier idea is still vague, say you want to talk it through again."
                )
    elif session.phase == "complete":
        stage_hint = (
            "\nWrap-up: first say what you can do now and what is still fuzzy. "
            "You may ask to see a model example, go back, or say no doubts."
        )

    topic_name = topic["name"]

    system = f"""You are simulating an undergrad student in a self-directed tutoring chat.

## Personality
{personality_prompt}

## Topic
{topic_name}

## Tutor just said
\"\"\"
{tutor_msg}
\"\"\"

## Rules
- Reply in first person as the student ONLY (1–3 short sentences).
- Stay inside the current topic the tutor is teaching — do not invent another subject.
- If the tutor asks an eliciting question, attempt YOUR answer first — don't ask the tutor to explain.
- If confused / missing context: partial or wrong answers are OK, then a check-in.
- If overconfident: answer quickly, maybe skip a step or use a buzzword incorrectly.
- NEVER copy the tutor's message. NEVER teach or explain like a tutor.
- NEVER write a complete deliverable, full diagram, or long list.

## Session phase: {session.phase}{stage_hint}
"""

    response = invoke_with_retry(model, [SystemMessage(content=system)])
    content = response.content if isinstance(response.content, str) else str(response.content)
    return content.strip()
