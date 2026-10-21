from __future__ import annotations

import csv
import io
from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    HttpUrl,
    SecretStr,
    StrictInt,
    model_validator,
)


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class Resource(StrictModel):
    title: str = Field(min_length=1, max_length=300)
    url: HttpUrl


class PracticeStage(StrictModel):
    label: str = Field(min_length=1, max_length=200)
    focus: str = Field(min_length=1, max_length=3000)


class Topic(StrictModel):
    id: str = Field(min_length=1, pattern=r"^[a-zA-Z0-9_-]+$")
    name: str = Field(min_length=1, max_length=200)
    resource: Resource
    alt_resource: Resource
    practice_label: str = Field(min_length=1, max_length=300)
    practice_prompt: str = Field(min_length=1, max_length=10000)
    practice_stages: list[PracticeStage] = Field(min_length=1, max_length=20)
    practice_options: list[str] = Field(default_factory=list, max_length=20)
    check_questions: list[str] = Field(default_factory=list, max_length=50)
    final_example: str = Field(min_length=1, max_length=20000)
    number: int = 100


class SocraticConfig(StrictModel):
    keywords: list[str] = Field(default_factory=list, max_length=8)
    optional_keywords: list[str] = Field(default_factory=list, max_length=48)
    dismissed_keywords: list[str] = Field(default_factory=list, max_length=500)
    learning_objective_id: UUID | None = None
    document_ids: list[str] = Field(default_factory=list, max_length=100)
    prompt: str = Field(default="", max_length=10000)
    minimum_messages: int = Field(default=1, ge=1, le=100)


    @model_validator(mode="after")
    def validate_keywords(self):
        from app.objective_extraction import _clean_keywords
        if any(not item.strip() or len(item) > 120 for item in self.keywords):
            raise ValueError("Keywords must contain 1 to 120 characters each.")
        self.keywords = _clean_keywords(self.keywords)
        seen = set()
        optional = []
        for item in self.optional_keywords:
            word = " ".join(item.split())
            if not word or len(word) > 120:
                raise ValueError("Optional keywords must contain 1 to 120 characters each.")
            if word.casefold() not in seen:
                seen.add(word.casefold())
                optional.append(word)
        self.optional_keywords = optional
        dismissed = []
        seen.clear()
        for item in self.dismissed_keywords:
            word = " ".join(item.split())
            if not word or len(word) > 120:
                raise ValueError("Dismissed keywords must contain 1 to 120 characters each.")
            if word.casefold() not in seen:
                seen.add(word.casefold())
                dismissed.append(word)
        self.dismissed_keywords = dismissed
        return self


class DebateConfig(StrictModel):
    document_ids: list[str] = Field(default_factory=list, max_length=100)
    scenario: str = Field(min_length=10, max_length=10000)
    opening_prompt: str = Field(default="", max_length=2000)
    minimum_messages: int = Field(default=3, ge=1, le=100)


class SelfDirectedConfig(StrictModel):
    custom_questions: list[str] = Field(default_factory=list, max_length=50)
    document_ids: list[str] = Field(default_factory=list, max_length=100)
    prompt: str = Field(default="", max_length=10000)
    learning_plan: dict = Field(default_factory=dict)


class ReflectionConfig(StrictModel):
    document_ids: list[str] = Field(default_factory=list, max_length=100)
    module_type: Literal["topic_based", "milestone_based"] = "topic_based"
    required_topics: list[str] = Field(default_factory=list, max_length=100)
    sub_topics: list[str] = Field(default_factory=list, max_length=100)
    expected_depth: Literal["surface", "applied", "analytical"] = "surface"
    probing_style: Literal["supportive", "socratic"] = "supportive"
    must_include_application: bool = False
    custom_notes: str = Field(default="", max_length=10000)
    milestone_prompt: str = Field(default="", max_length=10000)
    historical_data: str = Field(default="", max_length=2_000_000)

    def validate_publish(self):
        if self.module_type == "topic_based":
            if not any(t.strip() for t in self.sub_topics):
                raise ValueError("Add at least one reflection sub-topic before publishing.")
        else:
            if not self.milestone_prompt or not self.historical_data:
                raise ValueError("Milestone reflections require a prompt and historical CSV.")
            reader = csv.DictReader(io.StringIO(self.historical_data))
            if not {"name", "challenge", "solution"}.issubset(reader.fieldnames or []):
                raise ValueError("Historical CSV must contain name, challenge, and solution columns.")
            if not any(all((row.get(k) or "").strip() for k in ("name", "challenge", "solution")) for row in reader):
                raise ValueError("Historical CSV must contain at least one complete row.")


class TutorConfig(StrictModel):
    topic: Topic | None = None
    provider: Literal["openai", "groq"] = "openai"
    personality: str = "confused"


