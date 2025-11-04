# backend/routers/projects.py
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field
import re
from typing import List, Dict, Any, Optional

from backend.memory.conversation import save_message
from backend.engine.planner import generate_proposal
from backend.engine.context import set_last_proposal
from backend.core.config import settings
import jwt
from typing import Tuple
from backend.engine.brain import _pretty_proposal

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
# backend/routers/projects.py
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field
import re
from typing import List, Dict, Any, Optional

from backend.memory.conversation import save_message
from backend.engine.planner import generate_proposal
from backend.engine.context import set_last_proposal
from backend.core.config import settings
import jwt
from typing import Tuple
from backend.engine.brain import _pretty_proposal

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


# ---------------- Recomendaciones de proyectos similares ----------------
class RecommendIn(BaseModel):
    query: str = Field(..., min_length=3, description="Descripción del proyecto que quieres hacer")
    top_k: int = Field(5, ge=1, le=10)

class RecommendedItem(BaseModel):
    id: int
    requirements: str
    methodology: Optional[str] = None
    budget: Optional[Dict[str, Any]] = None
    team: Optional[List[Dict[str, Any]]] = None
    phases: Optional[List[Dict[str, Any]]] = None
    similarity: float
    pdf_url: str

@router.post("/recommend", response_model=List[RecommendedItem])
def recommend_similar(req: RecommendIn):
    # Primero: intentar con el índice TF‑IDF/NNeighbors.
    try:
        from backend.retrieval.similarity import get_retriever
        retr = get_retriever(); retr.refresh()
        items = retr.retrieve(req.query, top_k=req.top_k)
    except Exception:
        items = []

    # Fallback: búsqueda por palabras clave si no hay sklearn o índice vacío
    if not items:
        items = _keyword_recommend(req.query, top_k=req.top_k)

    out: List[Dict[str, Any]] = []
    for m in items:
        pid = int(m.get("id"))
        out.append({
            "id": pid,
            "requirements": m.get("requirements") or "",
            "methodology": m.get("methodology"),
            "budget": m.get("budget"),
            "team": m.get("team"),
            "phases": m.get("phases"),
            "similarity": float(m.get("similarity", 0.0)),
            "pdf_url": f"/projects/{pid}/report.pdf",
        })
    return out

def _keyword_recommend(query: str, top_k: int = 5):
    from sqlalchemy import or_
    from backend.memory.state_store import SessionLocal, ProposalLog
    toks = [t.strip() for t in query.lower().split() if len(t.strip()) >= 3][:6]
    if not toks:
        return []
    with SessionLocal() as db:
        conds = [ProposalLog.requirements.ilike(f"%{t}%") for t in toks]
        rows = db.query(ProposalLog).filter(or_(*conds)).order_by(ProposalLog.created_at.desc()).limit(20).all()
        res = []
        for r in rows:
            text = (r.requirements or '').lower()
            hit = sum(1 for t in toks if t in text)
            score = float(hit) / max(1, len(toks))
            res.append({
                "id": r.id,
                "requirements": r.requirements,
                "methodology": (r.proposal_json or {}).get("methodology"),
                "budget": (r.proposal_json or {}).get("budget"),
                "team": (r.proposal_json or {}).get("team"),
                "phases": (r.proposal_json or {}).get("phases"),
                "similarity": score,
            })
        # ordenar por score y cortar
        res.sort(key=lambda x: x.get("similarity", 0.0), reverse=True)
        return res[:top_k]


# ----------------- Endpoints para seguimiento (lista, detalle y checklist por fase) -----------------
def _phase_checklist_from_method(method: Optional[str], phase_name: str) -> List[str]:
    """Genera una checklist básica para una fase concreta combinando reglas por nombre
    de fase y prácticas de la metodología si están disponibles.
    """
    try:
        from backend.knowledge.methodologies import METHODOLOGIES
    except Exception:
        METHODOLOGIES = {}

    m = (METHODOLOGIES.get(method) or {}) if method else {}
    practicas = m.get("practicas", []) if isinstance(m, dict) else []
        # Guardar para explicaciones posteriores desde brain.py

    name = (phase_name or "").lower()
    tasks: List[str] = []

    # Tareas genéricas por tipo de fase
    if any(k in name for k in ("discover", "descub", "incep", "incepción", "inception")):
        tasks += [
            "Reunir stakeholders clave y validar objetivos",
            "Mapear requisitos y necesidades de usuario (user journeys)",
            "Definir criterios de aceptación / Definition of Ready",
            "Priorizar backlog inicial y definir MVP",
            "Detectar riesgos técnicos y dependencias (spikes si es necesario)",
        ]
    elif any(k in name for k in ("implement", "implementación", "iter", "sprint", "desarrollo")):
        tasks += [
            "Configurar repositorios, ramas y CI/CD",
            "Implementar features por prioridad con PR y code review",
            "Añadir pruebas unitarias e integración",
            "Revisar performance en piezas críticas",
        ]
    elif any(k in name for k in ("qa", "hardening", "pruebas", "estabiliz", "stabiliz")):
        tasks += [
            "Ejecutar pruebas de integración y end-to-end",
            "Pruebas de aceptación por parte del product owner",
            "Revisión de seguridad y remedio de vulnerabilidades",
            "Pruebas de carga/performance si procede",
        ]
    elif any(k in name for k in ("desplieg", "release", "puesta", "handover", "producción")):
        tasks += [
            "Preparar release notes y plan de despliegue",
            "Ejecutar checklist pre-despliegue (migraciones, backups)",
            "Desplegar a producción y monitorear métricas básicas",
            "Handover a equipo de operación y capacitación a usuarios",
        ]
    elif any(k in name for k in ("observab", "monitor", "ops", "oper")):
        tasks += [
            "Configurar logging, métricas y alertas",
            "Definir runbook y responsable de incidentes",
        ]
    else:
        # fallback genérico
        tasks += [
            "Revisar objetivos de la fase",
            "Confirmar entregables y criterios de aceptación",
        ]

    # Añadir prácticas recomendadas de la metodología como acciones sugeridas
    for p in practicas:
        if isinstance(p, str) and p not in tasks:
            tasks.append(f"Aplicar práctica: {p}")

    return tasks


