# backend/engine/brain.py
import re
import json
import copy
from typing import Tuple, Dict, Any, List, Optional

# Memoria de usuario (preferencias; opcional según tu state_store)
try:
    from backend.memory.state_store import get_client_prefs, upsert_client_pref
except Exception:  # pragma: no cover
    def get_client_prefs(*a, **k): return {}
    def upsert_client_pref(*a, **k): return None

from backend.engine.planner import generate_proposal
from backend.engine.context import (
    get_last_proposal, set_last_proposal,
    get_pending_change, set_pending_change, clear_pending_change
)

# set_last_area es opcional (para “fuentes” por área); si no existe, hacemos no-op
try:
    from backend.engine.context import set_last_area
except Exception:  # pragma: no cover
    def set_last_area(*a, **k):  # no-op si no existe
        return None

# Conocimiento de metodologías (explicaciones y comparativas + fuentes)
from backend.knowledge.methodologies import (
    explain_methodology_choice,
    recommend_methodology,
    compare_methods,
    normalize_method_name,
    METHODOLOGIES,
)

# Persistencia opcional
try:
    from backend.memory.state_store import save_proposal, log_message
except Exception:  # pragma: no cover
    def save_proposal(*a, **k): return None
    def log_message(*a, **k): return None

# NLU opcional
try:
    from backend.nlu.intents import IntentsRuntime
    _INTENTS = IntentsRuntime()
except Exception:  # pragma: no cover
    _INTENTS = None

# Recuperación de casos similares (TF-IDF k-NN) opcional
try:
    from backend.retrieval.similarity import get_retriever
    _SIM = get_retriever()
except Exception:  # pragma: no cover
    _SIM = None


# ===================== utilidades =====================

def _norm(text: str) -> str:
    return text.lower()

def _is_yes(text: str) -> bool:
    t = _norm(text).strip()
    return t in {"si", "sí", "s", "ok", "vale", "dale", "confirmo", "correcto"} or "adelante" in t

def _is_no(text: str) -> bool:
    t = _norm(text).strip()
    return t in {"no", "n", "mejor no"} or "cancel" in t or "cancela" in t


# ===================== detectores =====================

def _is_greeting(text: str) -> bool:
    return bool(re.search(r"\b(hola|buenas|hey|hello|qué tal|que tal)\b", text, re.I))

def _is_farewell(text: str) -> bool:
    return bool(re.search(r"\b(ad[ií]os|hasta luego|nos vemos|chao)\b", text, re.I))

def _is_thanks(text: str) -> bool:
    return bool(re.search(r"\b(gracias|thank[s]?|mil gracias)\b", text, re.I))

def _is_help(text: str) -> bool:
    t = _norm(text)
    return "ayuda" in t or "qué puedes hacer" in t or "que puedes hacer" in t

def _asks_methodology(text: str) -> bool:
    return bool(re.search(r"\b(scrum|kanban|scrumban|xp|lean|crystal|fdd|dsdm|safe|devops|metodolog[ií]a)\b", text, re.I))

def _asks_budget(text: str) -> bool:
    return bool(re.search(r"\b(presupuesto|coste|costos|estimaci[oó]n|precio)\b", text, re.I))

def _asks_team(text: str) -> bool:
    return bool(re.search(r"\b(equipo|roles|perfiles|staffing|personal|dimension)\b", text, re.I))

def _asks_risks_simple(text: str) -> bool:
    t = _norm(text)
    return ("riesgo" in t or "riesgos" in t)
def _accepts_proposal(text: str) -> bool:
    """Detecta 'acepto la propuesta', 'aprobamos', 'adelante con la propuesta', etc."""
    t = _norm(text)
    keys = [
        "aceptamos la propuesta", "acepto la propuesta", "aprobamos la propuesta", "aprobada la propuesta",
        "adelante con la propuesta", "ok con la propuesta", "conforme con la propuesta",
        "cerramos la propuesta", "aprobamos el plan", "acepto el plan", "ok al plan",
        "vamos adelante", "arrancamos el proyecto", "empecemos", "comencemos", "seguimos con esta propuesta"
    ]
    # Evitamos confundir el 'sí' de confirmaciones parciales: pedimos que aparezca 'propuesta' o 'plan' o un verbo claro
    return any(k in t for k in keys)

def _looks_like_staff_list(text: str) -> bool:
    """
    Detecta plantilla pegada tanto en múltiples líneas como en una sola línea
    (ej. '- Ana — Backend — ... - Luis — QA — ...').
    """
    t = _norm(text)
    role_hints = ["backend", "frontend", "qa", "quality", "tester", "devops", "sre", "pm",
                  "product owner", "po", "ux", "ui", "mobile", "android", "ios", "ml", "data", "arquitect"]
    # Caso 1: varias líneas y separadores
    if ("\n" in text) and any(sep in text for sep in ["—", "-", "|", ":"]) and any(h in t for h in role_hints):
        return True
    # Caso 2: una sola línea con varios items separados por ' - ' / ' • ' y patrón Nombre — Rol
    if "—" in text and (text.count(" - ") >= 2 or " • " in text or ";" in text):
        return True
    # Caso 3: al menos dos patrones 'nombre — rol' en la misma línea
    if len(re.findall(r"[A-Za-zÁÉÍÓÚÑáéíóúñ][^—\n]{1,40}\s—\s[A-Za-z]", text)) >= 2:
        return True
    return False


def _asks_why(text: str) -> bool:
    t = _norm(text)
    return ("por qué" in t) or ("por que" in t) or ("porque" in t) or ("justifica" in t) or ("explica" in t) or ("motivo" in t)

def _asks_phases_simple(text: str) -> bool:
    """Preguntas tipo: 'fases?', 'plan', 'timeline', 'entregas', 'roadmap' (sin 'por qué')."""
    t = _norm(text)
    keys = ["fase", "fases", "roadmap", "plan", "timeline", "cronograma", "entregas", "hitos"]
    return any(k in t for k in keys)

def _asks_why_phases(text: str) -> bool:
    t = _norm(text)
    return ("fase" in t or "fases" in t or "hitos" in t or "timeline" in t) and _asks_why(t)

def _asks_why_team_general(text: str) -> bool:
    t = _norm(text)
    return _asks_why(t) and ("equipo" in t or "roles" in t or "personal" in t or "plantilla" in t or "dimension" in t)

def _asks_why_role_count(text: str) -> Optional[Tuple[str, float]]:
    """Detecta 'por qué 2 backend', 'por qué 0.5 ux', etc."""
    t = _norm(text)
    m = re.search(r"(\d+(?:[.,]\d+)?)\s*(pm|project manager|tech\s*lead|arquitect[oa]|backend|frontend|qa|tester|quality|ux|ui|ml|data)", t)
    if not m:
        return None
    num_str, role_raw = m.groups()
    num = float(num_str.replace(",", "."))
    return (_canonical_role(role_raw), num)

def _looks_like_requirements(text: str) -> bool:
    kw = [
        "app","web","api","panel","admin","pagos","login","usuarios","microservicios",
        "ios","android","realtime","tiempo real","ml","ia","modelo","dashboard","reportes","integraci"
    ]
    score = sum(1 for k in kw if k in _norm(text))
    return score >= 2 or len(text.split()) >= 12

def _asks_similar(text: str) -> bool:
    t = _norm(text)
    return ("proyectos similares" in t or "proyectos parecidos" in t or "casos similares" in t or "algo parecido" in t or "parecido" in t)

def _asks_budget_breakdown(text: str) -> bool:
    t = _norm(text)
    keys = [
        "desglose", "detalle", "presupuesto detallado", "detalle del presupuesto",
        "por rol", "por roles", "tarifa", "partidas", "coste por", "costes por",
        "por fase", "por fases", "coste por fase", "reparto", "matriz",
        "en que se gasta", "en qué se gasta", "a que se destina", "a qué se destina",
        "para que va destinado", "para qué va destinado",
        "capex", "opex"
    ]
    return any(k in t for k in keys)

def _asks_training_plan(text: str) -> bool:
    t = _norm(text)
    return any(k in t for k in ["gaps", "carencias", "plan de formacion", "plan de formación", "upskilling", "formacion", "formación"])

def _asks_sources(text: str) -> bool:
    t = _norm(text)
    keys = ["fuente", "fuentes", "documentación", "documentacion", "autor", "autores", "bibliografía", "bibliografia", "en qué te basas", "en que te basas"]
    return any(k in t for k in keys)


# ---------- catálogo/definición de metodologías ----------

def _asks_method_list(text: str) -> bool:
    t = _norm(text)
    keys = [
        "qué metodologías", "que metodologias", "metodologías usas", "metodologias usas",
        "metodologías soportadas", "metodologias soportadas", "opciones", "lista de metodologías",
        "que opciones hay", "qué opciones hay"
    ]
    return any(k in t for k in keys)

def _asks_method_definition(text: str) -> bool:
    """Detecta 'qué es xp', 'explícame kanban', 'en qué consiste scrum', etc."""
    t = _norm(text)
    return any(k in t for k in ["qué es", "que es", "explica", "explícame", "explicame", "en qué consiste", "en que consiste", "definición", "definicion"])


# ===================== roles =====================

_ROLE_SYNONYMS = {
    "qa": "QA", "quality": "QA", "tester": "QA",
    "ux": "UX/UI", "ui": "UX/UI", "diseñ": "UX/UI",
    "pm": "PM", "project manager": "PM",
    "tech lead": "Tech Lead", "arquitect": "Tech Lead", "arquitecto": "Tech Lead",
    "backend": "Backend Dev", "frontend": "Frontend Dev",
    "ml": "ML Engineer", "data": "ML Engineer",
}

def _canonical_role(role_text: str) -> str:
    t = _norm(role_text)
    for k, v in _ROLE_SYNONYMS.items():
        if k in t:
            return v
    return role_text.strip().title()

def _extract_roles_from_text(text: str) -> List[str]:
    t = _norm(text)
    found = set()
    for k, v in _ROLE_SYNONYMS.items():
        if k in t:
            found.add(v)
    return list(found)

def _find_role_count_in_proposal(proposal: Dict[str, Any], role: str) -> Optional[float]:
    for r in proposal.get("team", []):
        if _norm(r["role"]) == _norm(role):
            return float(r["count"])
    return None


# ===================== fuentes para fases/equipo =====================

AGILE_TEAM_SOURCES: List[Dict[str, str]] = [
    {"autor": "Ken Schwaber & Jeff Sutherland", "titulo": "The Scrum Guide", "anio": "2020", "url": "https://scrumguides.org"},
    {"autor": "Kent Beck", "titulo": "Extreme Programming Explained", "anio": "2004", "url": "ISBN 0321278658"},
    {"autor": "David J. Anderson", "titulo": "Kanban", "anio": "2010", "url": "ISBN 0984521402"},
    {"autor": "Forsgren, Humble, Kim", "titulo": "Accelerate", "anio": "2018", "url": "ISBN 1942788339"},
    {"autor": "Skelton & Pais", "titulo": "Team Topologies", "anio": "2019", "url": "ISBN 1942788819"},
]

def _format_sources(sources) -> str:
    if not sources:
        return "No tengo fuentes adjuntas para esta recomendación."
    lines = []
    for s in sources:
        autor = s.get("autor", "")
        titulo = s.get("titulo", "")
        anio = s.get("anio", "")
        url = s.get("url", "")
        lines.append(f"- {autor}: *{titulo}* ({anio}). {url}")
    return "\n".join(lines)

def _collect_sources_for_area(proposal: Optional[Dict[str, Any]], area: str) -> List[Dict[str, str]]:
    out: List[Dict[str, str]] = []
    if proposal and proposal.get("methodology_sources"):
        out.extend(proposal["methodology_sources"])
    # Fases y equipo usan además fuentes genéricas de dinámicas y entrega ágil
    if area in {"phases", "equipo", "team"}:
        out.extend(AGILE_TEAM_SOURCES)
    # eliminamos duplicados (por título)
    uniq, seen = [], set()
    for s in out:
        key = (s.get("autor"), s.get("titulo"))
        if key not in seen:
            uniq.append(s)
            seen.add(key)
    return uniq


# ===================== pretty =====================

def _pretty_proposal(p: Dict[str, Any]) -> str:
    team = ", ".join(f"{t['role']} x{t['count']}" for t in p.get("team", []))
    phases = " → ".join(f"{ph['name']} ({ph['weeks']}s)" for ph in p.get("phases", []))

    all_risks = (p.get("risks") or [])
    base_risks = [r for r in all_risks if not _norm(str(r)).startswith("[control]")]
    controls = [r for r in all_risks if _norm(str(r)).startswith("[control]")]

    lines = [
        f"📌 Metodología: {p.get('methodology','')}",
        f"👥 Equipo: {team}" if team else "👥 Equipo: (sin definir)",
        f"🧩 Fases: {phases}" if phases else "🧩 Fases: (sin definir)",
        f"💶 Presupuesto: {p.get('budget',{}).get('total_eur', 0.0)} € (incluye {p.get('budget',{}).get('assumptions',{}).get('contingency_pct', 10)}% contingencia)",
        "⚠️ Riesgos: " + ("; ".join(base_risks) if base_risks else "(no definidos)")
    ]

    if controls:
        lines.append("🛡️ Plan de prevención:")
        for c in controls:
            clean = str(c)
            if clean.lower().startswith("[control]"):
                clean = clean[len("[Control]"):].strip()
            lines.append(f"- {clean}")

    return "\n".join(lines)


# ===================== explicabilidad =====================

