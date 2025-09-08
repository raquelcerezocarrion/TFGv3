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
def _asks_comms(text: str) -> bool:
    t = _norm(text)
    keys = ["comunicación", "comunicacion", "reuniones", "feedback", "cadencia", "rituales", "canales", "standups", "retro"]
    return any(k in t for k in keys)

def _asks_standards(text: str) -> bool:
    t = _norm(text)
    keys = ["estándares", "estandares", "normativas", "iso", "owasp", "gdpr", "rgpd", "accesibilidad", "wcag", "asvs", "samm"]
    return any(k in t for k in keys)

def _asks_kpis(text: str) -> bool:
    t = _norm(text)
    keys = ["kpi", "kpis", "objetivos", "indicadores", "metas", "éxito", "exito", "dora", "slo", "sla"]
    return any(k in t for k in keys)

def _asks_deliverables(text: str) -> bool:
    t = _norm(text)
    keys = ["entregables", "artefactos", "documentación", "documentacion", "checklist de entrega", "sow"]
    return any(k in t for k in keys)

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
    def eur(x) -> str:
        try:
            return f"{float(x):,.2f} €".replace(",", "X").replace(".", ",").replace("X", ".")
        except Exception:
            return f"{x} €"

    team = ", ".join(f"{t.get('role','')} x{float(t.get('count',0)) :g}" for t in (p.get("team") or []))
    phases = " → ".join(f"{ph.get('name','')} ({ph.get('weeks',0)}s)" for ph in (p.get("phases") or []))

    budget = p.get("budget", {}) or {}
    total = budget.get("total_eur", 0.0)
    cont_pct = (budget.get("assumptions", {}) or {}).get("contingency_pct", 10)

    # Riesgos y controles (mitigaciones)
    all_risks = list(p.get("risks") or [])
    base_risks = [r for r in all_risks if not _norm(str(r)).startswith("[control]")]
    controls = [r for r in all_risks if _norm(str(r)).startswith("[control]")]

    lines = [
        f"📌 Metodología: {p.get('methodology','')}",
        f"👥 Equipo: {team}" if team else "👥 Equipo: (sin definir)",
        f"🧩 Fases: {phases}" if phases else "🧩 Fases: (sin definir)",
        f"💶 Presupuesto: {eur(total)} (incluye {cont_pct}% contingencia)",
        "⚠️ Riesgos: " + ("; ".join(base_risks) if base_risks else "(no definidos)")
    ]

    # 📅 Plazos / calendario (debajo de Fases)
    tl = p.get("timeline") or {}
    events = tl.get("events") or []
    if events:
        lines.append("📅 Plazos:")
        try:
            for e in events:
                s = datetime.fromisoformat(e["start"]).date()
                en = datetime.fromisoformat(e["end"]).date()
                lines.append(f"- {e.get('phase','Fase')}: {_fmt_d(s)} → {_fmt_d(en)} ({float(e.get('weeks',0)):g}s)")
        except Exception:
            # Fallback si alguna fecha no parsea
            for e in events:
                lines.append(f"- {e.get('phase','Fase')}: {e.get('start')} → {e.get('end')} ({e.get('weeks','?')}s)")

    # 🛡️ Plan de prevención (controles)
    if controls:
        lines.append("🛡️ Plan de prevención:")
        for c in controls:
            clean = re.sub(r"^\s*\[control\]\s*", "", str(c), flags=re.I)
            lines.append(f"- {clean}")

    # 🗣️ Comunicación & feedback (si existe 'governance')
    g = p.get("governance") or {}
    if any(g.get(k) for k in ("channels", "cadence", "feedback_windows", "preferred_docs")):
        lines.append("🗣️ Comunicación & feedback:")
        if g.get("channels"):
            lines.append("- Canales: " + ", ".join(g["channels"]))
        if g.get("cadence"):
            lines.append("- Cadencia: " + " • ".join(g["cadence"]))
        if g.get("feedback_windows"):
            lines.append("- Ventanas de feedback: " + " • ".join(g["feedback_windows"]))
        if g.get("preferred_docs"):
            lines.append("- Artefactos de coordinación: " + ", ".join(g["preferred_docs"]))

    # 📏 Estándares / Normativas
    stds = list(p.get("standards") or [])
    if stds:
        lines.append("📏 Estándares/Normativas recomendados:")
        for s in stds:
            lines.append(f"- {s}")

    # 🎯 KPIs de éxito
    kpis = p.get("kpis") or {}
    if isinstance(kpis, dict) and kpis:
        lines.append("🎯 KPIs de éxito:")
        for grp, items in kpis.items():
            if items:
                lines.append(f"- {str(grp).title()}: " + " • ".join(items))

    # 📦 Entregables
    dels = list(p.get("deliverables") or [])
    if dels:
        lines.append("📦 Entregables:")
        for d in dels:
            lines.append(f"- {d}")

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

from collections import defaultdict
import re
from datetime import datetime

def _match_phase_archetype(name: str) -> str:
    n = _norm(name)
    if any(k in n for k in ["descubr", "discovery", "kickoff", "visión", "vision", "inicio"]):
        return "discovery"
    if any(k in n for k in ["analisis", "análisis", "requirements", "requisitos"]):
        return "analysis"
    if any(k in n for k in ["diseño", "ux", "ui", "wireframe", "protot"]):
        return "design"
    if any(k in n for k in ["arquitect", "architecture"]):
        return "architecture"
    if any(k in n for k in ["sprint", "desarrollo", "build", "implement", "coding"]):
        return "development"
    if any(k in n for k in ["qa", "test", "prueba", "quality", "verific"]):
        return "qa"
    if any(k in n for k in ["uat", "aceptación", "aceptacion", "usuario"]):
        return "uat"
    if any(k in n for k in ["deploy", "despliegue", "release", "lanzamiento"]):
        return "release"
    if any(k in n for k in ["cierre", "retro", "postmortem", "handover", "mantenimiento"]):
        return "closure"
    return "development"

def _phase_tasks_for_archetype(archetype: str, methodology: str) -> list:
    """Devuelve una lista de dicts {name, roles, explain} para esa fase."""
    m = _norm(methodology)
    t = []

    if archetype == "discovery":
        t = [
            {"name": "Entrevistas y alineación con stakeholders",
             "roles": ["PM", "UX"],
             "explain": "Reunirse con las personas clave para entender objetivos, restricciones y criterios de éxito."},
            {"name": "Definición de alcance y límites",
             "roles": ["PM", "Tech Lead"],
             "explain": "Acordar qué entra y qué no, versiones iniciales de roadmap y entregables."},
            {"name": "Mapa de usuarios y casos de uso",
             "roles": ["UX", "PM"],
             "explain": "Identificar tipos de usuario y los flujos principales que necesitan cubrir."},
            {"name": "Priorización inicial del backlog",
             "roles": ["PM", "Tech Lead"],
             "explain": "Ordenar funcionalidades por valor y riesgo para decidir el orden de trabajo."},
        ]

    elif archetype == "analysis":
        t = [
            {"name": "Historias de usuario y criterios de aceptación",
             "roles": ["PM", "QA"],
             "explain": "Redactar historias claras y criterios de aceptación comprobables para cada historia."},
            {"name": "Requisitos no funcionales",
             "roles": ["Tech Lead", "DevOps"],
             "explain": "Definir rendimiento, seguridad, observabilidad, accesibilidad y disponibilidad esperada."},
            {"name": "Riesgos y supuestos",
             "roles": ["PM", "Tech Lead"],
             "explain": "Registrar riesgos principales y supuestos críticos que hay que validar."},
        ]

    elif archetype == "design":
        t = [
            {"name": "Wireframes y flujo de pantallas",
             "roles": ["UX"],
             "explain": "Prototipos de baja/media fidelidad para validar la experiencia de usuario."},
            {"name": "Diseño UI y guías de estilo",
             "roles": ["UX"],
             "explain": "Componentes visuales, tipografías, colores y estados para asegurar consistencia."},
            {"name": "Revisión técnica de diseño",
             "roles": ["Tech Lead", "Frontend"],
             "explain": "Validar que los diseños son viables y alineados con la arquitectura y componentes."},
        ]

    elif archetype == "architecture":
        t = [
            {"name": "Decisiones de arquitectura (ADR)",
             "roles": ["Tech Lead"],
             "explain": "Tomar y documentar decisiones clave de arquitectura y sus alternativas."},
            {"name": "Modelado de datos y diseño de APIs",
             "roles": ["Backend", "Tech Lead"],
             "explain": "Definir entidades, relaciones y contratos de API entre servicios o módulos."},
            {"name": "Seguridad y cumplimiento",
             "roles": ["Tech Lead", "DevOps"],
             "explain": "Controles de seguridad, secretos, cifrado y requisitos regulatorios (p. ej., RGPD)."},
        ]

    elif archetype == "development":
        # Ajustes sutiles por metodología
        if "scrum" in m:
            planning_explain = "Planificar el trabajo del sprint con estimaciones y capacidad del equipo."
        elif "kanban" in m:
            planning_explain = "Acordar políticas de flujo, límites WIP y orden del tablero."
        else:
            planning_explain = "Planificar las actividades de implementación y dependencias."

        t = [
            {"name": "Planificación de trabajo",
             "roles": ["PM", "Tech Lead"],
             "explain": planning_explain},
            {"name": "Implementación backend",
             "roles": ["Backend"],
             "explain": "Desarrollar endpoints, lógica de negocio y acceso a datos con pruebas unitarias."},
            {"name": "Implementación frontend",
             "roles": ["Frontend"],
             "explain": "Construir vistas, estados y componentes reutilizables integrados con APIs."},
            {"name": "Integración y contratos API",
             "roles": ["Backend", "Frontend"],
             "explain": "Alinear contratos, gestionar errores y asegurar compatibilidad de extremo a extremo."},
            {"name": "Pipelines CI/CD",
             "roles": ["DevOps"],
             "explain": "Configurar pipelines de build, test y despliegue automatizados."},
            {"name": "Pruebas unitarias",
             "roles": ["Backend", "Frontend", "QA"],
             "explain": "Asegurar cobertura básica y evitar regresiones en componentes críticos."},
        ]

    elif archetype == "qa":
        t = [
            {"name": "Pruebas funcionales y de regresión",
             "roles": ["QA"],
             "explain": "Validar funcionalidades y comprobar que cambios no rompen lo existente."},
            {"name": "Pruebas end-to-end",
             "roles": ["QA"],
             "explain": "Simular flujos completos del usuario para detectar fallos de integración."},
            {"name": "Gestión de defectos",
             "roles": ["QA", "PM"],
             "explain": "Registrar, priorizar y hacer seguimiento de incidencias hasta su cierre."},
        ]

    elif archetype == "uat":
        t = [
            {"name": "Preparación de entorno y datos de prueba",
             "roles": ["QA", "DevOps"],
             "explain": "Dejar el entorno listo y con datos representativos para que negocio pruebe."},
            {"name": "Guía UAT y soporte durante pruebas",
             "roles": ["PM", "QA"],
             "explain": "Explicar qué probar y asistir a usuarios durante la validación."},
            {"name": "Recoger feedback y acta de aceptación",
             "roles": ["PM"],
             "explain": "Consolidar comentarios, acordar correcciones y documentar el OK de negocio."},
        ]

    elif archetype == "release":
        t = [
            {"name": "Checklist de publicación",
             "roles": ["DevOps", "Tech Lead"],
             "explain": "Verificar versiones, variables, backups y ventanas de despliegue."},
            {"name": "Despliegue y migraciones",
             "roles": ["DevOps", "Backend"],
             "explain": "Ejecutar el despliegue, migrar datos y validar salud de los servicios."},
            {"name": "Observabilidad post-release",
             "roles": ["DevOps", "Backend"],
             "explain": "Monitorizar métricas/logs y reaccionar ante alertas tras el lanzamiento."},
        ]

    elif archetype == "closure":
        t = [
            {"name": "Handover y documentación",
             "roles": ["PM", "Backend", "Frontend"],
             "explain": "Entregar documentación funcional y técnica, y acordar el soporte."},
            {"name": "Retrospectiva final",
             "roles": ["PM"],
             "explain": "Analizar qué funcionó y qué mejorar en siguientes iteraciones."},
            {"name": "Plan de mantenimiento",
             "roles": ["PM", "DevOps"],
             "explain": "Definir incidencias, ventanas de mantenimiento y estrategia de parches."},
        ]

    return t

