# backend/routers/projects.py
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field
from typing import List, Dict, Any, Optional

from backend.memory.conversation import save_message
from backend.engine.planner import generate_proposal
from backend.engine.context import set_last_proposal
from backend.core.config import settings
import jwt

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


@router.get("/{proposal_id}/report.pdf")
def proposal_report_pdf(proposal_id: int, request: Request):
    """Genera un PDF on‑the‑fly a partir de una propuesta almacenada (ProposalLog).
    Construimos una transcripción mínima con un bloque final de propuesta.
    """
    from backend.memory.state_store import SessionLocal, ProposalLog
    from backend.app import render_chat_report_inline
    from fastapi.responses import StreamingResponse
    from io import BytesIO
    from datetime import datetime

    with SessionLocal() as db:
        row = db.query(ProposalLog).filter(ProposalLog.id == proposal_id).first()
        if not row:
            raise HTTPException(status_code=404, detail="Propuesta no encontrada")
    # Log de visualización si viene Authorization con JWT válido
    try:
        token = None
        # 1) Authorization header
        auth = request.headers.get("Authorization") or ""
        if auth.lower().startswith("bearer "):
            token = auth.split()[1]
        # 2) token en query param como fallback (para <a href> sin cabeceras)
        if not token:
            token = request.query_params.get("token")
        if token:
            data = jwt.decode(token, settings.APP_NAME, algorithms=["HS256"])  # type: ignore
            user_id = int(data.get("user_id"))
            if user_id:
                from backend.memory.state_store import log_proposal_view
                log_proposal_view(user_id, proposal_id)
    except Exception:
        pass

    p = row.proposal_json or {}
    # Componer un bloque de texto similar al que muestra el asistente al final
    def fmt_team(team_list):
        try:
            return ", ".join([f"{t['role']} x{t.get('count', t.get('fte', 1))}" for t in (team_list or [])])
        except Exception:
            return ""

    def fmt_phases(phs):
        try:
            return " → ".join([f"{x.get('name','?')} ({x.get('weeks','?')} semanas)" for x in (phs or [])])
        except Exception:
            return ""

    budget = p.get("budget", {})
    budget_line = None
    try:
        total = budget.get("total_eur")
        cont  = budget.get("contingency_pct")
        if total is not None:
            budget_line = f"{float(total):,.2f} €".replace(",","X").replace(".",",").replace("X",".")
            if cont is not None: budget_line += f" (incluye {cont}% contingencia)"
    except Exception:
        pass

    lines = []
    if p.get("methodology"): lines.append(f"Metodología: {p['methodology']}")
    tm = fmt_team(p.get("team"))
    if tm: lines.append(f"Equipo: {tm}")
    ph = fmt_phases(p.get("phases"))
    if ph: lines.append(f"Fases: {ph}")
    if budget_line: lines.append(f"Presupuesto: {budget_line}")
    rs = p.get("risks") or []
    if isinstance(rs, list) and rs:
        lines.append("Riesgos: " + "; ".join([str(x) for x in rs[:8]]))

    block = "\n".join(["Propuesta final:"] + [f"■ {x}" for x in lines])
    messages = [
        {"role": "user", "content": f"[REQ] {row.requirements}", "ts": row.created_at.isoformat()},
        {"role": "assistant", "content": block, "ts": row.created_at.isoformat()},
    ]

    pdf_bytes = render_chat_report_inline(
        messages,
        title=f"Informe del proyecto · {p.get('methodology') or 'Propuesta'}",
        report_meta={
            "project": (p.get("title") or "Proyecto inspirado"),
            "client": "—",
            "author": "Asistente",
            "session_id": row.session_id,
            "subtitle": "Propuesta y decisiones derivadas",
        },
        report_options={
            "include_cover": True, "include_transcript": True,
            "include_analysis": True, "include_final_proposal": True,
            "analysis_depth": "standard", "font_name": "Helvetica"
        }
    )

    fname = f"propuesta_{proposal_id}_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.pdf"
    return StreamingResponse(BytesIO(pdf_bytes), media_type="application/pdf",
                              headers={"Content-Disposition": f'attachment; filename="{fname}"'})