def _explain_role(role: str, requirements: Optional[str]) -> List[str]:
    t = _norm(requirements or "")
    if role == "QA":
        base = [
            "Reduce fuga de defectos y coste de corrección en producción.",
            "Automatiza regresión y asegura criterios de aceptación."
        ]
        if "pagos" in t or "stripe" in t:
            base.append("Necesarias pruebas de integración con pasarela y anti-fraude.")
        return base
    if role == "UX/UI":
        base = ["Mejora conversión y usabilidad; reduce retrabajo de frontend."]
        if "panel" in t or "admin" in t or "mobile" in t or "app" in t:
            base.append("Define flujos y componentes reutilizables (design system).")
        return base
    if role == "Tech Lead":
        return ["Define arquitectura, estándares y CI/CD; desbloquea al equipo y controla deuda técnica."]
    if role == "PM":
        return ["Gestiona alcance, riesgos y stakeholders; protege al equipo y vigila plazos."]
    if role == "Backend Dev":
        base = ["Implementa APIs, dominio y seguridad; rendimiento y mantenibilidad del servidor."]
        if "pagos" in t:
            base.append("Integra pasarela de pagos, idempotencia y auditoría.")
        return base
    if role == "Frontend Dev":
        return ["Construye la UX final (React), estado y accesibilidad; integra con backend y diseño."]
    if role == "ML Engineer":
        return ["Prototipa/productiviza modelos; evalúa drift y sesgos; integra batch/online."]
    return ["Aporta valor específico al alcance detectado."]

def _explain_role_count(role: str, count: float, requirements: Optional[str]) -> List[str]:
    reasons = _explain_role(role, requirements)
    if count == 0.5:
        reasons.insert(0, "Dedicación parcial (0,5) por alcance acotado/consultivo.")
    elif count == 1:
        reasons.insert(0, "1 persona suficiente para ownership y coordinación del área.")
    elif count == 2:
        reasons.insert(0, "2 personas para paralelizar trabajo y reducir camino crítico.")
    elif count > 2:
        reasons.insert(0, f"{count:g} personas para throughput y cobertura de módulos en paralelo.")
    return reasons

def _explain_team_general(proposal: Dict[str, Any], requirements: Optional[str]) -> List[str]:
    t = _norm(requirements or "")
    reasons = [
        "Cobertura completa del ciclo: PM, Tech Lead, Backend/Frontend, QA, UX/UI.",
        "Dimensionado para equilibrar time-to-market y coste."
    ]
    if "pagos" in t or "stripe" in t:
        reasons.append("Se añade 0,5 Backend (payments) por PCI-DSS e idempotencia.")
    if "admin" in t or "panel" in t:
        reasons.append("Se añade 0,5 Frontend (admin) para backoffice (tablas, filtros).")
    if "ml" in t or "ia" in t or "modelo" in t:
        reasons.append("Se añade 0,5 ML Engineer para prototipos y puesta en producción.")
    return reasons

def _explain_phases_method_aware(proposal: Dict[str, Any]) -> List[str]:
    """Explica cada fase según la metodología actual."""
    method = proposal.get("methodology", "")
    lines: List[str] = []
    header = f"Fases justificadas según la metodología **{method}**:"
    lines.append(header)

    for ph in proposal.get("phases", []):
        n = _norm(ph["name"])
        if method == "Scrum":
            if "incepción" in n or "incepcion" in n or "plan" in n:
                lines.append("- Incepción/Plan de Releases: alinear alcance, roadmap y Definition of Done.")
            elif "sprint" in n or "desarrollo" in n:
                lines.append("- Sprints de Desarrollo (2w): foco en valor incremental, revisión y retrospectiva.")
            elif "qa" in n or "hardening" in n:
                lines.append("- QA/Hardening: estabilizar, pruebas de aceptación y performance previas al release.")
            elif "despliegue" in n or "transferencia" in n:
                lines.append("- Despliegue & Transferencia: puesta en producción y handover.")
            else:
                lines.append(f"- {ph['name']}: aporta entregables que reducen riesgos específicos.")
        elif method == "XP":
            if "discovery" in n or "historias" in n or "crc" in n:
                lines.append("- Discovery + Historias & CRC: modelado ligero, historias y tarjetas CRC para diseño.")
            elif "tdd" in n or "refactor" in n or "ci" in n:
                lines.append("- Iteraciones con TDD/Refactor/CI: calidad interna alta y entrega continua.")
            elif "aceptación" in n or "aceptacion" in n or "hardening" in n:
                lines.append("- Hardening & Pruebas de Aceptación: validar criterios de aceptación con cliente.")
            elif "release" in n or "handover" in n:
                lines.append("- Release & Handover: empaquetado, despliegue y transferencia.")
            else:
                lines.append(f"- {ph['name']}: reduce riesgo técnico/funcional asociado.")
        elif method == "Kanban":
            if "descubrimiento" in n or "diseño" in n:
                lines.append("- Descubrimiento & Diseño: preparar trabajo y políticas de flujo/WIP.")
            elif "flujo" in n or "wip" in n or "columnas" in n or "implementación" in n:
                lines.append("- Implementación flujo continuo: limitar WIP, políticas explícitas y métricas (lead time).")
            elif "qa" in n or "observabilidad" in n:
                lines.append("- QA continuo & Observabilidad: calidad integrada al flujo, telemetría y alertas.")
            elif "estabilización" in n or "producción" in n or "produccion" in n:
                lines.append("- Estabilización & Producción: endurecer y afinar operación.")
            else:
                lines.append(f"- {ph['name']}: contribuye al flujo con límites de WIP.")
        else:
            # Genérico
            if "descubr" in n:
                lines.append("- Descubrimiento: clarificar alcance y riesgos; evita construir lo equivocado.")
            elif "arquitect" in n or "setup" in n:
                lines.append("- Arquitectura & setup: estándares, CI/CD e infraestructura base.")
            elif "desarrollo" in n or "iterativo" in n:
                lines.append("- Desarrollo iterativo: MVP + valor en ciclos cortos.")
            elif "qa" in n or "hardening" in n:
                lines.append("- QA & hardening: pruebas y estabilización pre-release.")
            elif "despliegue" in n or "handover" in n:
                lines.append("- Despliegue & handover: release, documentación y formación.")
            else:
                lines.append(f"- {ph['name']}: entregables que reducen riesgos específicos.")
    return lines
# === NUEVO: detección y explicación de fase concreta ===

_PHASE_CANON = {
    'incepcion': {
        'incepcion','incepción','inception','discovery','inicio','kickoff',
        'plan de releases','plan de release','plan de entregas','plan de lanzamientos',
        'release planning','plan de lanzamiento'
    },
    'sprints de desarrollo': {
        'sprint','sprints','iteraciones','desarrollo','implementation','implementacion'
    },
    'qa/hardening': {
        'qa','quality','calidad','hardening','stabilization','stabilizacion',
        'aceptacion','aceptación','pruebas de aceptación','testing'
    },
    'despliegue & transferencia': {
        'despliegue','release','go-live','produccion','producción','handover',
        'transferencia','salida a produccion','salida a producción'
    },
    'descubrimiento & diseño': {
        'descubrimiento','discovery','diseño','diseno','design'
    }
}

def _norm_simple(s: str) -> str:
    t = (s or '').lower().strip()
    return t.translate(str.maketrans("áéíóúüñ", "aeiouun"))

def _phase_tokens(s: str) -> List[str]:
    return re.findall(r"[a-z0-9/]+", _norm_simple(s))

def _match_phase_name(query: str, proposal: Optional[Dict[str, Any]]) -> Optional[str]:
    tq = _norm_simple(query)

    def score(a: str, b: str) -> float:
        sa, sb = set(_phase_tokens(a)), set(_phase_tokens(b))
        return (len(sa & sb) / len(sa | sb)) if (sa and sb) else 0.0

    # 1) intentar casar con fases de la propuesta actual
    best, best_score = None, 0.0
    if proposal:
        for ph in proposal.get('phases', []):
            name = ph.get('name', '')
            sc = max(score(tq, name), score(name, tq))
            if sc > best_score:
                best, best_score = name, sc
            if _norm_simple(name) in tq or tq in _norm_simple(name):
                best, best_score = name, 1.0
                break

    # 2) si no hay match claro, usar alias/canon
    for canon, aliases in _PHASE_CANON.items():
        for a in aliases:
            if a in tq:
                if proposal:
                    for ph in proposal.get('phases', []):
                        if canon.split()[0] in _norm_simple(ph.get('name', '')):
                            return ph['name']
                return canon.title()

    return best

def _explain_specific_phase(asked: str, proposal: Optional[Dict[str, Any]]) -> str:
    method = (proposal or {}).get('methodology', 'Scrum')
    name = _match_phase_name(asked, proposal) or asked.title()
    n = _norm_simple(name)

    def block(title: str, bullets: List[str]) -> str:
        return f"**{title}:**\n- " + "\n- ".join(bullets)

    # Incepción / Plan de releases / Discovery
    if any(k in n for k in ['incepcion','inception','discovery','plan','inicio','kickoff']):
        return "\n\n".join([
            f"**{name}** — descripción detallada",
            block("Objetivo", [
                "Alinear visión, alcance y riesgos.",
                "Definir roadmap y criterios de éxito (DoR/DoD).",
                "Acordar governance, cadencia y Definition of Ready."
            ]),
            block("Entregables", [
                "Mapa de alcance y priorización.",
                "Plan de releases inicial y milestones.",
                "Backlog inicial con épicas/historias y riesgos identificados."
            ]),
            block("Buenas prácticas", [
                "Workshops con stakeholders.",
                "Decisiones visibles (ADR).",
                "Políticas de entrada al flujo/sprint claras."
            ]),
            block("KPIs", [
                "Claridad de alcance consensuada.",
                "Riesgos y supuestos registrados.",
                "Aprobación de stakeholders."
            ]),
            f"Metodología actual: **{method}**."
        ])

    # Sprints / Iteraciones / Desarrollo
    if any(k in n for k in ['sprint','iteracion','desarrollo']):
        cad = "2 semanas" if method in ("Scrum", "XP", "Scrumban") else "flujo continuo"
        return "\n\n".join([
            f"**{name}** — descripción detallada",
            block("Objetivo", [
                "Entregar valor incremental con feedback frecuente.",
                "Mantener calidad interna alta."
            ]),
            block("Entregables", [
                "Incremento potencialmente desplegable.",
                "Código revisado y probado.",
                "Demo/Review con stakeholders."
            ]),
            block("Buenas prácticas", [
                f"Cadencia de {cad} con límites WIP razonables.",
                "Pairing/PRs, definición de 'hecho' compartida.",
                "Backlog refinado."
            ]),
            block("KPIs", [
                "Lead time / cycle time.",
                "Velocidad estable.",
                "Baja tasa de defectos por iteración."
            ]),
            f"Metodología actual: **{method}**."
        ])

    # QA / Hardening / Estabilización
    if any(k in n for k in ['qa','hardening','stabiliz','aceptacion','testing']):
        return "\n\n".join([
            f"**{name}** — descripción detallada",
            block("Objetivo", [
                "Reducir defectos y riesgo operativo antes del release.",
                "Validar criterios de aceptación, performance y seguridad."
            ]),
            block("Entregables", [
                "Plan de pruebas ejecutado y evidencias.",
                "Pruebas de carga y seguridad.",
                "Issues críticos cerrados."
            ]),
            block("Buenas prácticas", [
                "Automatización de regresión/UI.",
                "Ambiente staging 'production-like'.",
                "Control de cambios (code freeze) acotado."
            ]),
            block("KPIs", [
                "Tasa de defectos abierta/cerrada.",
                "Cobertura de pruebas.",
                "Resultados de performance."
            ]),
            f"Metodología actual: **{method}**."
        ])

    # Despliegue / Release / Handover
    if any(k in n for k in ['despliegue','release','produccion','handover','transferencia','go-live','salida']):
        return "\n\n".join([
            f"**{name}** — descripción detallada",
            block("Objetivo", [
                "Poner el incremento en producción de forma segura.",
                "Transferir conocimiento a Operaciones/cliente."
            ]),
            block("Entregables", [
                "Checklist de release completado.",
                "Plan de rollback y comunicación.",
                "Documentación operativa y formación."
            ]),
            block("Buenas prácticas", [
                "Deploy gradual / feature flags.",
                "Observabilidad y alertas activas.",
                "Postmortem ligero si hay incidencias."
            ]),
            block("KPIs", [
                "Tiempo de recuperación (MTTR).",
                "Incidentes post-release.",
                "Adopción del usuario final."
            ]),
            f"Metodología actual: **{method}**."
        ])

    # Genérico
    return "\n\n".join([
        f"**{name}** — descripción detallada",
        block("Objetivo", [
            "Contribuir al resultado del proyecto bajo el enfoque seleccionado."
        ]),
        block("Entregables", [
            "Artefactos definidos para cerrar la fase.",
            "Riesgos mitigados y decisiones registradas."
        ]),
        block("Buenas prácticas", [
            "Definir criterios de entrada/salida.",
            "Visibilidad del trabajo y deudas."
        ]),
        f"Metodología actual: **{method}**."
    ])

def _explain_budget(proposal: Dict[str, Any]) -> List[str]:
    b = proposal["budget"]
    return [
        "Estimación = (headcount_equivalente × semanas × tarifa_media/rol).",
        "Se añade un 10% de contingencia para incertidumbre técnica/alcance.",
        f"Total estimado: {b['total_eur']} € (labor {b['labor_estimate_eur']} € + contingencia {b['contingency_10pct']} €)."
    ]