def _render_phase_task_breakdown(proposal: dict, staff: list) -> list:
    """
    Devuelve líneas de texto: por cada fase del plan, tareas asignadas a personas concretas.
    staff: [{'name','role','skills','seniority','availability'}...]
    """
    lines = []
    phases = proposal.get("phases", []) or []
    meth = proposal.get("methodology", "") or ""

    # Agrupar plantilla por rol canónico
    staff_by_role = defaultdict(list)
    for person in (staff or []):
        role = _canonical_role(person.get("role", ""))
        staff_by_role[_norm(role)].append(person)

    # Contador por rol para repartir tareas de forma round-robin
    rr_counters = defaultdict(int)

    def _pick_assignee(role_needed: str):
        key = _norm(_canonical_role(role_needed))
        pool = staff_by_role.get(key, [])
        if not pool:
            return None
        idx = rr_counters[key] % len(pool)
        rr_counters[key] += 1
        return pool[idx], _canonical_role(role_needed)

    if not phases:
        return ["No tengo fases definidas todavía para repartir tareas."]

    lines.append("Plan de trabajo detallado por fases y personas:")
    for ph in phases:
        pname = ph.get("name", "Fase")
        weeks = ph.get("weeks", 0)
        lines.append(f"")
        lines.append(f"Fase: {pname} ({weeks}s)")
        arche = _match_phase_archetype(pname)
        tasks = _phase_tasks_for_archetype(arche, meth)

        for t in tasks:
            assigned = None
            chosen_role = None
            for r in (t.get("roles") or []):
                picked = _pick_assignee(r)
                if picked:
                    assigned, chosen_role = picked
                    break

            if not assigned:
                falta = ", ".join(_canonical_role(r) for r in (t.get("roles") or []))
                lines.append(f"- {t['name']}: NO ASIGNADO. Falta perfil ({falta}). Qué es: {t['explain']}")
            else:
                nm = assigned.get("name", "Sin nombre")
                avail = assigned.get("availability") or assigned.get("availability_pct") or assigned.get("pct") or assigned.get("%") or 100
                try:
                    if isinstance(avail, str):
                        avail = int(re.sub(r"[^0-9]", "", avail) or "100")
                except Exception:
                    avail = 100
                lines.append(f"- {t['name']} — responsable: {nm} ({chosen_role}, {avail}% disponibilidad). Qué es: {t['explain']}")

    return lines

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
    cont_pct = float(after.get("budget", {}).get("assumptions", {}).get(
        "contingency_pct",
        before.get("budget", {}).get("assumptions", {}).get("contingency_pct", 10)
    ))

    delta_w = w1 - w0
    delta_f = f1 - f0
    delta_cost = round(b1 - b0, 2)

    lines: List[str] = []
    verdict = "neutra"

    def eur(x: float) -> str:
        return f"{float(x):,.2f} €".replace(",", "X").replace(".", ",").replace("X", ".")

    t = (patch.get("type") or "").lower()

    # ---------------- EQUIPO ----------------
    if t == "team":
        add_line("📌 Evaluación del cambio de **equipo**:", lines)

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

        if delta_f > 0 and delta_w == 0:
            add_line("➕ Más FTE con el mismo timeline → más throughput; potencialmente entregas antes dentro de las mismas semanas.", lines)
        if delta_f < 0 and delta_w == 0:
            add_line("➖ Menos FTE con igual timeline → riesgo de cuello de botella en desarrollo.", lines)

        if critical_removed:
            verdict = "mala"
        elif delta_f > 0 and has("qa"):
            verdict = "buena"
        elif delta_f < 0:
            verdict = "mala"
        else:
            verdict = "neutra"

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

        add_line("", lines)
        add_line("📊 **Impacto estimado:**", lines)
        add_line(f"- Semanas totales: {w0} → {w1}  (Δ {delta_w:+})", lines)
        add_line(f"- Headcount equivalente (FTE): {f0:g} → {f1:g}  (Δ {delta_f:+g})", lines)
        add_line(f"- Labor: {eur(labor0)} → {eur(labor1)}  (Δ {eur(labor1 - labor0)})", lines)
        add_line(f"- Total con contingencia ({cont_pct:.0f}%): {eur(b0)} → {eur(b1)}  (Δ {eur(delta_cost)})", lines)

    # ---------------- FASES ----------------
    elif t == "phases":
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
        add_line("📊 **Impacto estimado:**", lines)
        add_line(f"- Semanas totales: {w0} → {w1}  (Δ {delta_w:+})", lines)
        add_line(f"- Headcount equivalente (FTE): {f0:g} → {f1:g}  (Δ {delta_f:+g})", lines)
        add_line(f"- Total con contingencia ({cont_pct:.0f}%): {eur(b0)} → {eur(b1)}  (Δ {eur(delta_cost)})", lines)

    # ---------------- PRESUPUESTO ----------------
    elif t in ("budget", "rates", "contingency"):
        add_line("📌 Evaluación del cambio de **presupuesto**:", lines)

        rr = patch.get("role_rates") or patch.get("rates") or {}
        if rr:
            add_line("Tarifas por rol propuestas:", lines)
            current_rates = (before.get("budget", {}).get("assumptions", {}).get("role_rates_eur_pw", {}) or {})
            for r, v in rr.items():
                old = float(current_rates.get(_canonical_role(r), current_rates.get(r, 0.0)) or 0.0)
                add_line(f"- {_canonical_role(r)}: {eur(old)} → {eur(float(v))} /semana", lines)

        if "contingency_pct" in patch or (t == "contingency" and "pct" in patch):
            oldc = float(before.get("budget", {}).get("assumptions", {}).get("contingency_pct", cont_pct))
            newc = float(patch.get("contingency_pct", patch.get("pct", cont_pct)))
            add_line(f"Contingencia: {oldc:.0f}% → {newc:.0f}%.", lines)

        add_line("", lines)
        add_line("📊 **Impacto estimado:**", lines)
        add_line(f"- Labor: {eur(labor0)} → {eur(labor1)}  (Δ {eur(labor1 - labor0)})", lines)
        add_line(f"- Total con contingencia: {eur(b0)} → {eur(b1)}  (Δ {eur(delta_cost)})", lines)

        if delta_cost < 0:
            verdict = "buena"
        elif delta_cost > max(0.1 * (b0 or 1), 1):
            verdict = "mala"
        else:
            verdict = "neutra"

    # ---------------- RIESGOS ----------------
    elif t == "risks":
        add_line("📌 Evaluación del cambio de **riesgos/controles**:", lines)
        adds, rems = 0, 0
        if "ops" in patch:
            for op in (patch.get("ops") or []):
                if op.get("op") == "add": adds += 1
                if op.get("op") == "remove": rems += 1
        else:
            adds = len(patch.get("add", []) or [])
            rems = len(patch.get("remove", []) or [])
        if adds:
            add_line(f"✅ Se añaden {adds} controles/mitigaciones.", lines)
        if rems:
            add_line(f"⚠️ Se eliminan {rems} riesgos/controles.", lines)
        verdict = "buena" if adds and not rems else "neutra"
        add_line("", lines)
        add_line("No afecta directamente al presupuesto; mejora la gobernanza del riesgo.", lines)

    # ---------------- TIMELINE / CALENDARIO ----------------
    elif t == "timeline":
        add_line("📌 Evaluación del cambio de **plazos/calendario**:", lines)
        payload = None
        for op in (patch.get("ops") or []):
            if op.get("op") == "set":
                payload = op.get("value")
        if not payload:
            payload = after.get("timeline") or {}

        start_iso = payload.get("start_date")
        events = payload.get("events", [])
        try:
            sd = datetime.fromisoformat(start_iso).date() if start_iso else date.today()
        except Exception:
            sd = date.today()

        add_line(f"📅 Calendario propuesto desde { _fmt_d(sd) }:", lines)
        for e in events:
            try:
                s = datetime.fromisoformat(e["start"]).date()
                en = datetime.fromisoformat(e["end"]).date()
                add_line(f"- {e.get('phase','Fase')}: {_fmt_d(s)} → {_fmt_d(en)} ({float(e.get('weeks',0)):g}s)", lines)
            except Exception:
                add_line(f"- {e.get('phase','Fase')}: {e.get('start')} → {e.get('end')} ({e.get('weeks','?')}s)", lines)

        add_line("", lines)
        add_line("No cambia semanas ni presupuesto; solo documenta los plazos.", lines)
        verdict = "neutra"

    # ---------------- OTROS ----------------
    else:
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
    t = (patch.get("type") or "").lower()

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

    elif t in ("budget", "rates", "contingency"):
        # role_rates + contingency_pct (acepta varias formas)
        budget = p.get("budget", {}) or {}
        ass = budget.get("assumptions", {}) or {}
        role_rates = ass.get("role_rates_eur_pw", {}) or {}

        # 1) tarifas por rol
        rr = patch.get("role_rates") or patch.get("rates") or {}
        if rr:
            role_rates.update({_canonical_role(k): float(v) for k, v in rr.items()})

        p.setdefault("budget", {})
        p["budget"].setdefault("assumptions", {})
        p["budget"]["assumptions"]["role_rates_eur_pw"] = role_rates

        # 2) contingencia
        if "contingency_pct" in patch:
            p["budget"]["assumptions"]["contingency_pct"] = float(patch["contingency_pct"])
        if "pct" in patch and t in ("contingency",):
            p["budget"]["assumptions"]["contingency_pct"] = float(patch["pct"])

        p = _recompute_budget(p)

    elif t == "risks":
        # Soporta dos formatos:
        # a) {'type':'risks','add':[...],'remove':[...]}
        # b) {'type':'risks','ops':[{'op':'add','risk':'...'}, {'op':'remove','risk':'...'}]}
        risks = list(p.get("risks", []) or [])

        if "ops" in patch:
            for op in (patch.get("ops") or []):
                rtxt = op.get("risk") or op.get("value")
                if not rtxt:
                    continue
                if op.get("op") == "add":
                    if rtxt not in risks:
                        risks.append(rtxt)
                elif op.get("op") == "remove":
                    risks = [x for x in risks if _norm(x) != _norm(rtxt)]
        else:
            add = patch.get("add", []) or []
            remove = patch.get("remove", []) or []
            for r in add:
                if r not in risks:
                    risks.append(r)
            for r in remove:
                risks = [x for x in risks if _norm(x) != _norm(r)]

        p["risks"] = risks

    elif t == "timeline":
        # Patch con ops = [{'op':'set','value': {start_date, events:[{phase,start,end,weeks}]}}]
        payload = None
        for op in (patch.get("ops") or []):
            if op.get("op") == "set":
                payload = op.get("value")
        if payload:
            p["timeline"] = payload

    # —— NUEVOS TIPOS: comunicación/feedback, estándares, KPIs, entregables ——

    elif t in ("governance", "comms", "communication"):
        # ops: [{'op':'set','value': {channels, cadence, feedback_windows, preferred_docs}}]
        payload = None
        for op in (patch.get("ops") or []):
            if op.get("op") == "set":
                payload = op.get("value")
        if payload:
            p["governance"] = payload  # no afecta a presupuesto

    elif t == "standards":
        # ops: add/remove de cadenas; también acepta 'value' con lista completa para sustituir
        cur = list(p.get("standards") or [])
        if "ops" in patch:
            for op in (patch.get("ops") or []):
                val = op.get("value")
                if not val:
                    continue
                if op.get("op") == "add":
                    # evita duplicados (case-insensitive)
                    if not any(_norm(val) == _norm(x) for x in cur):
                        cur.append(val)
                elif op.get("op") == "remove":
                    cur = [x for x in cur if _norm(x) != _norm(val)]
            p["standards"] = cur
        elif isinstance(patch.get("value"), list):
            # set directo
            p["standards"] = list(patch.get("value") or [])

    elif t == "kpis":
        # ops: [{'op':'set','value': {grupo: [kpi1, kpi2]}}] o 'value' directo (dict)
        payload = None
        if "ops" in patch:
            for op in (patch.get("ops") or []):
                if op.get("op") == "set":
                    payload = op.get("value")
        elif isinstance(patch.get("value"), dict):
            payload = patch.get("value")
        if payload:
            p["kpis"] = payload  # no afecta a presupuesto

    elif t == "deliverables":
        # Soporta: lista completa en 'value' o 'ops' add/remove
        if "ops" in patch:
            cur = list(p.get("deliverables") or [])
            for op in (patch.get("ops") or []):
                val = op.get("value")
                if not val:
                    continue
                if op.get("op") == "add":
                    if not any(_norm(val) == _norm(x) for x in cur):
                        cur.append(val)
                elif op.get("op") == "remove":
                    cur = [x for x in cur if _norm(x) != _norm(val)]
            p["deliverables"] = cur
        elif isinstance(patch.get("value"), list):
            p["deliverables"] = list(patch.get("value") or [])

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

