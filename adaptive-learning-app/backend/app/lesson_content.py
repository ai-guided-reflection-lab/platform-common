"""Topic-independent lesson checks. No subject content is created at student runtime."""

LEVELS = ["foundational", "understanding", "application", "analysis", "challenge"]


def configuration_issues(plan: dict) -> list[str]:
    issues = []
    for key, label in {
        "topic": "Topic", "topic_introduction": "Introductory explanation",
        "introductory_example": "Introductory example", "approved_material": "Approved teaching material",
        "intended_difficulty": "Intended difficulty", "prerequisite_knowledge": "Prerequisite knowledge (or explicitly 'none')",
    }.items():
        if not plan.get(key, "").strip():
            issues.append(f"Add {label.lower()}.")
    if not plan.get("content_approved"):
        issues.append("Review and approve the lesson content, questions, answer keys, and practice rubrics before publishing.")
    objectives = {o["id"]: o for o in plan.get("objectives", [])}
    if not objectives:
        issues.append("Add learning objectives.")
    for objective in objectives.values():
        if not objective.get("rubric"):
            issues.append(f"Add an explicit assessment rubric for {objective['title']}.")
    resources = plan.get("study_resources", [])
    if not resources:
        issues.append("Add professor-approved learning resources.")
    for resource in resources:
        if not resource.get("description") or not resource.get("focus"):
            issues.append(f"Add a description and study focus for {resource['title']}.")
    quiz = plan.get("diagnostic_quiz", [])
    if len(quiz) != 5 or [q.get("difficulty") for q in quiz] != LEVELS:
        issues.append("Prepare exactly five questions in order: basics, understanding, application, analysis, challenge.")
    if len({q["id"] for q in quiz}) != len(quiz):
        issues.append("Quiz question identifiers must be unique.")
    for index, question in enumerate(quiz):
        prefix = f"Question {index + 1}"
        if not question.get("question", "").strip() or not question.get("explanation", "").strip() or any(not option.strip() for option in question["options"]):
            issues.append(f"{prefix}: complete its question, four options, and answer explanation.")
        if question.get("objective_id") not in objectives:
            issues.append(f"{prefix}: map it to a configured learning objective.")
        if not question.get("concept") or not question.get("material_reference"):
            issues.append(f"{prefix}: name its concept and the relevant approved teaching section.")
        if len(set(option.casefold().strip() for option in question["options"])) != 4:
            issues.append(f"{prefix}: provide four distinct options.")
        misconceptions = question.get("distractor_misconceptions", [])
        if len(misconceptions) != 4 or any(not item.strip() for i, item in enumerate(misconceptions) if i != question["correct_index"]):
            issues.append(f"{prefix}: describe the misconception represented by each distractor (four entries; leave the correct entry blank).")
        hint = question.get("hint", "").strip()
        if not hint or question["options"][question["correct_index"]].casefold() in hint.casefold():
            issues.append(f"{prefix}: add a conceptual hint that does not state the correct option.")
        if index >= 3 and not question.get("reasoning_rubric"):
            issues.append(f"{prefix}: add an explanation rubric.")
    if objectives and set(objectives) - {q.get("objective_id") for q in quiz}:
        issues.append("The diagnostic must cover every configured learning objective.")
    assets = {a["objective_id"]: a for a in plan.get("learning_assets", [])}
    if len(assets) != len(plan.get("learning_assets", [])) or set(assets) - set(objectives):
        issues.append("Practice banks must map uniquely to configured learning objectives.")
    for objective_id, objective in objectives.items():
        asset = assets.get(objective_id)
        if not asset or not asset.get("explanation") or not asset.get("worked_example") or not asset.get("counterexample"):
            issues.append(f"Add an approved explanation, worked example, and counterexample for {objective['title']}.")
            continue
        for level in ("foundational", "standard", "accelerated"):
            activities = asset.get(level, [])
            concepts = {q["concept"] for q in quiz if q["objective_id"] == objective_id and q.get("concept")}
            missing = concepts - {activity.get("concept") for activity in activities}
            if missing:
                issues.append(f"Add {level} follow-ups mapped to these concepts for {objective['title']}: {', '.join(sorted(missing))}.")
            if len(activities) < 2:
                issues.append(f"Add at least two fresh {level} activities for {objective['title']}.")
            for activity in activities:
                if not activity.get("prompt", "").strip() or not activity.get("hint", "").strip():
                    issues.append(f"Complete each {level} activity and hint for {objective['title']}.")
                if activity["prompt"].strip().casefold() in {q["question"].strip().casefold() for q in quiz}:
                    issues.append(f"Use a fresh practice example for {objective['title']}, rather than repeating a quiz question.")
                if not activity.get("rubric") and not objective.get("rubric"):
                    issues.append(f"Add a practice assessment rubric for {objective['title']}.")
    return list(dict.fromkeys(issues))
