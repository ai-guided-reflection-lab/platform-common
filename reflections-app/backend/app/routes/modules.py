"""Routes — Module CRUD."""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Module
from app.schemas import ModuleCreate, ModuleOut

router = APIRouter(prefix="/api/modules", tags=["modules"])


@router.get("", response_model=list[ModuleOut])
def list_modules(db: Session = Depends(get_db)):
    return db.query(Module).all()


@router.post("", response_model=ModuleOut, status_code=201)
def create_module(body: ModuleCreate, db: Session = Depends(get_db)):
    module = Module(name=body.name, module_type=body.module_type)
    db.add(module)
    db.commit()
    db.refresh(module)
    return module


@router.get("/{module_id}", response_model=ModuleOut)
def get_module(module_id: str, db: Session = Depends(get_db)):
    module = db.query(Module).filter(Module.id == module_id).first()
    if not module:
        raise HTTPException(404, "Module not found")
    return module