def _suggest_comms_for_method(method: str) -> Dict[str, Any]:
    m = (method or "").strip()
    if m == "Scrum":
        return {
            "channels": ["Slack/Teams", "Jira/YouTrack", "Email ejecutivo"],
            "cadence": ["Daily 15’", "Refinamiento 1/sem", "Review + Retro cada 2 sem"],
            "feedback_windows": ["Demo bisemanal (Review)", "Ventana de cambio al inicio de sprint"],
            "preferred_docs": ["DoR/DoD visibles", "Roadmap trimestral", "Actas ligeras"]
        }
    if m == "Kanban":
        return {
            "channels": ["Slack/Teams", "Kanban board (WIP)", "Email ejecutivo"],
            "cadence": ["Daily flow 10’", "Replenishment 1/sem", "Service review mensual"],
            "feedback_windows": ["Pull continuo + weekly checkpoint", "Políticas WIP visibles"],
            "preferred_docs": ["Políticas de flujo", "Definición de clases de servicio"]
        }
    return {
        "channels": ["Slack/Teams", "Issue tracker", "Email ejecutivo"],
        "cadence": ["Daily 15’", "Show & Tell semanal", "Retro/Review bisemanal"],
        "feedback_windows": ["Demo semanal", "Checklist de aceptación por historia"],
        "preferred_docs": ["ADR", "Backlog priorizado"]
    }

def _render_comms_plan(p: Dict[str, Any]) -> List[str]:
    g = (p.get("governance") or {})
    out = ["🗣️ **Comunicación & feedback**"]
    if g.get("channels"): out.append("- Canales: " + ", ".join(g["channels"]))
    if g.get("cadence"): out.append("- Cadencia: " + " • ".join(g["cadence"]))
    if g.get("feedback_windows"): out.append("- Ventanas de feedback: " + " • ".join(g["feedback_windows"]))
    if g.get("preferred_docs"): out.append("- Artefactos de coordinación: " + ", ".join(g["preferred_docs"]))
    return out

def _standards_for_context(p: Dict[str, Any]) -> List[str]:
    t = _norm(" ".join(p.get("risks", [])))
    out = ["ISO/IEC 25010 (calidad)", "OWASP ASVS (seguridad app)", "WCAG 2.2 AA (accesibilidad)"]
    if "pci" in t or "pago" in t or "stripe" in t or "chargeback" in t:
        out += ["PCI-DSS (pagos)", "ISO/IEC 27001/27002 (seguridad)", "ISO 31000 (riesgos)"]
    if any(k in t for k in ["datos", "privacidad", "rgpd", "gdpr"]):
        out += ["ISO/IEC 27701 (privacidad)", "GDPR (cumplimiento UE)"]
    seen, uniq = set(), []
    for s in out:
        if s not in seen:
            seen.add(s); uniq.append(s)
    return uniq

def _render_standards(p: Dict[str, Any]) -> List[str]:
    stds = p.get("standards") or []
    if not stds: stds = _standards_for_context(p)
    return ["📏 **Estándares/Normativas recomendados**"] + [f"- {s}" for s in stds] + [
        "_Nota_: recomendaciones; la **certificación** requeriría auditoría externa."
    ]

def _kpis_for_method(method: str) -> Dict[str, Any]:
    if method == "Scrum":
        return {"delivery": ["Velocidad estable (+/-15%)", "Defectos por sprint < 3"],
                "devops": ["Lead Time < 7 días", "CFD estable"],
                "calidad": ["Cobertura > 60%", "Fuga a prod < 1%"]}
    if method == "Kanban":
        return {"flow": ["Lead time p50 < 5 días", "WIP respetado"],
                "calidad": ["Tasa de retrabajo < 10%"]}
    return {"delivery": ["Release cada 2-4 semanas"], "calidad": ["Defectos críticos cerrados < 48h"]}

