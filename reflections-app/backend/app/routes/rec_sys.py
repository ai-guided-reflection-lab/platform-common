"""Routes — Recommendation System (SCS and LLM-SCS)."""
from __future__ import annotations

import io

import pandas as pd
from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import ModuleConfig
from app.schemas import MilestoneReflectRequest, MilestoneReflectResponse
from app.services.llm import get_llm_provider
from app.services.rec_sys_service import run_llm_scs, run_scs

router = APIRouter(prefix="/api/rec-sys", tags=["rec-sys"])


def _read_csv(raw: bytes) -> pd.DataFrame:
    try:
        return pd.read_csv(io.StringIO(raw.decode("utf-8")))
    except UnicodeDecodeError:
        return pd.read_csv(io.BytesIO(raw), encoding="latin-1")


@router.post("/run")
async def run_rec_sys(
    mode: str = Form(...),
    historical_data: UploadFile = File(...),
    current_students: UploadFile = File(...),
):
    """
    Run the recommendation system in SCS or LLM-SCS mode.

    mode: "scs" | "llm-scs"
    historical_data: CSV with columns — name, challenge, solution
    current_students: CSV with columns — Full Name, Email Address, student's reflection
    """
    if mode not in ("scs", "llm-scs"):
        raise HTTPException(status_code=400, detail="mode must be 'scs' or 'llm-scs'")

    hist_bytes = await historical_data.read()
    curr_bytes = await current_students.read()

    try:
        hist_df = _read_csv(hist_bytes)
        curr_df = _read_csv(curr_bytes)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Failed to parse CSV: {exc}")

    missing_hist = {"name", "challenge", "solution"} - set(hist_df.columns)
    if missing_hist:
        raise HTTPException(
            status_code=400,
            detail=f"Historical data CSV missing columns: {missing_hist}. Required: name, challenge, solution",
        )

    missing_curr = {"Full Name", "Email Address", "student's reflection"} - set(curr_df.columns)
    if missing_curr:
        raise HTTPException(
            status_code=400,
            detail=f"Current students CSV missing columns: {missing_curr}. Required: Full Name, Email Address, student's reflection",
        )

    hist_df.dropna(subset=["name", "challenge", "solution"], inplace=True)
    curr_df.dropna(subset=["Full Name", "student's reflection"], inplace=True)

    if hist_df.empty:
        raise HTTPException(status_code=400, detail="Historical data CSV has no valid rows.")
    if curr_df.empty:
        raise HTTPException(status_code=400, detail="Current students CSV has no valid rows.")

    try:
        if mode == "scs":
            results = run_scs(hist_df, curr_df)
        else:
            results = run_llm_scs(hist_df, curr_df, get_llm_provider())
    except RuntimeError as exc:
        raise HTTPException(status_code=500, detail=str(exc))

    return {"results": results}


@router.post("/milestone", response_model=MilestoneReflectResponse)
def run_milestone(body: MilestoneReflectRequest, db: Session = Depends(get_db)):
    """
    Run SCS for a single student reflection against a milestone module's historical data.
    """
    cfg = db.query(ModuleConfig).filter(ModuleConfig.module_id == body.module_id).first()
    if not cfg:
        raise HTTPException(404, "Module config not found")
    if not cfg.milestone_historical_data:
        raise HTTPException(400, "No historical data uploaded for this module")

    try:
        hist_df = pd.read_csv(io.StringIO(cfg.milestone_historical_data))
    except Exception as exc:
        raise HTTPException(500, f"Failed to parse stored historical data: {exc}")

    hist_df.dropna(subset=["name", "challenge", "solution"], inplace=True)
    if hist_df.empty:
        raise HTTPException(400, "Historical data has no valid rows")

    curr_df = pd.DataFrame([{
        "Full Name": body.student_name or "Student",
        "Email Address": body.student_email,
        "student's reflection": body.reflection,
    }])

    try:
        results = run_scs(hist_df, curr_df)
    except RuntimeError as exc:
        raise HTTPException(500, str(exc))

    return MilestoneReflectResponse(similar=results[0]["similar"] if results else [])
