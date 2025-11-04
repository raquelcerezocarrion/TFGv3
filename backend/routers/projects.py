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
    """Intento razonable de obtener propuestas relacionadas a un chat guardado.
    Extrae texto del `SavedChat` y busca ProposalLog cuya requirements coincidan
    parcialmente. Es un fallback para cuando abrimos un chat guardado.
    """
    from backend.memory.state_store import SessionLocal, ProposalLog, SavedChat
    with SessionLocal() as db:
        sc = db.query(SavedChat).filter(SavedChat.id == chat_id).first()
        if not sc:
            raise HTTPException(status_code=404, detail="Chat guardado no encontrado")
        raw = sc.content or ""
        # Intentar parsear JSON de mensajes; si es array, extraer textos assistant y user
        text_blob = raw
        try:
            import json as _json
            parsed = _json.loads(raw)
            if isinstance(parsed, list):
                parts = []
                for m in parsed:
                    if isinstance(m, dict) and m.get('content'):
                        parts.append(str(m.get('content')))
                text_blob = "\n".join(parts)
        except Exception:
            pass

        # Tokenizar por frases/palabras largas para buscar coincidencias
        toks = [t.strip() for t in re.split(r"\W+", text_blob.lower()) if len(t.strip()) >= 5][:8]
        out = []
        if toks:
            try:
                from sqlalchemy import or_
                conds = [ProposalLog.requirements.ilike(f"%{t}%") for t in toks]
                rows = db.query(ProposalLog).filter(or_(*conds)).order_by(ProposalLog.created_at.desc()).limit(20).all()
                for r in rows:
                    out.append({
                        "id": int(r.id),
                        "requirements": r.requirements,
                        "created_at": r.created_at.isoformat(),
                        "methodology": (r.proposal_json or {}).get("methodology"),
                    })
            except Exception:
                # ignore SQL issues and fallback to python-side heuristics below
                out = []

        # Si no encontramos coincidencias por tokens, intentamos heurística más robusta:
        # 1) parsear mensajes guardados y buscar bloques de assistant que parezcan la propuesta final
        if not out:
            try:
                import json as _json
                parsed = _json.loads(raw)
                assistant_texts = []
                if isinstance(parsed, list):
                    for m in parsed:
                        try:
                            if isinstance(m, dict) and (m.get('role') == 'assistant' or m.get('role') == 'system') and isinstance(m.get('content'), str):
                                txt = m.get('content')
                                if len(txt) > 40:
                                    assistant_texts.append(txt)
                        except Exception:
                            continue
                # buscar cada texto en proposal_json serializado
                if assistant_texts:
                    cand_rows = db.query(ProposalLog).order_by(ProposalLog.created_at.desc()).limit(200).all()
                    for at in assistant_texts:
                        at_norm = at.lower().strip()
                        for r in cand_rows:
                            try:
                                pj = _json.dumps(r.proposal_json or {})
                                if at_norm[:80] in pj.lower():
                                    out.append({
                                        "id": int(r.id),
                                        "requirements": r.requirements,
                                        "created_at": r.created_at.isoformat(),
                                        "methodology": (r.proposal_json or {}).get("methodology"),
                                    })
                            except Exception:
                                continue
                        if out:
                            break
            except Exception:
                pass

        # Fallback final: si aún no hay resultados, devolver las últimas 5 propuestas como ayuda UX
        if not out:
            rows = db.query(ProposalLog).order_by(ProposalLog.created_at.desc()).limit(5).all()
            for r in rows:
                out.append({
                    "id": int(r.id),
                    "requirements": r.requirements,
                    "created_at": r.created_at.isoformat(),
                    "methodology": (r.proposal_json or {}).get("methodology"),
                })

        return out


    @router.get("/{proposal_id}")
    def get_proposal(proposal_id: int):
        """Recupera la propuesta JSON completa por id."""
        from backend.memory.state_store import SessionLocal, ProposalLog
        with SessionLocal() as db:
            row = db.query(ProposalLog).filter(ProposalLog.id == proposal_id).first()
            if not row:
                raise HTTPException(status_code=404, detail="Propuesta no encontrada")
            return row.proposal_json or {}


