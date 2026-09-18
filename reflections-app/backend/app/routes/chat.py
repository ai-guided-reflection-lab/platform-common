"""Routes — Reflection Chat (start / message / end)."""

from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Student
from app.schemas import (
    ChatStartRequest, ChatStartResponse,
    ChatMessageRequest, ChatMessageResponse,
    ChatEndRequest, ChatEndResponse,
)
from app.agents import runner

router = APIRouter(prefix="/api/chat", tags=["chat"])


def _generate_anonymized_id() -> str:
    return f"anon-{uuid4().hex[:12]}"


@router.post("/start", response_model=ChatStartResponse)
def start_chat(body: ChatStartRequest, db: Session = Depends(get_db)):
    try:
        student = db.query(Student).filter(Student.id == body.student_id).first()
        if not student:
            student = Student(id=body.student_id, anonymized_id=_generate_anonymized_id())
            db.add(student)
            try:
                db.commit()
            except IntegrityError:
                db.rollback()
                student = db.query(Student).filter(Student.id == body.student_id).first()
                if not student:
                    student = Student(id=body.student_id, anonymized_id=_generate_anonymized_id())
                    db.add(student)
                    db.commit()

        session_id = str(uuid4())
        result = runner.invoke_start(
            session_id=session_id,
            student_id=body.student_id,
            module_id=body.module_id,
            db=db,
        )
        return ChatStartResponse(
            session_id=session_id,
            greeting=result["greeting"],
            total_questions=result["total_questions"],
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(500, f"Failed to start chat session: {str(e)}")


@router.post("/message", response_model=ChatMessageResponse)
def send_message(body: ChatMessageRequest):
    try:
        result = runner.invoke_message(
            session_id=body.session_id,
            user_message=body.message,
        )
    except Exception as e:
        err = str(e)
        if "not found" in err.lower() or "no checkpoint" in err.lower():
            raise HTTPException(404, "Session not found")
        raise HTTPException(500, f"Failed to process message: {err}")

    return ChatMessageResponse(
        reply=result["current_reply"],
        question_index=result["question_idx"],
        total_questions=result["total_questions"],
        is_bonus_phase=result["is_bonus_phase"],
    )


@router.post("/end", response_model=ChatEndResponse)
def end_chat(body: ChatEndRequest, db: Session = Depends(get_db)):
    try:
        result = runner.invoke_end(session_id=body.session_id, db=db)
    except Exception as e:
        err = str(e)
        if "not found" in err.lower() or "no checkpoint" in err.lower():
            raise HTTPException(404, "Session not found")
        raise HTTPException(500, f"Failed to end chat session: {err}")

    return ChatEndResponse(
        conversation_id=result["conversation_id"],
        evaluation=result["evaluation"],
    )
