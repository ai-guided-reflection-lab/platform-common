"""Compatibility entry points; lesson content must be explicitly configured."""


def ensure_learning_content(plan: dict, topic: str) -> dict:
    if len(plan.get("diagnostic_quiz", [])) != 5 or not plan.get("learning_assets"):
        raise ValueError("Prepare a five-question quiz and objective-aligned practice activities in the instructor studio.")
    return {**plan, "topic": topic}


def prepare_student_content(plan: dict) -> dict:
    return dict(plan)
