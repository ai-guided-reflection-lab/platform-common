from app.learning_flow import place_student, select_diagnostic_questions


def question(identifier, objective, difficulty):
    return {
        "id": identifier,
        "objective_id": objective,
        "difficulty": difficulty,
        "correct_index": 0,
    }


def diagnostic_bank():
    return [
        question("C-1", "B", "challenge"),
        question("F-1", "A", "foundational"),
        question("A-1", "B", "application"),
        question("F-2", "A", "foundational"),
        question("A-2", "B", "application"),
        question("C-2", "A", "challenge"),
        question("A-3", "A", "application"),
    ]


def test_diagnostic_selection_is_balanced_and_deterministic():
    selected = select_diagnostic_questions(diagnostic_bank())

    assert [item["id"] for item in selected] == ["F-1", "F-2", "A-1", "A-2", "C-1"]
    assert [item["difficulty"] for item in selected] == [
        "foundational",
        "foundational",
        "application",
        "application",
        "challenge",
    ]


def test_novice_standard_advanced_and_mixed_students_get_explainable_paths():
    questions = select_diagnostic_questions(diagnostic_bank())

    novice = place_student(questions, [1, 1, 1, 1, 1], ["A", "B"])
    assert novice.correct_count == 0
    assert novice.learning_path == "foundational"
    assert novice.objective_paths == {"A": "foundational", "B": "foundational"}

    standard = place_student(questions, [0, 1, 0, 0, 1], ["A", "B"])
    assert standard.correct_count == 3
    assert standard.learning_path == "standard"
    assert standard.objective_paths == {"A": "standard", "B": "standard"}

    advanced = place_student(questions, [0, 0, 0, 0, 0], ["A", "B"])
    assert advanced.correct_count == 5
    assert advanced.learning_path == "accelerated"
    assert advanced.objective_paths == {"A": "accelerated", "B": "accelerated"}

    mixed = place_student(questions, [0, 0, 1, 1, 1], ["A", "B"])
    assert mixed.learning_path == "foundational"
    assert mixed.objective_paths == {"A": "accelerated", "B": "foundational"}
