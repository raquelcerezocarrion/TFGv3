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
from fastapi import Depends
from backend.routers.user import get_current_user
from backend.memory import state_store

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


# ---------------- Recomendaciones de características del proyecto ----------------
class RecommendIn(BaseModel):
    query: str = Field(..., min_length=3, description="Descripción del proyecto que quieres hacer")

class RecommendationResponse(BaseModel):
    methodology: Dict[str, Any]
    typical_roles: List[Dict[str, str]]
    typical_phases: List[Dict[str, Any]]
    key_practices: List[str]
    important_considerations: List[str]

@router.post("/recommend", response_model=RecommendationResponse)
def recommend_project_info(req: RecommendIn):
    """
    Devuelve información típica sobre proyectos similares: metodología recomendada,
    roles habituales, fases típicas, prácticas clave y consideraciones importantes.
    """
    try:
        from backend.knowledge.methodologies import recommend_methodology, METHODOLOGIES, detect_signals
    except Exception:
        # Fallback si no se puede importar
        return _fallback_recommendations()
    
    # Detectar metodología recomendada
    methodology_name, reasons, scored = recommend_methodology(req.query)
    
    # Obtener info de la metodología
    method_info = METHODOLOGIES.get(methodology_name, {})
    
    # Detectar señales del proyecto para sugerir roles y prácticas
    signals = detect_signals(req.query)
    
    # Construir respuesta sobre metodología
    methodology_response = {
        "name": methodology_name,
        "description": method_info.get("vision", ""),
        "best_for": method_info.get("mejor_si", []),
        "avoid_if": method_info.get("evitar_si", []),
        "reasons": reasons[:3] if reasons else []
    }
    
    # Roles típicos según las señales detectadas
    typical_roles = _get_typical_roles(signals, req.query)
    
    # Fases típicas de la metodología
    typical_phases = _get_typical_phases(methodology_name)
    
    # Prácticas clave
    key_practices = method_info.get("practicas", [])
    
    # Consideraciones importantes
    important_considerations = _get_important_considerations(signals, methodology_name)
    
    return {
        "methodology": methodology_response,
        "typical_roles": typical_roles,
        "typical_phases": typical_phases,
        "key_practices": key_practices,
        "important_considerations": important_considerations
    }

def _get_typical_roles(signals: Dict[str, float], query: str) -> List[Dict[str, str]]:
    """Determina roles típicos según las señales del proyecto"""
    roles = [
        {"name": "Product Owner", "description": "Define requisitos y prioriza el backlog"}
    ]
    
    # Roles base para cualquier proyecto
    if signals.get("mobile", 0) > 0:
        roles.append({"name": "Mobile Developer", "description": "Desarrollo de aplicaciones móviles (iOS/Android)"})
    else:
        roles.append({"name": "Full Stack Developer", "description": "Desarrollo frontend y backend"})
    
    # Roles específicos según señales
    if signals.get("ml_ai", 0) > 0:
        roles.append({"name": "ML Engineer", "description": "Desarrollo e integración de modelos de ML/IA"})
        roles.append({"name": "Data Scientist", "description": "Análisis de datos y entrenamiento de modelos"})
    
    if signals.get("payments", 0) > 0 or signals.get("fintech", 0) > 0:
        roles.append({"name": "Payment Integration Specialist", "description": "Integración de pasarelas de pago"})
    
    if signals.get("quality_critical", 0) > 0 or signals.get("realtime", 0) > 0:
        roles.append({"name": "QA Engineer", "description": "Pruebas exhaustivas y aseguramiento de calidad"})
    
    if signals.get("regulated", 0) > 0:
        roles.append({"name": "Compliance Officer", "description": "Cumplimiento normativo y auditorías"})
    
    if signals.get("ops_flow", 0) > 0 or signals.get("high_availability", 0) > 0:
        roles.append({"name": "DevOps Engineer", "description": "Infraestructura, CI/CD y monitorización"})
    
    if signals.get("ux_heavy", 0) > 0:
        roles.append({"name": "UX/UI Designer", "description": "Diseño de experiencia e interfaces de usuario"})
    
    # Scrum Master si no es Kanban puro
    roles.append({"name": "Scrum Master / Facilitador", "description": "Facilita ceremonias y elimina impedimentos"})
    
    return roles[:8]  # Limitar a 8 roles más comunes

