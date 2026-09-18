"""SQLAlchemy models — minimal research-friendly schema."""

import uuid
from datetime import datetime, timezone

from sqlalchemy import (
    Column, String, Integer, Float, Boolean, Text, DateTime, ForeignKey, JSON,
)
from sqlalchemy.orm import relationship
from app.database import Base


def _uuid():
    return str(uuid.uuid4())


# ── Student ──────────────────────────────────────────────────────────────────
class Student(Base):
    __tablename__ = "students"

    id = Column(String, primary_key=True, default=_uuid)
    anonymized_id = Column(String, unique=True, nullable=False)

    conversations = relationship("Conversation", back_populates="student")


# ── Module ───────────────────────────────────────────────────────────────────
class Module(Base):
    __tablename__ = "modules"

    id = Column(String, primary_key=True, default=_uuid)
    name = Column(String, nullable=False)
    module_type = Column(String, default="topic_based", server_default="topic_based")  # topic_based | milestone_based

    config = relationship("ModuleConfig", back_populates="module", uselist=False)
    conversations = relationship("Conversation", back_populates="module")


# ── ModuleConfig ─────────────────────────────────────────────────────────────
class ModuleConfig(Base):
    __tablename__ = "module_configs"

    id = Column(String, primary_key=True, default=_uuid)
    module_id = Column(String, ForeignKey("modules.id"), unique=True, nullable=False)

    required_topics = Column(JSON, default=list)          # ["topic1", "topic2"]
    sub_topics = Column(JSON, default=list)               # drives chat questions
    expected_depth = Column(String, default="surface")    # surface | applied | analytical
    probing_style = Column(String, default="supportive")  # supportive | socratic
    must_include_application = Column(Boolean, default=False)
    custom_notes = Column(Text, default="")
    milestone_prompt = Column(Text, default="", server_default="")   # question shown to student
    milestone_historical_data = Column(Text, default="", server_default="")  # raw CSV content

    @property
    def has_historical_data(self) -> bool:
        return bool(self.milestone_historical_data)

    module = relationship("Module", back_populates="config")


# ── Conversation ─────────────────────────────────────────────────────────────
class Conversation(Base):
    __tablename__ = "conversations"

    id = Column(String, primary_key=True, default=_uuid)
    student_id = Column(String, ForeignKey("students.id"), nullable=False)
    module_id = Column(String, ForeignKey("modules.id"), nullable=False)
    transcript = Column(Text, default="")
    duration = Column(Integer, default=0)  # seconds
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    student = relationship("Student", back_populates="conversations")
    module = relationship("Module", back_populates="conversations")
    analytics = relationship("ReflectionAnalytics", back_populates="conversation", uselist=False)


# ── ReflectionAnalytics ─────────────────────────────────────────────────────
class ReflectionAnalytics(Base):
    __tablename__ = "reflection_analytics"

    id = Column(String, primary_key=True, default=_uuid)
    conversation_id = Column(String, ForeignKey("conversations.id"), unique=True, nullable=False)

    topics_covered = Column(JSON, default=list)
    missing_topics = Column(JSON, default=list)
    misconceptions = Column(JSON, default=list)
    reflection_depth_score = Column(Float, default=0.0)
    confidence_level = Column(Integer, default=0)
    engagement_score = Column(Float, default=0.0)

    conversation = relationship("Conversation", back_populates="analytics")
