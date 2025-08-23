# backend/routers/projects.py
from fastapi import APIRouter
from pydantic import BaseModel, Field
from typing import List, Dict, Any

from backend.memory.conversation import save_message
from backend.engine.planner import generate_proposal
from backend.engine.context import set_last_proposal

router = APIRouter()

class ProposalRequest(BaseModel):
    session_id: str = Field(..., min_length=1)
    requirements: str = Field(..., min_length=3)

class ProposalResponse(BaseModel):
    methodology: str
    team: List[Dict[str, Any]]
    phases: List[Dict[str, Any]]
    budget: Dict[str, Any]           # <- admite 'assumptions' anidado
    risks: List[str]
    explanation: List[str]           # <- lo generamos a partir de p['explanations']

@router.post("/proposal", response_model=ProposalResponse)
def proposal(req: ProposalRequest):
    # Log del mensaje del usuario
    save_message(req.session_id, "user", f"[REQ] {req.requirements}")

    # Generar propuesta
    p = generate_proposal(req.requirements)

    # Guardar para explicaciones posteriores desde brain.py
    set_last_proposal(req.session_id, p, req.requirements)

    # Log breve del asistente
    save_message(
        req.session_id,
        "assistant",
        f"[PROPUESTA {p['methodology']}] Presupuesto {p['budget']['total_eur']} €"
    )

    # Convertimos dict de 'explanations' en lista de textos legibles
    expl_list: List[str] = []
    ex = p.get("explanations") or {}
    if isinstance(ex, dict):
        if ex.get("methodology"):
            expl_list.append(str(ex["methodology"]))
        if ex.get("effort"):
            expl_list.append(str(ex["effort"]))
        if ex.get("notes"):
            expl_list.append(str(ex["notes"]))

    # Construimos la respuesta ajustada al modelo
    return {
        "methodology": p["methodology"],
        "team": p["team"],
        "phases": p["phases"],
        "budget": p["budget"],    # incluye assumptions; el modelo lo admite
        "risks": p["risks"],
        "explanation": expl_list or ["Generada automáticamente en base a los requisitos."],
    }