def _get_typical_phases(methodology: str) -> List[Dict[str, Any]]:
    """Devuelve fases típicas según la metodología"""
    m = methodology.lower()
    
    if 'scrum' in m:
        return [
            {"name": "Descubrimiento", "duration": "2 semanas", "description": "Definición de visión, MVP y backlog inicial"},
            {"name": "Sprints de Desarrollo", "duration": "8-12 semanas", "description": "Iteraciones de 2 semanas con entrega incremental"},
            {"name": "Hardening", "duration": "2 semanas", "description": "Estabilización, QA y corrección de bugs"},
            {"name": "Release", "duration": "1 semana", "description": "Despliegue a producción y handover"}
        ]
    elif 'kanban' in m:
        return [
            {"name": "Configuración del tablero", "duration": "1 semana", "description": "Definir columnas, WIP limits y políticas"},
            {"name": "Flujo continuo", "duration": "Ongoing", "description": "Trabajo continuo sin sprints fijos"},
            {"name": "Optimización", "duration": "Ongoing", "description": "Mejora continua del flujo y lead time"}
        ]
    elif 'xp' in m or 'extreme' in m:
        return [
            {"name": "Incepción técnica", "duration": "1-2 semanas", "description": "Setup, arquitectura y estándares"},
            {"name": "Iteraciones XP", "duration": "8-10 semanas", "description": "Desarrollo con TDD, pair programming y CI"},
            {"name": "Release seguro", "duration": "1 semana", "description": "Validación final y despliegue"}
        ]
    elif 'lean' in m:
        return [
            {"name": "Build MVP", "duration": "2-4 semanas", "description": "Construcción del producto mínimo viable"},
            {"name": "Measure", "duration": "1-2 semanas", "description": "Medición de métricas clave"},
            {"name": "Learn & Iterate", "duration": "Ongoing", "description": "Aprendizaje y pivoteo según datos"}
        ]
    else:
        return [
            {"name": "Planificación", "duration": "2 semanas", "description": "Definición de alcance y planificación"},
            {"name": "Desarrollo", "duration": "8-12 semanas", "description": "Implementación de funcionalidades"},
            {"name": "Pruebas", "duration": "2 semanas", "description": "QA y validación"},
            {"name": "Despliegue", "duration": "1 semana", "description": "Puesta en producción"}
        ]

def _get_important_considerations(signals: Dict[str, float], methodology: str) -> List[str]:
    """Devuelve consideraciones importantes según señales detectadas"""
    considerations = []
    
    if signals.get("payments", 0) > 0 or signals.get("fintech", 0) > 0:
        considerations.append("🔒 Seguridad crítica: implementar PCI DSS compliance y encriptación end-to-end")
        considerations.append("💳 Integración con pasarelas: considerar Stripe, PayPal o Redsys según región")
    
    if signals.get("regulated", 0) > 0:
        considerations.append("⚖️ Cumplimiento normativo: asegurar conformidad con GDPR/HIPAA/ISO según aplique")
        considerations.append("📋 Auditorías: documentar decisiones y mantener logs detallados")
    
    if signals.get("ml_ai", 0) > 0:
        considerations.append("🤖 Datos de calidad: la precisión del modelo depende de buenos datos de entrenamiento")
        considerations.append("⚡ Infraestructura ML: considerar GPU/TPU para entrenamiento si es necesario")
    
    if signals.get("mobile", 0) > 0:
        considerations.append("📱 Multiplataforma: evaluar Flutter/React Native vs nativo según complejidad")
        considerations.append("📲 App stores: planificar tiempo para revisiones de Apple/Google (5-7 días)")
    
    if signals.get("realtime", 0) > 0:
        considerations.append("⚡ Arquitectura realtime: websockets, message queues o servicios como Pusher/Ably")
        considerations.append("🔄 Escalabilidad: diseñar para manejar múltiples conexiones concurrentes")
    
    if signals.get("high_availability", 0) > 0 or signals.get("ops_flow", 0) > 0:
        considerations.append("🚀 DevOps sólido: CI/CD, monitorización 24/7 y plan de disaster recovery")
        considerations.append("📊 Observabilidad: logs centralizados, métricas y alertas (Datadog, New Relic)")
    
    if signals.get("startup", 0) > 0 or signals.get("uncertainty", 0) > 0:
        considerations.append("🎯 Foco en MVP: priorizar features críticas y lanzar rápido para validar")
        considerations.append("📈 Métricas desde día 1: analytics y tracking de user behavior para decisiones data-driven")
    
    if signals.get("ecommerce", 0) > 0 or signals.get("marketplace", 0) > 0:
        considerations.append("🛒 Checkout optimizado: reducir fricción para maximizar conversión")
        considerations.append("📦 Logística: integración con sistemas de envío y tracking")
    
    # Consideraciones de metodología
    if 'scrum' in methodology.lower():
        considerations.append("🔄 Ceremonias Scrum: daily standup, planning, review y retrospectiva son clave")
    elif 'kanban' in methodology.lower():
        considerations.append("📊 Visualización del flujo: mantener WIP limits estrictos para evitar cuellos de botella")
    elif 'xp' in methodology.lower():
        considerations.append("✅ TDD obligatorio: tests primero para calidad y refactoring seguro")
    
    if signals.get("quality_critical", 0) > 0:
        considerations.append("🧪 Testing exhaustivo: unit, integration, e2e y load testing son imprescindibles")
    
    return considerations[:6]  # Limitar a 6 consideraciones más importantes

