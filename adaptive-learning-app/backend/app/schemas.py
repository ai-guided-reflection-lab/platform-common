from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, StrictInt, model_validator


class RubricCriterion(BaseModel):
    description: str = Field(min_length=1, max_length=1000)
    # Each group contains equivalent expressions; all groups must be present.
    evidence_groups: list[list[str]] = Field(default_factory=list, max_length=10)


class Misconception(BaseModel):
    description: str = Field(min_length=1, max_length=1000)
    evidence_phrases: list[str] = Field(min_length=1, max_length=10)
    counterexample: str = Field(min_length=1, max_length=2000)


class Objective(BaseModel):
    id: str = Field(min_length=1, max_length=80)
    title: str = Field(min_length=1, max_length=160)
    description: str = Field(min_length=1, max_length=1200)
    success_criteria: list[str] = Field(min_length=1, max_length=10)
    diagnostic_prompt: str = Field(min_length=1, max_length=3000)
    rubric: list[RubricCriterion] = Field(default_factory=list, max_length=10)
    misconceptions: list[Misconception] = Field(default_factory=list, max_length=10)


class RequiredTask(BaseModel):
    title: str = Field(min_length=1, max_length=160)
    description: str = Field(min_length=1, max_length=1600)
    submission_prompt: str = Field(min_length=1, max_length=3000)


class StudyResource(BaseModel):
    title: str = Field(min_length=1, max_length=300)
    url: str = Field(pattern=r"^https://", max_length=1000)
    provider: str = Field(min_length=1, max_length=100)
    description: str = Field(default="", max_length=1000)
    focus: str = Field(default="", max_length=1000)


class QuizQuestion(BaseModel):
    id: str = Field(min_length=1, max_length=80)
    objective_id: str = Field(min_length=1, max_length=80)
    difficulty: Literal["foundational", "understanding", "application", "analysis", "challenge"]
    question: str = Field(default="", max_length=2000)
    options: list[str] = Field(min_length=4, max_length=4)
    correct_index: int = Field(ge=0, le=3)
    explanation: str = Field(default="", max_length=2000)
    concept: str = Field(default="", max_length=200)
    hint: str = Field(default="", max_length=1000)
    material_reference: str = Field(default="", max_length=1000)
    distractor_misconceptions: list[str] = Field(default_factory=list, max_length=4)
    reasoning_rubric: list[RubricCriterion] = Field(default_factory=list, max_length=10)


class PracticeQuestion(BaseModel):
    prompt: str = Field(default="", max_length=2500)
    hint: str = Field(default="", max_length=1500)
    concept: str = Field(default="", max_length=200)
    rubric: list[RubricCriterion] = Field(default_factory=list, max_length=10)


class ObjectiveLearningAssets(BaseModel):
    objective_id: str = Field(min_length=1, max_length=80)
    explanation: str = Field(default="", max_length=4000)
    worked_example: str = Field(default="", max_length=4000)
    analogy: str = Field(default="", max_length=2000)
    counterexample: str = Field(default="", max_length=2000)
    foundational: list[PracticeQuestion] = Field(min_length=2, max_length=5)
    standard: list[PracticeQuestion] = Field(min_length=2, max_length=5)
    accelerated: list[PracticeQuestion] = Field(min_length=2, max_length=5)
    misconceptions: list[str] = Field(default_factory=list, max_length=8)


class LearningPlan(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    course_context: str = Field(default="", max_length=1000)
    objectives: list[Objective] = Field(min_length=1, max_length=20)
    required_task: RequiredTask
    study_resources: list[StudyResource] = Field(default_factory=list, max_length=5)
    diagnostic_quiz: list[QuizQuestion] = Field(default_factory=list, max_length=8)
    learning_assets: list[ObjectiveLearningAssets] = Field(default_factory=list, max_length=20)
    topic: str = Field(default="", max_length=200)
    topic_introduction: str = Field(default="", max_length=1200)
    auto_generated: bool = False
    flow_version: Literal[1, 2] = 2
    approved_material: str = Field(default="", max_length=30000)
    introductory_example: str = Field(default="", max_length=3000)
    intended_difficulty: str = Field(default="", max_length=200)
    prerequisite_knowledge: str = Field(default="", max_length=2000)
    content_approved: bool = False

    @model_validator(mode="after")
    def unique_objectives(self):
        ids = [item.id for item in self.objectives]
        if len(ids) != len(set(ids)):
            raise ValueError("Objective ids must be unique.")
        return self


class AssignmentInput(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    instructions: str = Field(default="", max_length=4000)
    learning_plan: LearningPlan
    student_ids: list[str] = Field(default_factory=list)


class GeneratePlanInput(BaseModel):
    topic: str = Field(min_length=2, max_length=200)
    course_level: str = Field(default="Undergraduate", min_length=2, max_length=100)
    approved_material: str = Field(min_length=30, max_length=30000)
    objective_descriptions: list[str] = Field(min_length=1, max_length=20)
    study_resources: list[StudyResource] = Field(min_length=1, max_length=5)
    intended_difficulty: str = Field(min_length=1, max_length=200)
    prerequisite_knowledge: str = Field(min_length=1, max_length=2000)


class MessageInput(BaseModel):
    content: str = Field(min_length=1, max_length=8000)


class TaskSubmission(BaseModel):
    content: str = Field(min_length=1, max_length=20000)


class StudyCompletion(BaseModel):
    message: str = Field(default="I've finished studying", max_length=300)


class QuizSubmission(BaseModel):
    answers: list[int] = Field(min_length=5, max_length=5)


class LearningTurn(BaseModel):
    action: Literal["message", "answer", "hint", "continue", "choice", "pause", "resume"] = "message"
    content: str = Field(default="", max_length=8000)
    question_id: str | None = Field(default=None, max_length=80)
    option_index: StrictInt | None = Field(default=None, ge=0, le=3)
    confidence: Literal["low", "medium", "high"] | None = None
    explanation: str | None = Field(default=None, max_length=3000)
    turn_id: str = Field(min_length=1, max_length=100)


class UserPublic(BaseModel):
    id: str
    email: str
    display_name: str
    role: Literal["instructor", "student"]


class PlatformStudentInput(BaseModel):
    platform_user_id: str = Field(min_length=1, max_length=200)
    email: str = Field(min_length=3, max_length=320)
    display_name: str = Field(min_length=1, max_length=200)
