from __future__ import annotations

import csv
import io
from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, SecretStr, StrictInt, model_validator


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)








class SocraticConfig(StrictModel):
    document_ids: list[str] = Field(default_factory=list, max_length=100)
    prompt: str = Field(default="", max_length=10000)
    minimum_messages: int = Field(default=1, ge=1, le=100)


class DebateConfig(StrictModel):
    scenario: str = Field(min_length=10, max_length=10000)
    opening_prompt: str = Field(default="", max_length=2000)
    minimum_messages: int = Field(default=3, ge=1, le=100)


class SelfDirectedConfig(StrictModel):
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




CONFIG_MODELS = {"socratic": SocraticConfig, "reflections": ReflectionConfig, "debate": DebateConfig, "self-directed-learning": SelfDirectedConfig}


class AssignmentInput(StrictModel):
    course_id: UUID
    tool: Literal["socratic", "reflections", "debate", "self-directed-learning"]
    title: str = Field(min_length=1, max_length=200)
    instructions: str = Field(default="", max_length=10000)
    due_at: datetime | None = None
    audience: Literal["course", "selected"] = "course"
    recipient_ids: list[UUID] = Field(default_factory=list, max_length=10000)
    config: dict = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_config(self):
        self.config = CONFIG_MODELS[self.tool].model_validate(self.config).model_dump(mode="json")
        if self.due_at and self.due_at.tzinfo is None:
            raise ValueError("Due date must include a time zone.")
        if self.audience == "selected" and not self.recipient_ids:
            raise ValueError("Select at least one student.")
        return self


class MessageInput(StrictModel):
    message: str = Field(min_length=1, max_length=20000)
    request_id: UUID






class GenerateSubtopicsInput(StrictModel):
    main_topics: list[str] = Field(min_length=1, max_length=50)


class CanvasCredentials(StrictModel):
    access_token: SecretStr = Field(min_length=10, max_length=4096)


class CanvasCourseRequest(CanvasCredentials):
    course_id: int = Field(gt=0)


class CanvasImportRequest(CanvasCourseRequest):
    assignment_id: int = Field(gt=0)
    platform_course_id: UUID
    tool: Literal["socratic", "reflections", "debate", "self-directed-learning"] = "socratic"


class SelfDirectedStudyInput(StrictModel):
    message: str = Field(default="I've finished studying", min_length=1, max_length=300)



class SelfDirectedQuizInput(StrictModel):
    answers: list[int] = Field(min_length=5, max_length=5)



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
