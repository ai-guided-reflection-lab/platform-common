"""SQLAlchemy models — minimal research-friendly schema."""

import uuid
from datetime import datetime, timezone

from sqlalchemy import (
    Column, String, Integer, Float, Boolean, Text, DateTime, ForeignKey, JSON,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from app.database import Base, PLATFORM_DB_SCHEMA, REFLECTIONS_DB_SCHEMA


def _uuid():
    return str(uuid.uuid4())


# ── Student ──────────────────────────────────────────────────────────────────
class LegacyStudent(Base):
    """Historical standalone identities; platform sessions use PlatformUser."""

    __tablename__ = "students_reflections_app"
    __table_args__ = {"schema": REFLECTIONS_DB_SCHEMA}

    id = Column(String, primary_key=True, default=_uuid)
    anonymized_id = Column(String, unique=True, nullable=False)

    conversations = relationship("Conversation", back_populates="legacy_student")


class PlatformUser(Base):
    __tablename__ = "users_platform"
    __table_args__ = {"schema": PLATFORM_DB_SCHEMA}

    id = Column(UUID(as_uuid=False), primary_key=True)
    username = Column(Text, nullable=False)
    display_name = Column(Text)
    email = Column(Text, nullable=False)

    reflection_conversations = relationship("Conversation", back_populates="platform_user")


class PlatformCourse(Base):
    __tablename__ = "courses_platform"
    __table_args__ = {"schema": PLATFORM_DB_SCHEMA}

    id = Column(UUID(as_uuid=False), primary_key=True)
    course_code = Column(Text, nullable=False)
    title = Column(Text, nullable=False)

    reflection_modules = relationship("Module", back_populates="course")
    reflection_conversations = relationship("Conversation", back_populates="course")


# ── Module ───────────────────────────────────────────────────────────────────
class Module(Base):
    __tablename__ = "modules_reflections_app"
    __table_args__ = {"schema": REFLECTIONS_DB_SCHEMA}

    id = Column(String, primary_key=True, default=_uuid)
    name = Column(String, nullable=False)
    module_type = Column(String, default="topic_based", server_default="topic_based")  # topic_based | milestone_based
    course_id = Column(
        UUID(as_uuid=False),
        ForeignKey(f"{PLATFORM_DB_SCHEMA}.courses_platform.id"),
        nullable=True,
    )

    config = relationship("ModuleConfig", back_populates="module", uselist=False)
    conversations = relationship("Conversation", back_populates="module")
    course = relationship("PlatformCourse", back_populates="reflection_modules")


# ── ModuleConfig ─────────────────────────────────────────────────────────────
class ModuleConfig(Base):
    __tablename__ = "module_configs_reflections_app"
    __table_args__ = {"schema": REFLECTIONS_DB_SCHEMA}

    id = Column(String, primary_key=True, default=_uuid)
    module_id = Column(
        String,
        ForeignKey(f"{REFLECTIONS_DB_SCHEMA}.modules_reflections_app.id"),
        unique=True,
        nullable=False,
    )

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
    __tablename__ = "conversations_reflections_app"
    __table_args__ = {"schema": REFLECTIONS_DB_SCHEMA}

    id = Column(String, primary_key=True, default=_uuid)
    student_id = Column(
        String,
        ForeignKey(f"{REFLECTIONS_DB_SCHEMA}.students_reflections_app.id"),
        nullable=True,
    )
    platform_user_id = Column(
        UUID(as_uuid=False),
        ForeignKey(f"{PLATFORM_DB_SCHEMA}.users_platform.id"),
        nullable=True,
    )
    course_id = Column(
        UUID(as_uuid=False),
        ForeignKey(f"{PLATFORM_DB_SCHEMA}.courses_platform.id"),
        nullable=True,
    )
    module_id = Column(
        String,
        ForeignKey(f"{REFLECTIONS_DB_SCHEMA}.modules_reflections_app.id"),
        nullable=False,
    )
    transcript = Column(Text, default="")
    duration = Column(Integer, default=0)  # seconds
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    legacy_student = relationship("LegacyStudent", back_populates="conversations")
    platform_user = relationship("PlatformUser", back_populates="reflection_conversations")
    course = relationship("PlatformCourse", back_populates="reflection_conversations")
    module = relationship("Module", back_populates="conversations")
    analytics = relationship("ReflectionAnalytics", back_populates="conversation", uselist=False)


# ── ReflectionAnalytics ─────────────────────────────────────────────────────
class ReflectionAnalytics(Base):
    __tablename__ = "reflection_analytics_reflections_app"
    __table_args__ = {"schema": REFLECTIONS_DB_SCHEMA}

    id = Column(String, primary_key=True, default=_uuid)
    conversation_id = Column(
        String,
        ForeignKey(f"{REFLECTIONS_DB_SCHEMA}.conversations_reflections_app.id"),
        unique=True,
        nullable=False,
    )

    topics_covered = Column(JSON, default=list)
    missing_topics = Column(JSON, default=list)
    misconceptions = Column(JSON, default=list)
    reflection_depth_score = Column(Float, default=0.0)
    confidence_level = Column(Integer, default=0)
    engagement_score = Column(Float, default=0.0)

    conversation = relationship("Conversation", back_populates="analytics")