def _fallback_recommendations():
    """Respuesta de fallback si no hay sistema de metodologías"""
    return {
        "methodology": {
            "name": "Scrum",
            "description": "Marco ágil para desarrollo iterativo",
            "best_for": ["Proyectos con requisitos cambiantes", "Equipos pequeños-medianos"],
            "avoid_if": ["Proyectos con alcance muy fijo"],
            "reasons": []
        },
        "typical_roles": [
            {"name": "Product Owner", "description": "Define prioridades"},
            {"name": "Scrum Master", "description": "Facilita el proceso"},
            {"name": "Developers", "description": "Desarrollo del producto"}
        ],
        "typical_phases": [
            {"name": "Sprint Planning", "duration": "2 semanas", "description": "Planificación de iteración"},
            {"name": "Development", "duration": "10 días", "description": "Desarrollo incremental"},
            {"name": "Review & Retro", "duration": "2 días", "description": "Revisión y mejora"}
        ],
        "key_practices": ["Daily Standup", "Sprint Review", "Retrospectivas"],
        "important_considerations": ["Definir Definition of Done", "Mantener backlog priorizado"]
    }

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


# ----------------- Endpoints para proyectos (lista, detalle y checklist por fase) -----------------
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
        # First, query proposals specifically for this chat's sessions (saved-{chat_id}-*)
        chat_specific = db.query(ProposalLog).filter(
            ProposalLog.session_id.like(f"saved-{chat_id}-%")
        ).order_by(ProposalLog.created_at.desc()).all()
        
        # If we found chat-specific proposals, use them directly
        if chat_specific:
            for r in chat_specific:
                try:
                    out.append({
                        'id': int(r.id),
                        'requirements': r.requirements,
                        'created_at': r.created_at.isoformat(),
                        'methodology': (r.proposal_json or {}).get('methodology'),
                    })
                except Exception:
                    continue
        
        # Fallback: if no DB proposals found, parse inline proposals from chat content
        if not out and assistant_blocks:
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


