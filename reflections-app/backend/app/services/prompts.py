"""Prompt templates — professor-config-aware prompts for reflection and evaluation."""


def build_reflection_prompt(config: dict, questions: list[str], past_weak_areas: list[str] | None = None) -> str:
    """Build the chatbot system prompt from a ModuleConfig dict.

    Accepts pre-generated questions and optional cross-session weak areas.
    Instructs the LLM to respond in strict JSON format per message.
    """
    depth = config.get("expected_depth", "surface")
    style = config.get("probing_style", "supportive")
    require_app = config.get("must_include_application", False)
    custom_notes = config.get("custom_notes", "").strip()

    style_instruction = {
        "supportive": "Be warm, encouraging, and patient. Gently guide the student.",
        "socratic": "Use the Socratic method — ask probing counter-questions to deepen thinking.",
    }.get(style, "Be warm and encouraging.")

    depth_instruction = {
        "surface": "Accept brief summaries but encourage a bit more detail.",
        "applied": "Push the student to connect concepts to real-world applications.",
        "analytical": "Expect the student to compare, contrast, and critically evaluate ideas.",
    }.get(depth, "Accept brief summaries.")

    app_instruction = (
        "You MUST ask at least one question requiring the student to apply a concept to a real scenario."
        if require_app
        else ""
    )

    custom_notes_block = (
        f"\nPROFESSOR NOTES (highest priority — address these first):\n{custom_notes}\n"
        if custom_notes
        else ""
    )

    if questions:
        numbered = "\n".join(f"{i+1}. {q}" for i, q in enumerate(questions))
        questions_block = f"\nPRE-GENERATED QUESTIONS (ask these in order):\n{numbered}\n"
    else:
        questions_block = ""

    history_block = ""
    if past_weak_areas:
        areas = ", ".join(past_weak_areas)
        history_block = f"\nSTUDENT HISTORY: This student previously struggled with: {areas}. In bonus phase, revisit these areas.\n"

    return f"""You are a reflective learning assistant for a university course.
{custom_notes_block}{questions_block}{history_block}
SESSION RULES — follow these exactly:
1. Each student message includes a context tag [Q N/M: question text] telling you exactly which question is being evaluated. Evaluate ONLY that question.
2. NEVER skip questions, declare the session complete, or wrap up on your own — the system controls progress. Your only job is to evaluate the current answer and respond.
3. After each student reply, judge their answer:
   - Correct or adequate: set adequate=true. One brief acknowledgment, then ask the NEXT question from the list (if any remain).
   - Wrong or misconception: set adequate=false. Correct in 2-3 plain sentences, then re-ask the SAME question.
4. {depth_instruction}
5. {style_instruction}
6. {app_instruction}
7. BONUS PHASE: The context tag will say [BONUS PHASE]. Ask deeper exploratory questions. Always set adequate=true in bonus phase.

RESPONSE FORMAT — every reply must be valid JSON, nothing else:
{{"adequate": true/false, "reply": "plain text message to student"}}

adequate = true if the student answered the current question correctly or adequately.
adequate = false if the answer was wrong or incomplete.
reply = your message to the student. Plain text only, no markdown.
Do NOT output anything outside of this JSON object."""


def build_question_generation_prompt(sub_topics: list[str], config: dict) -> str:
    """Build a prompt to pre-generate one question per sub-topic."""
    depth = config.get("expected_depth", "surface")
    style = config.get("probing_style", "supportive")
    topics_list = "\n".join(f"- {t}" for t in sub_topics)

    depth_note = {
        "surface": "Keep questions straightforward — test basic recall and understanding.",
        "applied": "Frame questions around real-world application of concepts.",
        "analytical": "Frame questions that require comparing, contrasting, or critically evaluating.",
    }.get(depth, "Keep questions straightforward.")

    style_note = {
        "supportive": "Use warm, accessible phrasing.",
        "socratic": "Use open-ended phrasing that provokes deeper thinking.",
    }.get(style, "Use clear phrasing.")

    return f"""Generate exactly {len(sub_topics)} reflection questions, one per sub-topic listed below.

SUB-TOPICS:
{topics_list}

GUIDELINES:
- {depth_note}
- {style_note}
- One question per sub-topic, in the same order as the list above.
- Each question should be concise (one sentence).

Return ONLY a JSON array of {len(sub_topics)} question strings. No explanation, no markdown, no extra text.
Example format: ["Question about topic 1?", "Question about topic 2?"]"""


def build_subtopic_generation_prompt(main_topics: list[str]) -> str:
    """Build a prompt to auto-generate sub-topics from main topics."""
    topics_list = ", ".join(main_topics)
    return f"""Given these main course topics: {topics_list}

Generate a list of specific sub-topics that a student should be able to discuss after studying these topics.
Each sub-topic should be a concrete, testable concept (not a broad category).
Aim for 2-4 sub-topics per main topic.

Return ONLY a JSON array of sub-topic strings. No explanation, no markdown, no extra text.
Example: ["Array indexing", "Dynamic resizing", "Time complexity of operations"]"""


def build_evaluation_prompt(transcript: str, config: dict) -> str:
    """Build the evaluation prompt sent after a session ends."""
    topics = ", ".join(config.get("sub_topics", []) or config.get("required_topics", []))
    depth = config.get("expected_depth", "surface")

    return f"""You are an educational evaluation engine.

Below is a transcript of a student reflection session and the professor's expectations.

PROFESSOR EXPECTATIONS:
- Required topics: {topics or "none specified"}
- Expected depth: {depth}

TRANSCRIPT:
{transcript}

Evaluate this transcript and return ONLY a JSON object (no explanation, no markdown):

{{
  "topics_covered": ["list of topics the student discussed"],
  "missing_topics": ["required topics NOT discussed"],
  "misconceptions": ["any factual errors or misunderstandings detected"],
  "reflection_depth_score": <float 0-1, where 1 = fully meets {depth} depth>,
  "confidence_level": <int 1-5, from student self-report or inferred>,
  "engagement_score": <float 0-1, based on detail and effort shown>
}}

Return ONLY valid JSON. No extra text.
"""
