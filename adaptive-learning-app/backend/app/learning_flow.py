"""Deterministic placement rules for the self-directed learning flow."""

from __future__ import annotations

from dataclasses import dataclass


DIAGNOSTIC_SIZE = 5
DIFFICULTY_TARGETS = {
    "foundational": 2,
    "application": 2,
    "challenge": 1,
}
DIFFICULTY_WEIGHTS = {
    "foundational": 1,
    "understanding": 2,
    "application": 3,
    "analysis": 4,
    "challenge": 5,
}
PATH_ORDER = {"foundational": 0, "standard": 1, "accelerated": 2}


@dataclass(frozen=True)
class DiagnosticPlacement:
    correct_count: int
    learning_path: str
    objective_paths: dict[str, str]


def select_diagnostic_questions(question_bank: list[dict]) -> list[dict]:
    """Choose the same balanced five-item diagnostic for every student.

    Keeping selection deterministic makes placement reproducible and fair. The
    answers personalize the later path; the diagnostic itself does not change
    while the student is taking it.
    """
    selected: list[dict] = []
    levels = list(DIFFICULTY_WEIGHTS)
    if all(any(question.get("difficulty") == level for question in question_bank) for level in levels):
        return [next(question for question in question_bank if question["difficulty"] == level) for level in levels]
    selected_ids: set[str] = set()
    for difficulty, count in DIFFICULTY_TARGETS.items():
        for question in question_bank:
            if question.get("difficulty") != difficulty or question.get("id") in selected_ids:
                continue
            selected.append(question)
            selected_ids.add(question["id"])
            if sum(item.get("difficulty") == difficulty for item in selected) == count:
                break

    for question in question_bank:
        if len(selected) == DIAGNOSTIC_SIZE:
            break
        if question.get("id") not in selected_ids:
            selected.append(question)
            selected_ids.add(question["id"])

    if len(selected) != DIAGNOSTIC_SIZE:
        raise ValueError("A diagnostic requires at least five questions.")
    return selected


def _path_for_ratio(ratio: float) -> str:
    if ratio < 0.5:
        return "foundational"
    if ratio < 0.85:
        return "standard"
    return "accelerated"


def place_student(
    questions: list[dict],
    answers: list[int],
    objective_ids: list[str],
) -> DiagnosticPlacement:
    """Calculate a path per objective using difficulty-weighted evidence."""
    if len(questions) != DIAGNOSTIC_SIZE or len(answers) != DIAGNOSTIC_SIZE:
        raise ValueError("Placement requires exactly five questions and answers.")

    earned = {objective_id: 0 for objective_id in objective_ids}
    possible = {objective_id: 0 for objective_id in objective_ids}
    correct_count = 0
    for question, answer in zip(questions, answers, strict=True):
        objective_id = question["objective_id"]
        # Preserve placement for earlier published three-band quizzes.
        weight = (DIFFICULTY_WEIGHTS if any(q["difficulty"] == "understanding" for q in questions)
                  else {"foundational": 1, "application": 2, "challenge": 3})[question["difficulty"]]
        possible.setdefault(objective_id, 0)
        earned.setdefault(objective_id, 0)
        possible[objective_id] += weight
        if answer == question["correct_index"]:
            correct_count += 1
            earned[objective_id] += weight

    objective_paths = {
        objective_id: (
            _path_for_ratio(earned[objective_id] / possible[objective_id])
            if possible[objective_id]
            else "standard"
        )
        for objective_id in objective_ids
    }
    learning_path = min(objective_paths.values(), key=PATH_ORDER.__getitem__)
    return DiagnosticPlacement(correct_count, learning_path, objective_paths)