def _explain_budget_breakdown(proposal: Dict[str, Any]) -> List[str]:
    """
    Desglose máximo del presupuesto:
    - Por rol (FTE × tarifa/semana × semanas por fase y % del total de labor)
    - Por fase (suma de todos los roles + %)
    - Matriz rol × fase (importe por celda)
    - Asignación proporcional de la contingencia por rol y por fase
    - Tareas, personal (en € aprox.) y programas/recursos por fase, en función del nombre de la fase/metodología
    """
    p = proposal or {}
    b = p.get("budget", {}) or {}
    ass = b.get("assumptions", {}) or {}
    rates: Dict[str, float] = ass.get("role_rates_eur_pw", {}) or {}
    team: List[Dict[str, Any]] = p.get("team", []) or []
    phases: List[Dict[str, Any]] = p.get("phases", []) or []

    # Semanas totales: assumptions.project_weeks o suma de fases (fallback 1)
    weeks_total = int(ass.get("project_weeks") or sum(int(ph.get("weeks", 0)) for ph in phases) or 1)
    if not phases:
        phases = [{"name": "Proyecto", "weeks": weeks_total}]

    # FTE por rol
    role_to_fte = {str(r.get("role", "")).strip(): float(r.get("count", 0.0)) for r in team if str(r.get("role", "")).strip()}

    # Cálculos
    per_role: Dict[str, float] = {}
    per_phase: Dict[str, float] = {ph["name"]: 0.0 for ph in phases}
    matrix: Dict[str, Dict[str, float]] = {role: {ph["name"]: 0.0 for ph in phases} for role in role_to_fte}

    labor = 0.0
    for role, fte in role_to_fte.items():
        rate = float(rates.get(role, 1000.0))  # valor por defecto
        role_total = 0.0
        for ph in phases:
            w = int(ph.get("weeks", 0)) or 0
            cell = fte * rate * w
            matrix[role][ph["name"]] = cell
            per_phase[ph["name"]] += cell
            role_total += cell
        per_role[role] = role_total
        labor += role_total

    contingency_pct = float(ass.get("contingency_pct", 10.0))
    contingency_eur = labor * contingency_pct / 100.0
    total = labor + contingency_eur
# ====== staffing: parseo y matching ======

# Palabras clave por rol para puntuar habilidades
_ROLE_KEYWORDS = {
    "Backend Dev": ["api", "rest", "graphql", "python", "java", "node", "spring", "django", "fastapi", "sql", "postgres", "aws", "gcp", "azure", "seguridad"],
    "Frontend Dev": ["react", "vue", "angular", "typescript", "javascript", "css", "accesibilidad", "redux", "next", "vite"],
    "QA": ["qa", "testing", "pruebas", "e2e", "automat", "cypress", "playwright", "jest", "pytest", "regresion", "performance", "seguridad"],
    "Tech Lead": ["arquitect", "design", "estandares", "review", "mentoria", "lider", "solucion"],
    "PM": ["plan", "alcance", "prioridad", "stakeholder", "roadmap", "reporte", "cadencia"],
    "Product Owner": ["producto", "backlog", "prioridad", "historias", "aceptacion"],
    "DevOps": ["ci", "cd", "docker", "kubernetes", "k8s", "terraform", "aws", "gcp", "azure", "observabilidad", "prometheus", "grafana", "pipelines", "sre"],
    "UX/UI": ["ux", "ui", "figma", "research", "prototip", "usabilidad", "wireframe", "dise"],
    "ML Engineer": ["ml", "modelo", "pytorch", "tensorflow", "sklearn", "serving", "mlo"],
    "Data": ["etl", "elt", "sql", "warehouse", "dbt", "bigquery", "redshift", "spark"],
    "Mobile Dev": ["android", "kotlin", "swift", "react native", "flutter"]
}

def _parse_staff_list(text: str) -> List[Dict[str, Any]]:
    """
    Formato flexible (una o varias líneas):
    Nombre — Rol — Skills clave — Seniority — Disponibilidad%
    Separadores admitidos: —  -  |  :    (los items pueden venir en una sola línea: '- Ana — ... - Luis — ...')
    """
    # 1) Trocear en items (por líneas o bullets dentro de una misma línea)
    raw_lines: List[str] = []
    for ln in text.strip().splitlines() or [text.strip()]:
        ln = ln.strip()
        if not ln:
            continue
        # Si hay varios items en una misma línea, dividir por bullets ' - ' / ' • ' / ';'
        if re.search(r"\s[-•]\s+", ln) or ";" in ln:
            parts = re.split(r"\s[-•]\s+|;", ln)
            raw_lines += [p.strip() for p in parts if p.strip()]
        else:
            raw_lines.append(ln)

    staff: List[Dict[str, Any]] = []
    for raw in raw_lines:
        ln = raw.strip().lstrip("•*- ").strip()
        if not ln or "—" not in ln:
            # Acepta otros separadores si no vino '—'
            ln = re.sub(r"\s[-|:]\s", " — ", ln)
            if "—" not in ln:
                continue
        parts = re.split(r"\s*—\s*", ln)
        if len(parts) < 2:
            continue
        name = parts[0].strip()
        role = _canonical_role(parts[1])
        rest = " — ".join(parts[2:]) if len(parts) > 2 else ""
        # disponibilidad %
        m = re.search(r"(\d{1,3})\s*%", rest)
        availability = min(100, int(m.group(1))) if m else 100
        # seniority
        seniority = None
        for key in ["principal", "lead", "senior", "sr", "semi senior", "ssr", "mid", "jr", "junior"]:
            if key in _norm(rest):
                seniority = key
                break
        # skills
        skills = [s.strip() for s in re.split(r",|/|\|", rest) if s.strip()]
        # fallback si no hay comas
        if not skills:
            skills = re.findall(r"[a-zA-Z0-9+#/.]{2,}", rest)
        staff.append({"name": name, "role": role, "skills": skills, "availability_pct": availability, "seniority": seniority})
    return staff


def _score_staff_for_role(role: str, person: Dict[str, Any]) -> float:
    score = 0.0
    if _canonical_role(person.get("role", "")) == role:
        score += 4.0
    kws = _ROLE_KEYWORDS.get(role, [])
    hay = _norm(" ".join(person.get("skills", [])) + " " + (person.get("seniority") or ""))
    for kw in kws:
        if _norm(kw) in hay:
            score += 0.5
    s = _norm(person.get("seniority") or "")
    if "principal" in s or "lead" in s: score += 2.0
    elif "senior" in s or "sr" in s:     score += 1.2
    elif "junior" in s or "jr" in s:     score += 0.2
    avail = max(0.5, min(1.2, float(person.get("availability_pct", 100)) / 100.0))
    return score * avail
def _matched_keywords(role: str, person: Dict[str, Any]) -> List[str]:
    kws = _ROLE_KEYWORDS.get(role, [])
    hay = _norm((" ".join(person.get("skills", [])) + " " + (person.get("seniority") or "")).strip())
    out = []
    for kw in kws:
        if _norm(kw) in hay:
            # Devuelve la forma original si estaba en skills; si no, el kw
            hit = next((s for s in person.get("skills", []) if _norm(s) == _norm(kw)), kw)
            if hit not in out:
                out.append(hit)
    return out[:5]

def _why_person_for_role(role: str, person: Dict[str, Any]) -> str:
    matches = _matched_keywords(role, person)
    s = person.get("seniority") or ""
    a = person.get("availability_pct", 100)
    bits = []
    if matches:
        bits.append(f"skills afines ({', '.join(matches)})")
    if s:
        bits.append(f"seniority {s}")
    if a != 100:
        bits.append(f"disponibilidad {a}%")
    if _canonical_role(person.get("role","")) == role and not matches:
        bits.append("rol declarado coincide")
    return "; ".join(bits) or "perfil compatible con el rol"

def _phase_key(name: str) -> str:
    t = _norm(name)
    if any(k in t for k in ["discover", "dise", "kickoff", "plan"]): return "discovery"
    if any(k in t for k in ["sprint", "iterac", "kanban", "desarrollo", "build"]): return "build"
    if any(k in t for k in ["qa", "hardening", "stabil"]): return "qa"
    if any(k in t for k in ["release", "handover", "desplieg", "produ"]): return "release"
    return "generic"

_PHASE_ROLES = {
    "discovery": ["PM", "Product Owner", "Tech Lead", "UX/UI"],
    "build": ["Backend Dev", "Frontend Dev", "Mobile Dev", "DevOps", "QA", "Tech Lead"],
    "qa": ["QA", "DevOps", "Backend Dev", "Frontend Dev"],
    "release": ["DevOps", "Tech Lead", "PM"],
    "generic": ["PM", "Tech Lead", "QA", "Backend Dev", "Frontend Dev"]
}

def _suggest_staffing(proposal: Dict[str, Any], staff: List[Dict[str, Any]]) -> List[str]:
    """
    Devuelve asignación recomendada:
    - Por rol (mejor persona y por qué)
    - Por fase (mejor persona para cada rol esperado en esa fase) con breve justificación
    """
    roles_needed = [r.get("role") for r in proposal.get("team", []) if r.get("role")]
    lines: List[str] = []

    # — Por rol
    lines.append("**Asignación por rol (mejor persona y por qué)**")
    if not roles_needed:
        lines.append("- (La propuesta no tiene equipo definido todavía).")
    for role in roles_needed:
        if not staff:
            lines.append(f"- {role}: (no hay candidatos cargados)")
            continue
        cands = sorted(staff, key=lambda p: _score_staff_for_role(role, p), reverse=True)
        best = cands[0]
        why = _why_person_for_role(role, best)
        s = (best.get("seniority") or "").strip()
        a = best.get("availability_pct", 100)
        extra = f" ({s}, {a}%)" if s or a != 100 else ""
        lines.append(f"- {role}: {best['name']}{extra} → {why}")
        # alternativas rápidas (sin explicación para no saturar)
        alt = [c["name"] for c in cands[1:3]]
        if alt:
            lines.append(f"  · Alternativas: {', '.join(alt)}")

    # — Por fase
    lines.append("")
    lines.append("**Asignación sugerida por fase/tareas**")
    for ph in proposal.get("phases", []):
        pk = _phase_key(ph.get("name", ""))
        expected = [r for r in _PHASE_ROLES.get(pk, []) if r in roles_needed]
        if not expected:
            continue
        lines.append(f"- {ph.get('name','')}:")
        for role in expected:
            cands = sorted(staff, key=lambda p: _score_staff_for_role(role, p), reverse=True)
            if not cands:
                lines.append(f"  • {role}: (sin candidatos)")
                continue
            best = cands[0]
            why = _why_person_for_role(role, best)
            s = (best.get("seniority") or "").strip()
            a = best.get("availability_pct", 100)
            extra = f" ({s}, {a}%)" if s or a != 100 else ""
            lines.append(f"  • {role} → {best['name']}{extra}: {why}")
    return lines
# ====== GAPS & FORMACIÓN ======

_TRAINING_CATALOG = {
    "cypress": ["Cypress fundamentals (oficial)", "Curso E2E con Cypress", "Guía de patrones de test E2E"],
    "playwright": ["Playwright intro (MS)", "Playwright testing cookbook"],
    "tdd": ["TDD by example (K. Beck)", "Katas TDD (cyber-dojo)"],
    "owasp": ["OWASP Top 10 (oficial)", "Cheat Sheets OWASP"],
    "pci": ["PCI-DSS overview", "Stripe Radar & antifraude"],
    "stripe": ["Stripe Payments (docs)", "Idempotency keys (Stripe)"],
    "kubernetes": ["Kubernetes fundamentals (CKAD)", "K8s Hands-on Labs"],
    "terraform": ["Terraform up & running", "Oficial HashiCorp - intro"],
    "observability": ["Prometheus + Grafana (labs)", "OpenTelemetry 101"],
    "react": ["React beta docs", "React Testing Library"],
    "typescript": ["TS handbook", "Tipos avanzados para React"],
    "django": ["Django tutorial oficial", "DRF guía práctica"],
    "fastapi": ["FastAPI docs", "Pydantic patterns"],
    "spring": ["Spring Boot guides", "Spring Security basics"],
    "node": ["Node + Express docs", "Pruebas con Jest/Supertest"],
    "postgres": ["PostgreSQL performance", "Migrations & índices"],
    "ci/cd": ["GitHub Actions (oficial)", "GitLab CI pipelines"],
    "performance": ["k6/Locust intro", "Rendimiento web (MDN)"]
}

# temas "must" inferidos por stack/dominio/fases/metodología
def _infer_required_topics(proposal: Dict[str, Any]) -> List[str]:
    req = set()
    st = (proposal.get("stack") or {})
    meth = _norm(proposal.get("methodology", ""))
    if st:
        s = _norm(" ".join(f"{k}:{v}" for k, v in st.items()))
        if "aws" in s or "gcp" in s or "azure" in s:
            req.update(["kubernetes", "terraform", "observability", "ci/cd"])
        if "react" in s or "frontend" in s:
            req.update(["react", "typescript", "ci/cd"])
        if "django" in s or "fastapi" in s:
            req.update(["django", "fastapi", "ci/cd"])
        if "spring" in s or "java" in s:
            req.update(["spring", "ci/cd"])
        if "node" in s:
            req.update(["node", "ci/cd"])
        if "postgres" in s:
            req.add("postgres")
    # Riesgos/dominio conocidos
    risks = " ".join(_norm(r) for r in proposal.get("risks", []))
    if any(k in risks for k in ["pci", "fraude", "chargeback"]):
        req.update(["pci", "stripe", "owasp"])
    # QA y seguridad siempre aparecen en hardening
    if any("qa" in _norm(ph.get("name", "")) or "hardening" in _norm(ph.get("name", "")) for ph in proposal.get("phases", [])):
        req.update(["cypress", "playwright", "owasp", "performance"])
    # XP/Scrum → calidad interna
    if "xp" in meth or "scrum" in meth:
        req.add("tdd")
    return sorted(req)

