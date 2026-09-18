"""Routes — Analytics dashboard."""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Conversation, ReflectionAnalytics, Student
from app.schemas import AnalyticsRow

router = APIRouter(prefix="/api/analytics", tags=["analytics"])


@router.get("/{module_id}", response_model=list[AnalyticsRow])
def get_analytics(module_id: str, db: Session = Depends(get_db)):
    rows = (
        db.query(ReflectionAnalytics, Conversation, Student)
        .join(Conversation, ReflectionAnalytics.conversation_id == Conversation.id)
        .join(Student, Conversation.student_id == Student.id)
        .filter(Conversation.module_id == module_id)
        .all()
    )
    results = []
    for analytics, convo, student in rows:
        results.append(
            AnalyticsRow(
                conversation_id=convo.id,
                student_anonymized_id=student.anonymized_id,
                reflection_depth_score=analytics.reflection_depth_score,
                confidence_level=analytics.confidence_level,
                engagement_score=analytics.engagement_score,
                misconceptions=analytics.misconceptions or [],
                missing_topics=analytics.missing_topics or [],
                created_at=convo.created_at.isoformat() if convo.created_at else "",
            )
        )
    return results
