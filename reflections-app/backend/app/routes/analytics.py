"""Routes — Analytics dashboard."""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Conversation, LegacyStudent, PlatformUser, ReflectionAnalytics
from app.schemas import AnalyticsRow

router = APIRouter(prefix="/api/analytics", tags=["analytics"])


@router.get("/{module_id}", response_model=list[AnalyticsRow])
def get_analytics(module_id: str, db: Session = Depends(get_db)):
    rows = (
        db.query(ReflectionAnalytics, Conversation, LegacyStudent, PlatformUser)
        .join(Conversation, ReflectionAnalytics.conversation_id == Conversation.id)
        .outerjoin(LegacyStudent, Conversation.student_id == LegacyStudent.id)
        .outerjoin(PlatformUser, Conversation.platform_user_id == PlatformUser.id)
        .filter(Conversation.module_id == module_id)
        .all()
    )
    results = []
    for analytics, convo, legacy_student, platform_user in rows:
        student_label = (
            platform_user.display_name or platform_user.username
            if platform_user
            else legacy_student.anonymized_id
        )
        results.append(
            AnalyticsRow(
                conversation_id=convo.id,
                student_anonymized_id=student_label,
                reflection_depth_score=analytics.reflection_depth_score,
                confidence_level=analytics.confidence_level,
                engagement_score=analytics.engagement_score,
                misconceptions=analytics.misconceptions or [],
                missing_topics=analytics.missing_topics or [],
                created_at=convo.created_at.isoformat() if convo.created_at else "",
            )
        )
    return results