class ActivityDraftConfig(StrictModel):
    document_ids: list[str] = Field(default_factory=list, max_length=100)
    prompt: str = Field(default="", max_length=10000)
    scenario: str = Field(default="", max_length=10000)
    minimum_messages: int = Field(default=3, ge=1, le=100)


CONFIG_MODELS = {
    "self-directed-learning": SelfDirectedConfig,
    "debate": DebateConfig,
    "aiducate": ActivityDraftConfig,
    "socratic": SocraticConfig,
    "reflections": ReflectionConfig,
    "student-agent": TutorConfig,
}


class AssignmentInput(StrictModel):
    course_id: UUID
    tool: Literal[
        "socratic",
        "reflections",
        "student-agent",
        "self-directed-learning",
        "debate",
        "aiducate",
    ] | None
    title: str = Field(min_length=1, max_length=200)
    instructions: str = Field(default="", max_length=10000)
    due_at: datetime | None = None
    audience: Literal["course", "selected"] = "course"
    recipient_ids: list[UUID] = Field(default_factory=list, max_length=10000)
    config: dict = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_config(self):
        if self.tool is None:
            if self.config:
                raise ValueError("Choose a chatbot before adding its settings.")
        else:
            self.config = CONFIG_MODELS[self.tool].model_validate(self.config).model_dump(mode="json")
        if self.due_at and self.due_at.tzinfo is None:
            raise ValueError("Due date must include a time zone.")
        if self.audience == "selected" and not self.recipient_ids:
            raise ValueError("Select at least one student.")
        return self


class MessageInput(StrictModel):
    message: str = Field(min_length=1, max_length=20000)
    request_id: UUID
    clarification_index: int | None = Field(default=None, ge=0, le=2)
    concept_check_option: int | None = Field(default=None, ge=0, le=2)


class SocraticReflectionInput(StrictModel):
    summary: str = Field(min_length=1, max_length=4000)
    request_id: UUID


class ActionInput(StrictModel):
    action: Literal["navigate", "scenario"]
    value: str = Field(min_length=1, max_length=1000)
    request_id: UUID


class GenerateTopicInput(StrictModel):
    name: str = Field(min_length=1, max_length=200)
    provider: Literal["openai", "groq"] = "openai"


class GenerateSubtopicsInput(StrictModel):
    main_topics: list[str] = Field(min_length=1, max_length=50)

class SelfDirectedStudyInput(StrictModel):
    message: str = Field(default="I've finished studying", min_length=1, max_length=300)



class SelfDirectedQuizInput(StrictModel):
    answers: list[int] = Field(min_length=5, max_length=5)


class CanvasCredentials(StrictModel):
    access_token: SecretStr = Field(min_length=10, max_length=4096)


class CanvasCourseRequest(CanvasCredentials):
    course_id: int = Field(gt=0)


class CanvasImportRequest(CanvasCourseRequest):
    assignment_id: int = Field(gt=0)
    platform_course_id: UUID
    tool: Literal["socratic", "reflections", "student-agent", "debate"] = "socratic"


class SelfDirectedMessageInput(StrictModel):
    content: str = Field(min_length=1, max_length=8000)



class SelfDirectedTaskInput(StrictModel):
    content: str = Field(min_length=1, max_length=20000)



class SelfDirectedLearningTurn(StrictModel):
    action: Literal["message", "answer", "hint", "continue", "choice", "pause", "resume"] = "message"
    content: str = Field(default="", max_length=8000)
    question_id: str | None = Field(default=None, max_length=80)
    option_index: StrictInt | None = Field(default=None, ge=0, le=3)
    confidence: Literal["low", "medium", "high"] | None = None
    explanation: str | None = Field(default=None, max_length=3000)
    turn_id: str = Field(min_length=1, max_length=100)


class LearningObjectiveUpdate(StrictModel):
    keywords: list[str] | None = Field(default=None, min_length=1, max_length=8)
    objective: str | None = Field(default=None, min_length=1, max_length=500)
    prerequisites: list[str] | None = Field(default=None, max_length=5)
    success_criteria: list[str] | None = Field(default=None, max_length=5)
    common_misconceptions: list[str] | None = Field(default=None, max_length=4)
    diagnostic_question: str | None = Field(default=None, min_length=1, max_length=300)
    status: Literal["draft", "approved", "rejected"] | None = None

    @model_validator(mode="after")
    def validate_lists(self):
        for name in ("prerequisites", "success_criteria", "common_misconceptions"):
            values = getattr(self, name)
            if values is not None:
                if any(not isinstance(item, str) or not item.strip() or len(item) > 240 for item in values):
                    raise ValueError("Planning details must contain non-empty items of at most 240 characters.")
                setattr(self, name, list(dict.fromkeys(item.strip() for item in values)))
        if self.keywords is not None:
            from app.objective_extraction import _clean_keywords
            if any(not item.strip() or len(item) > 120 for item in self.keywords):
                raise ValueError("Keywords must contain 1 to 120 characters each.")
            self.keywords = _clean_keywords(self.keywords)
        return self