def _person_has_topic(person: Dict[str, Any], topic: str) -> bool:
    blob = _norm(" ".join(person.get("skills", [])) + " " + (person.get("seniority") or "") + " " + (person.get("role") or ""))
    return _norm(topic) in blob

def _closest_upskilling_candidates(staff: List[Dict[str, Any]], topic: str) -> List[Dict[str, Any]]:
    # heurística simple: rol más cercano + seniority + disponibilidad
    def proximity(p: Dict[str, Any]) -> float:
        r = _canonical_role(p.get("role", ""))
        s = _norm(p.get("seniority") or "")
        base = 0.0
        if topic in ("cypress", "playwright", "tdd", "owasp", "performance"):
            # QA/Dev enfoque
            if r in ("QA", "Backend Dev", "Frontend Dev"): base += 1.0
        if topic in ("kubernetes", "terraform", "observability", "ci/cd"):
            if r in ("DevOps", "Tech Lead", "Backend Dev"): base += 1.0
        if topic in ("react", "typescript"):
            if r == "Frontend Dev": base += 1.0
        if topic in ("django", "fastapi", "spring", "node", "postgres"):
            if r in ("Backend Dev", "Tech Lead"): base += 1.0
        if "lead" in s or "principal" in s or "senior" in s: base += 0.5
        base *= max(0.3, float(p.get("availability_pct", 100)) / 100.0)
        # bonus si ya aparece el tema de forma parcial en skills
        if _person_has_topic(p, topic): base += 1.0
        return base
    return sorted(staff, key=proximity, reverse=True)[:3]

def _analyze_skill_gaps(proposal: Dict[str, Any], staff: List[Dict[str, Any]]) -> Dict[str, Any]:
    topics = _infer_required_topics(proposal)
    present = {t: any(_person_has_topic(p, t) for p in staff) for t in topics}
    gaps = [t for t, ok in present.items() if not ok]
    findings = []
    for g in gaps:
        cands = _closest_upskilling_candidates(staff, g)
        resources = _TRAINING_CATALOG.get(g, [])[:2]
        findings.append({
            "topic": g,
            "why": f"Necesario por stack/dominio/fases (p.ej., {proposal.get('methodology','')}).",
            "upskill_candidates": [{"name": c["name"], "role": c.get("role",""), "availability_pct": c.get("availability_pct",100)} for c in cands],
            "resources": resources,
            "external_hint": "Refuerzo externo 0.5 FTE durante 2–4 semanas si no hay disponibilidad interna."
        })
    return {"topics": topics, "gaps": findings}

def _render_training_plan(proposal: Dict[str, Any], staff: List[Dict[str, Any]]) -> List[str]:
    report = _analyze_skill_gaps(proposal, staff)
    lines: List[str] = []
    if not report["topics"]:
        return ["(No detecto temas críticos a partir del stack/metodología actual.)"]
    lines.append("**Gaps detectados & plan de formación**")
    if not report["gaps"]:
        lines.append("- ✔︎ No hay carencias relevantes respecto al stack/metodología.")
        return lines
    for g in report["gaps"]:
        lines.append(f"- **{g['topic']}** — {g['why']}")
        if g["upskill_candidates"]:
            who = ", ".join(f"{c['name']} ({c['role']} {c['availability_pct']}%)" for c in g["upskill_candidates"])
            lines.append(f"  • Upskilling recomendado: {who}")
        if g["resources"]:
            lines.append(f"  • Recursos: " + " | ".join(g["resources"]))
        lines.append(f"  • Alternativa: {g['external_hint']}")
    return lines

    def _pct(x: float, base: float) -> float:
        return (100.0 * x / base) if base else 0.0

    def _eur(x: float) -> str:
        return f"{x:.2f} €"

    # Arquetipos de fase → tareas/recursos (por nombre)
    def phase_key(n: str) -> str:
        t = n.lower()
        if any(k in t for k in ["discover", "dise", "crc", "inception", "inicio", "kickoff"]): return "discovery"
        if any(k in t for k in ["sprint", "iterac", "kanban", "flujo", "desarrollo"]): return "build"
        if any(k in t for k in ["qa", "hardening", "stabil"]): return "qa"
        if any(k in t for k in ["release", "handover", "deploy", "despliegue", "produ"]): return "release"
        return "generic"

    TASKS = {
        "discovery": [
            "Workshops con stakeholders/usuarios",
            "Historias y tarjetas CRC; alcance/priorización",
            "Arquitectura objetivo y decisiones (ADR)",
            "Plan de releases/milestones; DoR/DoD"
        ],
        "build": [
            "Backend (APIs/domino/seguridad)",
            "Frontend/App (UI/estado/accesibilidad)",
            "Integraciones (pagos/terceros/notificaciones)",
            "Revisiones de código, pairing y refactor con TDD/CI"
        ],
        "qa": [
            "Plan/Estrategia de pruebas y evidencias",
            "Automatización (regresión/E2E)",
            "Performance y seguridad (no-funcionales)",
            "Cierre de defectos críticos"
        ],
        "release": [
            "Empaquetado y orquestación de despliegue",
            "Observabilidad: logging, métricas, alertas",
            "Comunicación/rollback y verificación en vivo",
            "Transferencia de conocimiento (runbooks)"
        ],
        "generic": [
            "Actividades específicas para el objetivo de la fase",
            "Sincronización con stakeholders y control de riesgos"
        ],
    }

    RESOURCES = {
        "discovery": ["Miro/Mural", "Confluence/Notion", "Jira/YouTrack", "C4/ADR"],
        "build": ["GitHub/GitLab", "CI (Actions/GitLab CI)", "Docker", "Kubernetes", "Postman", "Sentry"],
        "qa": ["JUnit/PyTest/Cypress/Playwright", "k6/Locust", "OWASP ZAP", "SonarQube"],
        "release": ["ArgoCD/FluxCD", "Terraform/CloudFormation", "Prometheus/Grafana", "Feature Flags"],
        "generic": ["Herramientas de gestión y repositorio de código"],
    }

    lines: List[str] = []
    lines.append("Presupuesto — **desglose máximo**")
    lines.append("")
    lines.append(f"Labor: {_eur(labor)}   •   Contingencia ({contingency_pct:.1f}%): {_eur(contingency_eur)}   •   Total: {_eur(total)}")
    lines.append("")

    # 1) Por roles
    lines.append("**Distribución por roles**:")
    if per_role:
        for role, amount in sorted(per_role.items(), key=lambda kv: kv[1], reverse=True):
            fte = role_to_fte.get(role, 0.0)
            rate = float(rates.get(role, 1000.0))
            lines.append(f"- {role}: {fte:g} FTE × {rate:.0f} €/sem × {weeks_total} sem → {_eur(amount)} ({_pct(amount, labor):.1f}%)")
    else:
        lines.append("- (No hay equipo definido; añade roles para una estimación precisa.)")

    # 2) Por fases
    lines.append("")
    lines.append("**Distribución por fases**:")
    for ph_name, amount in sorted(per_phase.items(), key=lambda kv: kv[1], reverse=True):
        w = next((int(ph.get("weeks", 0)) for ph in phases if ph["name"] == ph_name), 0)
        lines.append(f"- {ph_name} ({w}s): {_eur(amount)} ({_pct(amount, labor):.1f}%)")

    # 3) Matriz rol × fase
    lines.append("")
    lines.append("**Matriz rol × fase**:")
    any_cell = False
    for role, cells in matrix.items():
        parts = [f"{ph['name']}: {_eur(cells.get(ph['name'], 0.0))}" for ph in phases if cells.get(ph['name'], 0.0) > 0.0]
        if parts:
            lines.append(f"- {role}: " + " • ".join(parts))
            any_cell = True
    if not any_cell:
        lines.append("- (Sin celdas con importe; revisa FTE, tarifas o semanas).")

    # 4) Contingencia asignada
    lines.append("")
    lines.append(f"**Contingencia** {contingency_pct:.1f}% → {_eur(contingency_eur)} (asignación proporcional):")
    if labor > 0:
        lines.append("• Por **rol**: " + ", ".join(f"{r} {_eur(contingency_eur * (v/labor))}" for r, v in sorted(per_role.items(), key=lambda kv: kv[1], reverse=True)))
        lines.append("• Por **fase**: " + ", ".join(f"{ph} {_eur(contingency_eur * (v/labor))}" for ph, v in sorted(per_phase.items(), key=lambda kv: kv[1], reverse=True)))
    else:
        lines.append("• (No hay labor para distribuir.)")

    # 5) Tareas, personal y recursos por fase
    lines.append("")
    lines.append("**Tareas, personal y recursos por fase**:")
    for ph in phases:
        ph_name = ph.get("name", "")
        ph_cost = per_phase.get(ph_name, 0.0)
        key = phase_key(ph_name)
        task_list = TASKS.get(key, TASKS["generic"])
        res_list = RESOURCES.get(key, RESOURCES["generic"])
        # Top 3 roles con mayor peso en la fase
        top_roles = sorted(((r, matrix[r][ph_name]) for r in matrix), key=lambda kv: kv[1], reverse=True)[:3]
        lines.append(f"- {ph_name} — {_eur(ph_cost)}:")
        if any(v > 0 for _, v in top_roles):
            lines.append("  • Personal implicado: " + ", ".join(f"{r} {_eur(v)}" for r, v in top_roles if v > 0))
        lines.append("  • Tareas principales: " + "; ".join(task_list))
        lines.append("  • Programas/recursos: " + ", ".join(res_list))

    return lines


def _expand_risks(requirements: Optional[str], methodology: Optional[str]) -> List[str]:
    t = _norm(requirements or "")
    risks: List[str] = [
        "Cambios de alcance sin prioridad",
        "Dependencias externas",
        "Datos insuficientes para pruebas de rendimiento/escalado"
    ]
    if "pagos" in t or "stripe" in t:
        risks += ["Cumplimiento PCI-DSS y fraude", "Reintentos e idempotencia en cobros"]
    if "admin" in t or "panel" in t:
        risks += ["RBAC, auditoría y hardening en backoffice"]
    if "mobile" in t or "ios" in t or "android" in t or "app" in t:
        risks += ["Aprobación en tiendas y compatibilidad de dispositivos"]
    if "tiempo real" in t or "realtime" in t or "websocket" in t:
        risks += ["Latencia y picos → colas/cachés"]
    if "ml" in t or "ia" in t or "modelo" in t:
        risks += ["Calidad de datos, sesgo y drift de modelos"]
    if methodology == "Scrum":
        risks += ["Scope creep si DoR/DoD no están claros"]
    if methodology == "Kanban":
        risks += ["Multitarea si no se respetan límites de WIP"]
    return risks


# ====== detectar metodologías mencionadas ======
_METHOD_TOKENS = [
    "scrum","kanban","scrumban","xp","extreme programming","lean",
    "crystal","crystal clear","fdd","feature driven development",
    "dsdm","safe","scaled agile","devops"
]

def _mentioned_methods(text: str) -> List[str]:
    t = _norm(text)
    found: List[str] = []
    for raw in _METHOD_TOKENS:
        if raw in t:
            m = normalize_method_name(raw)
            if m not in found:
                found.append(m)
    return found


# ---------- helpers de catálogo/definiciones ----------

def _one_liner_from_info(info: Dict[str, Any], default_name: str) -> str:
    # resumen corto
    for k in ("resumen", "overview", "descripcion", "description"):
        if isinstance(info.get(k), str) and info[k].strip():
            s = info[k].strip()
            cut = s.find(".")
            return (s if cut == -1 else s[:cut+1]).strip()
    pract = info.get("practicas_clave") or info.get("practicas") or []
    fit = info.get("encaja_bien_si") or info.get("fit") or []
    if pract:
        return f"Marco {default_name} con prácticas clave: " + ", ".join(pract[:3]) + "."
    if fit:
        return f"Buena opción cuando: " + "; ".join(fit[:2]) + "."
    return f"Marco {default_name} para gestionar desarrollo ágil."

def _method_overview_text(method: str) -> str:
    """Ficha resumida de una metodología + fuentes."""
    info = METHODOLOGIES.get(method, {})
    lines = [f"**{method}** — ¿qué es y cuándo usarla?"]
    lines.append(_one_liner_from_info(info, method))
    pract = info.get("practicas_clave") or info.get("practicas") or []
    if pract:
        lines.append("**Prácticas clave:** " + ", ".join(pract))
    fit = info.get("encaja_bien_si") or info.get("fit") or []
    if fit:
        lines.append("**Encaja bien si:** " + "; ".join(fit))
    avoid = info.get("evitar_si") or info.get("avoid") or []
    if avoid:
        lines.append("**Evitar si:** " + "; ".join(avoid))
    src = info.get("sources") or []
    if src:
        lines.append("**Fuentes:**\n" + _format_sources(src))
    return "\n".join(lines)

def _catalog_text() -> str:
    """Lista todas las metodologías soportadas con un renglón de resumen cada una."""
    names = sorted(METHODOLOGIES.keys())
    bullets = []
    for name in names:
        bullets.append(f"- **{name}** — {_one_liner_from_info(METHODOLOGIES.get(name, {}), name)}")
    return "Metodologías que manejo:\n" + "\n".join(bullets) + "\n\n¿Quieres que te explique alguna en detalle o que recomiende la mejor para tu caso?"