@router.get("/list")
def list_proposals(session_id: str):
    """Lista propuestas guardadas para una sesión (cliente)."""
    from backend.memory.state_store import SessionLocal, ProposalLog
    with SessionLocal() as db:
        rows = db.query(ProposalLog).filter(ProposalLog.session_id == session_id).order_by(ProposalLog.created_at.desc()).all()
        out = []
        for r in rows:
            out.append({
                "id": int(r.id),
                "requirements": r.requirements,
                "created_at": r.created_at.isoformat(),
                "methodology": (r.proposal_json or {}).get("methodology"),
            })
        return out


@router.get("/from_chat/{chat_id}")
def list_proposals_from_chat(chat_id: int):
    """Return only assistant blocks from a saved chat that look like final
    proposals. The detection is strict: the block must start (after optional
    emoji/punctuation) with 'Metodología' and contain 'Equipo' or 'Fases' or
    'Presupuest' (presupuesto/€). If a ProposalLog matches the block (by
    containing a snippet) we return the persisted proposal; otherwise we return
    an inline proposal object so the frontend can show it.
    """
    from backend.memory.state_store import SessionLocal, ProposalLog, SavedChat
    import json as _json
    import re as _re

    def starts_with_metodologia(text: str) -> bool:
        if not text:
            return False
        s = text.strip()
        # remove leading non-letter chars (emojis/punct)
        lead = _re.sub(r'^[^\w\dáéíóúÁÉÍÓÚüÜ]+', '', s, flags=_re.UNICODE)
        return lead.lower().startswith('metodolog') or lead.lower().startswith('metodología') or lead.lower().startswith('metodologia')

    def is_proposal_block(text: str) -> bool:
        if not text or len(text.strip()) < 60:
            return False
        l = text.lower()
        if not starts_with_metodologia(text):
            return False
        if ('equipo' in l) or ('fases' in l) or ('presupuest' in l) or ('€' in text):
            return True
        return False

    with SessionLocal() as db:
        sc = db.query(SavedChat).filter(SavedChat.id == chat_id).first()
        if not sc:
            raise HTTPException(status_code=404, detail="Chat guardado no encontrado")

        raw = sc.content or ''
        try:
            parsed = _json.loads(raw)
        except Exception:
            parsed = None

        assistant_blocks = []
        if isinstance(parsed, list):
            for m in parsed:
                try:
                    if isinstance(m, dict) and (m.get('role') in ('assistant', 'system')) and isinstance(m.get('content'), str):
                        txt = m.get('content')
                        if is_proposal_block(txt):
                            ts = m.get('ts') or m.get('created_at')
                            assistant_blocks.append((txt, ts))
                except Exception:
                    continue

        out = []
        if assistant_blocks:
            cand_rows = db.query(ProposalLog).order_by(ProposalLog.created_at.desc()).limit(500).all()
            for (txt, ts) in assistant_blocks:
                snippet = txt.lower().strip()[:160]
                matched = False
                for r in cand_rows:
                    try:
                        pj = _json.dumps(r.proposal_json or {})
                        if snippet and snippet in pj.lower():
                            if not any(x.get('id') == int(r.id) for x in out):
                                out.append({
                                    'id': int(r.id),
                                    'requirements': r.requirements,
                                    'created_at': r.created_at.isoformat(),
                                    'methodology': (r.proposal_json or {}).get('methodology'),
                                })
                            matched = True
                            break
                    except Exception:
                        continue
                if not matched:
                    out.append({
                        'id': None,
                        'requirements': txt,
                        'created_at': (ts or sc.created_at.isoformat()),
                        'methodology': None,
                        'inline': True,
                    })

        return out


@router.post("/from_chat/{chat_id}/to_proposal")
def convert_chat_block_to_proposal(chat_id: int, payload: Dict[str, Any]):
    """Convierte un bloque detectado en el SavedChat en un ProposalLog persistente.
    Body: { "content": "texto del asistente", "requirements": optional }
    Devuelve { proposal_id, session_id, created_at }
    """
    from backend.memory.state_store import SessionLocal, SavedChat, save_proposal
    from datetime import datetime
    content = str(payload.get("content" or "")).strip()
    requirements = payload.get("requirements") or (content[:100] if content else "Propuesta importada desde chat")
    if not content:
        raise HTTPException(status_code=400, detail="Content requerido")

    with SessionLocal() as db:
        sc = db.query(SavedChat).filter(SavedChat.id == chat_id).first()
        if not sc:
            raise HTTPException(status_code=404, detail="Chat guardado no encontrado")

    # Construir un proposal_json mínimo a partir del bloque de asistente
    proposal_json = {
        "generated_from_chat": True,
        "assistant_block": content,
        "source_chat_id": int(chat_id),
    }

    # Generar un session_id único para esta propuesta importada
    sid = f"restored_chat_{chat_id}_{int(datetime.utcnow().timestamp())}"
    # Guardar la propuesta
    try:
        pid = save_proposal(sid, requirements, proposal_json)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"No se pudo crear la propuesta: {e}")

    return {"proposal_id": pid, "session_id": sid, "created_at": datetime.utcnow().isoformat()}