@router.get("/{proposal_id}/phases")
def get_proposal_phases(proposal_id: int):
    """Devuelve una lista de fases para una propuesta dada.
    Reglas:
    - Si la propuesta persistida contiene 'phases' en proposal_json, se devuelve tal cual (añadiendo checklist si hace falta).
    - Si no, se intenta inferir la metodología desde proposal_json['methodology'] o desde los 'requirements'
      usando `backend.knowledge.methodologies.recommend_methodology` y se generan fases por plantilla.
    Cada fase incluye { name, weeks (opcional), phase_idx, checklist: [..] }.
    """
    from backend.memory.state_store import SessionLocal, ProposalLog
    try:
        from backend.knowledge.methodologies import normalize_method_name, recommend_methodology
    except Exception:
        normalize_method_name = lambda x: x
        def recommend_methodology(text: str):
            return ("Scrum", [], [])

    def _default_phases_for_method(method: str):
        m = (method or "").lower()
        if 'kanban' in m:
            names = [
                ("Backlog & Priorización", None),
                ("Preparación / Ready", 1),
                ("Development / En progreso", None),
                ("Pruebas / QA", 1),
                ("Release / Despliegue", 1),
                ("Operación y Monitorización", None),
            ]
        elif 'safe' in m:
            names = [
                ("PI Planning (Program Increment)", 2),
                ("Iteraciones / Sprints (por equipo)", 8),
                ("System Demo & Integración", 1),
                ("Stabilización y Hardening", 1),
                ("Release & Inspect", 1),
            ]
        elif 'scrum' in m:
            names = [
                ("Descubrimiento / Incepción", 2),
                ("Sprints iterativos (Desarrollo)", 8),
                ("QA y Estabilización", 2),
                ("Despliegue / Release", 1),
                ("Operación / Mejora continua", None),
            ]
        elif 'scrumban' in m:
            names = [
                ("Incepción ligera", 1),
                ("Sprints / Cadencia ligera", 6),
                ("Flujo continuo / Kanban board", None),
                ("QA y Hardening", 1),
            ]
        elif 'xp' in m or 'extreme' in m:
            names = [
                ("Incepción y especificación técnica", 2),
                ("Iteraciones con prácticas XP", 8),
                ("Integración continua & Tests", None),
                ("Release seguro", 1),
            ]
        elif 'lean' in m:
            names = [
                ("Descubrimiento (MVP)", 2),
                ("Construir–Medir–Aprender (experimentos)", 6),
                ("Escalado/Optimización", None),
            ]
        else:
            names = [
                ("Descubrimiento", 2),
                ("Desarrollo e Integración", 8),
                ("QA y Estabilización", 2),
                ("Despliegue", 1),
            ]

        def _phase_description(method: str, name: str) -> str:
            nn = (name or '').lower()
            if 'descub' in nn or 'incepción' in nn or 'inception' in nn:
                return 'Fase de descubrimiento: validar hipótesis, identificar stakeholders y priorizar backlog.'
            if 'sprint' in nn or 'iter' in nn or 'desarrollo' in nn:
                return 'Entrega iterativa de funcionalidad siguiendo la priorización del backlog.'
            if 'qa' in nn or 'prueb' in nn or 'hardening' in nn:
                return 'Pruebas, validación y corrección de defectos antes del despliegue.'
            if 'deploy' in nn or 'desplieg' in nn or 'release' in nn:
                return 'Preparación y ejecución del despliegue a entornos de producción.'
            if 'oper' in nn or 'monitor' in nn:
                return 'Operación, monitorización y mejora continua post-release.'
            if 'planning' in nn or 'pi planning' in nn:
                return 'Planificación a nivel de programa para coordinar equipos y objetivos.'
            if 'backlog' in nn or 'prioriz' in nn:
                return 'Organización y priorización de las tareas pendientes y epics.'
            # fallback
            return f'Descripción de la fase "{name}" relacionada con la metodología {method}.'

        out = []
        for idx, (n, w) in enumerate(names):
            out.append({
                "name": n,
                "weeks": w,
                "phase_idx": idx,
                "description": _phase_description(method, n),
                "checklist": _phase_checklist_from_method(method, n)
            })
        return out

    with SessionLocal() as db:
        row = db.query(ProposalLog).filter(ProposalLog.id == proposal_id).first()
        if not row:
            raise HTTPException(status_code=404, detail="Propuesta no encontrada")

        pj = row.proposal_json or {}
        existing = pj.get('phases')
        if isinstance(existing, list) and existing:
            out = []
            for i, ph in enumerate(existing):
                if isinstance(ph, dict):
                    name = ph.get('name') or f"Fase {i+1}"
                    weeks = ph.get('weeks')
                    checklist = ph.get('checklist') or _phase_checklist_from_method(pj.get('methodology'), name)
                    description = ph.get('description') or (
                        f'Descripción de la fase "{name}" basada en la metodología {pj.get("methodology") or "desconocida"}.'
                    )
                else:
                    name = str(ph)
                    weeks = None
                    checklist = _phase_checklist_from_method(pj.get('methodology'), name)
                    description = f'Descripción de la fase "{name}" basada en la metodología {pj.get("methodology") or "desconocida"}.'
                out.append({"name": name, "weeks": weeks, "phase_idx": i, "description": description, "checklist": checklist})
            return out

        method = (pj.get('methodology') or '').strip() or None
        if not method:
            try:
                method, why, scored = recommend_methodology(row.requirements or '')
            except Exception:
                method = 'Scrum'

        method = normalize_method_name(method or '')
        phases = _default_phases_for_method(method)
        return phases


