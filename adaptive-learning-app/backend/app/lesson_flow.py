"""A persistent, topic-independent lesson conversation.

The configured key controls MCQ scoring. Student text only supplies evidence,
confidence, and preferences; it never changes a question or its answer key.
"""
from __future__ import annotations

import copy
import re

from .openai_client import assess_configured_response, explain_configured

WELCOME_QUESTION = "What feels most unfamiliar about this topic, or are you completely new to it?"
STUDY_INSTRUCTION = "Explore these resources at your own pace. You can ask me for explanations or examples while studying. When you’re ready for a short understanding check, reply ‘I am done.’"
QUIZ_INSTRUCTION = "I’ll ask five questions, one at a time. Choose an answer and give your confidence: low, medium, or high. For questions 4 and 5, also explain your choice in one sentence. You can say ‘I don’t know’ or ask for a hint."
REFLECTION_QUESTION = "What can you explain or do now that you couldn’t before?"
CHOICE_QUESTION = "Would you like another example, a harder challenge, a recap, or to pause here?"
CHOICES = ["A simpler explanation", "A worked example", "Another practice question", "An application challenge", "A recap"]
CHOICE_DESCRIPTIONS = {
    "A simpler explanation": "Break down the idea, then answer a guided question in your own words.",
    "A worked example": "Study a explained example, then reason through a different case.",
    "Another practice question": "Try a fresh question; get feedback and a deeper follow-up.",
    "An application challenge": "Apply the idea to a harder case and justify your decision.",
    "A recap": "Review the key idea, then explain it and apply it to a fresh case.",
}


def normalize(text: str) -> str:
    return re.sub(r"\s+", " ", text.lower().replace("’", "'")).strip()


def ready(text: str) -> bool:
    text = normalize(text)
    if re.search(r"\b(not|haven't|didn't|unfinished|still)\b", text):
        return False
    return bool(re.search(r"\b(done|ready|finished|completed)\b", text)) or text in {"let's continue", "continue to the quiz"}


def unknown(text: str) -> bool:
    return normalize(text).rstrip(".!?") in {"i don't know", "i do not know", "don't know", "unsure", "not sure", "idk", "skip"}


def welcome(plan: dict, name: str) -> str:
    objectives = "\n".join(f"• {o['title']}: {o['description']}" for o in plan["objectives"])
    return (f"Hi {name.split()[0]}, today we are going to discuss {plan['topic']}.\n\n"
            f"{plan['topic_introduction']}\n\nExample: {plan['introductory_example']}\n\n"
            f"Our learning objectives:\n{objectives}\n\n{WELCOME_QUESTION}")


def initial_state(plan: dict) -> dict:
    return {"version": 2, "lesson_snapshot": copy.deepcopy(plan), "stage": "welcome",
            "quiz_index": 0, "diagnostic": [], "pending_answer": None, "assistance": {},
            "demonstrated": [], "practice_history": [], "used_activities": [], "reflections": [],
            "self_report": None, "diagnostic_paths": {}, "current_paths": {}, "choices": [],
            "participation": {"responses": 0, "unknown_responses": 0, "help_requests": 0}}


def asset_for(plan, objective_id):
    return next(a for a in plan["learning_assets"] if a["objective_id"] == objective_id)


def objective_for(plan, objective_id):
    return next(o for o in plan["objectives"] if o["id"] == objective_id)


def study_message(plan):
    readings = "\n\n".join(f"{r['title']} ({r['provider']})\n{r['description']}\nFocus: {r['focus']}" for r in plan["study_resources"])
    return f"{STUDY_INSTRUCTION}\n\n{readings}"


def question_message(plan, index):
    question = plan["diagnostic_quiz"][index]
    options = "\n".join(f"{chr(65 + i)}. {option}" for i, option in enumerate(question["options"]))
    extra = " Include a one-sentence explanation of your choice." if index >= 3 else ""
    return f"Question {index + 1} of 5\n{question['question']}\n\n{options}\n\nChoose an answer and tell me your confidence: low, medium, or high.{extra}"