def _render_kpis(p: Dict[str, Any]) -> List[str]:
    k = p.get("kpis") or _kpis_for_method(p.get("methodology",""))
    lines = ["🎯 **KPIs de éxito**"]
    for group, items in k.items():
        lines.append(f"- {group.title()}: " + " • ".join(items))
    return lines

def _deliverables_for_plan(p: Dict[str, Any]) -> List[str]:
    base = ["Backlog priorizado", "ADR/Arquitectura", "CI/CD configurado", "Plan de pruebas", "Manual de usuario", "Runbooks"]
    return base

def _render_deliverables(p: Dict[str, Any]) -> List[str]:
    lst = p.get("deliverables") or _deliverables_for_plan(p)
    return ["📦 **Entregables**"] + [f"- {d}" for d in lst]

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
# ---------- Desglose avanzado de presupuesto (roles + actividades/fases) ----------
from typing import Dict, Any, List, Tuple

def _eur(x: float) -> str:
    try:
        return f"{x:,.2f} €".replace(",", "X").replace(".", ",").replace("X", ".")
    except Exception:
        return f"{x} €"

def _total_weeks(p: Dict[str, Any]) -> float:
    return float(sum(float(ph.get("weeks", 0)) for ph in (p.get("phases") or [])))

def _canonical_phase_bucket(name: str) -> str:
    n = (name or "").lower()
    if any(k in n for k in ["discover", "historia", "crc", "backlog", "kickoff"]): return "discovery"
    if any(k in n for k in ["iterac", "sprint", "desarroll", "build"]):            return "iterations"
    if any(k in n for k in ["hardening", "acept", "stabil", "qa final", "endgame"]):return "hardening"
    if any(k in n for k in ["release", "handover", "deploy", "entrega"]):          return "release"
    return "iterations"

def _role_profile(role: str) -> Dict[str, float]:
    r = (role or "").lower()
    if "pm" in r:                 return {"discovery": 0.30, "iterations": 0.30, "hardening": 0.20, "release": 0.20}
    if "tech" in r and "lead" in r:return {"discovery": 0.30, "iterations": 0.40, "hardening": 0.20, "release": 0.10}
    if "backend" in r:           return {"discovery": 0.05, "iterations": 0.70, "hardening": 0.20, "release": 0.05}
    if "frontend" in r:          return {"discovery": 0.05, "iterations": 0.70, "hardening": 0.20, "release": 0.05}
    if "qa" in r or "calidad" in r:return {"discovery": 0.05, "iterations": 0.40, "hardening": 0.40, "release": 0.15}
    if "ux" in r or "ui" in r or "dise" in r: return {"discovery": 0.60, "iterations": 0.30, "hardening": 0.05, "release": 0.05}
    return {"discovery": 0.20, "iterations": 0.50, "hardening": 0.20, "release": 0.10}

def _avg(lst: List[float]) -> float:
    return (sum(lst) / max(len(lst), 1)) if lst else 0.0

def _rate_for_role(rates: Dict[str, float], role: str, fallback_rate: float) -> float:
    if role in rates: return float(rates[role])
    rl = role.lower()
    for k, v in rates.items():
        if k.lower() in rl or rl in k.lower():
            return float(v)
    aliases = {"backend dev": "backend","frontend dev": "frontend","ux/ui": "ux","tech lead": "tech lead","pm": "pm","qa": "qa"}
    for ak, base in aliases.items():
        if ak in rl:
            for k, v in rates.items():
                if base in k.lower():
                    return float(v)
    return float(fallback_rate)

def _bucket_weeks(p: Dict[str, Any]) -> Dict[str, float]:
    buckets = {"discovery": 0.0, "iterations": 0.0, "hardening": 0.0, "release": 0.0}
    for ph in (p.get("phases") or []):
        buckets[_canonical_phase_bucket(ph.get("name",""))] += float(ph.get("weeks", 0.0))
    if sum(buckets.values()) == 0 and _total_weeks(p) > 0:
        buckets["iterations"] = _total_weeks(p)
    return buckets

def _breakdown_by_role_and_activity(p: Dict[str, Any]) -> Tuple[Dict[str, float], Dict[str, float], List[Tuple[str, str, float]]]:
    team = p.get("team") or []
    rates = dict(p.get("rates") or {})
    weeks_total = _total_weeks(p)
    buckets_weeks = _bucket_weeks(p)

    fte_total = sum(float(t.get("count", 0.0)) for t in team)
    labor_est_known = float((p.get("budget") or {}).get("labor_estimate_eur", 0.0))
    fallback_rate = (labor_est_known / (weeks_total * fte_total)) if (weeks_total>0 and fte_total>0 and labor_est_known>0) else _avg([float(v) for v in rates.values()]) or 0.0

    cost_by_role: Dict[str, float] = {}
    for t in team:
        role = t["role"]; fte = float(t.get("count", 0.0))
        rate = _rate_for_role(rates, role, fallback_rate)
        cost_by_role[role] = fte * weeks_total * rate

    denom_by_role: Dict[str, float] = {}
    profiles_cache: Dict[str, Dict[str, float]] = {}
    for role in cost_by_role:
        prof = _role_profile(role); profiles_cache[role] = prof
        denom_by_role[role] = sum(prof[b] * buckets_weeks.get(b, 0.0) for b in ("discovery","iterations","hardening","release")) or 1.0

    activities: List[Tuple[str, str, float]] = []
    cost_by_activity = {"discovery": 0.0, "iterations": 0.0, "hardening": 0.0, "release": 0.0}
    for role, role_total in cost_by_role.items():
        prof = profiles_cache[role]; denom = denom_by_role[role]
        for b in ("discovery","iterations","hardening","release"):
            share = (prof[b] * buckets_weeks.get(b, 0.0)) / denom
            euros = role_total * share
            if euros <= 0: continue
            activities.append((b, role, euros)); cost_by_activity[b] += euros

    activities.sort(key=lambda x: x[2], reverse=True)
    return cost_by_role, cost_by_activity, activities

def _render_budget_detail(p: Dict[str, Any]) -> List[str]:
    weeks_total = _total_weeks(p)
    budget = p.get("budget") or {}
    cont_pct = float(((budget.get("assumptions") or {}).get("contingency_pct", 10)))
    labor0 = float(budget.get("labor_estimate_eur", 0.0))
    total0 = float(budget.get("total_eur", labor0 * (1 + cont_pct / 100)))

    cost_by_role, cost_by_activity, activities = _breakdown_by_role_and_activity(p)

    lines: List[str] = []
    lines.append("💶 **Presupuesto — detalle**")
    lines.append(f"- Semanas totales: {weeks_total:g}")
    bw = _bucket_weeks(p)
    lines.append(f"- Semanas por fase/actividad: Discovery {bw['discovery']:g}s • Iteraciones {bw['iterations']:g}s • Hardening {bw['hardening']:g}s • Release {bw['release']:g}s")

    if cost_by_role:
        lines.append("\n📊 Coste por rol:")
        for role, euros in sorted(cost_by_role.items(), key=lambda x: x[1], reverse=True):
            lines.append(f"- {role}: {_eur(euros)}")
    else:
        lines.append("\n(No encuentro equipo/tarifas para desglosar por rol.)")

    if any(cost_by_activity.values()):
        lines.append("\n🔎 Coste por actividad/fase:")
        names = {"discovery":"Discovery / Historias","iterations":"Iteraciones (build)","hardening":"Hardening & Aceptación","release":"Release & Handover"}
        for b in ("iterations","discovery","hardening","release"):
            lines.append(f"- {names[b]}: {_eur(cost_by_activity.get(b, 0.0))}")
    else:
        lines.append("\n(No pude mapear fases; enséñame las fases para intentar de nuevo.)")

    if activities:
        lines.append("\n🏷️ **Top actividades (dónde se va más dinero):**")
        names = {"discovery":"Discovery / Historias","iterations":"Iteraciones","hardening":"Hardening & Aceptación","release":"Release & Handover"}
        for (b, role, euros) in activities[:5]:
            lines.append(f"- {names[b]} — {role}: {_eur(euros)}")

    lines.append(f"\nContingencia: {cont_pct:.0f}%")
    lines.append(f"Total mano de obra (estimado): {_eur(labor0) if labor0 > 0 else '—'}")
    lines.append(f"**Total con contingencia: {_eur(total0)}**")

    lines.append("\n¿Quieres ajustar el presupuesto? Prueba:")
    lines.append("- «contingencia a 15%»")
    lines.append("- «tarifa de Backend a 1200»  |  «tarifa de QA a 900»")
    return lines
# ---------- Calendario / plazos: parseo fecha inicio + construcción de timeline ----------
from datetime import date, datetime, timedelta
import math
from typing import Dict, Any, List, Tuple, Optional

_MONTHS_ES = {
    "enero":1,"febrero":2,"marzo":3,"abril":4,"mayo":5,"junio":6,"julio":7,"agosto":8,
    "septiembre":9,"setiembre":9,"octubre":10,"noviembre":11,"diciembre":12,
    "ene":1,"feb":2,"mar":3,"abr":4,"may":5,"jun":6,"jul":7,"ago":8,"sep":9,"oct":10,"nov":11,"dic":12
}

def _fmt_d(d: date) -> str:
    return d.strftime("%d/%m/%Y")

def _safe_float(x) -> float:
    try: return float(x)
    except Exception: return 0.0