# ====== detección de petición de cambio de metodología ======
_CHANGE_PAT = re.compile(
    r"(?:cambia(?:r)?\s+a|usar|quiero|prefiero|pasar\s+a)\s+(scrum|kanban|scrumban|xp|lean|crystal|fdd|dsdm|safe|devops)"
    r"(?:\s+(?:en\s+vez\s+de|en\s+lugar\s+de)\s+(scrum|kanban|scrumban|xp|lean|crystal|fdd|dsdm|safe|devops))?",
    re.I
)

def _parse_change_request(text: str) -> Optional[Tuple[str, Optional[str]]]:
    t = _norm(text)
    m = _CHANGE_PAT.search(t)
    if m:
        tgt = normalize_method_name(m.group(1))
        alt = normalize_method_name(m.group(2)) if m.group(2) else None
        return tgt, alt
    m2 = re.search(
        r"(scrum|kanban|scrumban|xp|lean|crystal|fdd|dsdm|safe|devops)\s+(?:en\s+vez\s+de|en\s+lugar\s+de)\s+"
        r"(scrum|kanban|scrumban|xp|lean|crystal|fdd|dsdm|safe|devops)", t)
    if m2:
        a = normalize_method_name(m2.group(1))
        b = normalize_method_name(m2.group(2))
        return a, b
    return None

def _retune_plan_for_method(p: Dict[str, Any], method: str) -> Dict[str, Any]:
    """Ajuste ligero de plan al forzar una metodología."""
    p = dict(p)
    p["methodology"] = method
    info = METHODOLOGIES.get(method, {})
    p["methodology_sources"] = info.get("sources", [])

    phases = []
    if method == "Kanban":
        phases = [
            {"name": "Descubrimiento & Diseño", "weeks": 2},
            {"name": "Implementación flujo continuo (WIP/Columnas)", "weeks": max(2, p["phases"][1]["weeks"]) if p.get("phases") else 4},
            {"name": "QA continuo & Observabilidad", "weeks": 2},
            {"name": "Estabilización & Puesta en Producción", "weeks": 1},
        ]
    elif method == "XP":
        phases = [
            {"name": "Discovery + Historias & CRC", "weeks": 2},
            {"name": "Iteraciones con TDD/Refactor/CI", "weeks": max(4, p["phases"][1]["weeks"]) if p.get("phases") else 6},
            {"name": "Hardening & Pruebas de Aceptación", "weeks": 2},
            {"name": "Release & Handover", "weeks": 1},
        ]
    elif method == "Scrum":
        phases = [
            {"name": "Incepción & Plan de Releases", "weeks": 2},
            {"name": "Sprints de Desarrollo (2w)", "weeks": max(4, p["phases"][1]["weeks"]) if p.get("phases") else 6},
            {"name": "QA/Hardening Sprint", "weeks": 2},
            {"name": "Despliegue & Transferencia", "weeks": 1},
        ]
    else:
        phases = p.get("phases", [])
    if phases:
        p["phases"] = phases
    # si cambian fases, hay que recalcular presupuesto
    p = _recompute_budget(p)
    return p


# ===================== NUEVO: cambios sobre toda la propuesta =====================

_PATCH_PREFIX = "__PATCH__:"

def _total_weeks(p: Dict[str, Any]) -> int:
    return sum(int(ph.get("weeks", 0)) for ph in p.get("phases", []))

def _fte_sum(p: Dict[str, Any]) -> float:
    return float(sum(float(r.get("count", 0)) for r in p.get("team", [])))

def _get_rate_map(p: Dict[str, Any]) -> Dict[str, float]:
    return (p.get("budget", {}).get("assumptions", {}).get("role_rates_eur_pw", {}) or {})

def _evaluate_patch(proposal: Dict[str, Any], patch: Dict[str, Any], req_text: Optional[str]) -> Tuple[str, str]:
    """
    Devuelve (texto_evaluacion, etiqueta_veredicto)
    etiqueta_veredicto ∈ {'buena', 'neutra', 'mala'}
    """
    before = copy.deepcopy(proposal)
    after = _apply_patch(proposal, patch)  # no muta 'proposal'

    def add_line(s: str, buf: List[str]): buf.append(s)

    w0 = _total_weeks(before)
    w1 = _total_weeks(after)
    f0 = _fte_sum(before)
    f1 = _fte_sum(after)

    b0 = float(before.get("budget", {}).get("total_eur", 0.0))
    b1 = float(after.get("budget", {}).get("total_eur", 0.0))
    labor0 = float(before.get("budget", {}).get("labor_estimate_eur", 0.0))
    labor1 = float(after.get("budget", {}).get("labor_estimate_eur", 0.0))
    cont_pct = float(after.get("budget", {}).get("assumptions", {}).get("contingency_pct",
                        before.get("budget", {}).get("assumptions", {}).get("contingency_pct", 10)))

    delta_w = w1 - w0
    delta_f = f1 - f0
    delta_cost = round(b1 - b0, 2)

    lines: List[str] = []
    verdict = "neutra"

    t = patch.get("type")
    if t == "team":
        add_line("📌 Evaluación del cambio de **equipo**:", lines)

        # Cobertura de roles críticos y señales de calidad
        roles_before = {r["role"].lower(): float(r["count"]) for r in before.get("team", [])}
        roles_after  = {r["role"].lower(): float(r["count"]) for r in after.get("team", [])}

        def had(role): return roles_before.get(role.lower(), 0.0) > 0.0
        def has(role): return roles_after.get(role.lower(), 0.0) > 0.0

        critical = {"pm": "PM", "tech lead": "Tech Lead", "qa": "QA"}
        critical_removed = [name for key, name in critical.items() if had(key) and not has(key)]
        critical_added   = [name for key, name in critical.items() if not had(key) and has(key)]

        if critical_removed:
            add_line(f"⚠️ Se elimina un rol crítico: {', '.join(critical_removed)} → riesgo de coordinación/calidad.", lines)
        if critical_added:
            add_line(f"✅ Se incorpora rol crítico: {', '.join(critical_added)} → mejora gobernanza/calidad.", lines)

        # Throughput / cuellos de botella
        if delta_f > 0 and delta_w == 0:
            add_line("➕ Más FTE con el mismo timeline → más throughput; potencialmente entregas antes dentro de las mismas semanas.", lines)
        if delta_f < 0 and delta_w == 0:
            add_line("➖ Menos FTE con igual timeline → riesgo de cuello de botella en desarrollo.", lines)

        # Veredicto
        if critical_removed:
            verdict = "mala"
        elif delta_f > 0 and has("qa"):
            verdict = "buena"
        elif delta_f < 0:
            verdict = "mala"
        else:
            verdict = "neutra"

        # ——— Detalle por rol afectado ———
        add_line("", lines)
        add_line("**Detalle por rol propuesto:**", lines)
        changed_any = False
        for rkey in sorted(set(list(roles_before.keys()) + list(roles_after.keys()))):
            old = float(roles_before.get(rkey, 0.0))
            new = float(roles_after.get(rkey, 0.0))
            if old == new:
                continue
            changed_any = True
            role_name = _canonical_role(rkey)
            reasons = _explain_role_count(role_name, new, req_text)
            add_line(f"🔹 Propuesta para **{role_name}**: {old:g} → {new:g} FTE", lines)
            for rs in reasons:
                add_line(f"   • {rs}", lines)
        if not changed_any:
            add_line("-(No hay variaciones de FTE por rol respecto al plan anterior).", lines)

        # ——— Impacto estimado numérico ———
        def eur(x: float) -> str:
            return f"{x:,.2f} €".replace(",", "X").replace(".", ",").replace("X", ".")

        add_line("", lines)
        add_line("📊 **Impacto estimado:**", lines)
        add_line(f"- Semanas totales: {w0} → {w1}  (Δ {delta_w:+})", lines)
        add_line(f"- Headcount equivalente (FTE): {f0:g} → {f1:g}  (Δ {delta_f:+g})", lines)
        add_line(f"- Labor: {eur(labor0)} → {eur(labor1)}  (Δ {eur(labor1 - labor0)})", lines)
        add_line(f"- Total con contingencia ({cont_pct:.0f}%): {eur(b0)} → {eur(b1)}  (Δ {eur(delta_cost)})", lines)

        # ——— Conclusión ———
        add_line("", lines)
        idea = {"buena": "buena idea", "mala": "mala idea", "neutra": "impacto neutro"}[verdict]
        add_line(f"✅ En general: **{idea}** para tu contexto, según heurísticas de calidad/gestión.", lines)

        # Pregunta de confirmación
        add_line("", lines)
        add_line("¿Aplico estos cambios? **sí/no**", lines)

    elif t == "phases":
        # (Sin cambios en esta rama; se mantiene tu lógica actual.)
        add_line("📌 Evaluación del cambio de **fases/timeline**:", lines)
        if delta_w < 0:
            pct = int(abs(delta_w) / (w0 or 1) * 100)
            add_line(f"⚠️ Reduces el timeline en {abs(delta_w)} semanas (~{pct}%). Riesgo de calidad/alcance si no se compensa con más equipo.", lines)
            verdict = "mala" if pct >= 20 else "neutra"
        elif delta_w > 0:
            add_line(f"✅ Aumentas el timeline en {delta_w} semanas → más colchón para QA/estabilización.", lines)
            verdict = "buena"
        else:
            add_line("≈ El número total de semanas no cambia. Impacto neutro salvo por la redistribución interna.", lines)
            verdict = "neutra"

        add_line("", lines)
        add_line("¿Aplico estos cambios? **sí/no**", lines)

    else:
        # Tipos no contemplados
        add_line(f"(Evaluación no implementada para tipo '{t}')", lines)
        verdict = "neutra"

    return "\n".join(lines), verdict


def _make_pending_patch(session_id: str, patch: Dict[str, Any], proposal: Optional[Dict[str, Any]] = None, req_text: Optional[str] = None) -> Tuple[str, str]:
    """Guarda un parche pendiente con evaluación y confirmación sí/no usando el mismo canal pending_change."""
    # Guardamos el parche en pending_change (compat: string con prefijo)
    try:
        set_pending_change(session_id, _PATCH_PREFIX + json.dumps(patch, ensure_ascii=False))
    except Exception:
        set_pending_change(session_id, _PATCH_PREFIX + json.dumps(patch))

    area = patch.get("type", "propuesta")
    summary = _summarize_patch(patch)

    eval_block = ""
    if proposal:
        try:
            eval_text, _ = _evaluate_patch(proposal, patch, req_text)
            eval_block = "\n\n" + eval_text
        except Exception:
            eval_block = "\n\n(Nota: no pude calcular la evaluación automática, pero puedo aplicar el cambio igualmente.)"

    msg = f"Propones cambiar **{area}**:\n{summary}{eval_block}\n\n¿Aplico estos cambios? **sí/no**"
    return msg, f"Parche pendiente ({area})."

def _parse_pending_patch(pending_val: str) -> Optional[Dict[str, Any]]:
    if isinstance(pending_val, str) and pending_val.startswith(_PATCH_PREFIX):
        try:
            return json.loads(pending_val[len(_PATCH_PREFIX):])
        except Exception:
            return None
    return None

def _summarize_patch(patch: Dict[str, Any]) -> str:
    t = patch.get("type")
    if t == "team":
        ops = patch.get("ops", [])
        lines = []
        for op in ops:
            if op["op"] == "set":
                lines.append(f"- {op['role']} → {op['count']} FTE")
            elif op["op"] == "add":
                lines.append(f"- Añadir {op['count']} {op['role']}")
            elif op["op"] == "remove":
                lines.append(f"- Quitar {op['role']}")
        return "\n".join(lines) if lines else "- (sin cambios detectados)"
    if t == "phases":
        ops = patch.get("ops", [])
        lines = []
        for op in ops:
            if op["op"] == "set_weeks":
                lines.append(f"- Fase '{op['name']}' → {op['weeks']} semanas")
            elif op["op"] == "add":
                lines.append(f"- Añadir fase '{op['name']}' ({op['weeks']}s)")
            elif op["op"] == "remove":
                lines.append(f"- Quitar fase '{op['name']}'")
        return "\n".join(lines) if lines else "- (sin cambios detectados)"
    if t == "budget":
        lines = []
        if "contingency_pct" in patch:
            lines.append(f"- Contingencia → {patch['contingency_pct']}%")
        for role, rate in patch.get("role_rates", {}).items():
            lines.append(f"- Tarifa {role} → {rate} €/pw")
        return "\n".join(lines) if lines else "- (sin cambios detectados)"
    if t == "risks":
        lines = []
        for r in patch.get("add", []):
            lines.append(f"- Añadir riesgo: {r}")
        for r in patch.get("remove", []):
            lines.append(f"- Quitar riesgo: {r}")
        return "\n".join(lines) if lines else "- (sin cambios detectados)"
    return "- Cambio genérico a propuesta."

def _recompute_budget(p: Dict[str, Any]) -> Dict[str, Any]:
    """Recalcula presupuesto en base a team, phases y role_rates/contingencia."""
    p = copy.deepcopy(p)
    phases = p.get("phases", [])
    team = p.get("team", [])
    budget = p.get("budget", {}) or {}
    ass = budget.get("assumptions", {}) or {}
    role_rates = ass.get("role_rates_eur_pw", {}) or {
        "PM": 1200.0, "Tech Lead": 1400.0,
        "Backend Dev": 1100.0, "Frontend Dev": 1000.0,
        "QA": 900.0, "UX/UI": 1000.0, "ML Engineer": 1400.0,
    }
    contingency_pct = round(100 * (budget.get("contingency_10pct", 0.0) / budget.get("labor_estimate_eur", 1.0))) if budget.get("labor_estimate_eur") else 10
    # permitir override si ya vino en ass
    if isinstance(ass.get("contingency_pct"), (int, float)):
        contingency_pct = ass["contingency_pct"]

    project_weeks = sum(ph.get("weeks", 0) for ph in phases)
    by_role: Dict[str, float] = {}
    for r in team:
        role = r["role"]; cnt = float(r["count"])
        rate = float(role_rates.get(role, 1000.0))
        by_role.setdefault(role, 0.0)
        by_role[role] += cnt * project_weeks * rate

    labor = round(sum(by_role.values()), 2)
    contingency = round((contingency_pct / 100.0) * labor, 2)
    total = round(labor + contingency, 2)

    p["budget"] = {
        "labor_estimate_eur": labor,
        "contingency_10pct": contingency,  # mantenemos el nombre original aunque cambie el pct
        "total_eur": total,
        "by_role": by_role,
        "assumptions": {
            "project_weeks": project_weeks,
            "role_rates_eur_pw": role_rates,
            "contingency_pct": contingency_pct
        }
    }
    return p