def parse_option(content, question):
    text = normalize(content)
    if unknown(text):
        return None
    letters = re.findall(r"(?:^|\boption\s+|\banswer\s+(?:is\s+)?|\bchoose\s+(?:option\s+)?|\bselect\s+(?:option\s+)?|\b(?:think|pick|go with|it is|it's)\s+)([a-d])\b", text)
    # Reject alternatives such as 'A or B' rather than guessing.
    if re.search(r"\b[a-d]\s*(?:or|and|/)\s*[a-d]\b", text):
        raise ValueError("Please choose one option (A, B, C, or D), or say ‘I don't know.’")
    option_matches = [i for i, option in enumerate(question["options"]) if normalize(option).rstrip(".") == text.rstrip(".") or normalize(option) in text]
    choices = {ord(letter) - 97 for letter in letters} | set(option_matches)
    if len(choices) == 1:
        return choices.pop()
    raise ValueError("Please choose one option (A, B, C, or D), repeat its text, or say ‘I don't know.’")


def parse_confidence(content):
    matches = set(re.findall(r"\b(low|medium|high)\b", normalize(content)))
    return next(iter(matches)) if len(matches) == 1 else None


def parse_explanation(content):
    match = re.search(r"\b(because|since|my reasoning is)\b(.+)", content, re.I)
    return match.group(0).strip() if match else None


def support_message(plan, state, content):
    """Use approved snippets, not topic branches or invented teaching content."""
    objective_id = state.get("target_objective") or plan["objectives"][0]["id"]
    for objective in plan["objectives"]:
        if normalize(objective["title"]) in normalize(content) or objective["id"].lower() in normalize(content):
            objective_id = objective["id"]
            break
    asset = asset_for(plan, objective_id)
    excerpts = state.get("study_context", [])
    clarification = explain_configured(content, plan["approved_material"], {key: asset.get(key) for key in ("explanation", "worked_example", "analogy")}, excerpts)
    if clarification:
        return clarification
    if any(word in normalize(content) for word in ("overwhelm", "too much", "confused", "smaller", "lost")):
        return f"Let's make this smaller.\n\n{asset['explanation']}\n\nFocus on {objective_for(plan, objective_id)['title'].lower()} in the first resource; you can pause whenever you need."
    source = f"Course note ({excerpts[0]['filename']}): {' '.join(excerpts[0]['content'].split())[:500]}\n\n" if excerpts else ""
    return (source + f"{asset['explanation']}\n\nWorked example: {asset['worked_example']}"
            + (f"\n\nAnalogy (a simplified comparison): {asset['analogy']}" if asset.get("analogy") else ""))


def next_activity(plan, state, objective_id, level, *, supported=False):
    asset = asset_for(plan, objective_id)
    used = set(state["used_activities"])
    activities = list(enumerate(asset[level]))
    concept = state.get("target_concept")
    if concept:
        activities = [pair for pair in activities if pair[1].get("concept") == concept]
    activities.sort(key=lambda pair: pair[1].get("concept") != concept)
    for index, item in activities:
        activity_id = f"{objective_id}:{level}:{index}"
        if activity_id not in used:
            state["activity"] = {**item, "id": activity_id, "objective_id": objective_id,
                                 "level": level, "assisted": supported, "revisions": 0}
            state["target_objective"] = objective_id
            state["stage"] = "adaptive_learning"
            state["choices"] = []
            return item["prompt"]
    state["stage"] = "learning_choice"
    state["activity"] = None
    state["choices"] = CHOICES
    return "You have tried the available activities at this level. You can choose a different format or pause here."


def deeper_probe(plan, state, objective_id):
    """Stay on the selected concept, using a different authored case without hints."""
    asset = asset_for(plan, objective_id)
    for level in ("accelerated", "standard", "foundational"):
        if any(item.get("concept") == state.get("target_concept") and f"{objective_id}:{level}:{i}" not in state["used_activities"] for i, item in enumerate(asset[level])):
            return next_activity(plan, state, objective_id, level)
    state.update(stage="learning_choice", choices=list(CHOICES), activity=None)
    return "You've used the available cases for this concept. We can review it, choose another approach, or pause here."


