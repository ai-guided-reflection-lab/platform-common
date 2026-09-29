from __future__ import annotations

import re


def _question(prompt: str, hint: str) -> dict:
    return {"prompt": prompt, "hint": hint}


def _generic_assets(objective: dict, topic: str) -> dict:
    title = objective["title"]
    description = objective["description"]
    return {
        "objective_id": objective["id"],
        "explanation": (
            f"Focus on this objective: {description} Start by identifying the key terms, "
            f"then connect them to a concrete {topic} example."
        ),
        "worked_example": (
            f"A strong response about {title.lower()} names the relevant concept, applies it "
            "to a specific case, and explains why the evidence supports the conclusion."
        ),
        "foundational": [
            _question(
                f"Define the central idea in ‘{title}’ in one or two sentences.",
                "Use the objective description and identify the most important term.",
            ),
            _question(
                f"Give a simple example of {title.lower()} and identify the part that makes it fit.",
                "An example needs both a case and an explanation of the connection.",
            ),
        ],
        "standard": [
            _question(
                f"Apply {title.lower()} to a realistic undergraduate-level situation.",
                "State the concept, apply it, and justify the conclusion.",
            ),
            _question(
                f"Compare a correct and incorrect use of {title.lower()}.",
                "Make the difference observable rather than merely labeling the cases.",
            ),
        ],
        "accelerated": [
            _question(
                f"Analyze a borderline case where {title.lower()} is difficult to apply.",
                "Identify the competing interpretations and defend one with evidence.",
            ),
            _question(
                f"What limitation or trade-off appears when applying {title.lower()} in practice?",
                "Connect the limitation to a concrete consequence.",
            ),
        ],
        "misconceptions": [
            "Repeats terminology without explaining the mechanism",
            "Provides an example without explaining why it fits",
        ],
    }


def _llm_assets(objective: dict) -> dict:
    foundations = "fundamental" in objective["title"].lower() or "generate" in objective["description"].lower()
    if foundations:
        return {
            "objective_id": objective["id"],
            "explanation": (
                "A standard large language model generates text one token at a time. It uses "
                "patterns represented in learned parameters and the current context to estimate "
                "which token is likely to come next; it does not normally retrieve a complete "
                "stored answer from a database."
            ),
            "worked_example": (
                "Given ‘The capital of France is’, the context makes ‘Paris’ much more probable "
                "than an unrelated token. The model emits a token, adds it to the context, and "
                "repeats the prediction process."
            ),
            "foundational": [
                _question("What is a token, and what does an LLM predict during generation?", "Separate the text unit from the prediction task."),
                _question("Why is an LLM not simply a database of complete answers?", "Think about learned parameters and step-by-step generation."),
            ],
            "standard": [
                _question("Explain how context changes the next token an LLM may generate.", "Use two different sentence beginnings as evidence."),
                _question("Explain why fluent output is not proof that an answer is true.", "Connect statistical plausibility to factual verification."),
            ],
            "accelerated": [
                _question("Contrast next-token generation with search-engine retrieval and identify one hybrid system that uses both.", "RAG is one useful comparison."),
                _question("Analyze how tokenization and a limited context window can affect an LLM response.", "Discuss at least one concrete failure mode."),
            ],
            "misconceptions": [
                "An LLM searches a database for a complete answer",
                "Fluent output proves human-like understanding",
                "The model verifies every statement before producing it",
            ],
        }
    return _generic_assets(objective, "large language models")