def _parse_start_date_es(text: str, today: Optional[date] = None) -> Optional[date]:
    """Soporta: YYYY-MM-DD, DD/MM/YYYY, DD-MM-YYYY, 'hoy', 'mañana', 'en 10 días|semanas',
       '1 de octubre (de 2025)', 'octubre 1 2025'."""
    t = (text or "").lower().strip()
    if not today: today = date.today()

    # palabras
    if "hoy" in t: return today
    if "mañana" in t or "manana" in t: return today + timedelta(days=1)

    # en X días/semanas
    m = re.search(r"en\s+(\d+)\s*(dia|días|dias|semana|semanas)", t)
    if m:
        n = int(m.group(1))
        unit = m.group(2)
        return today + timedelta(days=n if "semana" not in unit else n * 7)

    # ISO
    m = re.search(r"\b(\d{4})-(\d{2})-(\d{2})\b", t)
    if m:
        y, mo, d = map(int, m.groups())
        return date(y, mo, d)

    # DD/MM/YYYY o DD-MM-YYYY
    m = re.search(r"\b(\d{1,2})[/-](\d{1,2})[/-](\d{2,4})\b", t)
    if m:
        d, mo, y = m.groups()
        y = int(y);  y = y + 2000 if y < 100 else y
        return date(int(y), int(mo), int(d))

    # '1 de octubre de 2025' / '1 de oct 2025' / '1 de octubre'
    m = re.search(r"\b(\d{1,2})\s+de\s+([a-záéíóú]+)(?:\s+de\s+(\d{4}))?", t)
    if m:
        d = int(m.group(1)); mon = m.group(2).replace("á","a").replace("é","e").replace("í","i").replace("ó","o").replace("ú","u")
        mon = _MONTHS_ES.get(mon, None)
        if mon:
            y = int(m.group(3)) if m.group(3) else today.year
            return date(y, mon, d)

    # 'octubre 1 2025'
    m = re.search(r"\b([a-záéíóú]+)\s+(\d{1,2})(?:\s+(\d{4}))?", t)
    if m:
        mon = m.group(1).replace("á","a").replace("é","e").replace("í","i").replace("ó","o").replace("ú","u")
        mon = _MONTHS_ES.get(mon, None)
        if mon:
            d = int(m.group(2))
            y = int(m.group(3)) if m.group(3) else today.year
            return date(y, mon, d)

    return None

def _build_timeline(proposal: Dict[str, Any], start: date) -> Dict[str, Any]:
    """Construye events = [{phase,start,end,weeks}] avanzando por semanas."""
    events: List[Dict[str, Any]] = []
    current = start
    for ph in (proposal.get("phases") or []):
        w = _safe_float(ph.get("weeks", 0.0))
        days = int(math.ceil(w * 7)) if w > 0 else 0
        end = current + timedelta(days=days-1) if days > 0 else current
        events.append({
            "phase": ph.get("name", "Fase"),
            "weeks": w,
            "start": current.isoformat(),
            "end": end.isoformat()
        })
        current = end + timedelta(days=1)
    return {
        "start_date": start.isoformat(),
        "events": events
    }

def _render_timeline_text(proposal: Dict[str, Any], start: date) -> List[str]:
    tl = _build_timeline(proposal, start)
    evs = tl["events"]
    out = [f"📅 **Plan de plazos** — inicio { _fmt_d(start) }"]
    if not evs:
        out.append("- (No hay fases definidas).")
        return out
    for e in evs:
        s = datetime.fromisoformat(e["start"]).date()
        en = datetime.fromisoformat(e["end"]).date()
        out.append(f"- {e['phase']}: {_fmt_d(s)} → {_fmt_d(en)} ({e['weeks']:g}s)")
    return out

def _build_timeline_patch(proposal: Dict[str, Any], start: date) -> Dict[str, Any]:
    """Patch que añade p['timeline'] con start_date + events."""
    tl = _build_timeline(proposal, start)
    return {
        "type": "timeline",
        "ops": [
            {"op": "set", "value": tl}
        ]
    }

def _looks_like_timeline_intent(t: str) -> bool:
    z = _norm(t)
    keys = ["calendario","plazo","plazos","fechas","cronograma","timeline","plan de plazos","cuándo empez","cuando empez"]
    return any(k in z for k in keys)

# ===================== FORMACIÓN: helpers, estado y contenido =====================

_TRAINING_SESSIONS: Dict[str, Dict[str, Any]] = {}

def _get_training_state(session_id: str) -> Dict[str, Any]:
    return _TRAINING_SESSIONS.get(session_id, {"active": False, "level": None})

def _set_training_state(session_id: str, st: Dict[str, Any]) -> None:
    _TRAINING_SESSIONS[session_id] = {"active": bool(st.get("active")), "level": st.get("level")}

def _enter_training(session_id: str) -> None:
    _set_training_state(session_id, {"active": True, "level": None})

def _exit_training(session_id: str) -> None:
    _set_training_state(session_id, {"active": False, "level": None})

def _wants_training(text: str) -> bool:
    t = _norm(text)
    keys = ["aprender", "formación", "formacion", "enseñame", "enséñame", "quiero formarme", "modo formación", "formarme"]
    return any(k in t for k in keys)

def _training_exit(text: str) -> bool:
    t = _norm(text)
    return ("salir de la formaci" in t) or (t.strip() in {"salir", "terminar formacion", "terminar formación"})

_LEVEL_ALIASES = {
    "principiante": "beginner", "inicio": "beginner", "novato": "beginner",
    "intermedio": "intermediate", "medio": "intermediate",
    "experto": "expert", "avanzado": "expert"
}

def _parse_level(text: str) -> Optional[str]:
    t = _norm(text)
    for k, v in _LEVEL_ALIASES.items():
        if re.search(rf"\b{k}\b", t):
            return v
    return None

def _one_liner_from_info(info: Dict[str, Any], name: str) -> str:
    for k in ["resumen", "one_liner", "descripcion", "descripción", "description"]:
        if info.get(k):
            return str(info[k])
    base = {
        "Scrum": "Marco ágil con sprints cortos para entregar valor frecuente.",
        "Kanban": "Flujo continuo con límites de trabajo en curso (WIP).",
        "XP": "Prácticas técnicas (TDD, refactor, CI) e iteraciones cortas.",
        "Lean": "Eliminar desperdicios y acelerar el flujo de valor.",
        "Scrumban": "Híbrido Scrum + Kanban para planificar y controlar el flujo.",
        "Crystal": "Método adaptable según tamaño y criticidad del equipo.",
        "FDD": "Entrega por funcionalidades bien definidas.",
        "DSDM": "Ágil de negocio con timeboxes y priorización MoSCoW.",
        "SAFe": "Escalado ágil con trenes de release y PI Planning.",
        "DevOps": "Dev + Ops: automatización, despliegue continuo y fiabilidad."
    }
    return base.get(normalize_method_name(name), f"Enfoque para organizar trabajo y entregar valor.")

def _training_topic_and_method(text: str) -> Tuple[Optional[str], Optional[str]]:
    """
    Detecta tema y método solicitado.
    tema ∈ {'metodologias','fases','roles','metricas','quees','ventajas'} o None
    """
    t = _norm(text)
    topic = None
    if any(x in t for x in ["metodolog", "metodos", "métodos"]):
        topic = "metodologias"
    if any(x in t for x in ["fase", "fases", "ritual", "ceremonia"]):
        topic = "fases"
    if any(x in t for x in ["rol", "roles", "equipo", "perfiles"]):
        topic = "roles"
    if any(x in t for x in ["metrica", "métrica", "metricas", "métricas", "indicador", "kpi"]):
        topic = "metricas"
    if any(x in t for x in ["que es", "qué es", "definicion", "definición", "explica", "explicame", "explícame"]):
        topic = "quees"
    if any(x in t for x in ["ventaja", "beneficio", "cuando usar", "cuándo usar", "pros"]):
        topic = "ventajas"

    methods_mentioned = _mentioned_methods(text)
    method = methods_mentioned[0] if methods_mentioned else None
    return topic, method