def _apply_patch(proposal: Dict[str, Any], patch: Dict[str, Any]) -> Dict[str, Any]:
    """Aplica un parche estructurado a la propuesta y recalcula lo necesario."""
    p = copy.deepcopy(proposal)
    t = patch.get("type")

    if t == "team":
        ops = patch.get("ops", [])
        # normalizamos roles
        for op in ops:
            op["role"] = _canonical_role(op["role"])
        # aplicar
        role_index = {r["role"].lower(): i for i, r in enumerate(p.get("team", []))}
        for op in ops:
            rkey = op["role"].lower()
            if op["op"] == "set":
                if rkey in role_index:
                    p["team"][role_index[rkey]]["count"] = float(op["count"])
                else:
                    p["team"].append({"role": op["role"], "count": float(op["count"])})
            elif op["op"] == "add":
                if rkey in role_index:
                    p["team"][role_index[rkey]]["count"] = float(p["team"][role_index[rkey]]["count"]) + float(op["count"])
                else:
                    p["team"].append({"role": op["role"], "count": float(op["count"])})
            elif op["op"] == "remove":
                p["team"] = [r for r in p["team"] if _norm(r["role"]) != rkey]
        p = _recompute_budget(p)

    elif t == "phases":
        ops = patch.get("ops", [])
        # mapa por nombre (case-insensitive)
        def _find_phase_idx(name: str) -> Optional[int]:
            for i, ph in enumerate(p.get("phases", [])):
                if _norm(ph["name"]) == _norm(name):
                    return i
            return None
        for op in ops:
            if op["op"] == "set_weeks":
                idx = _find_phase_idx(op["name"])
                if idx is not None:
                    p["phases"][idx]["weeks"] = int(op["weeks"])
            elif op["op"] == "add":
                p.setdefault("phases", []).append({"name": op["name"], "weeks": int(op["weeks"])})
            elif op["op"] == "remove":
                p["phases"] = [ph for ph in p.get("phases", []) if _norm(ph["name"]) != _norm(op["name"])]
        p = _recompute_budget(p)

    elif t == "budget":
        # role_rates + contingency_pct
        budget = p.get("budget", {}) or {}
        ass = budget.get("assumptions", {}) or {}
        role_rates = ass.get("role_rates_eur_pw", {}) or {}
        role_rates.update({ _canonical_role(k): float(v) for k, v in (patch.get("role_rates") or {}).items() })
        p.setdefault("budget", {})  # ensure
        p["budget"].setdefault("assumptions", {})
        p["budget"]["assumptions"]["role_rates_eur_pw"] = role_rates
        if "contingency_pct" in patch:
            pct = float(patch["contingency_pct"])
            p["budget"]["assumptions"]["contingency_pct"] = pct
        p = _recompute_budget(p)

    elif t == "risks":
        add = patch.get("add", []) or []
        remove = patch.get("remove", []) or []
        risks = p.get("risks", [])[:]
        for r in add:
            if r not in risks:
                risks.append(r)
        for r in remove:
            risks = [x for x in risks if _norm(x) != _norm(r)]
        p["risks"] = risks

    # mantenemos sources de metodología siempre
    info = METHODOLOGIES.get(p.get("methodology", ""), {})
    p["methodology_sources"] = info.get("sources", [])
    return p

# ---------- Parsers de lenguaje natural → parches ----------

def _parse_team_patch(text: str) -> Optional[Dict[str, Any]]:
    """
    Interpreta órdenes de cambio de equipo en lenguaje natural y devuelve un patch.
    Soporta:
      - 'añade 0.5 qa', 'agrega 1 backend'
      - 'pon 2 backend', 'pon pm a 1', 'sube qa a 0,5', 'baja frontend a 1'
      - 'quita ux', 'elimina qa'
    Devuelve: {"type":"team","ops":[{"op":"add|set|remove","role":"QA","count":0.5}, ...]}
    """
    t = _norm(text)

    # Verbos
    add_verbs = r"(?:añade|agrega|suma|incluye|mete)"
    set_verbs = r"(?:deja|ajusta|pon|pone|establece|setea|sube|baja|pasa|cambia)"
    rem_verbs = r"(?:quita|elimina|borra|saca)"

    # Patrones
    #   add      : 'añade 0.5 qa'
    add_pat = re.findall(fr"{add_verbs}\s+(\d+(?:[.,]\d+)?)\s+([a-zA-Z\s/]+)", t)

    #   set A    : 'pon 2 backend'  / 'sube a 1 qa'
    set_pat_a = re.findall(fr"{set_verbs}\s+(?:a\s+)?(\d+(?:[.,]\d+)?)\s+([a-zA-Z\s/]+)", t)

    #   set B    : 'pon pm a 1' / 'quiero poner qa en 0,5' / 'baja backend a 2'
    set_pat_b = re.findall(fr"{set_verbs}\s+([a-zA-Z\s/]+)\s+(?:a|en)\s+(\d+(?:[.,]\d+)?)", t)

    #   remove   : 'quita ux'
    rem_pat = re.findall(fr"{rem_verbs}\s+([a-zA-Z\s/]+)", t)

    def _to_float(num: str) -> float:
        return float(num.replace(",", "."))

    ops: List[Dict[str, Any]] = []

    for num, role in add_pat:
        ops.append({"op": "add", "role": role.strip(), "count": _to_float(num)})

    for num, role in set_pat_a:
        ops.append({"op": "set", "role": role.strip(), "count": _to_float(num)})

    for role, num in set_pat_b:
        ops.append({"op": "set", "role": role.strip(), "count": _to_float(num)})

    role_tokens = ("pm","lead","arquitect","backend","frontend","qa","ux","ui","ml","data","tester","quality","devops")
    for role in rem_pat:
        if any(k in _norm(role) for k in role_tokens):
            ops.append({"op": "remove", "role": role.strip()})

    return {"type": "team", "ops": ops} if ops else None


def _parse_phases_patch(text: str) -> Optional[Dict[str, Any]]:
    t = _norm(text)
    ops = []
    # set weeks: fase X a 8 semanas / cambia 'Sprints de Desarrollo (2w)' a 10 semanas
    for name, weeks in re.findall(r"(?:fase\s+)?'([^']+?)'\s+a\s+(\d+)\s*sem", t):
        ops.append({"op": "set_weeks", "name": name.strip(), "weeks": int(weeks)})
    for weeks, name in re.findall(r"(?:cambia|ajusta|pon)\s+(\d+)\s*sem(?:anas|ana|s)?\s+a\s+'([^']+)'", t):
        ops.append({"op": "set_weeks", "name": name.strip(), "weeks": int(weeks)})

    # add phase: añade fase 'Pilotaje' 2 semanas
    for name, weeks in re.findall(r"(?:añade|agrega)\s+fase\s+'([^']+?)'\s+(\d+)\s*sem", t):
        ops.append({"op": "add", "name": name.strip(), "weeks": int(weeks)})

    # remove phase: quita/elimina fase 'QA'
    for name in re.findall(r"(?:quita|elimina)\s+fase\s+'([^']+?)'", t):
        ops.append({"op": "remove", "name": name.strip()})

    if ops:
        return {"type": "phases", "ops": ops}
    return None

def _parse_budget_patch(text: str) -> Optional[Dict[str, Any]]:
    t = _norm(text)
    role_rates = {}
    # tarifa de backend a 1200 / rate pm 1300
    for role, rate in re.findall(r"(?:tarifa|rate)\s+de?\s+([a-zA-Z\s/]+?)\s+a\s+(\d+)", t):
        role_rates[_canonical_role(role.strip())] = float(rate)
    # contingencia a 15%
    cont = re.search(r"contingencia\s+(?:a\s+)?(\d+)\s*%+", t)
    patch: Dict[str, Any] = {"type": "budget"}
    if role_rates:
        patch["role_rates"] = role_rates
    if cont:
        patch["contingency_pct"] = float(cont.group(1))
    if len(patch.keys()) > 1:
        return patch
    return None

def _parse_risks_patch(text: str) -> Optional[Dict[str, Any]]:
    t = _norm(text)
    add = [s.strip() for s in re.findall(r"(?:añade|agrega)\s+r(?:iesgo|isk)o?:?\s+(.+)", t)]
    remove = [s.strip() for s in re.findall(r"(?:quita|elimina)\s+r(?:iesgo|isk)o?:?\s+(.+)", t)]
    if add or remove:
        return {"type": "risks", "add": add, "remove": remove}
    return None

def _parse_any_patch(text: str) -> Optional[Dict[str, Any]]:
    # prioridad por áreas claras
    for parser in (_parse_team_patch, _parse_phases_patch, _parse_budget_patch, _parse_risks_patch):
        patch = parser(text)
        if patch:
            return patch
    return None

# ---------- NUEVO: helpers de riesgos (detalle + plan de prevención) ----------

def _risk_controls_for_item(item: str, methodology: str) -> List[str]:
    """Devuelve controles de prevención para un riesgo, adaptados a la metodología."""
    t = _norm(item)
    m = (methodology or "").strip()
    controls: List[str] = []

    # Scope / cambios de alcance
    if "cambio" in t or "alcance" in t or "scope" in t:
        controls += [
            "[Control] Cambios de alcance sin prioridad — Backlog priorizado y refinamiento regular",
            "[Control] Cambios de alcance sin prioridad — Definition of Ready/Done visibles",
            "[Control] Cambios de alcance sin prioridad — Roadmap con hitos y criterios de aceptación por épica",
        ]
        if m in ("Scrum", "XP"):
            controls.append("[Control] Cambios de alcance sin prioridad — Sprint Planning / Review efectivas")
        if m == "Kanban":
            controls.append("[Control] Cambios de alcance sin prioridad — Políticas explícitas de WIP y clases de servicio")

    # Dependencias externas / APIs / terceros
    if "dependenc" in t or "api" in t or "tercer" in t:
        controls += [
            "[Control] Dependencias de terceros — Pact tests / contratos",
            "[Control] Dependencias de terceros — Timeouts y retries con backoff (circuit breaker)",
            "[Control] Dependencias de terceros — Feature flags para isolar integraciones",
        ]
        if m == "Kanban":
            controls.append("[Control] Dependencias de terceros — Visualización de bloqueos (Blocked) y SLAs en tablero")

    # Datos/rendimiento/escalado
    if "datos insuficientes" in t or "rendimiento" in t or "escal" in t or "performance" in t:
        controls += [
            "[Control] Datos insuficientes para pruebas de rendimiento/escalado — Datasets sintéticos + anonimización",
            "[Control] Datos insuficientes para pruebas de rendimiento/escalado — Pruebas de carga + APM",
            "[Control] Datos insuficientes para pruebas de rendimiento/escalado — CI con tests automáticos",
            "[Control] Datos insuficientes para pruebas de rendimiento/escalado — Métricas de defectos y cobertura",
        ]
        if m == "XP":
            controls += [
                "[Control] Datos insuficientes para pruebas de rendimiento/escalado — TDD sistemático",
                "[Control] Datos insuficientes para pruebas de rendimiento/escalado — Pair programming",
                "[Control] Datos insuficientes para pruebas de rendimiento/escalado — Refactor continuo",
            ]

    # PCI / fraude / cobros / idempotencia
    if "pci" in t or "fraude" in t or "chargeback" in t or "cobro" in t or "pago" in t:
        controls += [
            "[Control] Cumplimiento PCI-DSS y fraude/chargebacks — Threat modeling ligero",
            "[Control] Cumplimiento PCI-DSS y fraude/chargebacks — Escaneo SAST/DAST en pipeline",
            "[Control] Cumplimiento PCI-DSS y fraude/chargebacks — Separación de datos sensibles y tokenización",
            "[Control] Cumplimiento PCI-DSS y fraude/chargebacks — 3DS / Radar antifraude y revisión de contracargos",
            "[Control] Idempotencia y reintentos en cobros — Idempotency-Key por operación",
            "[Control] Idempotencia y reintentos en cobros — Colas/reintentos con backoff",
        ]
        if m in ("XP", "Scrum"):
            controls.append("[Control] Idempotencia y reintentos en cobros — Design reviews (ADR)")

    # Aprobación en tiendas / compatibilidad dispositivos
    if "tienda" in t or "store" in t or "dispositivo" in t or "compatib" in t:
        controls += [
            "[Control] Aprobación en tiendas y compatibilidad de dispositivos — Matriz de compatibilidad + dispositivos reales",
            "[Control] Aprobación en tiendas y compatibilidad de dispositivos — Observabilidad (logs, métricas, trazas)",
            "[Control] Aprobación en tiendas y compatibilidad de dispositivos — Feature flags y despliegues graduales",
        ]

    # IA / sesgo / drift
    if "sesgo" in t or "drift" in t or "modelo" in t:
        controls += [
            "[Control] Calidad de datos, sesgo y drift de modelos — Datasets de validación + monitor de drift",
            "[Control] Calidad de datos, sesgo y drift de modelos — Retraining plan y alertas de performance",
        ]

    # Genérico por metodología si no casó nada
    if not controls:
        if m == "Scrum":
            controls = [
                "[Control] Gestión de riesgos — Revisión por sprint + retro para riesgos emergentes",
                "[Control] Gestión de riesgos — DoD con criterios de calidad y QA temprano",
            ]
        elif m == "Kanban":
            controls = [
                "[Control] Gestión de riesgos — Políticas explícitas, límites WIP y visualización de bloqueos",
                "[Control] Gestión de riesgos — Métricas de flujo (CFD, lead time) con alertas",
            ]
        else:  # XP u otros
            controls = [
                "[Control] Gestión de riesgos — TDD/CI, revisiones de código y feature toggles",
                "[Control] Gestión de riesgos — Despliegues pequeños y reversibles (trunk-based)",
            ]

    seen: set = set()
    out: List[str] = []
    for c in controls:
        if c not in seen:
            out.append(c)
            seen.add(c)
    return out