def evaluate_diagnostic(plan, state):
    score = 0
    diagnosis = []
    for index, entry in enumerate(state["diagnostic"]):
        question = plan["diagnostic_quiz"][index]
        correct = entry["option_index"] == question["correct_index"]
        score += int(correct)
        reasoning = assess_configured_response(
            entry.get("explanation") or "", question.get("reasoning_rubric") or [],
            objective_for(plan, question["objective_id"]), plan["approved_material"], question["question"],
        ) if entry.get("explanation") else {"category": "insufficient_evidence", "score": 0, "feedback": "No explanation was recorded."}
        if entry["option_index"] is None:
            need = "clarification_choice"
        elif not correct and entry.get("confidence") == "high":
            need = "counterexample_revision"
        elif not correct and index < 2:
            need = "simpler_support"
        elif not correct:
            need = "targeted_practice"
        elif index >= 3 and reasoning["category"] != "sound_reasoning":
            need = "reasoning_probe"
        elif entry.get("assistance_used"):
            need = "independent_check"
        elif entry.get("confidence") == "low":
            need = "confidence_building"
        else:
            need = "application_challenge"
        misconception = question["distractor_misconceptions"][entry["option_index"]] if not correct and entry["option_index"] is not None else None
        diagnosis.append({**entry, "correct": correct, "question": question["question"], "misconception": misconception,
                          "objective_id": question["objective_id"], "concept": question["concept"],
                          "reasoning": reasoning, "need": need,
                          "explanation_of_answer": question["explanation"],
                          "correct_index": question["correct_index"]})
    state["diagnostic"] = diagnosis
    state["quiz_score"] = score
    state["diagnostic_complete"] = True
    priority = {"counterexample_revision": 0, "simpler_support": 1, "targeted_practice": 2,
                "reasoning_probe": 3, "clarification_choice": 4, "independent_check": 5,
                "confidence_building": 6, "application_challenge": 7}
    for objective in plan["objectives"]:
        results = [d for d in diagnosis if d["objective_id"] == objective["id"]]
        needs = {d["need"] for d in results}
        path = "foundational" if needs & {"simpler_support", "counterexample_revision", "clarification_choice"} else "standard" if needs - {"application_challenge"} else "accelerated"
        state["diagnostic_paths"][objective["id"]] = path
    state["current_paths"] = dict(state["diagnostic_paths"])
    chosen = min(diagnosis, key=lambda d: priority[d["need"]])
    state["selected_followup"] = chosen["need"]
    state["concept_gaps"] = [{"concept": item["concept"], "objective_id": item["objective_id"], "need": item["need"]} for item in diagnosis if not item["correct"] or item["need"] in {"reasoning_probe", "independent_check"}]
    state["target_objective"] = chosen["objective_id"]
    state["target_concept"] = chosen["concept"]
    strengths = list(dict.fromkeys(d["concept"] for d in diagnosis if d["correct"]))
    feedback = f"Quiz score: {score}/5.\n\n"
    feedback += "Your selections showed understanding of: " + ", ".join(strengths) + ".\n\n" if strengths else "The quiz does not yet give clear evidence of the concepts you understand.\n\n"
    if not chosen["correct"]:
        feedback += f"Your answers suggest we should spend more time on {chosen['concept']}. Let's work through it together.\n\n"
    elif chosen["need"] == "reasoning_probe":
        feedback += f"You selected the right answer for {chosen['concept']}; let's explore the reasoning behind it.\n\n"
    elif chosen["need"] in {"confidence_building", "independent_check"}:
        feedback += f"Let's strengthen your independent understanding of {chosen['concept']}.\n\n"
    else:
        feedback += f"Your quiz answers look strong. Let's explore {chosen['concept']} more deeply.\n\n"
    state.update(stage="learning_choice", choices=list(CHOICES), activity=None, depth_checks=0, choice_flow_version=1)
    return feedback + "How would you like to work on this concept? Choose one approach below, and then we'll go through it one question at a time."


def handle_quiz(plan, state, turn):
    index = state["quiz_index"]
    question = plan["diagnostic_quiz"][index]
    if turn.question_id and turn.question_id != question["id"]:
        raise ValueError("That answer belongs to a previous question. Please answer the current question.")
    if turn.action == "hint" or "hint" in normalize(turn.content) or is_help(turn.content):
        state["assistance"].setdefault(question["id"], []).append("conceptual_hint")
        return f"Hint: {question['hint']}\n\nTake your time and choose an answer when you are ready."
    pending = state.get("pending_answer")
    if pending and turn.action in {"continue", "message", "answer"}:
        # The original selection remains fixed while metadata is collected.
        pending["confidence"] = turn.confidence or parse_confidence(turn.content) or pending["confidence"]
        pending["explanation"] = (turn.explanation or parse_explanation(turn.content) or (turn.content.strip() if index >= 3 and turn.content.strip() and not parse_confidence(turn.content) else None) or pending["explanation"])
        entry = pending
    else:
        try:
            option = turn.option_index if turn.option_index is not None else parse_option(turn.content, question)
        except ValueError as exc:
            return str(exc)
        entry = {"question_id": question["id"], "original_answer": turn.content or chr(65 + option) if option is not None else turn.content or "I don't know",
                 "option_index": option, "confidence": turn.confidence or parse_confidence(turn.content),
                 "explanation": (turn.explanation or parse_explanation(turn.content) or "").strip() or None,
                 "assistance_used": bool(state["assistance"].get(question["id"])),
                 "assistance": list(state["assistance"].get(question["id"], []))}
        missing = []
        if not entry["confidence"]:
            missing.append("your confidence (low, medium, or high)")
        if index >= 3 and not entry["explanation"]:
            missing.append("a one-sentence explanation")
        if missing:
            state["pending_answer"] = entry
            return "Thanks—your choice is recorded. Please add " + " and ".join(missing) + ", or continue without it."
    entry["missing_confidence"] = entry["confidence"] is None
    entry["missing_explanation"] = index >= 3 and not entry["explanation"]
    entry["assistance"] = list(state["assistance"].get(question["id"], []))
    entry["assistance_used"] = bool(entry["assistance"])
    state["diagnostic"].append(entry)
    state["pending_answer"] = None
    state["quiz_index"] += 1
    if state["quiz_index"] < 5:
        return "Thanks—answer recorded. Here's the next question.\n\n" + question_message(plan, state["quiz_index"])
    return evaluate_diagnostic(plan, state)


