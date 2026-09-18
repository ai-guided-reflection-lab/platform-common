"""Recommendation system service — SCS and LLM-SCS modes."""
from __future__ import annotations

import logging
from typing import Any

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)

# Module-level model cache — avoids reloading the transformer on each request.
_embedding_model = None


def _get_embedding_model():
    global _embedding_model
    if _embedding_model is None:
        try:
            from sentence_transformers import SentenceTransformer
            _embedding_model = SentenceTransformer("stsb-roberta-large")
        except ImportError:
            raise RuntimeError(
                "sentence-transformers is not installed. "
                "Run: pip install sentence-transformers"
            )
    return _embedding_model


def _cosine_scores(historical_embeddings, current_embedding) -> np.ndarray:
    from sentence_transformers import util
    return util.pytorch_cos_sim(historical_embeddings, current_embedding).cpu().numpy().flatten()


def run_scs(historical_df: pd.DataFrame, current_df: pd.DataFrame, k: int = 5) -> list[dict[str, Any]]:
    """
    SCS mode: find the top-k most similar historical students for each current student.

    historical_df must have columns: name, challenge, solution
    current_df must have columns:   Full Name, Email Address, student's reflection
    """
    model = _get_embedding_model()

    challenges_past = historical_df["challenge"].astype(str).values
    embeddings_past = model.encode(challenges_past, convert_to_tensor=True, show_progress_bar=False)

    results: list[dict] = []
    for _, row in current_df.iterrows():
        name = str(row.get("Full Name", ""))
        email = str(row.get("Email Address", ""))
        reflection = str(row.get("student's reflection", ""))

        current_emb = model.encode(reflection, convert_to_tensor=True)
        scores = _cosine_scores(embeddings_past, current_emb)

        temp = historical_df[["name", "challenge", "solution"]].copy()
        temp["cos_score"] = scores
        temp = temp[temp["name"] != name]  # exclude student's own past entries
        top_k = (
            temp.nlargest(k, "cos_score")[["cos_score", "challenge", "solution", "name"]]
            .reset_index(drop=True)
            .to_dict("records")
        )
        # round scores for readability
        for entry in top_k:
            entry["cos_score"] = round(float(entry["cos_score"]), 4)

        results.append({"email": email, "name": name, "reflection": reflection, "similar": top_k})

    return results


def run_llm_scs(
    historical_df: pd.DataFrame,
    current_df: pd.DataFrame,
    llm_provider,
    k: int = 5,
) -> list[dict[str, Any]]:
    """
    LLM-SCS mode: SCS + LLM-generated personalised recommendation email per student.
    """
    results = run_scs(historical_df, current_df, k)

    role = (
        "You are an instructor assistant of an introduction to data mining course. "
        "You want to help students with their challenges but also increase students' "
        "sense of belonging. You are writing emails to students to provide advice "
        "about how to tackle their challenges"
    )
    context = (
        "You are given a current students' reflection called Student Reflection. "
        "The reflection prompts were 'What was your biggest challenge?' and "
        "'What is a potential solution to your challenge?' "
        "You are also given former students' reflections. These reflections were "
        "automatically selected by our algorithm to have the most similar challenges "
        "to the student out of our dataset. However, the similarity may not be clear. "
        "Make sure the student actually talks about a challenge before using it in the email."
    )
    task = (
        "Please write an email between 100-250 words to the student that accomplishes "
        "the following tasks:\n"
        "(1) Summarize your understanding of the student's current challenge and validate their struggles.\n"
        "(2) Assure the student that they are not alone, and provide a general summary of previous students' challenges.\n"
        "(3) Identify the general topic the former students' reflections have in common and how it relates to this student's challenge.\n"
        "(4) Provide a general summary of the previous students' solutions and comment on their usefulness.\n"
        "(5) Provide your own solutions to the challenge based on best practices in teaching.\n"
        "(6) Include only the email content — no subject line, greeting, or sign-off."
    )

    for result in results:
        similar_text = "\n\n".join(
            f"Student {i + 1}:\nChallenge: {s['challenge']}\nSolution: {s['solution']}"
            for i, s in enumerate(result["similar"])
        )
        similar_text = f"'''\n{similar_text}\n'''"

        prompt = (
            f"Your role is: {role}\n\n"
            f"Your context is: {context}\n\n"
            f"Your task is: {task}\n\n"
            f"Here is a list of students' previous challenges and solutions:\n{similar_text}\n\n"
            f"Student Reflection: {result['reflection']}"
        )

        try:
            result["llm_output"] = llm_provider.generate([{"role": "user", "content": prompt}])
        except Exception as exc:
            logger.error("LLM generation failed for %s: %s", result["name"], exc)
            result["llm_output"] = f"[Error generating recommendation: {exc}]"

    return results