def _build_risk_controls_patch(p: Dict[str, Any]) -> Dict[str, Any]:
    """Construye un patch {'type':'risks','add':[...]} con controles para cada riesgo base."""
    methodology = p.get("methodology", "")
    all_risks = (p.get("risks") or [])
    base = [r for r in all_risks if not _norm(str(r)).startswith("[control]")]
    current = set(all_risks)
    adds: List[str] = []
    for r in base:
        for c in _risk_controls_for_item(r, methodology):
            if c not in current and c not in adds:
                adds.append(c)
    return {"type": "risks", "add": adds, "remove": []}


def _render_risks_detail(p: Dict[str, Any]) -> List[str]:
    """Texto detallado de riesgos + plan de prevención, adaptado a metodología."""
    methodology = p.get("methodology", "")
    risks = [r for r in (p.get("risks") or []) if not _norm(str(r)).startswith("[control]")]
    lines: List[str] = [f"⚠️ **Riesgos principales** (metodología {methodology}):"]
    if not risks:
        lines.append("- (No hay riesgos definidos aún)")
        return lines

    for r in risks:
        t = _norm(r)
        # Mini-explicación heurística
        if "alcance" in t or "scope" in t:
            expl = "El alcance tiende a crecer; sin priorización puede bloquear fechas y aumentar coste."
        elif "dependenc" in t or "api" in t or "tercer" in t:
            expl = "Los terceros pueden fallar o cambiar contratos; impacta en plazos y calidad."
        elif "rendimiento" in t or "escal" in t or "datos insuficientes" in t:
            expl = "Sin datos y pruebas adecuadas es fácil no cumplir SLAs de rendimiento/escala."
        elif "pci" in t or "fraude" in t or "cobro" in t or "pago" in t:
            expl = "Pagos requieren cumplimiento y antifraude; fallos implican multas o pérdidas."
        elif "tiend" in t or "dispositivo" in t or "compatib" in t:
            expl = "Stores y fragmentación de dispositivos elevan la probabilidad de rechazo o bugs."
        elif "sesgo" in t or "drift" in t:
            expl = "Los modelos degradan con el tiempo; sesgo o drift afectan KPIs y experiencia."
        else:
            expl = "Riesgo relevante identificado para este contexto."

        lines.append(f"- **{r}** — {expl}")
        ctrls = _risk_controls_for_item(r, methodology)
        if ctrls:
            lines.append("  Prevención:")
            for c in ctrls:
                lines.append(f"  - {c.replace('[Control]', '').strip()}")

    lines.append("\n¿Quieres **añadir este plan de prevención a la propuesta**? **sí/no**")
    return lines

# ===================== generación de respuesta =====================