def is_help(content):
    text = normalize(content)
    return ("?" in text and not any(word in text for word in ("because", "therefore", "since"))) or any(phrase in text for phrase in ("explain", "help me", "hint", "another example", "analogy", "overwhelmed")) and not any(phrase in text for phrase in ("because", "therefore", "since"))


def handle_practice(plan, state, turn):
    state["choices"] = []
    activity = state.get("activity")
    if not activity:
        state["stage"] = "learning_choice"
        return CHOICE_QUESTION, None
    if turn.action == "hint" or "hint" in normalize(turn.content):
        activity["assisted"] = True
        return f"Hint: {activity['hint']}\n\nTry the example in your own words.", None
    if unknown(turn.content):
        activity["assisted"] = True
        return f"Let's take one smaller step. {activity['hint']}\n\nWhat does that suggest for this case? Explain the first part you can reason through.", None
    if is_help(turn.content):
        activity["assisted"] = True
        return support_message(plan, state, turn.content) + "\n\n" + activity["prompt"], None
    objective = objective_for(plan, activity["objective_id"])
    assessment = assess_configured_response(turn.content, activity.get("rubric") or objective["rubric"], objective, plan["approved_material"], activity["prompt"])
    # Repeating revealed quiz text or a previous successful answer is not fresh evidence.
    response = normalize(turn.content)
    copied = any(response == normalize(q["explanation"]) or response == normalize(q["options"][q["correct_index"]]) for q in plan["diagnostic_quiz"])
    copied = copied or any(response == normalize(h["response"]) and h["demonstrated"] for h in state["practice_history"])
    independent = assessment["category"] == "sound_reasoning" and not activity["assisted"] and not copied
    record = {"objective_id": objective["id"], "activity_id": activity["id"], "response": turn.content,
              "assisted": activity["assisted"], "demonstrated": independent, "score": assessment["score"],
              "category": assessment["category"], "rationale": assessment["feedback"], "revision": activity["revisions"]}
    state["practice_history"].append(record)
    state["used_activities"] = list(dict.fromkeys([*state["used_activities"], activity["id"]]))
    if independent:
        state["depth_checks"] = state.get("depth_checks", 0) + 1
        if state["depth_checks"] < 2:
            return assessment["feedback"] + "\n\nLet's go one step deeper with a different case. Explain why your answer fits, using the details of the example.\n\n" + deeper_probe(plan, state, objective["id"]), record
        state["demonstrated"] = list(dict.fromkeys([*state["demonstrated"], objective["id"]]))
        state["demonstrated_concepts"] = list(dict.fromkeys([*state.get("demonstrated_concepts", []), activity.get("concept")]))
        state["current_paths"][objective["id"]] = "accelerated"
        state.update(stage="reflection", choices=[], activity=None)
        return assessment["feedback"] + "\n\n" + REFLECTION_QUESTION, record
    if assessment["category"] == "sound_reasoning":
        state["current_paths"][objective["id"]] = "standard"
        return "That response addresses the rubric with support. Let's check it using a fresh independent example. Explain both your answer and why it fits this case.\n\n" + deeper_probe(plan, state, objective["id"]), record
    activity["revisions"] += 1
    state["current_paths"][objective["id"]] = "foundational" if assessment["category"] == "identifiable_misconception" else "standard"
    if copied:
        return "Try applying the idea to this new case rather than repeating a revealed quiz answer.\n\n" + activity["prompt"], record
    counterexample = asset_for(plan, objective["id"])["counterexample"] if assessment["category"] == "identifiable_misconception" else ""
    return (assessment["feedback"] + (f"\n\nConsider this counterexample: {counterexample}" if counterexample else "") + "\n\nRevise your explanation for this example: " + activity["prompt"]), record


