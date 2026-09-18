"""Assignment-bound internal endpoints, protected by the service-token middleware."""
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Module, ModuleConfig, Student
from app.agents import runner

router = APIRouter(prefix="/internal/platform", tags=["platform-internal"])


class ModuleInput(BaseModel):
    name: str
    config: dict


class StartInput(BaseModel):
    session_id: UUID
    student_id: UUID
    module_id: UUID


class MessageInput(BaseModel):
    session_id: UUID
    request_id: UUID
    message: str


class EndInput(BaseModel):
    session_id: UUID


@router.put("/modules/{module_id}")
def prepare_module(module_id: UUID, body: ModuleInput, db: Session = Depends(get_db)):
    module_id = str(module_id)
    cfg = dict(body.config)
    module_type = cfg.pop("module_type")
    cfg["milestone_historical_data"] = cfg.pop("historical_data", "")
    module = db.get(Module, module_id)
    if module:
        # Idempotent publishing: this assignment's private module is immutable.
        stored = db.query(ModuleConfig).filter_by(module_id=module_id).one()
        if module.module_type != module_type or any(getattr(stored, k) != v for k, v in cfg.items()):
            raise HTTPException(409, "This module is already published with different settings.")
        return {"id": module.id}
    module = Module(id=module_id, name=body.name, module_type=module_type)
    db.add(module)
    db.flush()
    db.add(ModuleConfig(module_id=module_id, **cfg))
    db.commit()
    return {"id": module.id}


@router.post("/start")
def start(body: StartInput, db: Session = Depends(get_db)):
    sid = str(body.session_id)
    state = runner.platform_state(sid)
    if state:
        if state.get("student_id") != str(body.student_id) or state.get("module_id") != str(body.module_id):
            raise HTTPException(409, "Session identity mismatch.")
        state = runner.platform_resume_start(sid, db)
    else:
        student_id = str(body.student_id)
        if not db.get(Student, student_id):
            db.add(Student(id=student_id, anonymized_id=f"platform-{student_id}"))
            db.commit()
        state = runner.invoke_start(sid, str(body.student_id), str(body.module_id), db)
    return {"greeting": state["greeting"], "total_questions": state["total_questions"]}


@router.post("/message")
def message(body: MessageInput):
    state = runner.platform_message(str(body.session_id), body.message, str(body.request_id))
    return {"reply": state["current_reply"], "question_index": state["question_idx"],
            "total_questions": state["total_questions"], "is_bonus_phase": state["is_bonus_phase"]}


@router.post("/end")
def end(body: EndInput, db: Session = Depends(get_db)):
    state = runner.platform_end(str(body.session_id), db)
    return {"conversation_id": state["conversation_id"], "evaluation": state["evaluation"]}