def _generic_quiz(topic: str, objectives: list[dict]) -> list[dict]:
    first, second = objectives[0], objectives[min(1, len(objectives) - 1)]
    return [
        {
            "id": "QUIZ-1",
            "objective_id": first["id"],
            "difficulty": "foundational",
            "question": f"Which response best demonstrates the objective ‘{first['title']}’?",
            "options": [
                "An explanation that uses the key concept accurately and gives a relevant example",
                "A confident statement without supporting reasoning",
                "A list of unrelated vocabulary",
                "A personal preference with no connection to the topic",
            ],
            "correct_index": 0,
            "explanation": "A strong foundational response combines accurate concepts with a relevant example.",
        },
        {
            "id": "QUIZ-2",
            "objective_id": first["id"],
            "difficulty": "foundational",
            "question": f"What is the best first step when explaining {topic}?",
            "options": [
                "Assume every reader already knows the terminology",
                "Begin with an unrelated conclusion",
                "Identify and define the central mechanism or idea",
                "Avoid giving any examples",
            ],
            "correct_index": 2,
            "explanation": "Defining the central idea gives later examples and applications a clear foundation.",
        },
        {
            "id": "QUIZ-3",
            "objective_id": second["id"],
            "difficulty": "application",
            "question": "Which approach provides the strongest application evidence?",
            "options": [
                "Repeat the definition without using it",
                "Apply the concept to a case and explain why the evidence supports the result",
                "State that the concept is important",
                "Choose an answer without justification",
            ],
            "correct_index": 1,
            "explanation": "Application requires using the concept and justifying the result with evidence.",
        },
        {
            "id": "QUIZ-4",
            "objective_id": second["id"],
            "difficulty": "application",
            "question": "A result looks plausible but lacks supporting evidence. What should you do?",
            "options": [
                "Accept it because it sounds confident",
                "Remove all context",
                "Treat plausibility as proof",
                "Verify it against the course material or another reliable source",
            ],
            "correct_index": 3,
            "explanation": "Plausibility is not evidence; important claims should be verified.",
        },
        {
            "id": "QUIZ-5",
            "objective_id": second["id"],
            "difficulty": "challenge",
            "question": "Which answer shows the strongest critical understanding?",
            "options": [
                "It gives only a definition",
                "It provides an example without explaining it",
                "It applies the concept, supports the reasoning, and identifies a limitation or trade-off",
                "It avoids considering limitations",
            ],
            "correct_index": 2,
            "explanation": "Critical understanding combines application, evidence, and awareness of limitations.",
        },
    ]


def _llm_quiz(objectives: list[dict]) -> list[dict]:
    first, second = objectives[0], objectives[min(1, len(objectives) - 1)]
    return [
        {"id": "LLM-Q1", "objective_id": first["id"], "difficulty": "foundational", "question": "What does a standard LLM primarily do when generating text?", "options": ["Predicts likely next tokens from context", "Searches a database for a complete stored answer", "Verifies every statement on the internet", "Copies one training document word for word"], "correct_index": 0, "explanation": "An LLM repeatedly predicts likely next tokens using learned patterns and the current context."},
        {"id": "LLM-Q2", "objective_id": first["id"], "difficulty": "foundational", "question": "What is a token?", "options": ["A guaranteed factual claim", "A complete database record", "A unit of text processed by the model", "A human review score"], "correct_index": 2, "explanation": "Tokens are the text units the model processes and predicts."},
        {"id": "LLM-Q3", "objective_id": second["id"], "difficulty": "application", "question": "Which prompt is most likely to produce a useful undergraduate explanation?", "options": ["Tell me everything", "Explain transformers to a first-year CS student in 200 words, define attention, and include one analogy", "Transformers?", "Write something technical"], "correct_index": 1, "explanation": "The strongest prompt provides a task, audience, scope, constraints, and requested content."},
        {"id": "LLM-Q4", "objective_id": second["id"], "difficulty": "application", "question": "An LLM gives a confident citation that cannot be found. What is the best response?", "options": ["Use it because the wording is confident", "Assume the source was deleted", "Cite the LLM as the original research", "Treat it as a possible hallucination and verify it in a reliable database"], "correct_index": 3, "explanation": "Generated citations and important claims must be verified against original reliable sources."},
        {"id": "LLM-Q5", "objective_id": second["id"], "difficulty": "challenge", "question": "Why can RAG improve an LLM answer without guaranteeing correctness?", "options": ["It retrains the entire model for every question", "It prevents the model from generating text", "It adds relevant external context, but retrieval and generation can still introduce errors", "It guarantees that every retrieved source is correct"], "correct_index": 2, "explanation": "RAG supplies external context, but retrieval can miss or select poor passages and the model can misinterpret them."},
    ]


def ensure_learning_content(plan: dict, topic: str) -> dict:
    """Guarantee a five-item placement quiz and three-level practice bank."""
    result = {**plan, "topic": topic, "auto_generated": True}
    normalized = re.sub(r"[^a-z]+", " ", topic.lower()).strip()
    if len(result.get("diagnostic_quiz", [])) != 5:
        result["diagnostic_quiz"] = (
            _llm_quiz(result["objectives"])
            if "language model" in normalized or normalized == "llm"
            else _generic_quiz(topic, result["objectives"])
        )
    existing = {item.get("objective_id"): item for item in result.get("learning_assets", [])}
    assets = []
    for objective in result["objectives"]:
        item = existing.get(objective["id"])
        if not item:
            item = _llm_assets(objective) if "language model" in normalized or normalized == "llm" else _generic_assets(objective, topic)
        assets.append(item)
    result["learning_assets"] = assets
    return result