def handle_choice(plan, state, content):
    choice = normalize(content)
    if not any(word in choice for word in ("recap", "challenge", "harder", "example", "simpler", "clarification", "smaller", "practice", "continue", "next")):
        return "Choose a simpler explanation, a worked example, another practice question, an application challenge, or a recap."
    state.update(selected_format=content, choices=[], depth_checks=0)
    state["activity"] = None
    current = state.get("target_objective")
    next_gap = next((gap for gap in state.get("concept_gaps", []) if gap["concept"] not in state.get("demonstrated_concepts", [])), None)
    if not next_gap:
        next_gap = next((q for q in plan["diagnostic_quiz"] if q["concept"] not in state.get("demonstrated_concepts", [])), None)
    if state.get("target_concept") in state.get("demonstrated_concepts", []) and next_gap:
        state.update(target_objective=next_gap["objective_id"], target_concept=next_gap["concept"])
        current = next_gap["objective_id"]
    objective_id = current if current and current not in state["demonstrated"] else next((o["id"] for o in plan["objectives"] if o["id"] not in state["demonstrated"]), current or plan["objectives"][0]["id"])
    focus = next((q for q in plan["diagnostic_quiz"] if q["objective_id"] == objective_id and q["concept"] == state.get("target_concept")), None)
    if not focus:
        focus = next(q for q in plan["diagnostic_quiz"] if q["objective_id"] == objective_id)
        state["target_concept"] = focus["concept"]
    concept = focus["concept"]
    explanation = focus["explanation"]
    earlier = next((d for d in state.get("diagnostic", []) if d["question_id"] == focus["id"]), {})
    contrast = f"Your earlier choice suggested: {earlier['misconception']}. Compare that with the idea below.\n\n" if earlier.get("need") == "counterexample_revision" and earlier.get("misconception") else ""
    if "recap" in choice:
        return f"Recap — {concept}\n{explanation}\nRemember: {focus['hint']}\n\nNow put the idea into your own words while answering this case.\n\n" + next_activity(plan, state, objective_id, "standard", supported=True)
    if "challenge" in choice or "harder" in choice:
        return f"Application challenge — {concept}\nApply the idea to this case. Make a decision and justify it with specific details.\n\n" + next_activity(plan, state, objective_id, "accelerated")
    if "example" in choice:
        return (contrast + f"Worked example — {concept}\nConsider the example from your quiz: {focus['question']}\nThe answer is: {focus['options'][focus['correct_index']]}.\nWhy: {explanation}\n\nNow reason through a different case. Explain how the same idea applies.\n\n" + next_activity(plan, state, objective_id, "foundational", supported=True))
    if "simpler" in choice or "clarification" in choice or "smaller" in choice:
        return contrast + f"Let's break down {concept}.\n{explanation}\n{focus['hint']}\n\nTake this case one step at a time. What is your answer, and why?\n\n" + next_activity(plan, state, objective_id, "foundational", supported=True)
    if "practice" in choice or "continue" in choice or "next" in choice:
        return f"Fresh practice — {concept}\nTry this in your own words. I will use your reasoning to decide what to probe next.\n\n" + next_activity(plan, state, objective_id, "standard")
    return CHOICE_QUESTION