def generate_reply(session_id: str, message: str) -> Tuple[str, str]:
    text = message.strip()
    proposal, req_text = get_last_proposal(session_id)

    # 0) Cambio pendiente → sí/no (metodología o parches de propuesta)
    pending = get_pending_change(session_id)
    if pending:
        pending_val = pending["target_method"]
        # ¿es un parche general?
        pending_patch = _parse_pending_patch(pending_val)
        if pending_patch:
            if _is_yes(text):
                if not proposal or not req_text:
                    clear_pending_change(session_id)
                    return "Necesito una propuesta base antes de cambiar. Usa '/propuesta: ...'.", "Cambio pendiente sin propuesta."
                new_plan = _apply_patch(proposal, pending_patch)
                set_last_proposal(session_id, new_plan, req_text)
                clear_pending_change(session_id)
                try:
                    save_proposal(session_id, req_text, new_plan)
                    log_message(session_id, "assistant", f"[CAMBIO CONFIRMADO → {pending_patch.get('type')}]")
                except Exception:
                    pass
                return _pretty_proposal(new_plan), f"Cambio confirmado ({pending_patch.get('type')})."
            elif _is_no(text):
                clear_pending_change(session_id)
                return "Perfecto, mantengo la propuesta tal cual.", "Cambio cancelado por el usuario."
            else:
                # Cuando hay duda, recordamos que hay evaluación previa en el mensaje anterior
                return "Tengo un cambio **pendiente** con evaluación. ¿Lo aplico? **sí/no**", "Esperando confirmación de cambio."
        else:
            # flujo original de cambio de metodología
            if _is_yes(text):
                target = pending_val  # método objetivo
                if not proposal or not req_text:
                    clear_pending_change(session_id)
                    return "Necesito una propuesta base antes de cambiar. Usa '/propuesta: ...'.", "Cambio pendiente sin propuesta."
                new_plan = _retune_plan_for_method(proposal, target)
                set_last_proposal(session_id, new_plan, req_text)
                clear_pending_change(session_id)
                try:
                    save_proposal(session_id, req_text, new_plan)
                    log_message(session_id, "assistant", f"[CAMBIO CONFIRMADO → {target}]")
                except Exception:
                    pass
                return _pretty_proposal(new_plan), f"Cambio confirmado a {target}."
            elif _is_no(text):
                clear_pending_change(session_id)
                return "Perfecto, mantengo la metodología actual.", "Cambio cancelado por el usuario."
            else:
                return "Tengo un cambio de metodología **pendiente**. ¿Lo aplico? **sí/no**", "Esperando confirmación de cambio."

    # Intents (si hay modelo entrenado)
    intent, conf = ("other", 0.0)
    if _INTENTS is not None:
        try:
            intent, conf = _INTENTS.predict(text)
        except Exception:
            pass
    if conf >= 0.80:
        if intent == "greet":
            return "¡Hola! ¿En qué te ayudo con tu proyecto? Describe requisitos o usa '/propuesta: ...' y preparo un plan.", "Saludo (intent)."
        if intent == "goodbye":
            return "¡Hasta luego! Si quieres, deja aquí los requisitos y seguiré trabajando en la propuesta.", "Despedida (intent)."
        if intent == "thanks":
            return "¡A ti! Si necesitas presupuesto o plan de equipo, dime los requisitos.", "Agradecimiento (intent)."
    # ——— Aceptación de propuesta → pedir plantilla del equipo para asignar personas
    if proposal and _accepts_proposal(text):
        try:
            set_last_area(session_id, "staffing")
        except Exception:
            pass
        prompt = (
            "¡Genial, propuesta **aprobada**! Para asignar personas a cada tarea, "
            "cuéntame tu plantilla (una por línea) con este formato:\n"
            "Nombre — Rol — Skills clave — Seniority — Disponibilidad%\n"
            "Ejemplos:\n"
            "- Ana Ruiz — Backend — Python, Django, AWS — Senior — 100%\n"
            "- Luis Pérez — QA — Cypress, E2E — Semi Senior — 50%"
        )
        return prompt, "Solicitud de plantilla."

       # ——— Si el usuario pega su plantilla: parsear, asignar y analizar formación
    if proposal and _looks_like_staff_list(text):
        staff = _parse_staff_list(text)
        if not staff:
            return ("No pude reconocer la plantilla. Usa: 'Nombre — Rol — Skills — Seniority — %'.",), "Formato staff no válido."
        asign = _suggest_staffing(proposal, staff)
        training = _render_training_plan(proposal, staff)
        try:
            set_last_area(session_id, "staffing")
        except Exception:
            pass
        return ("\n".join(asign + [""] + training)), "Asignación + formación."

    # Comando explícito: /propuesta
    if text.lower().startswith("/propuesta:"):
        req = text.split(":", 1)[1].strip() or "Proyecto genérico"
        try:
            log_message(session_id, "user", f"[REQ] {req}")
        except Exception:
            pass
        p = generate_proposal(req)
        # adjunta fuentes de metodología
        info = METHODOLOGIES.get(p.get("methodology", ""), {})
        p["methodology_sources"] = info.get("sources", [])
        set_last_proposal(session_id, p, req)
        try:
            save_proposal(session_id, req, p)
            if _SIM is not None:
                _SIM.refresh()
            log_message(session_id, "assistant", f"[PROPUESTA {p['methodology']}] {p['budget']['total_eur']} €")
        except Exception:
            pass
        return _pretty_proposal(p), "Propuesta generada."

    # Comando explícito: /cambiar:   (se mantiene para método y se amplía con parches)
    if text.lower().startswith("/cambiar:"):
        arg = text.split(":", 1)[1].strip()
        # si coincide con una metodología conocida → cambio directo
        target = normalize_method_name(arg)
        if target in METHODOLOGIES:
            if not proposal or not req_text:
                return "Primero necesito una propuesta en esta sesión. Usa '/propuesta: ...' y luego confirma el cambio.", "Cambiar sin propuesta."
            new_plan = _retune_plan_for_method(proposal, target)
            set_last_proposal(session_id, new_plan, req_text)
            try:
                save_proposal(session_id, req_text, new_plan)
                log_message(session_id, "assistant", f"[CAMBIO METODOLOGIA → {target}]")
            except Exception:
                pass
            return _pretty_proposal(new_plan), f"Plan reajustado a {target}."
        # si no, intento parsear como parche general y pido confirmación con evaluación
        patch = _parse_any_patch(arg)
        if patch:
            if not proposal:
                return "Primero necesito una propuesta en esta sesión. Usa '/propuesta: ...' y después propón cambios.", "Cambiar: sin propuesta."
            return _make_pending_patch(session_id, patch, proposal, req_text)
        return "No entendí qué cambiar. Puedes usar ejemplos: '/cambiar: añade 0.5 QA', '/cambiar: contingencia a 15%'", "Cambiar: sin parseo."

    # Cambio natural de metodología → consejo + confirmación
    change_req = _parse_change_request(text)
    if change_req:
        target, alternative = change_req
        if not proposal or not req_text:
            return ("Para evaluar si conviene cambiar a **{}**, necesito una propuesta base. "
                    "Genera una con '/propuesta: ...' y vuelvo a aconsejarte.".format(target)), "Cambio: sin propuesta."
        current = proposal.get("methodology")
        _, _, scored = recommend_methodology(req_text)
        score_map = {name: (score, hits) for name, score, hits in scored}
        sc_current, hits_current = score_map.get(current, (0.0, []))
        sc_target, hits_target = score_map.get(target, (0.0, []))
        margin = 0.02
        advisable = sc_target >= sc_current + margin

        why_target = explain_methodology_choice(req_text, target)
        evitar_target = METHODOLOGIES.get(target, {}).get("evitar_si", [])
        evitar_current = METHODOLOGIES.get(current, {}).get("evitar_si", [])

        head = f"Propones cambiar a **{target}** (actual: **{current}**)."
        scores = f"Puntuaciones → {current}: {sc_current:.2f} • {target}: {sc_target:.2f}"

        if advisable:
            msg = [head, "✅ **Sí parece conveniente** el cambio.", scores]
            if hits_target:
                msg.append("Señales a favor: " + "; ".join(hits_target))
            if why_target:
                msg.append("Razones:")
                msg += [f"- {x}" for x in why_target]
            if evitar_current:
                msg.append(f"Cuándo **no** conviene {current}: " + "; ".join(evitar_current))
        else:
            msg = [head, "❌ **No aconsejo** el cambio en este contexto.", scores]
            if hits_current:
                msg.append("Señales para mantener la actual: " + "; ".join(hits_current))
            why_current = explain_methodology_choice(req_text, current)
            if why_current:
                msg.append("Razones para mantener:")
                msg += [f"- {x}" for x in why_current]
            if evitar_target:
                msg.append(f"Riesgos si cambiamos a {target}: " + "; ".join(evitar_target))

        # aquí guardamos un pending_change clásico (solo método)
        set_pending_change(session_id, target)
        msg.append(f"¿Quieres que **cambie el plan a {target}** ahora? **sí/no**")
        return "\n".join(msg), "Consejo de cambio con confirmación."

    # NUEVO: Cambios naturales a otras áreas → confirmación con parche + evaluación
    if proposal:
        patch = _parse_any_patch(text)
        if patch:
            return _make_pending_patch(session_id, patch, proposal, req_text)

    # Documentación/autores (citas)
    if _asks_sources(text):
        sour = []
        if proposal:
            sour.extend(proposal.get("methodology_sources", []) or METHODOLOGIES.get(proposal.get("methodology",""),{}).get("sources", []))
            for s in AGILE_TEAM_SOURCES:
                sour.append(s)
            text_out = "Fuentes generales de la propuesta — referencias:\n" + _format_sources(sour)
            return text_out, "Citas/Documentación."
        else:
            return ("Aún no tengo una propuesta guardada en esta sesión. Genera una con '/propuesta: ...' y te cito autores y documentación."), "Citas: sin propuesta."

    # Casos similares
    if _SIM is not None and _asks_similar(text):
        query = req_text or text
        sims = _SIM.retrieve(query, top_k=3)
        if not sims:
            return "Aún no tengo casos guardados suficientes para comparar. Genera una propuesta con '/propuesta: ...' y lo intento de nuevo.", "Similares: sin datos."
        lines = []
        for s in sims:
            team = ", ".join(f"{r['role']} x{r['count']}" for r in s.get("team", []))
            total = s.get("budget", {}).get("total_eur")
            lines.append(f"• Caso #{s['id']} — Metodología {s['methodology']}, Equipo: {team}, Total: {total} €, similitud {s['similarity']:.2f}")
        return "Casos similares en mi memoria:\n" + "\n".join(lines), "Similares (k-NN TF-IDF)."
    # ★★★ Intent “riesgos” → detalle + plan y preparar confirmación ★★★
    if _asks_risks_simple(text):
        try:
            set_last_area(session_id, "riesgos")
        except Exception:
            pass

        if not proposal:
            return ("Aún no tengo una propuesta para analizar riesgos. "
                    "Genera una con '/propuesta: ...' y luego te detallo riesgos y plan de prevención."), "Riesgos sin propuesta."

        # 1) Texto detallado + plan adaptado a la metodología
        detailed_lines = _render_risks_detail(proposal)
        text_out = "\n".join(detailed_lines)

        # 2) Preparar parche para añadir los controles a la propuesta
        try:
            patch = _build_risk_controls_patch(proposal)  # {'type':'risks','add':[...]}
            eval_text, _ = _make_pending_patch(session_id, patch, proposal, req_text)
            return text_out + "\n\n" + eval_text, "Riesgos + plan (pendiente de confirmación)."
        except Exception:
            # Si no se pudo preparar/parchear, al menos devolvemos el texto
            return text_out, "Riesgos (detalle sin patch)."

    # -------- catálogo y definiciones de metodologías --------
    if _asks_method_list(text):
        try:
            set_last_area(session_id, "metodologia")
        except Exception:
            pass
        return _catalog_text(), "Catálogo de metodologías."

    methods_in_text = _mentioned_methods(text)
    if _asks_method_definition(text) and len(methods_in_text) == 1:
        try:
            set_last_area(session_id, "metodologia")
        except Exception:
            pass
        m = methods_in_text[0]
        return _method_overview_text(m), f"Definición de {m}."

    # Intenciones básicas
    if _is_greeting(text):
        return "¡Hola! ¿En qué te ayudo con tu proyecto? Describe requisitos o usa '/propuesta: ...' y preparo un plan.", "Saludo."
    if _is_farewell(text):
        return "¡Hasta luego! Si quieres, deja aquí los requisitos y seguiré trabajando en la propuesta.", "Despedida."
    if _is_thanks(text):
        return "¡A ti! Si necesitas presupuesto o plan de equipo, dime los requisitos.", "Agradecimiento."
    if _is_help(text):
        return (
            "Puedo: 1) generar una propuesta completa (equipo, fases, metodología, presupuesto, riesgos), "
            "2) explicar por qué tomo cada decisión (con citas), 3) evaluar y **aplicar cambios** en metodología **y en toda la propuesta** (equipo, fases, presupuesto, riesgos) con confirmación **sí/no**.\n"
            "Ejemplos: 'añade 0.5 QA', 'tarifa de Backend a 1200', 'contingencia a 15%', \"cambia 'Sprints de Desarrollo (2w)' a 8 semanas\", 'quita fase \"QA\"', 'añade riesgo: cumplimiento RGPD'."
        ), "Ayuda."
    # NUEVO: si preguntan por una fase concreta → explicarla en detalle
    phase_detail = _match_phase_name(text, proposal)
    if phase_detail and (any(k in _norm(text) for k in [
        "qué es","que es","explica","explícame","explicame",
        "en qué consiste","en que consiste","para qué sirve","para que sirve",
        "definición","definicion"
    ]) or "?" in text or len(text.split()) <= 6):
        try:
            set_last_area(session_id, "phases")
        except Exception:
            pass
        return _explain_specific_phase(text, proposal), f"Fase concreta: {phase_detail}."

    # Fases (sin 'por qué')
    if _asks_phases_simple(text) and not _asks_why(text):
        set_last_area(session_id, "phases")
        if proposal:
            lines = _explain_phases_method_aware(proposal)
            brief = " • ".join(f"{ph['name']} ({ph['weeks']}s)" for ph in proposal.get("phases", []))
            return "Fases del plan:\n" + "\n".join(lines) + f"\n\nResumen: {brief}", "Fases (explicación)."
        else:
            return ("Aún no tengo una propuesta para explicar las fases. Genera una con '/propuesta: ...' y te explico cada fase y su motivo."), "Fases sin propuesta."

    # Rol concreto (sin 'por qué')
    roles_mentioned = _extract_roles_from_text(text)
    if roles_mentioned and not _asks_why(text):
        if len(roles_mentioned) == 1:
            r = roles_mentioned[0]
            set_last_area(session_id, "equipo")
            bullets = _explain_role(r, req_text)
            extra = ""
            if proposal:
                cnt = _find_role_count_in_proposal(proposal, r)
                if cnt is not None:
                    bullets = _explain_role_count(r, cnt, req_text)
                    extra = f"\nEn esta propuesta: **{cnt:g} {r}**."
            return (f"{r} — función/valor:\n- " + "\n".join(bullets) + extra), "Rol concreto."
        else:
            return ("Veo varios roles mencionados. Dime uno concreto (p. ej., 'QA' o 'Tech Lead') y te explico su función y por qué está en el plan."), "Varios roles."

    # Preguntas de dominio (sin 'por qué')
    if _asks_methodology(text) and not _asks_why(text):
        try:
            set_last_area(session_id, "metodologia")
        except Exception:
            pass
        return (_catalog_text()), "Metodologías (catálogo)."
    if _asks_budget(text) and not _asks_why(text):
        if proposal:
            return ("\n".join(_explain_budget(proposal))), "Presupuesto."
        return ("Para estimar presupuesto considero: alcance → equipo → semanas → tarifas por rol + 10% de contingencia."), "Guía presupuesto."
    if _asks_budget_breakdown(text):
        if proposal:
            return ("Presupuesto — desglose por rol:\n" + "\n".join(_explain_budget_breakdown(proposal))), "Desglose presupuesto."
        else:
            return ("Genera primero una propuesta con '/propuesta: ...' para poder desglosar el presupuesto por rol."), "Sin propuesta para desglose."
    if _asks_team(text) and not _asks_why(text):
        set_last_area(session_id, "equipo")
        if proposal:
            reasons = _explain_team_general(proposal, req_text)
            return ("Equipo propuesto — razones:\n- " + "\n".join(reasons)), "Equipo."
        return (
            "Perfiles típicos: PM, Tech Lead, Backend, Frontend, QA, UX. "
            "La cantidad depende de módulos: pagos, panel admin, mobile, IA… "
            "Describe el alcance y dimensiono el equipo."
        ), "Guía roles."

    # ===================== 'por qué' =====================
    if _asks_why(text):
        current_method = proposal["methodology"] if proposal else None

        # Comparativa directa si el usuario menciona 2 metodologías
        methods_in_text = _mentioned_methods(text)
        if len(methods_in_text) >= 2:
            a, b = methods_in_text[0], methods_in_text[1]
            if req_text:
                _, _, scored = recommend_methodology(req_text)
                m = {name: (score, whylist) for name, score, whylist in scored}
                chosen = current_method if current_method in (a, b) else (a if m.get(a, (0, []))[0] >= m.get(b, (0, []))[0] else b)
                other = b if chosen == a else a
                sc_chosen, reasons_hits_chosen = m.get(chosen, (0.0, []))
                sc_other, _ = m.get(other, (0.0, []))
                top3 = ", ".join([f"{name}({score:.2f})" for name, score, _ in scored[:3]])

                why_chosen = explain_methodology_choice(req_text or "", chosen)
                evitar_other = METHODOLOGIES.get(other, {}).get("evitar_si", [])

                msg = [
                    f"He usado **{chosen}** en vez de **{other}** porque se ajusta mejor a tus requisitos.",
                    f"Puntuaciones: {chosen}={sc_chosen:.2f} vs {other}={sc_other:.2f}. Top3: {top3}."
                ]
                if reasons_hits_chosen:
                    msg.append("Señales que favorecen la elegida: " + "; ".join(reasons_hits_chosen))
                if why_chosen:
                    msg.append("A favor de la elegida:")
                    msg += [f"- {x}" for x in why_chosen]
                if evitar_other:
                    msg.append(f"Cuándo **no** conviene {other}: " + "; ".join(evitar_other))
                return "\n".join(msg), "Comparativa de metodologías (justificada)."
            else:
                lines = compare_methods(a, b)
                return "\n".join(lines), "Comparativa de metodologías (genérica)."

        # “¿por qué esa metodología?” o 1 sola mencionada
        target = None
        if methods_in_text:
            target = methods_in_text[0]
        elif "metodolog" in _norm(text):
            target = current_method

        if target:
            set_last_area(session_id, "metodologia")
            why_lines = explain_methodology_choice(req_text or "", target)
            rank_line = ""
            if req_text:
                _, _, scored = recommend_methodology(req_text)
                score_map = {name: score for name, score, _ in scored}
                if target in score_map:
                    top3 = ", ".join([f"{name}({score:.2f})" for name, score, _ in scored[:3]])
                    rank_line = f"\nPuntuación {target}: {score_map[target]:.2f}. Top3: {top3}."
            return f"¿Por qué **{target}**?\n- " + "\n".join(why_lines) + rank_line, "Explicación metodología."

        # Otras 'por qué'
        if proposal and _asks_why_team_general(text):
            set_last_area(session_id, "equipo")
            reasons = _explain_team_general(proposal, req_text)
            team_lines = [f"- {t['role']} x{t['count']}" for t in proposal["team"]]
            return ("Equipo — por qué:\n- " + "\n".join(reasons) + "\nDesglose: \n" + "\n".join(team_lines)), "Equipo por qué."

        rc = _asks_why_role_count(text)
        if proposal and rc:
            set_last_area(session_id, "equipo")
            role, count = rc
            return (f"¿Por qué **{count:g} {role}**?\n- " + "\n".join(_explain_role_count(role, count, req_text))), "Cantidad por rol."

        if proposal and _asks_why_phases(text):
            set_last_area(session_id, "phases")
            expl = _explain_phases_method_aware(proposal)
            m = re.search(r"\b(\d+)\s*fases\b", _norm(text))
            if m:
                asked = int(m.group(1))
                expl.insert(1, f"Se han propuesto {len(proposal['phases'])} fases (preguntas por {asked}).")
            return ("Fases — por qué:\n" + "\n".join(expl)), "Fases por qué."

        if proposal and _asks_budget(text):
            return ("Presupuesto — por qué:\n- " + "\n".join(_explain_budget(proposal))), "Presupuesto por qué."

        roles_why = _extract_roles_from_text(text)
        if proposal and roles_why:
            set_last_area(session_id, "equipo")
            r = roles_why[0]
            cnt = _find_role_count_in_proposal(proposal, r)
            if cnt is not None:
                return (f"¿Por qué **{r}** en el plan?\n- " + "\n".join(_explain_role_count(r, cnt, req_text))), "Rol por qué."
            else:
                return (f"¿Por qué **{r}**?\n- " + "\n".join(_explain_role(r, req_text))), "Rol por qué."

        if proposal:
            generic = [
                f"Metodología: {proposal['methodology']}",
                "Equipo dimensionado por módulos detectados y equilibrio coste/velocidad.",
                "Fases cubren descubrimiento→entrega; cada una reduce un riesgo.",
                "Presupuesto = headcount × semanas × tarifa por rol + % de contingencia."
            ]
            return ("Explicación general:\n- " + "\n".join(generic)), "Explicación general."
        else:
            return (
                "Puedo justificar metodología, equipo, fases, presupuesto y riesgos. "
                "Genera una propuesta con '/propuesta: ...' y la explico punto por punto."
            ), "Sin propuesta."

    # Interpretar requisitos → propuesta
    if _looks_like_requirements(text):
        p = generate_proposal(text)
        info = METHODOLOGIES.get(p.get("methodology", ""), {})
        p["methodology_sources"] = info.get("sources", [])
        set_last_proposal(session_id, p, text)
        try:
            log_message(session_id, "user", f"[REQ] {text}")
            save_proposal(session_id, text, p)
            if _SIM is not None:
                _SIM.refresh()
            log_message(session_id, "assistant", f"[PROPUESTA {p['methodology']}] {p['budget']['total_eur']} €")
        except Exception:
            pass
        return _pretty_proposal(p), "Propuesta a partir de requisitos."
    # ——— GAPS & FORMACIÓN BAJO DEMANDA ———
    if _asks_training_plan(text):
        # Si tienes un store de plantilla en memoria, recógelo; si no, pedimos que pegue la plantilla
        staff = []
        try:
            staff = get_staff_roster(session_id)  # si implementaste el store opcional
        except Exception:
            staff = []
        if not staff:
            return ("Pégame la **plantilla** (Nombre — Rol — Skills — Seniority — %) para analizar carencias y proponerte un plan de formación."), "Falta plantilla."
        training = _render_training_plan(proposal, staff) if proposal else ["Primero generemos una propuesta para conocer stack/metodología."]
        return ("\n".join(training)), "Plan de formación."

    # Fallback
    return (
        "Te he entendido. Dame más contexto (objetivo, usuarios, módulos clave) "
        "o escribe '/propuesta: ...' y te entrego un plan completo con justificación y fuentes."
    ), "Fallback."
