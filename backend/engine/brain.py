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
    return bool(re.search(r"\b(equipo|roles|perfiles|staffing|personal|plantilla|dimension)\b", text, re.I))

def _asks_risks_simple(text: str) -> bool:
    t = _norm(text)
    return ("riesgo" in t or "riesgos" in t)

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
    return any(k in t for k in ["desglose", "detalle", "por rol", "tarifa", "partidas", "coste por", "costes por"])

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
    team = ", ".join(f"{t['role']} x{t['count']}" for t in p["team"])
    phases = " → ".join(f"{ph['name']} ({ph['weeks']}s)" for ph in p["phases"])
    return (
        f"📌 Metodología: {p['methodology']}\n"
        f"👥 Equipo: {team}\n"
        f"🧩 Fases: {phases}\n"
        f"💶 Presupuesto: {p['budget']['total_eur']} € (incluye 10% contingencia)\n"
        f"⚠️ Riesgos: " + "; ".join(p["risks"])
    )


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

def _explain_budget(proposal: Dict[str, Any]) -> List[str]:
    b = proposal["budget"]
    return [
        "Estimación = (headcount_equivalente × semanas × tarifa_media/rol).",
        "Se añade un 10% de contingencia para incertidumbre técnica/alcance.",
        f"Total estimado: {b['total_eur']} € (labor {b['labor_estimate_eur']} € + contingencia {b['contingency_10pct']} €)."
    ]

def _explain_budget_breakdown(proposal: Dict[str, Any]) -> List[str]:
    b = proposal.get("budget", {}) or {}
    by_role = b.get("by_role", {}) or {}
    ass = b.get("assumptions", {}) or {}
    rates = ass.get("role_rates_eur_pw", {}) or {}
    weeks = ass.get("project_weeks")
    lines = []
    if by_role and weeks:
        lines.append(f"Desglose por rol (semanas de proyecto: {weeks}):")
        for role, amount in by_role.items():
            rate = rates.get(role, "N/A")
            lines.append(f"- {role}: {amount:.2f} €  (tarifa {rate} €/pw)")
    else:
        lines.append("No hay desglose por rol disponible.")
    lines.append(f"Labor: {b.get('labor_estimate_eur')} €  +  Contingencia (10%): {b.get('contingency_10pct')} €")
    lines.append(f"Total: {b.get('total_eur')} €")
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

def _make_pending_patch(session_id: str, patch: Dict[str, Any]) -> Tuple[str, str]:
    """Guarda un parche pendiente con confirmación sí/no usando el mismo canal pending_change."""
    try:
        set_pending_change(session_id, _PATCH_PREFIX + json.dumps(patch, ensure_ascii=False))
    except Exception:
        # fallback por si falla el state_store
        set_pending_change(session_id, _PATCH_PREFIX + json.dumps(patch))
    area = patch.get("type", "propuesta")
    summary = _summarize_patch(patch)
    return f"Propones cambiar **{area}**:\n{summary}\n\n¿Aplico estos cambios? **sí/no**", f"Parche pendiente ({area})."

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
    t = _norm(text)
    # add: añade 0.5 qa / agrega 1 backend
    add_pat = re.findall(r"(?:añade|agrega|suma)\s+(\d+(?:[.,]\d+)?)\s+([a-zA-Z\s/]+)", t)
    # set: deja/ajusta/pon 2 backend ; sube/baja a 1 qa
    set_pat = re.findall(r"(?:deja|ajusta|pon|pone|establece|setea|sube|baja)\s+(?:a\s+)?(\d+(?:[.,]\d+)?)\s+([a-zA-Z\s/]+)", t)
    # remove: quita/elimina ux
    rem_pat = re.findall(r"(?:quita|elimina|borra)\s+([a-zA-Z\s/]+)", t)

    ops = []
    for num, role in add_pat:
        ops.append({"op": "add", "role": role.strip(), "count": float(num.replace(",", "."))})
    for num, role in set_pat:
        ops.append({"op": "set", "role": role.strip(), "count": float(num.replace(",", "."))})
    for role in rem_pat:
        # evita marcar 'fase' etc como rol por falso positivo: role tokens típicos
        if any(k in role for k in ["pm","lead","arquitect","backend","frontend","qa","ux","ui","ml","data","tester","quality"]):
            ops.append({"op": "remove", "role": role.strip()})

    if ops:
        return {"type": "team", "ops": ops}
    return None

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
                return "Tengo un cambio **pendiente**. ¿Lo aplico? **sí/no**", "Esperando confirmación de cambio."
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
        # si no, intento parsear como parche general y pido confirmación
        patch = _parse_any_patch(arg)
        if patch:
            return _make_pending_patch(session_id, patch)
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

    # NUEVO: Cambios naturales a otras áreas → confirmación con parche
    if proposal:
        patch = _parse_any_patch(text)
        if patch:
            return _make_pending_patch(session_id, patch)

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

    # Fallback
    return (
        "Te he entendido. Dame más contexto (objetivo, usuarios, módulos clave) "
        "o escribe '/propuesta: ...' y te entrego un plan completo con justificación y fuentes."
    ), "Fallback."