def transition(state: dict, turn) -> tuple[dict, str, dict | None]:
    state = copy.deepcopy(state)
    plan = state["lesson_snapshot"]
    state["participation"]["responses"] += 1
    state["participation"]["unknown_responses"] += int(unknown(turn.content))
    state["participation"]["help_requests"] += int(turn.action == "hint" or is_help(turn.content))
    text = normalize(turn.content).rstrip(".!?")
    if turn.action == "pause" or text in {"pause", "pause here", "stop", "take a break"}:
        if state["stage"] != "paused":
            state["resume_stage"] = state["stage"]
        state.update(stage="paused", choices=["Resume"])
        return state, "Paused here. Your progress is saved; resume whenever you are ready.", None
    if state["stage"] == "paused":
        if turn.action == "resume" or text in {"resume", "continue", "ready"}:
            state["stage"] = state.pop("resume_stage", "study_resources")
            state["choices"] = list(CHOICES) if state["stage"] == "learning_choice" else []
            reply = question_message(plan, state["quiz_index"]) if state["stage"] == "diagnostic_quiz" else state.get("activity", {}).get("prompt") if state.get("activity") else WELCOME_QUESTION if state["stage"] == "welcome" else REFLECTION_QUESTION if state["stage"] == "reflection" else CHOICE_QUESTION if state["stage"] == "learning_choice" else study_message(plan)
            return state, "Welcome back.\n\n" + reply, None
        return state, "Your session is paused. Choose Resume when you want to continue.", None
    if turn.action == "choice" and state["stage"] in {"adaptive_learning", "learning_choice"}:
        return state, handle_choice(plan, state, turn.content), None
    if state["stage"] == "welcome":
        state["self_report"] = turn.content.strip() or None
        # Self-report adjusts emphasis, never ability or placement.
        emphasis = support_message(plan, state, turn.content) if is_help(turn.content) or any(word in text for word in ("new", "unfamiliar", "overwhelm")) else "We can focus on any part that feels unfamiliar as you study."
        state["stage"] = "study_resources"
        return state, emphasis + "\n\n" + study_message(plan), None
    if state["stage"] == "study_resources":
        if ready(turn.content):
            state["stage"] = "diagnostic_quiz"
            state["readiness_statement"] = turn.content
            return state, QUIZ_INSTRUCTION + "\n\n" + question_message(plan, 0), None
        return state, support_message(plan, state, turn.content) + "\n\nReturn to the resources at your own pace. Reply ‘I am done’ when you want to try the quiz.", None
    if state["stage"] == "diagnostic_quiz":
        return state, handle_quiz(plan, state, turn), None
    if state["stage"] == "adaptive_learning":
        if normalize(turn.content).rstrip(".!?") in {normalize(c) for c in CHOICES}:
            return state, handle_choice(plan, state, turn.content), None
        reply, evidence = handle_practice(plan, state, turn)
        return state, reply, evidence
    if state["stage"] == "reflection":
        if is_help(turn.content) or unknown(turn.content):
            return state, "You can describe one idea or task that feels clearer now, or pause and return later.\n\n" + REFLECTION_QUESTION, None
        state["reflections"].append({"objective_id": state.get("target_objective"), "content": turn.content})
        state.update(stage="learning_choice", choices=CHOICES)
        return state, "Thanks for reflecting on your progress.\n\n" + CHOICE_QUESTION, None
    if state["stage"] == "learning_choice":
        return state, handle_choice(plan, state, turn.content), None
    raise ValueError("This learning stage is not available.")


def public_state(state: dict) -> dict:
    """Never expose the snapshot, future questions, keys, hints, or practice rubrics."""
    plan = state["lesson_snapshot"]
    result = {key: copy.deepcopy(state.get(key)) for key in (
        "version", "stage", "quiz_index", "quiz_score", "diagnostic_complete", "self_report",
        "demonstrated", "practice_history", "reflections", "choices", "selected_followup",
        "diagnostic_paths", "current_paths", "selected_format", "target_objective", "concept_gaps", "participation")}
    result["choices"] = list(CHOICES) if state["stage"] == "learning_choice" else []
    result["choice_descriptions"] = CHOICE_DESCRIPTIONS if result["choices"] else {}
    result["depth_checks"] = state.get("depth_checks", 0)
    if state["stage"] == "diagnostic_quiz" or state.get("resume_stage") == "diagnostic_quiz":
        question = plan["diagnostic_quiz"][state["quiz_index"]]
        result["current_question"] = {key: question[key] for key in ("id", "question", "options", "difficulty", "concept")}
        pending = state.get("pending_answer")
        result["metadata_requested"] = bool(pending)
        result["recorded_option"] = pending["option_index"] if pending else None
    if state.get("diagnostic_complete"):
        result["diagnostic"] = copy.deepcopy(state["diagnostic"])
    else:
        result["diagnostic"] = [{key: item.get(key) for key in ("question_id", "original_answer", "option_index", "confidence", "explanation", "assistance_used", "missing_confidence", "missing_explanation")} for item in state["diagnostic"]]
    if state.get("activity"):
        result["current_activity"] = {key: state["activity"][key] for key in ("id", "prompt", "objective_id", "concept", "level", "assisted", "revisions")}
    return result