@router.get("/{proposal_id}/open_session")
def open_session_for_proposal(proposal_id: int):
    """Crea una session_id temporal para abrir un chat contextual sobre la propuesta
    y devuelve un `assistant_summary` que el frontend puede mostrar al inicializar el chat.
    """
    from backend.memory.state_store import SessionLocal, ProposalLog
    from datetime import datetime

    with SessionLocal() as db:
        row = db.query(ProposalLog).filter(ProposalLog.id == proposal_id).first()
        if not row:
            raise HTTPException(status_code=404, detail="Propuesta no encontrada")

        pj = row.proposal_json or {}
        # session id temporal para el frontend
        sid = f"proposal_{proposal_id}_{int(datetime.utcnow().timestamp())}"

        # Intentar generar un resumen legible: preferir estructura de propuesta
        try:
            if isinstance(pj, dict) and pj.get('methodology'):
                summary = _pretty_proposal(pj)
            else:
                summary = pj.get('assistant_block') or pj.get('requirements') or ''
        except Exception:
            summary = pj.get('assistant_block') or pj.get('requirements') or ''

        return {"session_id": sid, "assistant_summary": summary}


@router.get("/{proposal_id}/phases/{phase_idx}/definition")
def get_phase_definition(proposal_id: int, phase_idx: int):
    """Devuelve la definición ampliada de una fase concreta.
    Si la fase almacenada/plantilla ya incluye 'description' la devuelve.
    En caso contrario, intenta usar la función de explicación del brain
    para generar una descripción detallada contextualizada en la propuesta.
    """
    from backend.memory.state_store import SessionLocal, ProposalLog
    try:
        # intentar reutilizar la lista de fases ya generada
        phases = get_proposal_phases(proposal_id)
    except HTTPException:
        raise
    except Exception:
        phases = []

    if not phases or phase_idx < 0 or phase_idx >= len(phases):
        raise HTTPException(status_code=404, detail="Fase no encontrada")

    ph = phases[phase_idx]

    # Try to fetch the stored proposal to detect methodology and allow returning structured data
    with SessionLocal() as db:
        row = db.query(ProposalLog).filter(ProposalLog.id == proposal_id).first()
        pj = row.proposal_json or {} if row else {}

    desc = ph.get('description')

    # Attempt to find structured phase info for the proposal methodology regardless of desc presence
    structured = None
    try:
        from backend.knowledge.methodologies import get_method_phases, normalize_method_name
        import re
        method = (pj.get('methodology') or '').strip() or None
        if method:
            key = normalize_method_name(method)
            mp = get_method_phases(key) or []
            
            # Try exact match first
            phase_name_lower = (ph.get('name') or '').lower().strip()
            for s in mp:
                if (s.get('name') or '').lower().strip() == phase_name_lower:
                    structured = s
                    break
            
            # If no exact match, try fuzzy matching by tokens
            if not structured and phase_name_lower:
                # Tokenize the phase name from proposal
                tokens = set(re.findall(r'\w+', phase_name_lower))
                best_match = None
                best_score = 0
                
                for s in mp:
                    s_name = (s.get('name') or '').lower().strip()
                    s_tokens = set(re.findall(r'\w+', s_name))
                    
                    # Calculate Jaccard similarity
                    if s_tokens:
                        intersection = len(tokens & s_tokens)
                        union = len(tokens | s_tokens)
                        score = intersection / union if union > 0 else 0
                        
                        if score > best_score and score >= 0.3:  # At least 30% similarity
                            best_score = score
                            best_match = s
                
                # Special handling for common aliases
                if not best_match:
                    if any(w in phase_name_lower for w in ['discovery', 'incep', 'inicio', 'kickoff']):
                        # Use first phase as it's typically inception/discovery
                        if mp:
                            best_match = mp[0]
                
                structured = best_match
    except Exception:
        structured = None

    if desc and not structured:
        return {"definition": desc}

    # si no hay descripción o hay structured pero necesitamos una explicación textual, intentar usar brain._explain_specific_phase
    try:
        from backend.engine.brain import _explain_specific_phase
        # recuperar propuesta completa para contexto
        # _explain_specific_phase espera el texto preguntado y la proposal dict
        asked = f"¿Qué es la fase {ph.get('name')}?"
        expl = _explain_specific_phase(asked, pj) if callable(_explain_specific_phase) else None
        if expl:
            resp = {"definition": expl}
            if structured:
                resp["structured"] = structured
            return resp
    except Exception:
        pass

    # fallback: if we had structured data, return it with a textual summary; otherwise return generic description
    if structured:
        # build a lightweight textual definition if desc missing
        text_def = desc or f"{structured.get('name')} — {structured.get('summary') or ('Descripción de la fase ' + structured.get('name'))}"
        return {"definition": text_def, "structured": structured}

    return {"definition": ph.get('description') or f"Descripción de la fase '{ph.get('name')}'."}
    return {"definition": ph.get('description') or f"Descripción de la fase '{ph.get('name')}'."}
