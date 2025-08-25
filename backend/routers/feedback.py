from __future__ import annotations
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from typing import Optional
from backend.memory.state_store import save_feedback, get_last_proposal_row

router = APIRouter()

class FeedbackRequest(BaseModel):
    session_id: str = Field(..., min_length=1)
    accepted: bool
    score: Optional[int] = Field(None, ge=1, le=5)
    notes: Optional[str] = None

class FeedbackResponse(BaseModel):
    proposal_id: int
    feedback_id: int
    message: str

@router.post("/feedback", response_model=FeedbackResponse)
def register_feedback(req: FeedbackRequest):
    last = get_last_proposal_row(req.session_id)
    if not last:
        raise HTTPException(400, detail="No hay propuesta previa en esta sesión.")
    fid = save_feedback(req.session_id, req.accepted, req.score, req.notes)
    if not fid:
        raise HTTPException(500, detail="No se pudo guardar feedback.")
    return FeedbackResponse(
        proposal_id=last.id,
        feedback_id=fid,
        message="Feedback registrado. Se usará para reentrenar el modelo."
    )