# Contenido por metodología (fases/rituales/roles/métricas/prácticas avanzadas)
_TRAIN_METHOD = {
    "Scrum": {
        "rituales": ["Planning", "Daily", "Review", "Retrospective", "Refinement"],
        "fases":    ["Incepción/Plan de releases", "Sprints de desarrollo (2 semanas)", "QA/Hardening", "Despliegue y transferencia"],
        "roles":    ["Product Owner", "Scrum Master", "Equipo de desarrollo (Dev/QA/UX)"],
        "metrics":  ["Velocidad", "Burndown/Burnup", "Lead time", "Cycle time"],
        "avanzado": ["Definition of Ready/Done claros", "Descomposición de épicas", "Evitar mini-waterfalls"]
    },
    "Kanban": {
        "rituales": ["Replenishment", "Revisión de flujo", "Retro de flujo"],
        "fases":    ["Discovery y diseño", "Flujo continuo con WIP", "QA continuo", "Estabilización/operación"],
        "roles":    ["Product/Project", "Tech Lead", "Equipo (Dev/QA/UX)"],
        "metrics":  ["Lead time", "Throughput", "WIP", "Cumulative Flow"],
        "avanzado": ["Políticas explícitas", "Clases de servicio/SLAs", "Gestión de bloqueos"]
    },
    "XP": {
        "rituales": ["Iteraciones cortas", "Planning game", "Retro", "Integración continua"],
        "fases":    ["Discovery + Historias", "Iteraciones con TDD/Refactor/CI", "Pruebas de aceptación", "Release y traspaso"],
        "roles":    ["Cliente/PO", "Equipo de desarrollo", "Coach (opcional)"],
        "metrics":  ["Cobertura de tests", "Frecuencia de despliegue", "Cambios fallidos"],
        "avanzado": ["TDD/ATDD", "Pair/Mob programming", "Feature toggles"]
    },
    "Lean": {
        "rituales": ["Kaizen", "Gemba", "Revisión del flujo de valor"],
        "fases":    ["Mapa de valor", "Eliminar desperdicios", "Entregas por demanda"],
        "roles":    ["Líder de producto", "Equipo multifuncional"],
        "metrics":  ["Lead time", "Takt time", "WIP"],
        "avanzado": ["JIT", "Poka-Yoke", "Teoría de colas"]
    },
    "Scrumban": {
        "rituales": ["Daily", "Replenishment", "Retro"],
        "fases":    ["Backlog a flujo con WIP", "Revisiones periódicas", "Release continuo"],
        "roles":    ["PO/PM", "Scrum Master o Flow Manager", "Equipo"],
        "metrics":  ["Velocidad y métricas de flujo"],
        "avanzado": ["WIP dinámico", "Políticas híbridas sprint/flujo"]
    },
    "Crystal": {
        "rituales": ["Entregas frecuentes", "Retro e inspección", "Revisión de trabajo"],
        "fases":    ["Inicio ligero", "Iteraciones", "Release"],
        "roles":    ["Usuarios clave", "Equipo polivalente"],
        "metrics":  ["Frecuencia de entrega"],
        "avanzado": ["Ajustar prácticas a tamaño/criticidad"]
    },
    "FDD": {
        "rituales": ["Plan por funcionalidades", "Diseñar por funcionalidad", "Construir por funcionalidad"],
        "fases":    ["Modelo de dominio", "Lista de funcionalidades", "Diseño y construcción iterativa"],
        "roles":    ["Chief Programmer", "Class Owners", "Equipo"],
        "metrics":  ["Progreso por funcionalidad"],
        "avanzado": ["Feature teams y ownership claro"]
    },
    "DSDM": {
        "rituales": ["Timeboxing", "MoSCoW", "Workshops"],
        "fases":    ["Preproyecto", "Exploración", "Ingeniería", "Implementación"],
        "roles":    ["Business Sponsor/Visionary", "Team Leader", "Solution Dev/Tester"],
        "metrics":  ["Cumplimiento de timebox", "Valor entregado"],
        "avanzado": ["Facilitación y MoSCoW estricta"]
    },
    "SAFe": {
        "rituales": ["PI Planning", "System demo", "Inspect & Adapt"],
        "fases":    ["ARTs por PI", "Cadencias sincronizadas", "Release train"],
        "roles":    ["Product Manager/PO", "RTE", "System Architect"],
        "metrics":  ["Predictabilidad", "Tiempo de flujo", "Objetivos de PI"],
        "avanzado": ["Lean Portfolio y guardrails de inversión"]
    },
    "DevOps": {
        "rituales": ["Postmortems sin culpa", "Revisión de pipeline", "Game days"],
        "fases":    ["Integración continua", "Despliegue continuo", "Operación y observabilidad", "Mejora continua"],
        "roles":    ["Dev", "Ops/SRE", "Security"],
        "metrics":  ["DORA: frecuencia despliegue, tiempo de entrega, MTTR, tasa de fallos"],
        "avanzado": ["Infraestructura como código", "Entrega progresiva", "SLO/SLA y error budgets"]
    }
}

def _level_label(code: str) -> str:
    return {"beginner": "principiante", "intermediate": "intermedio", "expert": "experto"}.get(code, "?")

def _training_intro(level: str) -> str:
    lv = _level_label(level)
    return (
        f"Nivel seleccionado: {lv}.\n\n"
        "Temas disponibles: metodologías, fases, roles, métricas, ventajas.\n"
        "Ejemplos:\n"
        "- quiero aprender sobre Kanban\n"
        "- fases de Scrum\n"
        "- roles del equipo en XP\n"
        "- métricas de DevOps\n"
        "- ventajas de SAFe\n\n"
        "Cuando quieras terminar, escribe: salir de la formación."
    )

def _training_catalog(level: str) -> str:
    names = sorted(METHODOLOGIES.keys())
    if level == "beginner":
        bullets = [f"- {n}: {_one_liner_from_info(METHODOLOGIES.get(n, {}), n)}" for n in names]
    elif level == "intermediate":
        bullets = [f"- {n}: prácticas clave: " + ", ".join((METHODOLOGIES.get(n, {}).get("practicas_clave") or [])[:4]) for n in names]
    else:
        bullets = [f"- {n}: encaja si: " + "; ".join((METHODOLOGIES.get(n, {}).get("encaja_bien_si") or [])[:3]) for n in names]
    return "Metodologías disponibles:\n" + "\n".join(bullets) + "\n\nPide: quiero aprender sobre <metodología>."

def _training_method_card(method: str, level: str) -> str:
    m = normalize_method_name(method)
    info_m = _TRAIN_METHOD.get(m, {})
    overview = _one_liner_from_info(METHODOLOGIES.get(m, {}), m)

    lines: List[str] = [f"{m} — mini formación ({_level_label(level)})", f"Qué es: {overview}"]

    if level == "beginner":
        if info_m.get("rituales"):
            lines.append("Rituales típicos: " + ", ".join(info_m["rituales"]))
        if info_m.get("roles"):
            lines.append("Roles recomendados: " + ", ".join(info_m["roles"]))
        lines.append("Consejo: visualiza el trabajo y pide feedback frecuente.")
    elif level == "intermediate":
        if info_m.get("fases"):
            lines.append("Fases típicas: " + " → ".join(info_m["fases"]))
        if info_m.get("metrics"):
            lines.append("Métricas útiles: " + ", ".join(info_m["metrics"]))
    else:
        if info_m.get("metrics"):
            lines.append("Métricas clave: " + ", ".join(info_m["metrics"]))
        if info_m.get("avanzado"):
            lines.append("Prácticas avanzadas: " + ", ".join(info_m["avanzado"]))

    lines.append('Pide “fases de <metodología>”, “roles de <metodología>”, “métricas de <metodología>” o escribe “salir de la formación”.')
    return "\n".join(lines)

def _training_phases_card(level: str, method: Optional[str] = None) -> str:
    m = normalize_method_name(method) if method else None
    data = _TRAIN_METHOD.get(m or "Scrum", _TRAIN_METHOD["Scrum"])
    phases = data.get("fases") or ["Descubrimiento", "Desarrollo iterativo", "QA/Hardening", "Release"]

    title = f"Fases en {m}" if m else "Fases típicas"
    lines = [f"{title} — nivel {_level_label(level)}"]
    if level == "beginner":
        lines += [f"- {p}" for p in phases]
        lines.append("Tip: cierra cada fase con una demo y una checklist de hecho.")
    elif level == "intermediate":
        lines += [f"- {p} (artefactos y salidas claras)" for p in phases]
        lines.append("Mide tiempo de ciclo por fase y defectos detectados.")
    else:
        lines += [f"- {p} (riesgos a reducir y políticas de entrada/salida)" for p in phases]
        lines.append("Optimiza WIP y colas con datos.")
    lines.append('Para más contenido: “roles”, “métricas” o “salir de la formación”.')
    return "\n".join(lines)

def _training_roles_card(level: str, method: Optional[str] = None) -> str:
    m = normalize_method_name(method) if method else None
    roles = (_TRAIN_METHOD.get(m, {}) or _TRAIN_METHOD["Scrum"]).get("roles",
            ["PO/PM", "Scrum Master/Facilitador", "Tech Lead", "Backend", "Frontend", "QA", "UX/UI", "DevOps"])
    title = f"Roles en {m}" if m else "Roles del equipo"
    lines = [f"{title} — nivel {_level_label(level)}"]
    if level == "beginner":
        lines += [f"- {r}: función en una frase" for r in roles]
        lines.append("Asegura prioridades claras y poca multitarea.")
    elif level == "intermediate":
        lines += [f"- {r}: responsabilidades y artefactos asociados" for r in roles]
        lines.append("Evita handoffs largos; pairing y Definition of Done compartido.")
    else:
        lines += [f"- {r}: responsabilidades, riesgos y anti-patrones comunes" for r in roles]
        lines.append("Mide carga y throughput del equipo.")
    lines.append('Puedes pedir “fases”, “métricas” o escribir “salir de la formación”.')
    return "\n".join(lines)

def _training_metrics_card(level: str, method: Optional[str] = None) -> str:
    m = normalize_method_name(method) if method else None
    metrics = (_TRAIN_METHOD.get(m, {}) or _TRAIN_METHOD["Scrum"]).get("metrics", ["Lead time", "Cycle time"])
    title = f"Métricas en {m}" if m else "Métricas útiles"
    lines = [f"{title} — nivel {_level_label(level)}"]
    if level == "beginner":
        lines.append("Para empezar, mira estas métricas y su tendencia:")
        lines += [f"- {x}" for x in metrics[:3]]
    elif level == "intermediate":
        lines.append("Úsalas para ver cuellos de botella y predecir entregas:")
        lines += [f"- {x}: qué mide y cómo mejora la entrega" for x in metrics]
    else:
        lines.append("Consejos avanzados:")
        lines += [f"- {x}: define objetivos, revisa outliers y correlación con calidad" for x in metrics]
    lines.append('Pide “fases”, “roles” o escribe “salir de la formación”.')
    return "\n".join(lines)

def _training_define_card(level: str, method: str) -> str:
    m = normalize_method_name(method)
    overview = _one_liner_from_info(METHODOLOGIES.get(m, {}), m)
    extra = ""
    if level == "intermediate":
        extra = " Cómo se trabaja: ciclos cortos, trabajo visible y feedback constante."
    elif level == "expert":
        extra = " Enfócate en riesgos, flujo y decisiones basadas en datos."
    return f"Qué es {m}: {overview}{extra}"

