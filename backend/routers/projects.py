# backend/routers/projects.py
from fastapi import APIRouter
from pydantic import BaseModel, Field
from typing import List, Dict, Any
from backend.memory.conversation import save_message
from backend.engine.planner import generate_proposal
from backend.engine.context import set_last_proposal   # ← NUEVO

router = APIRouter()

class ProposalRequest(BaseModel):
    session_id: str = Field(..., min_length=1)
    requirements: str = Field(..., min_length=3)

class ProposalResponse(BaseModel):
    methodology: str
    team: List[Dict[str, Any]]
    phases: List[Dict[str, Any]]
    budget: Dict[str, float]
    risks: List[str]
    explanation: List[str]

@router.post("/proposal", response_model=ProposalResponse)
def proposal(req: ProposalRequest):
    save_message(req.session_id, role="user", content=f"[REQ] {req.requirements}")
    p = generate_proposal(req.requirements)

    # Guarda para explicaciones posteriores
    set_last_proposal(req.session_id, p, req.requirements)

    save_message(
        req.session_id,
        role="assistant",
        content=f"[PROPUESTA {p['methodology']}] Presupuesto {p['budget']['total_eur']} €"
    )
    return ProposalResponse(**p)