@router.get("/{proposal_id}/open_session")
def open_proposal_session(proposal_id: int):
    """Prepara una sesión de chat asociada a una propuesta guardada.
    - Carga la propuesta en la memoria del 'brain' para que las siguientes
    llamadas al chat (WebSocket/HTTP) usen ese contexto.
    - Devuelve el `session_id` asociado a la propuesta y un bloque resumen
    de la propuesta listo para mostrar como mensaje inicial del asistente.
    """
    from backend.memory.state_store import SessionLocal, ProposalLog
    from backend.engine.context import set_last_proposal
    with SessionLocal() as db:
        row = db.query(ProposalLog).filter(ProposalLog.id == proposal_id).first()
        if not row:
            raise HTTPException(status_code=404, detail="Propuesta no encontrada")
        p = row.proposal_json or {}
        sid = row.session_id

    # Setear en el contexto en memoria para que generate_reply use esta propuesta
    try:
        set_last_proposal(sid, p, row.requirements)
        # Log minimal del asistente
        try:
            save_message(sid, "assistant", f"[PROPUESTA CARGADA] {p.get('methodology','')} — {p.get('budget',{}).get('total_eur','?')} €")
        except Exception:
            pass
    except Exception:
        # No fallar la llamada por problemas de memoria en proceso
        pass

    # Construir un resumen legible usando util del brain
    try:
        pretty = _pretty_proposal(p)
    except Exception:
        pretty = "Propuesta cargada. Pide 'fases', 'presupuesto' o pregunta sobre la fase concreta."

    return {"session_id": sid, "assistant_summary": pretty}


    @router.get("/{proposal_id}/phases")
    def get_proposal_phases(proposal_id: int):
        """Devuelve las fases de la propuesta y una checklist sugerida por fase."""
        from backend.memory.state_store import SessionLocal, ProposalLog
        with SessionLocal() as db:
            row = db.query(ProposalLog).filter(ProposalLog.id == proposal_id).first()
            if not row:
                raise HTTPException(status_code=404, detail="Propuesta no encontrada")
            p = row.proposal_json or {}
            method = p.get("methodology")
            phases = p.get("phases") or []
            out = []
            for idx, ph in enumerate(phases):
                name = ph.get("name") if isinstance(ph, dict) else str(ph)
                weeks = ph.get("weeks") if isinstance(ph, dict) else None
                checklist = _phase_checklist_from_method(method, name)
                out.append({"index": idx, "name": name, "weeks": weeks, "checklist": checklist})
            return out


    @router.get("/{proposal_id}/phases/{phase_idx}")
    def get_phase_detail(proposal_id: int, phase_idx: int):
        """Detalle de una fase concreta: checklist y contexto (metodología, decision_log)."""
        from backend.memory.state_store import SessionLocal, ProposalLog
        with SessionLocal() as db:
            row = db.query(ProposalLog).filter(ProposalLog.id == proposal_id).first()
            if not row:
                raise HTTPException(status_code=404, detail="Propuesta no encontrada")
            p = row.proposal_json or {}
            phases = p.get("phases") or []
            if phase_idx < 0 or phase_idx >= len(phases):
                raise HTTPException(status_code=400, detail="Índice de fase fuera de rango")
            ph = phases[phase_idx]
            name = ph.get("name") if isinstance(ph, dict) else str(ph)
            weeks = ph.get("weeks") if isinstance(ph, dict) else None
            checklist = _phase_checklist_from_method(p.get("methodology"), name)
            # contexto adicional útil para el usuario
            context = {
                "methodology": p.get("methodology"),
                "decision_log": p.get("decision_log", []),
                "methodology_sources": p.get("methodology_sources", []),
            }
            return {"index": phase_idx, "name": name, "weeks": weeks, "checklist": checklist, "context": context}


    # ----------------- Endpoints de seguimiento persistente -----------------
    class TrackingCreateIn(BaseModel):
        name: Optional[str] = None


    @router.post("/{proposal_id}/tracking")
    def create_tracking(proposal_id: int, payload: TrackingCreateIn, request: Request):
        """Crea un run de seguimiento para la propuesta: genera tareas por fase y las persiste.
        Requiere Authorization (JWT con 'user_id')."""
        # validar propuesta
        from backend.memory.state_store import SessionLocal, ProposalLog, create_tracking_run
        # extraer token
        try:
            auth = request.headers.get("Authorization") or ""
            if not auth.lower().startswith("bearer "):
                raise Exception("Missing token")
            token = auth.split()[1]
            data = jwt.decode(token, settings.APP_NAME, algorithms=["HS256"])  # type: ignore
            user_id = int(data.get("user_id"))
        except Exception:
            raise HTTPException(status_code=401, detail="Authorization required")

        with SessionLocal() as db:
            row = db.query(ProposalLog).filter(ProposalLog.id == proposal_id).first()
            if not row:
                raise HTTPException(status_code=404, detail="Propuesta no encontrada")
            p = row.proposal_json or {}

        # construir tareas por fase
        phases = p.get("phases") or []
        method = p.get("methodology")
        tasks = []
        for idx, ph in enumerate(phases):
            name = ph.get("name") if isinstance(ph, dict) else str(ph)
            checklist = _phase_checklist_from_method(method, name)
            # cada item de checklist -> tarea individual
            for item in checklist:
                tasks.append({"phase_idx": idx, "text": f"{name} — {item}"})

        run_id = create_tracking_run(user_id, proposal_id, payload.name or f"Seguimiento propuesta {proposal_id}", tasks)
        return {"run_id": run_id, "task_count": len(tasks)}


    @router.get("/{proposal_id}/tracking")
    def list_tracking_for_proposal(proposal_id: int, request: Request):
        try:
            auth = request.headers.get("Authorization") or ""
            if not auth.lower().startswith("bearer "):
                raise Exception("Missing token")
            token = auth.split()[1]
            data = jwt.decode(token, settings.APP_NAME, algorithms=["HS256"])  # type: ignore
            user_id = int(data.get("user_id"))
        except Exception:
            raise HTTPException(status_code=401, detail="Authorization required")
        from backend.memory.state_store import list_tracking_runs
        return list_tracking_runs(user_id, proposal_id)


    @router.get("/tracking/{run_id}")
    def get_tracking_run_endpoint(run_id: int, request: Request):
        try:
            auth = request.headers.get("Authorization") or ""
            if not auth.lower().startswith("bearer "):
                raise Exception("Missing token")
            token = auth.split()[1]
            data = jwt.decode(token, settings.APP_NAME, algorithms=["HS256"])  # type: ignore
            user_id = int(data.get("user_id"))
        except Exception:
            raise HTTPException(status_code=401, detail="Authorization required")
        from backend.memory.state_store import get_tracking_run
        run = get_tracking_run(run_id)
        if not run:
            raise HTTPException(status_code=404, detail="Run no encontrado")
        if int(run.get("user_id") or 0) != int(user_id):
            raise HTTPException(status_code=403, detail="No autorizado")
        return run


    @router.post("/tracking/{run_id}/tasks/{task_idx}/toggle")
    def toggle_task(run_id: int, task_idx: int, body: Dict[str, Any], request: Request):
        """Marca/desmarca una tarea del run. Body: {"completed": true|false}"""
        try:
            auth = request.headers.get("Authorization") or ""
            if not auth.lower().startswith("bearer "):
                raise Exception("Missing token")
            token = auth.split()[1]
            data = jwt.decode(token, settings.APP_NAME, algorithms=["HS256"])  # type: ignore
            user_id = int(data.get("user_id"))
        except Exception:
            raise HTTPException(status_code=401, detail="Authorization required")

        from backend.memory.state_store import get_tracking_run, toggle_task_completion
        run = get_tracking_run(run_id)
        if not run:
            raise HTTPException(status_code=404, detail="Run no encontrado")
        if int(run.get("user_id") or 0) != int(user_id):
            raise HTTPException(status_code=403, detail="No autorizado")

        completed = bool(body.get("completed", True))
        res = toggle_task_completion(run_id, int(task_idx), completed)
        if res is None:
            raise HTTPException(status_code=400, detail="Índice de tarea fuera de rango")
        return {"completed": res}


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

