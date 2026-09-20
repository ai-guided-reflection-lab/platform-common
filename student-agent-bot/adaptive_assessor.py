"""Structured response assessment for the platform-owned adaptive loop."""

from enum import StrEnum

from langchain_core.messages import HumanMessage, SystemMessage
from pydantic import BaseModel, Field

from models import get_model, invoke_with_retry

ASSESSOR_VERSION = "oop-assessor-v1"


class CorrectnessState(StrEnum):
    INCORRECT = "incorrect"
    PARTIAL = "partial"
    CORRECT = "correct"


class CompletenessState(StrEnum):
    INCOMPLETE = "incomplete"
    PARTIAL = "partial"
    COMPLETE = "complete"


class IndependenceLevel(StrEnum):
    GUIDED = "guided"
    SUPPORTED = "supported"
    INDEPENDENT = "independent"


class StructuredAssessment(BaseModel):
    objective_id: str
    assessment_type: str
    correctness: CorrectnessState
    completeness: CompletenessState
    independence: IndependenceLevel
    misconception_code: str | None = None
    misconception_detail: str | None = None
    rationale: str = Field(min_length=1, max_length=1000)
    assessor_version: str = ASSESSOR_VERSION


def assess_response(provider: str, objective: dict, assessment: dict, student_response: str) -> dict:
    """Evaluate evidence only; never choose progression, mastery, or an action."""
    model = get_model(provider).with_structured_output(StructuredAssessment)
    system = """You evaluate one student response for an introductory software engineering course.
Return only the requested structured object. Do not choose a tutoring action, objective progression,
mastery status, or assignment completion.

Categorical rules:
- correctness: incorrect, partial, or correct.
- completeness: incomplete, partial, or complete for this exact prompt.
- independence: independent unless the supplied context says a hint or solution was given;
  supported for a limited hint; guided when the response follows substantial scaffolding.
- Use a short stable misconception_code only when a concrete misconception is evident.
- Code is evaluated as text. Do not claim to execute it.
"""
    human = f"""Objective ID: {objective['id']}
Objective: {objective['description']}
Assessment type: {assessment['assessment_type']}
Prompt: {assessment['prompt']}
Code shown in prompt: {assessment.get('code') or '(none)'}

Student response:
{student_response}
"""
    result = invoke_with_retry(model, [SystemMessage(content=system), HumanMessage(content=human)])
    if isinstance(result, StructuredAssessment):
        parsed = result
    else:
        parsed = StructuredAssessment.model_validate(result)
    # IDs/types are application inputs, never model-authoritative fields.
    parsed.objective_id = objective["id"]
    parsed.assessment_type = assessment["assessment_type"]
    parsed.assessor_version = ASSESSOR_VERSION
    return parsed.model_dump(mode="json")