def _training_benefits_card(level: str, method: str) -> str:
    m = normalize_method_name(method)
    fit = METHODOLOGIES.get(m, {}).get("encaja_bien_si") or []
    avoid = METHODOLOGIES.get(m, {}).get("evitar_si") or []
    lines = [f"Ventajas y cuándo usar {m} — nivel {_level_label(level)}"]
    if fit:
        lines.append("Va especialmente bien si: " + "; ".join(fit))
    if level != "beginner" and avoid:
        lines.append("Precauciones: " + "; ".join(avoid))
    return "\n".join(lines)


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
                return "Tengo un cambio pendiente con evaluación. ¿Lo aplico? sí/no", "Esperando confirmación de cambio."
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
                return "Tengo un cambio de metodología pendiente. ¿Lo aplico? sí/no", "Esperando confirmación de cambio."

    # === MODO FORMACIÓN: activar, guiar por nivel/temas y salir ===
    if _wants_training(text):
        _enter_training(session_id)
        return (
            "Modo formación activado.\n"
            "¿Cuál es tu nivel? principiante, intermedio o experto.\n"
            "Puedes salir cuando quieras diciendo: salir de la formación."
        ), "Formación: activada"

    tr = _get_training_state(session_id)
    if tr.get("active"):
        if _training_exit(text):
            _exit_training(session_id)
            return ("Salgo del modo formación. ¿Generamos una propuesta? Usa /propuesta: ..."), "Formación: salida"

        if not tr.get("level"):
            lv = _parse_level(text)
            if not lv:
                return ("Indícame tu nivel: principiante, intermedio o experto.\n"
                        "Para terminar: salir de la formación."), "Formación: esperando nivel"
            tr["level"] = lv
            _set_training_state(session_id, tr)
            return _training_intro(lv), "Formación: nivel fijado"

        # Peticiones dentro de formación
        topic, method_in_text = _training_topic_and_method(text)

        # Preguntas específicas con método → responde SOLO a eso
        if topic == "fases" and method_in_text:
            return _training_phases_card(tr["level"], method_in_text), f"Formación: fases de {method_in_text}"
        if topic == "roles" and method_in_text:
            return _training_roles_card(tr["level"], method_in_text), f"Formación: roles de {method_in_text}"
        if topic == "metricas" and method_in_text:
            return _training_metrics_card(tr["level"], method_in_text), f"Formación: métricas de {method_in_text}"
        if topic == "quees" and method_in_text:
            return _training_define_card(tr["level"], method_in_text), f"Formación: qué es {method_in_text}"
        if topic == "ventajas" and method_in_text:
            return _training_benefits_card(tr["level"], method_in_text), f"Formación: ventajas {method_in_text}"

        # Preguntas generales sin método
        if topic == "metodologias":
            return _training_catalog(tr["level"]), "Formación: catálogo"
        if topic == "fases":
            return _training_phases_card(tr["level"]), "Formación: fases"
        if topic == "roles":
            return _training_roles_card(tr["level"]), "Formación: roles"
        if topic == "metricas":
            return _training_metrics_card(tr["level"]), "Formación: métricas"

        # “Quiero aprender sobre <método>”
        if method_in_text:
            return _training_method_card(method_in_text, tr["level"]), f"Formación: {method_in_text}"

        # Ayuda contextual
        return (
            f"Estás en modo formación (nivel {_level_label(tr['level'])}).\n"
            "Pídeme: metodologías, fases, roles, métricas o ‘quiero aprender sobre <metodología>’.\n"
            "Para salir, escribe: salir de la formación."
        ), "Formación: ayuda"

    # Intents (si hay modelo entrenado)
    intent, conf = ("other", 0.0)
    if _INTENTS is not None:
        try:
            intent, conf = _INTENTS.predict(text)
        except Exception:
            pass
    if conf >= 0.80:
        if intent == "greet":
            return "¡Hola! ¿Quieres generar una propuesta de proyecto o aprender un poco sobre consultoría? Si prefieres aprender, di: quiero formarme.", "Saludo (intent)."
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
            "¡Genial, propuesta aprobada! Para asignar personas a cada tarea, "
            "cuéntame tu plantilla (una por línea) con este formato:\n"
            "Nombre — Rol — Skills clave — Seniority — Disponibilidad%\n"
            "Ejemplos:\n"
            "- Ana Ruiz — Backend — Python, Django, AWS — Senior — 100%\n"
            "- Luis Pérez — QA — Cypress, E2E — Semi Senior — 50%"
        )
        return prompt, "Solicitud de plantilla."

    # ——— Si el usuario pega su plantilla: parsear, asignar, formación y tareas por fase
    if proposal and _looks_like_staff_list(text):
        staff = _parse_staff_list(text)
        if not staff:
            return "No pude reconocer la plantilla. Usa: 'Nombre — Rol — Skills — Seniority — %'.", "Formato staff no válido."

        # 1) Sugerir asignación por rol
        try:
            asign = _suggest_staffing(proposal, staff)
        except Exception:
            asign = ["Asignación sugerida no disponible por ahora."]

        # 2) Plan de formación
        try:
            training = _render_training_plan(proposal, staff)
        except Exception:
            training = ["Plan de formación no disponible por ahora."]

        # 3) Desglose de tareas por persona y por fase
        try:
            phase_tasks = _render_phase_task_breakdown(proposal, staff)
        except Exception as e:
            phase_tasks = [f"No pude generar el desglose de tareas por fase: {e}"]

        try:
            set_last_area(session_id, "staffing")
        except Exception:
            pass

        out = []
        if asign:
            out += asign
        if training:
            out += [""] + training
        if phase_tasks:
            out += [""] + phase_tasks

        return "\n".join(out), "Asignación + formación + tareas por fase."

    # Comando explícito: /propuesta
    if text.lower().startswith("/propuesta:"):
        req = text.split(":", 1)[1].strip() or "Proyecto genérico"
        try:
            log_message(session_id, "user", f"[REQ] {req}")
        except Exception:
            pass
        p = generate_proposal(req)
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

    # Comando explícito: /cambiar:
    if text.lower().startswith("/cambiar:"):
        arg = text.split(":", 1)[1].strip()
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
        # si no, intentar parsear como parche general (equipo, fases, presupuesto, riesgos, …)
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
            return ("Para evaluar si conviene cambiar a {}, necesito una propuesta base. "
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

        head = f"Propones cambiar a {target} (actual: {current})."
        scores = f"Puntuaciones → {current}: {sc_current:.2f} • {target}: {sc_target:.2f}"

        if advisable:
            msg = [head, "Sí parece conveniente el cambio.", scores]
            if hits_target:
                msg.append("Señales a favor: " + "; ".join(hits_target))
            if why_target:
                msg.append("Razones:")
                msg += [f"- {x}" for x in why_target]
            if evitar_current:
                msg.append(f"Cuándo no conviene {current}: " + "; ".join(evitar_current))
        else:
            msg = [head, "No aconsejo el cambio en este contexto.", scores]
            if hits_current:
                msg.append("Señales para mantener la actual: " + "; ".join(hits_current))
            why_current = explain_methodology_choice(req_text, current)
            if why_current:
                msg.append("Razones para mantener:")
                msg += [f"- {x}" for x in why_current]
            if evitar_target:
                msg.append(f"Riesgos si cambiamos a {target}: " + "; ".join(evitar_target))

        set_pending_change(session_id, target)
        msg.append(f"¿Quieres que cambie el plan a {target} ahora? sí/no")
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

    # CALENDARIO / PLAZOS → pide fecha, calcula y prepara confirmación
    if _looks_like_timeline_intent(text) or _parse_start_date_es(text) is not None:
        if not proposal:
            return ("Primero genero una propuesta para conocer fases/semana y así calcular los plazos. "
                    "Usa '/propuesta: ...'."), "Calendario sin propuesta."

        start = _parse_start_date_es(text)
        if not start:
            return ("¿Desde cuándo quieres empezar el proyecto? "
                    "Dime una fecha (por ejemplo: 2025-10-01, 1/10/2025, 1 de octubre, en 2 semanas)."), "Pedir fecha inicio."

        preview_lines = _render_timeline_text(proposal, start)
        try:
            patch = _build_timeline_patch(proposal, start)
            eval_text, _ = _make_pending_patch(session_id, patch, proposal, req_text)
            return "\n".join(preview_lines) + "\n\n" + eval_text, "Calendario (pendiente confirmación)."
        except Exception:
            return "\n".join(preview_lines), "Calendario (solo vista)."

    # COMUNICACIÓN & FEEDBACK (Gobernanza)
    ntext = _norm(text)
    if any(w in ntext for w in [
        "feedback","retroaliment","comunicacion","comunicación","canal","reunion","reunión",
        "ceremonia","cadencia","ritmo","status","demo","retro","governance","gobernanza"
    ]):
        if not proposal:
            return ("Primero necesito una propuesta para adaptar canales y cadencias a metodología y fases. "
                    "Usa '/propuesta: ...'."), "Gobernanza sin propuesta."

        meth = (proposal.get("methodology") or "").lower()
        tl = proposal.get("timeline") or {}

        channels = ["Slack/Teams (canal #proyecto)", "Jira/Board Kanban", "Confluence/Docs", "Google Meet/Zoom para síncronas"]
        if "scrum" in meth:
            cadence = ["Daily 15 min", "Planning cada 2 semanas", "Review + Retrospectiva cada 2 semanas"]
        elif "kanban" in meth:
            cadence = ["Daily 10 min", "Revisión de flujo semanal", "Retrospectiva mensual"]
        elif "waterfall" in meth or "cascada" in meth:
            cadence = ["Status semanal 30 min", "Comité de cambios quincenal", "Revisión de hito por fase"]
        else:
            cadence = ["Status semanal 30 min", "Demostración quincenal", "Retrospectiva mensual"]

        feedback_windows = []
        events = tl.get("events") or []
        if events:
            for e in events:
                try:
                    s = datetime.fromisoformat(e["start"]).date()
                    en = datetime.fromisoformat(e["end"]).date()
                    feedback_windows.append(f"{e.get('phase','Fase')}: {_fmt_d(s)} → {_fmt_d(en)} (feedback al final de la fase)")
                except Exception:
                    feedback_windows.append(f"{e.get('phase','Fase')}: {e.get('start')} → {e.get('end')} (feedback al final de la fase)")
        else:
            feedback_windows = ["Definir ventanas de feedback al fijar calendario (demos quincenales y revisión al cierre de cada fase)."]

        preferred_docs = ["Definition of Ready/Done", "ADR (Architecture Decision Records)", "Roadmap y Changelog", "Guía de PR y DoR/DoD"]

        preview = [
            f"Comunicación y feedback (metodología: {proposal.get('methodology','')}):",
            "- Canales: " + ", ".join(channels),
            "- Cadencia: " + " • ".join(cadence),
            "- Ventanas de feedback:",
        ] + [f"  • {fw}" for fw in feedback_windows] + [
            "- Artefactos: " + ", ".join(preferred_docs)
        ]

        gov = {
            "channels": channels,
            "cadence": cadence,
            "feedback_windows": feedback_windows,
            "preferred_docs": preferred_docs
        }
        try:
            patch = {"type": "governance", "ops": [{"op": "set", "value": gov}]}
            eval_text, _ = _make_pending_patch(session_id, patch, proposal, req_text)
            return "\n".join(preview) + "\n\n" + eval_text, "Gobernanza (pendiente confirmación)."
        except Exception:
            return "\n".join(preview), "Gobernanza (solo vista)."

    # RIESGOS → detalle + plan + confirmación
    if _asks_risks_simple(text):
        try:
            set_last_area(session_id, "riesgos")
        except Exception:
            pass

        if not proposal:
            return ("Aún no tengo una propuesta para analizar riesgos. "
                    "Genera una con '/propuesta: ...' y luego te detallo riesgos y plan de prevención."), "Riesgos sin propuesta."

        try:
            detailed_lines = _render_risks_detail(proposal)
            text_out = "\n".join(detailed_lines)
        except Exception:
            lst = _expand_risks(req_text, proposal.get("methodology"))
            extra = f"\n\nPuedo añadir un plan de prevención adaptado a {proposal.get('methodology','')}." if proposal.get("methodology") else ""
            text_out = "Riesgos:\n- " + "\n- ".join(lst) + extra

        try:
            patch = _build_risk_controls_patch(proposal)  # {'type':'risks','ops':[...]}
            eval_text, _ = _make_pending_patch(session_id, patch, proposal, req_text)
            return text_out + "\n\n" + eval_text, "Riesgos + plan (pendiente de confirmación)."
        except Exception:
            return text_out, "Riesgos (detalle sin patch)."

    # Catálogo y definiciones de metodologías
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
        return "¡Hola! ¿Quieres generar una propuesta de proyecto o aprender un poco sobre consultoría? Si prefieres aprender, di: quiero formarme.", "Saludo."
    if _is_farewell(text):
        return "¡Hasta luego! Si quieres, deja aquí los requisitos y seguiré trabajando en la propuesta.", "Despedida."
    if _is_thanks(text):
        return "¡A ti! Si necesitas presupuesto o plan de equipo, dime los requisitos.", "Agradecimiento."
    if _is_help(text):
        return (
            "Puedo: 1) generar una propuesta completa (equipo, fases, metodología, presupuesto, riesgos), "
            "2) explicar por qué tomo cada decisión (con citas), 3) evaluar y aplicar cambios con confirmación (sí/no) en metodología y en toda la propuesta, "
            "4) modo formación por niveles (principiante/intermedio/experto).\n"
            "Ejemplos: 'añade 0.5 QA', 'tarifa de Backend a 1200', 'contingencia a 15%', 'cambia Sprints de Desarrollo a 8 semanas', "
            "'quita fase QA', 'añade riesgo: cumplimiento RGPD', 'quiero formarme'."
        ), "Ayuda."

    # si preguntan por una fase concreta → explicarla en detalle
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
                    extra = f"\nEn esta propuesta: {cnt:g} {r}."
            return (f"{r} — función y valor:\n- " + "\n- ".join(bullets) + extra), "Rol concreto."
        else:
            return ("Veo varios roles mencionados. Dime uno concreto (por ejemplo, QA o Tech Lead) y te explico su función."), "Varios roles."

    # Preguntas de dominio (sin 'por qué')
    if _asks_methodology(text) and not _asks_why(text):
        try:
            set_last_area(session_id, "metodologia")
        except Exception:
            pass
        return _catalog_text(), "Metodologías (catálogo)."

    # Presupuesto (detalle visible)
    if (_asks_budget(text) or "presupuesto" in _norm(text)) and not _asks_why(text):
        if proposal:
            try:
                set_last_area(session_id, "presupuesto")
            except Exception:
                pass
            try:
                detail = _render_budget_detail(proposal)   # helper de detalle (roles + actividades)
                return "\n".join(detail), "Presupuesto (detalle)."
            except Exception:
                return "\n".join(_explain_budget(proposal)), "Presupuesto."
        return ("Para estimar presupuesto considero: alcance → equipo → semanas → tarifas por rol + % de contingencia.\n"
                "Genera una propuesta con '/propuesta: ...' y te doy el detalle."), "Guía presupuesto."

    # Alias de desglose → también muestra el detalle
    if _asks_budget_breakdown(text) or "desglose" in _norm(text) or "detalle" in _norm(text):
        if proposal:
            try:
                set_last_area(session_id, "presupuesto")
            except Exception:
                pass
            try:
                detail = _render_budget_detail(proposal)
                return "\n".join(detail), "Presupuesto (detalle)."
            except Exception:
                try:
                    breakdown = _explain_budget_breakdown(proposal)
                    return "Presupuesto — desglose por rol:\n" + "\n".join(breakdown), "Desglose presupuesto."
                except Exception:
                    return "\n".join(_explain_budget(proposal)), "Presupuesto."
        else:
            return "Genera primero una propuesta con '/propuesta: ...' para poder desglosar el presupuesto por rol.", "Sin propuesta para desglose."

    if _asks_team(text) and not _asks_why(text):
        set_last_area(session_id, "equipo")
        if proposal:
            reasons = _explain_team_general(proposal, req_text)
            return "Equipo propuesto — razones:\n- " + "\n".join(reasons), "Equipo."
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
                    f"He usado {chosen} en vez de {other} porque se ajusta mejor a tus requisitos.",
                    f"Puntuaciones: {chosen}={sc_chosen:.2f} vs {other}={sc_other:.2f}. Top3: {top3}."
                ]
                if reasons_hits_chosen:
                    msg.append("Señales que favorecen la elegida: " + "; ".join(reasons_hits_chosen))
                if why_chosen:
                    msg.append("A favor de la elegida:")
                    msg += [f"- {x}" for x in why_chosen]
                if evitar_other:
                    msg.append(f"Cuándo no conviene {other}: " + "; ".join(evitar_other))
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
            return f"¿Por qué {target}?\n- " + "\n".join(why_lines) + rank_line, "Explicación metodología."

        # Otras 'por qué'
        if proposal and _asks_why_team_general(text):
            set_last_area(session_id, "equipo")
            reasons = _explain_team_general(proposal, req_text)
            team_lines = [f"- {t['role']} x{t['count']}" for t in proposal["team"]]
            return "Equipo — por qué:\n- " + "\n".join(reasons) + "\nDesglose:\n" + "\n".join(team_lines), "Equipo por qué."

        rc = _asks_why_role_count(text)
        if proposal and rc:
            set_last_area(session_id, "equipo")
            role, count = rc
            return f"¿Por qué {count:g} {role}?\n- " + "\n".join(_explain_role_count(role, count, req_text)), "Cantidad por rol."

        if proposal and _asks_why_phases(text):
            set_last_area(session_id, "phases")
            expl = _explain_phases_method_aware(proposal)
            m = re.search(r"\b(\d+)\s*fases\b", _norm(text))
            if m:
                asked = int(m.group(1))
                expl.insert(1, f"Se han propuesto {len(proposal['phases'])} fases (preguntas por {asked}).")
            return "Fases — por qué:\n" + "\n".join(expl), "Fases por qué."

        if proposal and _asks_budget(text):
            return "Presupuesto — por qué:\n- " + "\n".join(_explain_budget(proposal)), "Presupuesto por qué."

        roles_why = _extract_roles_from_text(text)
        if proposal and roles_why:
            set_last_area(session_id, "equipo")
            r = roles_why[0]
            cnt = _find_role_count_in_proposal(proposal, r)
            if cnt is not None:
                return f"¿Por qué {r} en el plan?\n- " + "\n".join(_explain_role_count(r, cnt, req_text)), "Rol por qué."
            else:
                return f"¿Por qué {r}?\n- " + "\n".join(_explain_role(r, req_text)), "Rol por qué."

        if proposal:
            generic = [
                f"Metodología: {proposal['methodology']}",
                "Equipo dimensionado por módulos detectados y equilibrio coste/velocidad.",
                "Fases cubren descubrimiento a entrega; cada una reduce un riesgo.",
                "Presupuesto = headcount × semanas × tarifa por rol + % de contingencia."
            ]
            return "Explicación general:\n- " + "\n- ".join(generic), "Explicación general."
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

    # GAPS & FORMACIÓN BAJO DEMANDA
    if _asks_training_plan(text):
        staff = []
        try:
            staff = get_staff_roster(session_id)
        except Exception:
            staff = []
        if not staff:
            return "Pégame la plantilla (Nombre — Rol — Skills — Seniority — %) para analizar carencias y proponerte un plan de formación.", "Falta plantilla."
        training = _render_training_plan(proposal, staff) if proposal else ["Primero generemos una propuesta para conocer stack/metodología."]
        return "\n".join(training), "Plan de formación."

    # Fallback
    return (
        "Te he entendido. Dame más contexto (objetivo, usuarios, módulos clave) "
        "o escribe '/propuesta: ...' y te entrego un plan completo con justificación y fuentes."
    ), "Fallback."
