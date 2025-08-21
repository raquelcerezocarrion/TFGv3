from fastapi import APIRouter
from pydantic import BaseModel, Field
from typing import List, Dict, Any
from backend.memory.conversation import save_message

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

    text = req.requirements.lower()
    if any(k in text for k in ["tiempo real", "flujos continuos", "operación continua"]):
        methodology = "Kanban"
    elif any(k in text for k in ["requisitos cambiantes", "incertidumbre alta"]):
        methodology = "Scrum"
    else:
        methodology = "Scrumban"

    team = [
        {"role": "PM", "count": 1, "skills": ["gestión", "stakeholders", "riesgos"]},
        {"role": "Tech Lead", "count": 1, "skills": ["arquitectura", "devops"]},
        {"role": "Backend Dev", "count": 2, "skills": ["Python", "FastAPI"]},
        {"role": "Frontend Dev", "count": 1, "skills": ["React", "Vite", "Tailwind"]},
        {"role": "QA", "count": 1, "skills": ["pruebas", "automatización"]},
        {"role": "UX/UI", "count": 0.5, "skills": ["figma", "ux research"]},
    ]

    phases = [
        {"name": "Descubrimiento", "weeks": 1, "deliverables": ["Alcance", "Riesgos", "Plan"]},
        {"name": "Arquitectura y setup", "weeks": 1, "deliverables": ["CI/CD", "Infra básica"]},
        {"name": "Desarrollo iterativo", "weeks": 6, "deliverables": ["MVP", "Iteraciones"]},
        {"name": "QA & hardening", "weeks": 2, "deliverables": ["Pruebas", "Performance"]},
        {"name": "Despliegue & handover", "weeks": 1, "deliverables": ["Manual", "Formación"]},
    ]

    budget = {
        "labor_estimate_eur": 48000.0,
        "contingency_10pct": 4800.0,
        "total_eur": 52800.0
    }

    risks = [
        "Cambios de alcance sin control de versiones",
        "Dependencias externas (APIs/pagos) con latencias",
        "Falta de datos reales para pruebas de carga",
    ]

    explanation = [
        f"Metodología '{methodology}' por palabras clave detectadas.",
        "Equipo equilibrado para time-to-market vs coste.",
        "Presupuesto orientativo con 10% de contingencia.",
        "En Parte 2: IA entrenada + optimización y explicabilidad real.",
    ]

    save_message(req.session_id, role="assistant",
                 content=f"[PROPUESTA {methodology}] Presupuesto {budget['total_eur']} €")

    return ProposalResponse(
        methodology=methodology,
        team=team,
        phases=phases,
        budget=budget,
        risks=risks,
        explanation=explanation,
    )
