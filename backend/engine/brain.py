# backend/engine/brain.py

import re
import json
import copy
import unicodedata
from typing import Tuple, Dict, Any, List, Optional
import logging

# Context helpers for session proposal state
try:
    from backend.engine.context import (
        get_last_proposal, set_last_proposal,
        get_pending_change, set_pending_change, clear_pending_change,
        set_last_area, get_last_area
    )
except Exception:
    # Fallback stubs if context module isn't available (should not happen in normal env)
    def get_last_proposal(*a, **k): return (None, None)
    def set_last_proposal(*a, **k): return None
    def get_pending_change(*a, **k): return None
    def set_pending_change(*a, **k): return None
    def clear_pending_change(*a, **k): return None
    def set_last_area(*a, **k): return None
    def get_last_area(*a, **k): return None

# Memoria de usuario 
try:
    from backend.memory.state_store import get_client_prefs, upsert_client_pref
except Exception:  # pragma: no cover
    def get_client_prefs(*a, **k): return {}
    def upsert_client_pref(*a, **k): return None


def _is_no(text: str) -> bool:
    """Detecta respuestas negativas del usuario: 'no', 'mejor no', 'cancelar'..."""
    t = _norm(text)
    if not t:
        return False
    no_set = {"no", "n", "mejor no", "nop", "negativo"}
    if t in no_set:
        return True
    if any(tok in t for tok in ("cancel", "cancela", "anula", "nunca", "no lo hagas", "no aplicar")):
        return True
    return False


def _norm(s: str) -> str:
    """Normalize text: lowercase, strip accents and extra spaces for robust matching."""
    if s is None:
        return ""
    try:
        nk = unicodedata.normalize('NFKD', s.lower())
        return ''.join(c for c in nk if not unicodedata.combining(c)).strip()
    except Exception:
        return (s or '').lower().strip()

# Intents classifier (optional). If no model is available, keep None.
_INTENTS = None

# Similarity helper (optional). If not available, keep None.
_SIM = None

# Importar catálogo de metodologías (datos estructurados sobre fases/prácticas)
try:
    from backend.knowledge.methodologies import METHODOLOGIES, get_method_phases, normalize_method_name
except Exception:
    # Fallbacks para entornos de test donde el módulo no esté disponible
    METHODOLOGIES = {}
    def get_method_phases(m: str) -> List[Dict]:
        return []
    def normalize_method_name(n: str) -> str:
        return (n or '').strip().title()


# ===================== detectores =====================

def _is_greeting(text: str) -> bool:
    # detección sencilla por tokens comunes
    t = _norm(text)
    for k in ("hola", "buenas", "hey", "hello", "qué tal", "que tal"):
        if k in t:
            return True
    return False

def _is_farewell(text: str) -> bool:
    t = _norm(text)
    for k in ("adios", "adiós", "hasta luego", "nos vemos", "chao"):
        if k in t:
            return True
    return False

def _is_thanks(text: str) -> bool:
    t = _norm(text)
    for k in ("gracias", "mil gracias", "thank", "thanks"):
        if k in t:
            return True
    return False

def _is_help(text: str) -> bool:
    t = _norm(text)
    return "ayuda" in t or "qué puedes hacer" in t or "que puedes hacer" in t

def _asks_methodology(text: str) -> bool:
    # versión simple: buscar tokens comunes en el texto
    t = _norm(text)
    for k in ["scrum", "kanban", "scrumban", "xp", "lean", "devops", "metodologia", "metodología"]:
        if k in t:
            return True
    return False

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
    # palabras clave sencillas
    t = _norm(text)
    return any(k in t for k in ["similar", "similares", "parecido", "parecidos", "casos parecidos", "proyectos similares"]) 

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


def _project_context_summary(p: Optional[Dict[str, Any]]) -> str:
    """Resumen corto (una línea o dos) con metodología, presupuesto y notas rápidas.
    Útil para anteponer contexto a respuestas generadas por acciones.
    """
    if not p:
        return "(Sin propuesta asociada)"
    meth = p.get("methodology") or "(no definida)"
    budget = p.get("budget") or {}
    total = budget.get("total_eur")
    try:
        total_fmt = _eur(float(total)) if total is not None else "(no estimado)"
    except Exception:
        total_fmt = str(total) or "(no estimado)"
    cont = float(((budget.get("assumptions") or {}).get("contingency_pct", 0)))
    team = p.get("team") or []
    team_brief = ", ".join(f"{t.get('role','?')} x{t.get('count',0)}" for t in team[:6])
    if len(team) > 6:
        team_brief += ", …"
    parts = [f"Metodología: {meth}", f"Presupuesto estimado: {total_fmt} (contingencia {cont:.0f}%);"]
    if team_brief:
        parts.append(f"Equipo: {team_brief}")
    return " • ".join(parts)




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
    header = f"Fases justificadas según la metodología {method}:"
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
# === Detección y explicación de fase concreta ===

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
                    # Preferir una fase de la proposal que contenga exactamente el alias
                    # (por ejemplo, si el usuario dice 'discovery' y la propuesta tiene
                    # una fase llamada 'Discovery', devolver esa fase). Si no se encuentra
                    # una coincidencia exacta con el alias, caer atrás a la búsqueda por
                    # la forma canónica (p.ej. 'incepcion').
                    for ph in proposal.get('phases', []):
                        try:
                            if a in _norm_simple(ph.get('name', '') or ''):
                                return ph['name']
                        except Exception:
                            continue
                    for ph in proposal.get('phases', []):
                        try:
                            if canon.split()[0] in _norm_simple(ph.get('name', '') or ''):
                                return ph['name']
                        except Exception:
                            continue
                return canon.title()

    return best

def _explain_specific_phase(asked: str, proposal: Optional[Dict[str, Any]]) -> str:
    method = (proposal or {}).get('methodology', 'Scrum')
    name = _match_phase_name(asked, proposal) or asked.title()
    n = _norm_simple(name)

    def block(title: str, bullets: List[str]) -> str:
        return f"{title}:\n- " + "\n- ".join(bullets)

    # Incepción / Plan de releases / Discovery
    if any(k in n for k in ['incepcion','inception','discovery','plan','inicio','kickoff']):
            return "\n\n".join([
            f"{name} — descripción detallada",
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
            f"Metodología actual: {method}."
        ])

    # Sprints / Iteraciones / Desarrollo
    if any(k in n for k in ['sprint','iteracion','desarrollo']):
        cad = "2 semanas" if method in ("Scrum", "XP", "Scrumban") else "flujo continuo"
        return "\n\n".join([
            f"{name} — descripción detallada",
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
            f"Metodología actual: {method}."
        ])

    # QA / Hardening / Estabilización
    if any(k in n for k in ['qa','hardening','stabiliz','aceptacion','testing']):
        return "\n\n".join([
            f"{name} — descripción detallada",
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
            f"Metodología actual: {method}."
        ])

    # Despliegue / Release / Handover
    if any(k in n for k in ['despliegue','release','produccion','handover','transferencia','go-live','salida']):
        return "\n\n".join([
            f"{name} — descripción detallada",
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
            f"Metodología actual: {method}."
        ])

    # Genérico
    return "\n\n".join([
        f"{name} — descripción detallada",
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
        f"Metodología actual: {method}."
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

    # Semanas totales: assumptions.project_weeks o suma de fases
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
            # Acepta otros separadores si no hay '—'
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
    # heurística: puntuación 0-10
    score = 0.0
    if _canonical_role(person.get("role", "")) == role:
        score += 5.0
    # puntos por keywords
    hay = _norm(" ".join(person.get("skills", [])) + " " + (person.get("seniority") or ""))
    for kw in (_ROLE_KEYWORDS.get(role, []) or [])[:6]:
        if _norm(kw) in hay:
            score += 1.0
    s = _norm(person.get("seniority") or "")
    if "lead" in s or "principal" in s:
        score += 1.5
    elif "senior" in s or "sr" in s:
        score += 0.8
    elif "junior" in s or "jr" in s:
        score += 0.1
    try:
        avail = float(person.get("availability_pct", 100)) / 100.0
    except Exception:
        avail = 1.0
    if avail < 0.5:
        score *= 0.7
    return score
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
    lines.append("Asignación por rol (mejor persona y por qué)")
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
        # alternativas rápidas
        alt = [c["name"] for c in cands[1:3]]
        if alt:
            lines.append(f"  · Alternativas: {', '.join(alt)}")

    # — Por fase
    lines.append("")
    lines.append("Asignación sugerida por fase/tareas")
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
    # XP/Scrum: calidad interna
    if "xp" in meth or "scrum" in meth:
        req.add("tdd")
    return sorted(req)

def _person_has_topic(person: Dict[str, Any], topic: str) -> bool:
    blob = _norm(" ".join(person.get("skills", [])) + " " + (person.get("seniority") or "") + " " + (person.get("role") or ""))
    return _norm(topic) in blob

def _closest_upskilling_candidates(staff: List[Dict[str, Any]], topic: str) -> List[Dict[str, Any]]:
    # heurística: rol más cercano + seniority + disponibilidad
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
    lines.append("Gaps detectados & plan de formación")
    if not report["gaps"]:
        lines.append("- ✔︎ No hay carencias relevantes respecto al stack/metodología.")
        return lines
    for g in report["gaps"]:
        lines.append(f"- {g['topic']} — {g['why']}")
        if g.get("upskill_candidates"):
            who = ", ".join(f"{c.get('name')} ({c.get('role','')} {c.get('availability_pct',100)}%)" for c in g.get("upskill_candidates", []))
            lines.append(f"  • Upskilling recomendado: {who}")
        if g.get("resources"):
            lines.append(f"  • Recursos: " + " | ".join(g.get("resources", [])))
        lines.append(f"  • Alternativa: {g.get('external_hint','')}")
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
        # Ajustes por metodología
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

    # Arquetipos de fase: tareas/recursos
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
    lines.append("Presupuesto — desglose máximo")
    lines.append("")
    lines.append(f"Labor: {_eur(labor)}   •   Contingencia ({contingency_pct:.1f}%): {_eur(contingency_eur)}   •   Total: {_eur(total)}")
    lines.append("")

    # 1) Por roles
    lines.append("Distribución por roles:")
    if per_role:
        for role, amount in sorted(per_role.items(), key=lambda kv: kv[1], reverse=True):
            fte = role_to_fte.get(role, 0.0)
            rate = float(rates.get(role, 1000.0))
            lines.append(f"- {role}: {fte:g} FTE × {rate:.0f} €/sem × {weeks_total} sem → {_eur(amount)} ({_pct(amount, labor):.1f}%)")
    else:
        lines.append("- (No hay equipo definido; añade roles para una estimación precisa.)")

    # 2) Por fases
    lines.append("")
    lines.append("Distribución por fases:")
    for ph_name, amount in sorted(per_phase.items(), key=lambda kv: kv[1], reverse=True):
        w = next((int(ph.get("weeks", 0)) for ph in phases if ph["name"] == ph_name), 0)
        lines.append(f"- {ph_name} ({w}s): {_eur(amount)} ({_pct(amount, labor):.1f}%)")

    # 3) Matriz rol × fase
    lines.append("")
    lines.append("Matriz rol × fase:")
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
    lines.append(f"Contingencia {contingency_pct:.1f}% → {_eur(contingency_eur)} (asignación proporcional):")
    if labor > 0:
        lines.append("• Por **rol**: " + ", ".join(f"{r} {_eur(contingency_eur * (v/labor))}" for r, v in sorted(per_role.items(), key=lambda kv: kv[1], reverse=True)))
        lines.append("• Por **fase**: " + ", ".join(f"{ph} {_eur(contingency_eur * (v/labor))}" for ph, v in sorted(per_phase.items(), key=lambda kv: kv[1], reverse=True)))
    else:
        lines.append("• (No hay labor para distribuir.)")

    # 5) Tareas, personal y recursos por fase
    lines.append("")
    lines.append("Tareas, personal y recursos por fase:")
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
    lines = [f"{method} — ¿qué es y cuándo usarla?"]
    lines.append(_one_liner_from_info(info, method))
    pract = info.get("practicas_clave") or info.get("practicas") or []
    if pract:
        lines.append("Prácticas clave: " + ", ".join(pract))
    fit = info.get("encaja_bien_si") or info.get("fit") or []
    if fit:
        lines.append("Encaja bien si: " + "; ".join(fit))
    avoid = info.get("evitar_si") or info.get("avoid") or []
    if avoid:
        lines.append("Evitar si: " + "; ".join(avoid))
    src = info.get("sources") or []
    if src:
        lines.append("Fuentes:\n" + _format_sources(src))
    return "\n".join(lines)

def _catalog_text() -> str:
    """Lista todas las metodologías soportadas con un renglón de resumen cada una."""
    names = sorted(METHODOLOGIES.keys())
    bullets = []
    for name in names:
        bullets.append(f"- {name} — {_one_liner_from_info(METHODOLOGIES.get(name, {}), name)}")
    return "Metodologías que manejo:\n" + "\n".join(bullets) + "\n\n¿Quieres que te explique alguna en detalle o que recomiende la mejor para tu caso?"


# ====== detección de petición de cambio de metodología ======
_CHANGE_PAT = re.compile(
    r"(?:cambia(?:r)?\s+a|usar|quiero|prefiero|pasar\s+a)\s+(scrum|kanban|scrumban|xp|lean|crystal|fdd|dsdm|safe|devops)"
    r"(?:\s+(?:en\s+vez\s+de|en\s+lugar\s+de)\s+(scrum|kanban|scrumban|xp|lean|crystal|fdd|dsdm|safe|devops))?",
    re.I
)

def _handle_suggested_action(text: str, proposal: Dict[str, Any]) -> Optional[str]:
    """
    Maneja las acciones sugeridas y devuelve la respuesta detallada correspondiente.
    """
    t = _norm(text)
    
    if "desglosar tareas de discovery" in t:
        return handle_discovery_tasks(proposal)
    elif "riesgos técnicos" in t:
        return handle_risk_analysis(proposal)
    elif "kpis del proyecto" in t:
        return handle_kpis_definition(proposal)
    elif "plan de pruebas" in t or "qa" in t:
        return handle_qa_plan(proposal)
    elif "estrategia de despliegue" in t:
        return handle_deployment_strategy(proposal)
    elif "definir entregables" in t:
        return handle_deliverables(proposal)
    
    return None

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


# ===================== Cambios sobre toda la propuesta =====================

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
        add_line("📌 Evaluación del cambio de equipo:", lines)

        roles_before = {r["role"].lower(): float(r["count"]) for r in before.get("team", [])}
        roles_after = {r["role"].lower(): float(r["count"]) for r in after.get("team", [])}

        def had(role):
            return roles_before.get(role.lower(), 0.0) > 0.0

        def has(role):
            return roles_after.get(role.lower(), 0.0) > 0.0

        critical = {"pm": "PM", "tech lead": "Tech Lead", "qa": "QA"}
        critical_removed = [name for key, name in critical.items() if had(key) and not has(key)]
        critical_added = [name for key, name in critical.items() if not had(key) and has(key)]

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
        add_line("Detalle por rol propuesto:", lines)
        changed_any = False
        for rkey in sorted(set(list(roles_before.keys()) + list(roles_after.keys()))):
            old = float(roles_before.get(rkey, 0.0))
            new = float(roles_after.get(rkey, 0.0))
            if old == new:
                continue
            changed_any = True
            role_name = _canonical_role(rkey)
            reasons = _explain_role_count(role_name, new, req_text)
            add_line(f"🔹 Propuesta para {role_name}: {old:g} → {new:g} FTE", lines)
            for rs in reasons:
                add_line(f"   • {rs}", lines)
        if not changed_any:
            add_line("-(No hay variaciones de FTE por rol respecto al plan anterior).", lines)

        add_line("", lines)
        add_line("📊 Impacto estimado:", lines)
        add_line(f"- Semanas totales: {w0} → {w1}  (Δ {delta_w:+})", lines)
        add_line(f"- Headcount equivalente (FTE): {f0:g} → {f1:g}  (Δ {delta_f:+g})", lines)
        add_line(f"- Labor: {eur(labor0)} → {eur(labor1)}  (Δ {eur(labor1 - labor0)})", lines)
        add_line(f"- Total con contingencia ({cont_pct:.0f}%): {eur(b0)} → {eur(b1)}  (Δ {eur(delta_cost)})", lines)

    # ---------------- FASES ----------------
    elif t == "phases":
        add_line("📌 Evaluación del cambio de fases/timeline:", lines)
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
        add_line("📊 Impacto estimado:", lines)
        add_line(f"- Semanas totales: {w0} → {w1}  (Δ {delta_w:+})", lines)
        add_line(f"- Headcount equivalente (FTE): {f0:g} → {f1:g}  (Δ {delta_f:+g})", lines)
        add_line(f"- Total con contingencia ({cont_pct:.0f}%): {eur(b0)} → {eur(b1)}  (Δ {eur(delta_cost)})", lines)

    # ---------------- PRESUPUESTO ----------------
    elif t in ("budget", "rates", "contingency"):
        add_line("📌 Evaluación del cambio de presupuesto:", lines)

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
        add_line("📊 Impacto estimado:", lines)
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
        add_line("📌 Evaluación del cambio de riesgos/controles:", lines)
        adds, rems = 0, 0
        if "ops" in patch:
            for op in (patch.get("ops") or []):
                if op.get("op") == "add":
                    adds += 1
                if op.get("op") == "remove":
                    rems += 1
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
        add_line("📌 Evaluación del cambio de plazos/calendario:", lines)
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

        add_line(f"📅 Calendario propuesto desde {_fmt_d(sd)}:", lines)
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
    # Guardamos el parche en pending_change
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

    # —— Comunicación/feedback, estándares, KPIs, entregables ——

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

# ---------- Parsers de lenguaje natural: Parches ----------

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

    # Verbos comunes (simplificados)
    add_verbs = r"(?:anade|añade|agrega|suma|incluye|mete|añadir|agregar)"
    set_verbs = r"(?:deja|ajusta|pon|pone|establece|setea|sube|baja|pasa|cambia|poner|poner a)"
    rem_verbs = r"(?:quita|elimina|borra|saca|quitar|eliminar)"

    # Helper para convertir tokens numericos y palabras como 'medio'->0.5
    def _to_float(num: str) -> float:
        if not num:
            return 1.0
        s = num.strip().lower()
        if s in ("medio", "0.5", "0,5", "media"):
            return 0.5
        # manejar 'uno'/'dos' simples opcionalmente
        words = {"uno": 1.0, "dos": 2.0, "tres": 3.0, "cuatro": 4.0}
        if s in words:
            return float(words[s])
        try:
            return float(s.replace(",", "."))
        except Exception:
            return 1.0

    ops: List[Dict[str, Any]] = []

    # Buscar patrones 'añade 0.5 qa' o 'añade qa' (sin número -> 1)
    for m in re.finditer(fr"{add_verbs}\s+(?:(\d+[.,]?\d*)\s+)?([a-zA-Z\s/]+)", t):
        num, role = m.groups()
        ops.append({"op": "add", "role": role.strip(), "count": _to_float(num)})

    # Patrones de set tipo 'pon 2 backend' o 'pon backend a 2'
    for m in re.finditer(fr"{set_verbs}\s+(?:(\d+[.,]?\d*)\s+)?([a-zA-Z\s/]+)", t):
        num, role = m.groups()
    # si el match capturó el rol y el num está en la otra forma, intentar otro regex
        if role and re.search(r"\d", role) and not num:
            # intentar invertir grupos
            inv = re.search(fr"{set_verbs}\s+([a-zA-Z\s/]+)\s+(?:a|en)\s+(\d+[.,]?\d*)", t)
            if inv:
                role = inv.group(1); num = inv.group(2)
        ops.append({"op": "set", "role": role.strip(), "count": _to_float(num)})

    # Patrones 'pon pm a 1' / 'baja backend a 2'
    for m in re.finditer(fr"{set_verbs}\s+([a-zA-Z\s/]+)\s+(?:a|en)\s+(\d+[.,]?\d*)", t):
        role, num = m.groups()
        ops.append({"op": "set", "role": role.strip(), "count": _to_float(num)})

    # Remover roles: 'quita ux' etc.
    for m in re.finditer(fr"{rem_verbs}\s+([a-zA-Z\s/]+)", t):
        role = m.group(1)
        ops.append({"op": "remove", "role": role.strip()})

    # Filtrar ops vacas o mal formadas
    cleaned: List[Dict[str, Any]] = []
    for op in ops:
        r = op.get("role") or ""
        if not r:
            continue
        # normalizar espacios
        op["role"] = re.sub(r"\s+", " ", r).strip()
        if op.get("op") in ("add", "set"):
            try:
                op["count"] = float(op.get("count", 1.0))
            except Exception:
                op["count"] = 1.0
        cleaned.append(op)

    return {"type": "team", "ops": cleaned} if cleaned else None


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

# ---------- Helpers de riesgos (detalle + plan de prevención) ----------

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


def _render_phase_rich_response(ntext: str, phase_info: Dict, method: str, phase_asked: str) -> str:
    """Genera una respuesta rica y orientada a preguntas para una fase concreta.

    ntext: texto normalizado de la consulta del usuario
    phase_info: diccionario con campos de la fase (goals, checklist, kpis, etc.)
    method: nombre de la metodología
    phase_asked: texto original de la fase mencionada
    """
    lines = [f">> Sobre la fase {phase_info.get('name', phase_asked)} (metodología: {method}):\n"]

    # Resumen y contexto
    if phase_info.get('summary'):
        lines.append(phase_info.get('summary'))

    # Preguntas frecuentes / intenciones detectadas
    # Problemas / bloqueos
    if any(k in ntext for k in ["problema","issue","bloqueado","retraso","atascado","dificultad","error"]):
        if phase_info.get('common_issues'):
            lines.append('\nPROBLEMAS COMUNES:')
            for issue in phase_info.get('common_issues', []):
                lines.append(f"  - {issue}")
        if phase_info.get('mitigations'):
            lines.append('\nMEDIDAS RECOMENDADAS:')
            for mit in phase_info.get('mitigations', []):
                lines.append(f"  - {mit}")

    # Cambios / ajustes / checklist
    if any(k in ntext for k in ["cambio","modificar","ajustar","revisar","checklist","validar","comprobar"]):
        if phase_info.get('goals'):
            lines.append('\nOBJETIVOS:')
            for g in phase_info.get('goals', []):
                lines.append(f"  - {g}")
        if phase_info.get('checklist'):
            lines.append('\nCHECKLIST DETALLADO:')
            for c in phase_info.get('checklist', []):
                lines.append(f"  - {c}")

    # Cómo hacerlo / responsabilidades
    if any(k in ntext for k in ["como","que hacer","ayuda","necesito","roles","responsab","quien"]):
        if phase_info.get('roles_responsibilities'):
            lines.append('\nROLES Y RESPONSABILIDADES:')
            for role, resp in (phase_info.get('roles_responsibilities') or {}).items():
                lines.append(f"  - {role}: {resp}")
        if phase_info.get('questions_to_ask'):
            lines.append('\nPREGUNTAS ÚTILES PARA EL EQUIPO:')
            for q in phase_info.get('questions_to_ask', [])[:8]:
                lines.append(f"  - {q}")

    # KPIs y entregables
    if phase_info.get('kpis'):
        lines.append('\nKPIs SUGERIDOS:')
        for kpi in phase_info.get('kpis', [])[:8]:
            lines.append(f"  - {kpi}")
    if phase_info.get('deliverables'):
        lines.append('\nENTREGABLES PRINCIPALES:')
        for d in phase_info.get('deliverables', [])[:8]:
            lines.append(f"  - {d}")

    # Si el usuario pide 'amplía', 'detalla', 'desglosa' o 'más' sobre KPIs/entregables/prácticas
    expand_triggers = ["amplia", "ampliar", "amplía", "detalla", "detallar", "desglosa", "desglosar", "más", "mas", "explica", "profundiza", "profundizar", "describir", "desglosar"]
    if any(tok in ntext for tok in expand_triggers):
        # KPIs
        if _asks_kpis(ntext) or any(k in ntext for k in ["kpi", "kpis", "indicador", "indicadores", "objetivo", "metrica", "métrica"]):
            try:
                kblocks = _expand_kpis_for_phase(phase_info)
                lines.append('\n' + "\n".join(kblocks))
            except Exception:
                lines.append('\n(No pude generar el desglose de KPIs en este momento.)')

        # Entregables
        if _asks_deliverables(ntext) or any(k in ntext for k in ["entregable", "entregables", "artefacto", "artefactos", "documentación", "documentacion"]):
            try:
                dblocks = _expand_deliverables_for_phase(phase_info)
                lines.append('\n' + "\n".join(dblocks))
            except Exception:
                lines.append('\n( No pude generar el desglose de entregables en este momento.)')

        # Sugerencias prácticas / checklist / owners
        if any(k in ntext for k in ["sugerencia", "sugerencias", "práctica", "practica", "prácticas", "practicas", "checklist", "acciones", "pasos", "responsable", "owner", "owners", "propietario"]):
            try:
                pblocks = _expand_practices_for_phase(phase_info, method)
                lines.append('\n' + "\n".join(pblocks))
            except Exception:
                lines.append('\n(No pude generar sugerencias prácticas en este momento.)')

    # Si el usuario pregunta 'qué pasa si...' o escenarios
    if any(k in ntext for k in ["si", "y si", "qué pasa", "que pasa"]):
        lines.append('\nESCENARIOS COMUNES Y RESPUESTAS:')
        # heurísticas simples basadas en mitigations/common_issues
        if phase_info.get('common_issues'):
            for issue in phase_info.get('common_issues', [])[:3]:
                lines.append(f"  - Si ocurre '{issue}': revisar {phase_info.get('mitigations',[ 'acciones de mitigación no disponibles'])[0]}")
        else:
            lines.append("  - Si surge un bloqueo: identificar owner, reducir scope y comunicar impacto al PO.")

    # Añadir duración si existe
    if phase_info.get('typical_weeks'):
        lines.append(f"\nDuración típica: {phase_info.get('typical_weeks')} semanas")

    return "\n".join(lines)


def _expand_kpis_for_phase(phase_info: Dict, proposal: Optional[Dict[str, Any]] = None) -> List[str]:
    """Genera un desglose detallado de cada KPI sugerido: cómo medirlo, frecuencia, owner y objetivo inicial."""
    out: List[str] = []
    kpis = phase_info.get('kpis') or []
    if not kpis:
        return ["(No hay KPIs sugeridos para esta fase en el catálogo/propuesta.)"]
    out.append('DETALLE DE KPIs (medición, frecuencia, owner, objetivo inicial):')
    # Owner heuristics: prefer roles declared in the phase if present
    phase_roles = []
    try:
        phase_roles = list((phase_info.get('roles_responsibilities') or {}).keys())
    except Exception:
        phase_roles = []

    for k in kpis:
        # heurística: intentar inferir tipo y unidad
        kk = k.strip()
        meas = 'Métrica (ej. porcentaje / tiempo / ratio)'
        freq = 'Semanal'
        owner = 'PM / Tech Lead'
        target = 'Objetivo inicial a definir (ej. referencia basada en primer sprint)'
        # asignar owner por heurística usando roles de la fase si existen
        if phase_roles:
            # preferir PO, PM, Tech Lead, QA
            for pref in ('Product Owner', 'PO', 'PM', 'Tech Lead', 'QA', 'DevOps'):
                for r in phase_roles:
                    if pref.lower() in r.lower():
                        owner = r
                        break
                if owner != 'PM / Tech Lead':
                    break
        if any(tok in _norm(kk) for tok in ['lead time', 'leadtime', 'lead-time']):
            meas = 'Tiempo medio (días) desde creación hasta despliegue'
            freq = 'Diaria / semanal agregada'
            owner = 'Tech Lead / DevOps'
            target = 'Reducir un 10–20% en 2–3 sprints'
        if any(tok in _norm(kk) for tok in ['velocidad', 'velocity', 'sprint completion']):
            meas = 'Puntos de historia completados por sprint'
            freq = 'Por sprint'
            owner = 'PO / Scrum Master'
            target = 'Establecer baseline y estabilizar (+/- 10%)'
        if any(tok in _norm(kk) for tok in ['defect', 'defecto', 'escape rate']):
            meas = 'Número de defectos críticos en producción por release'
            freq = 'Por release / semanal para trending'
            owner = 'QA / Tech Lead'
            if phase_roles:
                owner = next((r for r in phase_roles if 'qa' in _norm(r) or 'quality' in _norm(r)), owner)
            target = 'Minimizar a 0–1 críticos por release'
        # sugerencia de objetivo numérico ejemplo según tipo
        example_target = target
        if 'lead time' in _norm(kk):
            example_target = 'Reducir a < X días (ej. 2–4 días) en 4 semanas'
        if 'velocidad' in _norm(kk) or 'velocity' in _norm(kk):
            example_target = 'Establecer baseline en los 2 primeros sprints y mejorar ~10% en 3 sprints'
        if 'defect' in _norm(kk) or 'defecto' in _norm(kk):
            example_target = '0–1 defectos críticos por release'

        out.append(f"- {kk}: {meas}; Frecuencia: {freq}; Owner sugerido: {owner}; Objetivo sugerido: {example_target}")
    return out


def _expand_deliverables_for_phase(phase_info: Dict, proposal: Optional[Dict[str, Any]] = None) -> List[str]:
    """Para cada entregable, devuelve descripción, criterios de aceptación y responsible sugerido."""
    dels = phase_info.get('deliverables') or []
    if not dels:
        return ["(No hay entregables definidos para esta fase.)"]
    out: List[str] = []
    out.append('ENTREGABLES — descripción, criterios de aceptación y responsable sugerido:')
    for d in dels:
        name = d if isinstance(d, str) else str(d)
        desc = f'Descripción breve de {name}.'
        criteria = 'Criterios de aceptación: entregable completo, pruebas asociadas, documentación mínima, revisión por stakeholder.'
        owner = 'PM / Equipo responsable (según alcance)'
        # heurística: si parece roadmap o backlog, proponer PO/PM
        if 'roadmap' in _norm(name) or 'backlog' in _norm(name):
            owner = 'Product Owner (PO)'
            criteria = 'Priorizar ítems, estimar historias y validar alcance con stakeholders.'
        if 'definition of done' in _norm(name) or 'definition of ready' in _norm(name):
            owner = 'Tech Lead + PO'
            criteria = 'Documento firmado por PO y Tech Lead con checklist verificable.'
        # Construir criterios de aceptación más concretos según tipo de entregable
        ac_lines = [criteria]
        if any(tok in _norm(name) for tok in ['roadmap','release','plan']):
            ac_lines = [
                'Criterios de aceptación: roadmap aprobado por stakeholders clave',
                'Contiene hitos y dependencias con owners',
                'Incluye criterio de salida (Go/No-Go) para cada release'
            ]
        if any(tok in _norm(name) for tok in ['backlog','historias','story','epic']):
            ac_lines = [
                'Criterios de aceptación: historias estimadas y priorizadas',
                'Cada historia con DoR y criterios de aceptación claros',
                'Historias pequeñas (<= 3 días) para la primera iteración'
            ]
        if any(tok in _norm(name) for tok in ['informe','report','pruebas','test','evidence']):
            ac_lines = [
                'Criterios de aceptación: evidencia reproducible de pruebas',
                'Resultados con umbrales claros (p. ej. p95 < X ms)',
                'Observaciones y responsables de fallo/accion'
            ]

        ac_text = ' | '.join(ac_lines)
        out.append(f"- {name}: {desc} \n  • {ac_text} \n  • Responsable sugerido: {owner}")
    return out


def _expand_practices_for_phase(phase_info: Dict, method: str, proposal: Optional[Dict[str, Any]] = None) -> List[str]:
    """Expande las sugerencias prácticas en pasos concretos, checklist mínima y tiempos estimados."""
    pract = phase_info.get('practices') or phase_info.get('practicas') or []
    # fallback to questions_to_ask or checklist if practices not present
    if not pract:
        pract = phase_info.get('questions_to_ask') or []
    if not pract and phase_info.get('checklist'):
        pract = phase_info.get('checklist')[:5]

    if not pract:
        return ["(No hay sugerencias prácticas estructuradas para esta fase.)"]

    out: List[str] = []
    out.append('SUGERENCIAS PRÁCTICAS DETALLADAS — pasos, checklist mínima y estimación:')
    for i, p in enumerate(pract[:8], start=1):
        title = p if isinstance(p, str) else str(p)
        step_desc = f'Paso {i}: {title}.\n  • Acción 1: Preparar artefactos necesarios.\n  • Acción 2: Ejecutar con stakeholders clave.\n  • Acción 3: Registrar decisiones (ADR) y owners.'
        est = 'Estimación: 0.5–2 días' if len(title) < 60 else 'Estimación: 1–5 días'
        owner = 'PM / Facilitador'
        # heurística para QA/testing
        if any(tok in _norm(title) for tok in ['test', 'qa', 'prueba', 'aceptación']):
            owner = 'QA'
            est = 'Estimación: 1–3 días (depende de cobertura)'
        out.append(f"- {title}: {step_desc} \n  • Tiempo estimado: {est} \n  • Responsable sugerido: {owner}")
    return out


def _format_practices_only(phase_info: Dict, method: str, proposal: Optional[Dict[str, Any]] = None) -> str:
    """Devuelve solo las sugerencias prácticas detalladas en un formato compacto y estructurado.

    Cada práctica incluye: título, pasos claros, checklist mínima, estimación y responsable sugerido.
    """
    pract = phase_info.get('practices') or phase_info.get('practicas') or []
    if not pract:
        # fallback a questions_to_ask o checklist
        pract = phase_info.get('questions_to_ask') or []
    if not pract and phase_info.get('checklist'):
        pract = phase_info.get('checklist')[:8]

    if not pract:
        return "(No hay sugerencias prácticas estructuradas para esta fase.)"

    lines: List[str] = []
    lines.append('SUGERENCIAS PRÁCTICAS DETALLADAS:')
    phase_roles = list((phase_info.get('roles_responsibilities') or {}).keys())

    for i, p in enumerate(pract[:12], start=1):
        title = p if isinstance(p, str) else str(p)
        # pasos concretos
        steps = [
            f"1) Preparar: reunir artefactos necesarios (doc, prototipos, datos, accesos).",
            f"2) Ejecutar: sesión/acción con stakeholders clave y recoger decisiones.",
            f"3) Formalizar: registrar decisiones (ADR), asignar owners y actualizar backlog/runbook."
        ]
        # checklist derivada
        checklist = [
            "Artefactos preparados (si aplica): templates/comunicaciones/PRs/boards)",
            "Owners asignados para cada punto crítico",
            "Criterios de aceptación definidos y documentados",
            "Evidencias o métricas iniciales para medir progreso"
        ]
        # estimación y owner heurística
        est = '0.5–2 días' if len(title) < 60 else '1–5 días'
        owner = 'PM / Facilitador'
        if any(tok in _norm(title) for tok in ['test', 'qa', 'prueba', 'aceptación']):
            owner = 'QA'
            est = '1–3 días (depende de cobertura)'
        elif any(tok in _norm(title) for tok in ['workshop','workshop','entrevistas','interview','stakeholder']):
            owner = next((r for r in phase_roles if 'owner' in _norm(r) or 'product' in _norm(r) or 'pm' in _norm(r)), owner)

        lines.append(f"\n{i}. {title}")
        lines.append("  Pasos:")
        for s in steps:
            lines.append(f"   - {s}")
        lines.append("  Checklist mínima:")
        for c in checklist:
            lines.append(f"   - {c}")
        lines.append(f"  Estimación: {est}")
        lines.append(f"  Responsable sugerido: {owner}")

    return "\n".join(lines)


def _generate_phase_suggested_questions(phase_info: Dict) -> List[str]:
    """Genera una lista de preguntas sugeridas (varias formulaciones) que el asistente podrá entender.

    Esto ayuda a orientar al usuario y también sirve como base para mapear la intención
    del usuario a una expansión concreta (KPIs, entregables, checklist, riesgos, owners...).
    """
    qs: List[str] = []
    name = phase_info.get('name') or 'esta fase'

    # General
    qs += [
        f"¿Cuáles son los KPIs clave para {name}?",
        f"¿Puedes detallar los entregables de {name}?",
        f"¿Qué checklist mínima recomiendas para {name}?",
        f"¿Qué riesgos hay en {name} y cómo mitigarlos?",
        f"¿Qué prácticas concretas sugieres para ejecutar {name}?",
        f"¿Quiénes deberían ser los owners en {name}?",
        f"¿Qué criterios de aceptación aplica cada entregable de {name}?",
        f"¿Cómo medir si {name} fue exitoso?",
        f"Dame pasos prácticos para empezar con {name}.",
        f"¿Qué dependencias debo vigilar durante {name}?",
    ]

    # Por KPIs concretos
    for k in (phase_info.get('kpis') or [])[:6]:
        qs.append(f"¿Cómo medir '{k}' en {name}?")
        qs.append(f"¿Cuál sería un objetivo inicial para '{k}'?")

    # Por entregables concretos
    for d in (phase_info.get('deliverables') or [])[:6]:
        qs.append(f"¿Cuál es el criterio de aceptación para '{d}'?")
        qs.append(f"¿Quién debería ser el responsable de '{d}'?")

    # Por prácticas/checklist
    for p in (phase_info.get('practices') or phase_info.get('practicas') or [])[:6]:
        qs.append(f"¿Cómo ejecutar '{p}' en {name}?")

    # Deduplicate and normalize length
    seen = set(); out = []
    for q in qs:
        nq = q.strip()
        if nq.lower() in seen:
            continue
        seen.add(nq.lower())
        out.append(nq)
        if len(out) >= 20:
            break
    return out


def _match_phase_user_intent(ntext: str, phase_info: Dict) -> Optional[Tuple[str, Optional[str]]]:
    """Intent matching simple: devuelve (intent, detail) donde intent ∈ {kpis, deliverables, practices, risks, owners, checklist, roles, timeline}

    detail puede contener el nombre concreto (p.ej. nombre del KPI o entregable) si se detecta.
    """
    t = _norm(ntext)
    # palabras clave simples
    if any(k in t for k in ["kpi", "kpis", "indicador", "indicadores", "objetivo", "metrica", "métrica"]):
        # buscar si menciona un KPI concreto
        for k in (phase_info.get('kpis') or []):
            if _norm(k) in t or _norm(k).split()[0] in t:
                return ("kpis", k)
        return ("kpis", None)
    if any(k in t for k in ["entregable", "entregables", "artefacto", "artefactos", "documentación", "documentacion", "deliverable"]):
        for d in (phase_info.get('deliverables') or []):
            if _norm(d) in t or _norm(d).split()[0] in t:
                return ("deliverables", d)
        return ("deliverables", None)
    if any(k in t for k in ["práctica", "practica", "prácticas", "practicas", "pasos", "checklist", "acciones", "cómo hacer", "como hacer", "cómo ejecutar", "como ejecutar"]):
        for p in (phase_info.get('practices') or phase_info.get('practicas') or []):
            if _norm(p) in t or _norm(p).split()[0] in t:
                return ("practices", p)
        return ("practices", None)
    if any(k in t for k in ["riesgo", "riesgos", "mitig", "mitigar", "riesgo crítico", "blocking"]):
        return ("risks", None)
    if any(k in t for k in ["owner", "propietario", "responsable", "quien", "quién", "a cargo", "encargado"]):
        # si menciona un entregable o rol concreto, devolver detail
        for d in (phase_info.get('deliverables') or []):
            if _norm(d) in t:
                return ("owners", d)
        return ("owners", None)
    if any(k in t for k in ["roles", "responsab", "perfil", "perfil requerido", "quién participa", "quién debería"]):
        return ("roles", None)
    if any(k in t for k in ["duración", "semanas", "plazo", "tiempo", "estimación", "estimado"]):
        return ("timeline", None)
    # Cambios presupuestarios: contingencia, % o palabra 'contingencia'
    m_pct = re.search(r"(contingenc|contingencia|contingency|contingencia)\s*(?:[:=]?\s*)?(\d{1,2})\s*%", t)
    if m_pct:
        try:
            pct = int(m_pct.group(2))
            return ("budget_change", pct)
        except Exception:
            return ("budget_change", None)
    if any(k in t for k in ["contingencia", "contingency", "contingenc"]) and re.search(r"\d{1,2}%", t):
        m = re.search(r"(\d{1,2})%", t)
        if m:
            return ("budget_change", int(m.group(1)))
        return ("budget_change", None)
    # Añadir/quitar personal
    if any(k in t for k in ["añadir", "agregar", "contratar", "nuevo empleado", "nuevo perfil", "incorporar"]) or re.search(r"\b(anadir|añadir|agregar|contratar)\b", t):
        # intentar extraer rol y cantidad
        m = re.search(r"(\d+(?:[.,]\d+)?)\s*(?:persona?s?|fte|fte?s?)", t)
        cnt = float(m.group(1).replace(",", ".")) if m else 1.0
        # buscar rol candidato (palabras del diccionario de roles)
        role = None
        for k in _ROLE_SYNONYMS.keys():
            if k in t:
                role = _ROLE_SYNONYMS[k]
                break
        # si no hay rol explícito, intentar buscar palabras comunes
        if not role:
            for cand in ["pm", "tech lead", "backend", "frontend", "qa", "ux", "ml"]:
                if cand in t:
                    role = _canonical_role(cand)
                    break
        return ("add_employee", f"{cnt}:{role}" if role else f"{cnt}:unknown")
    # Cambiar duración de fase
    m_weeks = re.search(r"(\d{1,3})\s*(?:semanas|s|weeks)", t)
    if any(k in t for k in ["aumentar", "reducir", "acortar", "ampliar", "cambiar semanas", "cambiar duración"]) and m_weeks:
        return ("change_phase_weeks", int(m_weeks.group(1)))
    # Pregunta genérica: ¿puedo hacer cambios?
    if any(k in t for k in ["puedo hacer cambios", "puedo cambiar", "puedo modificar", "hacer cambios", "cambios?"]):
        return ("can_change", None)
    return None


# ------------------ Especialistas por metodología (Scrum primero) ------------------
def _scrum_phase_specialist(ntext: str, phase_info: Dict, proposal: Optional[Dict[str, Any]] = None) -> str:
    """Genera recomendaciones y acciones específicas para fases de Scrum.

    Devuelve texto adicional pensado exclusivamente para la vista de seguimiento.
    """
    name = (phase_info.get('name') or '').lower()
    lines: List[str] = []

    # Incepción / Plan de Releases (discovery)
    if any(k in name for k in ['incepción', 'incepcion', 'discovery', 'plan de releases']):
        lines.append('SUGERENCIAS PRÁCTICAS (Incepción / Discovery):')
        lines.append('- Validar y priorizar las 3 hipótesis con mayor impacto; asigna owners para cada hipótesis.')
        lines.append('- Ejecuta 1 workshop de alineación con stakeholders y acuerda criterios de éxito (KPIs concretos).')
        lines.append('- Entregables inmediatos: backlog inicial priorizado, roadmap de releases y definition of ready para primer sprint.')
        if proposal:
            lines.append('- Revisa dependencias detectadas en la propuesta y marca como riesgos con owners.')

    # Sprints / Desarrollo iterativo
    if any(k in name for k in ['sprints', 'desarrollo iterativo', 'iteración', 'sprint']):
        lines.append('SUGERENCIAS PRÁCTICAS (Sprints / Desarrollo iterativo):')
        lines.append('- Revisa que cada historia tenga DoR y DoD claros; crea una checklist mínima de DoD técnica y de negocio.')
        lines.append('- Si hay retrasos, calcula la desviación de velocity de los últimos 3 sprints y ajusta forecast.')
        lines.append('- Implementa un burndown diario y registra impedimentos; asigna owners para cada impedimento con SLA de resolución.')
        if phase_info.get('checklist'):
            lines.append('- Para mejorar cumplimiento, automatiza ejecución de los pasos críticos de la checklist en CI.')

    # Hardening & Pruebas de aceptación
    if any(k in name for k in ['hardening', 'pruebas', 'aceptación', 'testing']):
        lines.append('SUGERENCIAS PRÁCTICAS (Hardening / Aceptación):')
        lines.append('- Definir gates automáticos en CI que impidan avanzar si fallan tests críticos (integration/e2e).')
        lines.append('- Prioriza bugs por severidad y fecha límite de fix; crea un plan de estabilización con owners y tiempos de resolución.')
        lines.append('- Verifica entornos de staging reproducibles y añade smoke tests post-deploy.')
        if phase_info.get('kpis'):
            lines.append(f"- KPIs objetivo sugeridos: {', '.join(phase_info.get('kpis', [])[:3])}")

    # Release & Handover
    if any(k in name for k in ['release', 'handover', 'despliegue']):
        lines.append('SUGERENCIAS PRÁCTICAS (Release & Handover):')
        lines.append('- Define plan de rollback con pasos concretos y owner en cada paso; prueba el rollback en staging.')
        lines.append('- Asegura runbooks y monitorización (dashboards + alertas) listos antes del deploy.')
        lines.append('- Realiza una verificación post-release (smoke + checks de integridad) con checklist y responsables.')
        if proposal:
            lines.append('- Programa una retro específica para recoger lecciones aprendidas y actualizar Definition of Done si procede.')

    # Si no hemos añadido nada, devolver cadena vacía
    if not lines:
        return ''

    return "\n".join(lines)


def _apply_method_specialist(method: str, ntext: str, phase_info: Dict, base_resp: str, proposal: Optional[Dict[str, Any]] = None) -> str:
    """Encapsula la llamada al especialista correspondiente según metodología.

    Actualmente implementa sólo Scrum; devuelve el texto combinado.
    """
    m = normalize_method_name(method) if method else ''
    extra = ''
    try:
        if m == 'Scrum'.lower() or m.lower() == 'scrum':
            extra = _scrum_phase_specialist(ntext, phase_info, proposal)
    except Exception:
        extra = ''

    if extra:
        return base_resp + "\n\n---\n\n" + extra
    return base_resp

# ----------------------------------------------------------------------------------


def _merge_proposal_and_catalog_phase(proposal: Optional[Dict[str, Any]], phase_name_or_idx: str, method: str) -> Dict:
    """Devuelve una versión 'merged' de la fase, priorizando datos de la proposal.

    phase_name_or_idx: puede ser un nombre parcial de fase o un índice (string de número).
    method: nombre de metodología (normalizado o no).
    """
    merged: Dict = {}
    # 1) intentar tomar desde proposal si existe
    if proposal:
        # si se pasó un número
        try:
            idx = int(phase_name_or_idx)
            phases_prop = proposal.get('phases') or []
            if 0 <= idx < len(phases_prop):
                merged.update(phases_prop[idx] or {})
        except Exception:
            # intentar match por nombre parcial
            phases_prop = proposal.get('phases') or []
            n = _norm_simple(phase_name_or_idx)
            for ph in phases_prop:
                if ph and _norm_simple(ph.get('name','')) in n or n in _norm_simple(ph.get('name','')):
                    merged.update(ph or {})
                    break

    # 2) enriquecer con catálogo metodologías
    try:
        cat_phases = get_method_phases(method) or []
        # buscar el mismo por nombre (canon)
        n = _norm_simple(phase_name_or_idx)
        for c in cat_phases:
            cn = _norm_simple(c.get('name',''))
            if cn and (cn in n or n in cn or (merged.get('name') and _norm_simple(merged.get('name')) in cn or cn in _norm_simple(merged.get('name')))):
                # añadir solo claves que no estén en merged o que sean vacías
                for k, v in c.items():
                    if k not in merged or not merged.get(k):
                        merged[k] = v
                break
    except Exception:
        pass

    # 3) asegurarnos de campos clave
    merged.setdefault('name', phase_name_or_idx)
    merged.setdefault('summary', merged.get('summary') or '')
    merged.setdefault('goals', merged.get('goals') or [])
    merged.setdefault('checklist', merged.get('checklist') or [])
    merged.setdefault('roles_responsibilities', merged.get('roles_responsibilities') or {})
    merged.setdefault('kpis', merged.get('kpis') or [])
    merged.setdefault('deliverables', merged.get('deliverables') or [])
    merged.setdefault('questions_to_ask', merged.get('questions_to_ask') or [])
    return merged


# ---------------- Structured short answers for phase follow-ups ----------------
# For the seguimiento view we want concise, focused answers to short questions
# like "qué es <fase>", "objetivo", "entregables", "prácticas" etc.
# This dictionary contains short responses per methodology -> phase -> question type.
PHASE_SHORT_RESPONSES: Dict[str, Dict[str, Dict[str, str]]] = {
    "Scrum": {
        "Incepción & Plan de Releases": {
            "definition": "Incepción / Discovery: fase inicial para alinear visión, alcance y roadmap; se define backlog inicial y criterios de éxito.",
            "objective": "Alinear stakeholders, priorizar epics y definir Definition of Ready/Done para el primer sprint.",
            "deliverables": "ENTREGABLES PRINCIPALES:\n- Backlog priorizado\n- Roadmap de releases\n- Definition of Done inicial",
            "practices": "Workshops con stakeholders, mapping de alcance y priorización por valor/riesgo.",
            "kpis": "% historias listas para sprint; claridad del alcance; aprobación de stakeholders.",
        },
        "Sprints de Desarrollo (2w)": {
            "definition": "Sprints de Desarrollo: ciclos iterativos (normalmente 2 semanas) para entregar incrementos de valor.",
            "objective": "Entregar increments potencialmente desplegables y recoger feedback frecuente.",
            "deliverables": "Incremento funcional, tests, demo y release notes por sprint.",
            "practices": "Planning, Daily, Review, Retrospectiva; Definition of Done y CI/CD integrada.",
            "kpis": "Velocidad del equipo, lead time por historia, tasa de defectos por sprint.",
        },
        "QA/Hardening Sprint": {
            "definition": "Fase de estabilización y pruebas antes de release: centra en QA, performance y cierre de defectos.",
            "practices": "Automatización de regresión, pruebas de carga y checklist de release.",
            "deliverables": "Evidencias de pruebas, informes de performance y correcciones críticas cerradas.",
        },
        "Despliegue & Transferencia": {
            "definition": "Release & Handover: puesta en producción y transferencia operativa al equipo de soporte/cliente.",
            "practices": "Deploy canary/blue-green, runbooks y verificación post-release.",
            "deliverables": "Checklist de release, plan de rollback y runbooks operativos.",
        }
    },
    "Kanban": {
        "Descubrimiento & Diseño": {
            "definition": "Descubrimiento & Diseño: preparar el trabajo y las políticas de flujo; definir los ítems prioritarios para el tablero.",
            "practices": "Mapear flujo, definir políticas de entrada/salida y limitar WIP.",
        }
    }
}


# Definiciones cortas para entregables comunes (normalizadas)
DELIVERABLE_DEFINITIONS: Dict[str, str] = {
    "backlog priorizado": "Backlog priorizado: lista ordenada de ítems (épicas, historias) priorizados por valor y riesgo; incluye estimaciones, criterios de aceptación y dependencias, y sirve como fuente para planificar sprints/releases.",
    "backlog": "Backlog priorizado: lista ordenada de ítems (épicas, historias) priorizados por valor y riesgo; incluye estimaciones y criterios de aceptación.",
    "roadmap de releases": "Roadmap de releases: calendario de alto nivel con hitos y releases previstos, objetivos por release y fechas/marcos temporales aproximados.",
    "plan de releases": "Roadmap de releases: calendario de alto nivel con hitos y releases previstos y objetivos por release.",
    "definition of done": "Definition of Done: conjunto de criterios mínimos que debe cumplir una historia para considerarse completa (tests, documentación, revisión de código, despliegue, etc.).",
    "definition of done inicial": "Definition of Done inicial: versión inicial de los criterios de 'done' acordada en Incepción para validar historias en los primeros sprints.",
}


def _find_deliverable_key(text: str) -> Optional[str]:
    """Busca una clave conocida de entregable en el texto (normalizado).
    Devuelve la clave tal y como aparece en DELIVERABLE_DEFINITIONS o None.
    """
    if not text:
        return None
    t = _norm_simple(text)
    for k in DELIVERABLE_DEFINITIONS.keys():
        if _norm_simple(k) in t or t in _norm_simple(k):
            return k
    # intento por tokens: buscar palabras clave por entregable
    for k in DELIVERABLE_DEFINITIONS.keys():
        tokens = _phase_tokens(k)
        if all(tok in t for tok in tokens):
            return k
    return None


def _determine_phase_question_type(text: str) -> Optional[str]:
    """Clasifica una pregunta sobre una fase en un tipo simple para devolver
    una respuesta corta y dirigida.
    Devuelve por ejemplo: 'definition','objective','deliverables','practices','kpis','checklist','owners','timeline','risks'
    """
    t = _norm(text)
    # Priorizar preguntas explícitas
    # Si el usuario pregunta 'qué es X' y X es un entregable conocido, priorizar esa definición
    if any(k in t for k in ("qué es", "que es", "definici", "definicion", "definición", "en qué consiste", "en que consiste")):
        try:
            if _find_deliverable_key(t):
                return "deliverable_def"
        except Exception:
            pass
        return "definition"
    if any(k in t for k in ("objetivo", "propósito", "para qué")):
        return "objective"
    if any(k in t for k in ("entregables", "artefacto", "documentación", "documentacion", "deliverable")):
        return "deliverables"

    # Si la pregunta es del tipo 'qué es <entregable>' devolvemos una clasificación específica
    if any(k in t for k in ("qué es", "que es", "qué significa", "que significa", "define", "definición", "definicion")):
        # buscar si menciona algún entregable conocido
        try:
            if _find_deliverable_key(t):
                return "deliverable_def"
        except Exception:
            pass
    if any(k in t for k in ("prácticas", "practicas", "sugerencias prácticas", "sugerencias practicas", "cómo hacerlo", "cómo abordar", "como abordar")):
        return "practices"
    if any(k in t for k in ("kpi", "kpis", "métricas", "metricas", "indicadores")):
        return "kpis"
    if any(k in t for k in ("checklist", "lista", "tareas inmediatas", "qué hacer", "que hacer")):
        return "checklist"
    if any(k in t for k in ("responsable", "owner", "owners", "roles", "quién", "quien")):
        return "owners"
    if any(k in t for k in ("duración", "duracion", "semanas", "timeline", "plazo", "tiempo")):
        return "timeline"
    if any(k in t for k in ("riesgo", "riesgos", "risk", "mitig")):
        return "risks"
    # fallback: short queries with few words likely ask 'what is'
    if len(text.split()) <= 6 or "?" in text:
        return "definition"
    return None


def _short_phase_response(method: str, phase_name: str, qtype: str, proposal: Optional[Dict[str, Any]] = None, user_text: Optional[str] = None) -> str:
    """Devuelve una respuesta corta y enfocada basada en PHASE_SHORT_RESPONSES,
    con fallback a generadores más largos si no existe la entrada.
    """
    method_norm = normalize_method_name((method or "").strip()) if method else method
    # Manejar definiciones puntuales de entregables
    if qtype == "deliverable_def":
        # intentamos detectar el entregable en el texto o en la fase
        key = _find_deliverable_key(user_text or phase_name or "")
        if key and key in DELIVERABLE_DEFINITIONS:
            return DELIVERABLE_DEFINITIONS[key]
        # intentar buscar en los deliverables de la propuesta/phase
        try:
            if proposal:
                dels = proposal.get("deliverables") or proposal.get("entregables") or []
                txt = _norm_simple(user_text or "")
                for d in dels:
                    if d and (_norm_simple(d) in txt or txt in _norm_simple(d)):
                        # devolver definición corta basada en el nombre
                        return f"{d}: (entregable definido en la propuesta)."
        except Exception:
            pass
        # fallback genérico
        return (f"{(user_text or phase_name)} — Entregable definido como artefacto de la fase. "
                f"Puedo detallar si confirmas cuál de los entregables quieres que explique.")
    # intentar por metodología explícita
    if method_norm and method_norm in PHASE_SHORT_RESPONSES:
        # buscar la fase más parecida por tokens
        phases_map = PHASE_SHORT_RESPONSES[method_norm]
        # match exact or by normalized tokens
        key = None
        for ph in phases_map.keys():
            if _norm_simple(ph) in _norm_simple(phase_name) or _norm_simple(phase_name) in _norm_simple(ph):
                key = ph
                break
        if not key:
            # try direct lookup
            key = next((p for p in phases_map.keys() if _norm_simple(p) == _norm_simple(phase_name)), None)
        if key:
            resp = phases_map[key].get(qtype)
            if resp:
                return resp

    # fallback: usar la explicación genérica breve basada en _explain_specific_phase
    try:
        short = _explain_specific_phase(phase_name, proposal or {"methodology": method or ""})
        # _explain_specific_phase returns a multi-block text; take the first paragraph as concise fallback
        first = short.split("\n\n")[0]
        return first
    except Exception:
        return f"{phase_name} — fase del proyecto (detalle breve no disponible)."


def generate_reply(session_id: str, message: str) -> Tuple[str, str]:
    text = message.strip()
    try:
        logger = logging.getLogger(__name__)
        logger.debug(f"generate_reply session={session_id} message={text[:200]!r}")
    except Exception:
        pass
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

    # Intents 
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

    # Respuesta rápida: si el usuario pregunta "qué es <entregable>" devolver definición aunque no haya proposal/fase
    try:
        quick_q = _determine_phase_question_type(text)
        if quick_q == "deliverable_def":
            k = _find_deliverable_key(text)
            if k:
                return DELIVERABLE_DEFINITIONS.get(k, f"{k} — definición no disponible."), "Definición de entregable."
            else:
                return ("¿Qué entregable quieres que defina? Por ejemplo: 'backlog priorizado', 'roadmap de releases', 'Definition of Done'."), "Pregunta: definición entregable"
    except Exception:
        pass

    # ——— Aceptación de propuesta: pedir plantilla del equipo para asignar personas
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

    # Cambio natural de metodología: consejo + confirmación
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

    # Cambios naturales a otras áreas → confirmación con parche + evaluación
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

    # CALENDARIO / PLAZOS: pide fecha, calcula y prepara confirmación
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

    # RIESGOS: detalle + plan + confirmación
    if _asks_risks_simple(text):
        try:
            set_last_area(session_id, "riesgos")
        except Exception:
            pass

        # Si no hay propuesta en sesión, intentar generar una provisional a partir
        # de los requisitos guardados o del propio texto (como hace la sección
        # de acciones guiadas más abajo). Si falla, devolver el mensaje instructivo.
        if not proposal:
            seed = req_text or text
            try:
                tmp = generate_proposal(seed)
                info = METHODOLOGIES.get(tmp.get("methodology", ""), {})
                tmp["methodology_sources"] = info.get("sources", [])
                set_last_proposal(session_id, tmp, seed)
                proposal = tmp
            except Exception:
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

    # PREGUNTAS ESPECÍFICAS DE SEGUIMIENTO sobre fases
    ntext = _norm(text)
    phase_mentioned = _match_phase_name(text, proposal)
    try:
        logging.getLogger(__name__).debug(f"phase_mentioned={phase_mentioned!r} ntext={ntext[:120]!r}")
    except Exception:
        pass

    # Preguntas del tipo "¿qué fase es esta?", "en qué fase estamos", "qué fase estoy"
    def _is_which_phase_query(nt: str) -> bool:
        checks = [
            "que fase es esta", "qué fase es esta", "en que fase estamos", "en qué fase estamos",
            "que fase estoy", "qué fase estoy", "qué fase es", "que fase es",
            "en que fase estoy", "en qué fase estoy"
        ]
        for c in checks:
            if c in nt:
                return True
        # also short forms like 'qué fase' or 'que fase' alone
        if nt.strip() in ("que fase", "qué fase"):
            return True
        return False

    if _is_which_phase_query(ntext):
        # Intentar inferir la fase desde la propuesta o desde el historial de conversación
        if not proposal:
            # Si hay requisitos guardados, intentar generar provisionalmente
            seed = req_text or text
            try:
                tmp = generate_proposal(seed)
                info = METHODOLOGIES.get(tmp.get("methodology", ""), {})
                tmp["methodology_sources"] = info.get("sources", [])
                set_last_proposal(session_id, tmp, seed)
                proposal = tmp
            except Exception:
                proposal = None

        if not proposal:
            return ("No tengo una propuesta ni contexto para saber a qué fase te refieres. "
                    "Genera una propuesta con '/propuesta: ...' o dime a qué artefacto/fase te refieres."), "Qué fase: sin propuesta"

        # Buscar en el historial la última referencia a una fase
        try:
            msgs = list_messages(session_id, limit=40) or []
        except Exception:
            msgs = []

        found_phase = None
        # recorremos los mensajes más recientes buscando coincidencias con fases de la proposal
        try:
            for m in reversed(msgs):
                content = getattr(m, 'content', '') or getattr(m, 'text', '') or ''
                if not content:
                    continue
                cand = _match_phase_name(content, proposal)
                if cand:
                    found_phase = cand
                    break
        except Exception:
            found_phase = None

        method = (proposal or {}).get('methodology', '(no definida)')
        if found_phase:
            return (f"Según el contexto reciente estás hablando de la fase: '{found_phase}' del plan. "
                    f"La metodología del proyecto es: {method}.") , f"Qué fase: {found_phase}"

        # Si no aparece en historial, devolver resumen y pedir que el usuario aclare
        phases_list = proposal.get('phases') or []
        brief = ", ".join(f"{i+1}. {ph.get('name','(sin nombre)')}" for i, ph in enumerate(phases_list[:6]))
        return (f"La propuesta actual usa la metodología '{method}'. Las fases del plan son: {brief}. "
                "¿A cuál de estas te refieres (puedes indicar número o nombre)?"), "Qué fase: pedir aclaración"

    # Comando explícito para pedir detalle de una fase por índice o nombre: '/fase:2' o '/fase nombre'
    if text.lower().startswith('/fase'):
        # formato: /fase:2 o /fase 2 o /fase: nombre
        arg = None
        if ':' in text:
            arg = text.split(':',1)[1].strip()
        else:
            parts = text.split(None,1)
            arg = parts[1].strip() if len(parts) > 1 else None

        if not arg:
            return ("Indica la fase que quieres ver. Ej: '/fase: 1' o '/fase: Incepción'"), "Comando fase: falta argumento"

        if not proposal:
            return ("Para ver la fase de un proyecto necesito que exista una propuesta en esta sesión. Usa '/propuesta: ...' primero."), "Fase sin propuesta"

        method = proposal.get('methodology') or 'Scrum'
        merged = _merge_proposal_and_catalog_phase(proposal, arg, method)
        try:
            resp = _render_phase_rich_response(_norm(arg), merged, method, merged.get('name', arg))
            try:
                resp = _apply_method_specialist(method, _norm(arg), merged, resp, proposal)
            except Exception:
                pass
            return resp, f"Detalle fase: {merged.get('name', arg)}"
        except Exception:
            return _explain_specific_phase(text, proposal), "Fase: fallback"
    
    # Detectar preguntas de seguimiento (problemas, cambios, retrasos, dudas)
    is_followup_question = any(k in ntext for k in [
        "problema","issue","bloqueado","bloqueada","retraso","atascado","atascada",
        "dificultad","cambio","modificar","ajustar","revisar",
        "como","que hacer","ayuda con","necesito","duda","consulta",
        "no funciona","falla","error"
    ])
    
    if phase_mentioned and is_followup_question:
        try:
            set_last_area(session_id, "phases")
        except Exception:
            pass
        
        # Obtener información estructurada de la fase
        method = (proposal or {}).get('methodology', 'Scrum')
        try:
            # Normalizar el nombre de la metodología para buscar las fases
            method_normalized = normalize_method_name(method)
            phases = get_method_phases(method_normalized) or []
        except Exception:
            phases = []
        
        # Buscar la fase específica
        phase_info = None
        if phases:
            n = _norm_simple(phase_mentioned)
            for ph in phases:
                pn = _norm_simple(ph.get('name', '') or '')
                if pn and (pn in n or n in pn):
                    phase_info = ph
                    break
        
        # Construir respuesta contextual basada en el conocimiento de la fase
        if phase_info:
            try:
                # Intent match: si el usuario pregunta algo concreto sobre KPIs/entregables/prácticas/riesgos/owners
                intent_match = _match_phase_user_intent(ntext, phase_info)
                if intent_match:
                    intent, detail = intent_match
                    pieces: List[str] = [f">> Sobre la fase {phase_info.get('name', phase_mentioned)} (metodología: {method}):\n"]
                    # Responder según intención detectada
                    if intent == 'kpis':
                        try:
                            kblocks = _expand_kpis_for_phase(phase_info, proposal)
                            # si hay detail (nombre del KPI), filtrar
                            if detail:
                                kblocks = [b for b in kblocks if detail.lower() in b.lower() or detail in b]
                                if not kblocks:
                                    kblocks = [f"No he encontrado detalles para el KPI '{detail}', pero aquí tienes los KPIs generales:"] + _expand_kpis_for_phase(phase_info, proposal)
                            pieces.append("\n" + "\n".join(kblocks))
                        except Exception:
                            pieces.append('\n(No pude generar el desglose de KPIs en este momento.)')

                    elif intent == 'deliverables':
                        try:
                            dblocks = _expand_deliverables_for_phase(phase_info, proposal)
                            if detail:
                                dblocks = [b for b in dblocks if detail.lower() in b.lower() or detail in b]
                                if not dblocks:
                                    dblocks = [f"No encontré el entregable '{detail}' exacto; aquí los entregables principales:"] + _expand_deliverables_for_phase(phase_info, proposal)
                            pieces.append("\n" + "\n".join(dblocks))
                        except Exception:
                            pieces.append('\n(No pude generar el desglose de entregables en este momento.)')

                    elif intent == 'practices':
                        try:
                            # Return ONLY the detailed practical suggestions, as requested
                            if detail:
                                # Try to find a matching practice by name
                                all_practs = phase_info.get('practices') or phase_info.get('practicas') or phase_info.get('questions_to_ask') or phase_info.get('checklist') or []
                                match = None
                                for pr in all_practs:
                                    if detail.lower() in _norm(pr) or _norm(pr) in detail.lower():
                                        match = pr
                                        break
                                if match:
                                    mini_phase = dict(phase_info)
                                    mini_phase['practices'] = [match]
                                    formatted = _format_practices_only(mini_phase, method, proposal)
                                    return formatted, f"Seguimiento de fase: {phase_mentioned}"
                                # si no hay match, caemos a devolver todas las prácticas
                            formatted = _format_practices_only(phase_info, method, proposal)
                            return formatted, f"Seguimiento de fase: {phase_mentioned}"
                        except Exception:
                            return '\n(No pude generar sugerencias prácticas en este momento.)', f"Seguimiento de fase: {phase_mentioned}"

                    elif intent == 'risks':
                        try:
                            # usar _expand_risks basado en req_text y metodología
                            rlist = _expand_risks(req_text or '', method)
                            pieces.append('\nRIESGOS SUGERIDOS:')
                            for r in rlist:
                                pieces.append(f"  - {r}")
                        except Exception:
                            pieces.append('\n(No pude enumerar los riesgos en este momento.)')

                    elif intent in ('owners', 'roles'):
                        try:
                            rr = phase_info.get('roles_responsibilities') or {}
                            if intent == 'owners' and detail:
                                # intentar adivinar owner para el entregable concreto
                                candidates = [r for r, desc in rr.items() if _norm(detail) in _norm(r) or _norm(detail) in _norm(desc)]
                                if candidates:
                                    pieces.append(f"Responsable(s) sugerido(s) para '{detail}':")
                                    for c in candidates:
                                        pieces.append(f"  - {c}: {rr.get(c)}")
                                else:
                                    pieces.append(f"Responsables en esta fase:")
                                    for r, desc in rr.items():
                                        pieces.append(f"  - {r}: {desc}")
                            else:
                                pieces.append(f"Roles y responsabilidades en {phase_info.get('name','esta fase')}:")
                                for r, desc in rr.items():
                                    pieces.append(f"  - {r}: {desc}")
                        except Exception:
                            pieces.append('\n(No pude obtener owners/roles en este momento.)')

                    elif intent == 'timeline':
                        tw = phase_info.get('typical_weeks') or phase_info.get('weeks') or None
                        if tw:
                            pieces.append(f"\nDuración típica estimada: {tw} semanas")
                        else:
                            pieces.append('\nNo hay una duración típica definida para esta fase.')

                    elif intent == 'budget_change':
                        # detail puede ser un int (pct) o None
                        try:
                            if not proposal:
                                pieces.append('\nNecesito una propuesta base para calcular el impacto presupuestario.')
                            else:
                                if isinstance(detail, int):
                                    patch = {"type": "budget", "contingency_pct": int(detail)}
                                    eval_text, verdict = _evaluate_patch(proposal, patch, req_text)
                                    pieces.append('\nEvaluación del cambio de contingencia:')
                                    pieces.append(eval_text)
                                else:
                                    pieces.append('\nIndica el nuevo porcentaje de contingencia (p. ej. "contingencia 15%") para que calcule el impacto en el presupuesto.')
                        except Exception:
                            pieces.append('\n(No pude calcular el impacto presupuestario en este momento.)')

                    elif intent == 'add_employee':
                        try:
                            if not proposal:
                                pieces.append('\nNecesito la propuesta para estimar el impacto de añadir personal.')
                            else:
                                # detail viene como 'count:Role' o 'count:unknown'
                                cnt_role = str(detail or '')
                                parts = cnt_role.split(":")
                                try:
                                    cnt = float(parts[0])
                                except Exception:
                                    cnt = 1.0
                                role = parts[1] if len(parts) > 1 else None
                                role_name = _canonical_role(role) if role and role != 'unknown' else 'Unknown'
                                ops = [{"op": "add", "role": role_name, "count": cnt}]
                                patch = {"type": "team", "ops": ops}
                                eval_text, verdict = _evaluate_patch(proposal, patch, req_text)
                                pieces.append('\nEvaluación al añadir personal:')
                                pieces.append(eval_text)
                        except Exception:
                            pieces.append('\n(No pude evaluar el cambio de equipo en este momento.)')

                    elif intent == 'change_phase_weeks':
                        try:
                            if not proposal:
                                pieces.append('\nNecesito la propuesta para calcular el efecto del cambio de duración de la fase.')
                            else:
                                if isinstance(detail, int):
                                    ph_name = phase_info.get('name')
                                    ops = [{"op": "set_weeks", "name": ph_name, "weeks": int(detail)}]
                                    patch = {"type": "phases", "ops": ops}
                                    eval_text, verdict = _evaluate_patch(proposal, patch, req_text)
                                    pieces.append('\nEvaluación del cambio de duración:')
                                    pieces.append(eval_text)
                                else:
                                    pieces.append('\nIndica el número de semanas (p. ej. "aumentar 2 semanas") para que calcule el impacto.')
                        except Exception:
                            pieces.append('\n(No pude evaluar el cambio de duración en este momento.)')

                    elif intent == 'can_change':
                        # Guidance: how to request changes and what the assistant can do within a phase
                        try:
                            guidance = [
                                "Sí — puedes proponer cambios relacionados con presupuesto, equipo o duración de fases.",
                                "Ejemplos de preguntas que puedo atender en el contexto de esta fase:",
                                "  - 'Si aumento la contingencia a 15% ¿cómo cambia el presupuesto?'",
                                "  - 'Quiero añadir 1 QA ¿qué impacto tiene en coste y duración?'",
                                "  - 'Podemos reducir esta fase 1 semana? ¿qué riesgos añadiría?'",
                                "Para aplicar un cambio pídemelo y yo generaré una evaluación; si la confirmas, lo aplicaré a la propuesta."
                            ]
                            pieces.append('\n' + "\n".join(guidance))
                        except Exception:
                            pieces.append('\n(No puedo generar la guía sobre cambios en este momento.)')

                    else:
                        # fallback genérico
                        pieces.append(_render_phase_rich_response(ntext, phase_info, method, phase_mentioned))

                    # añadir preguntas sugeridas al final para orientar follow-ups
                    try:
                        sug = _generate_phase_suggested_questions(phase_info)
                        if sug:
                            pieces.append('\nPreguntas que puedes hacerme sobre esta fase:')
                            for q in sug[:8]:
                                pieces.append(f"  - {q}")
                    except Exception:
                        pass

                    base_out = "\n".join(pieces)
                    try:
                        base_out = _apply_method_specialist(method, ntext, phase_info, base_out, proposal)
                    except Exception:
                        pass
                    return base_out, f"Seguimiento de fase: {phase_mentioned}"

                # Si no hay intención clara, devolver la respuesta rica por defecto
                resp = _render_phase_rich_response(ntext, phase_info, method, phase_mentioned)
                try:
                    resp = _apply_method_specialist(method, ntext, phase_info, resp, proposal)
                except Exception:
                    pass
                return resp, f"Seguimiento de fase: {phase_mentioned}"
            except Exception:
                # Fallback seguro a la explicación textual existente
                return _explain_specific_phase(text, proposal), f"Fase concreta: {phase_mentioned}."
        else:
            # Fallback si no hay info estructurada
            return _explain_specific_phase(text, proposal), f"Fase concreta: {phase_mentioned}."
    
    # si preguntan por una fase concreta: explicarla en detalle (caso general)
    phase_detail = _match_phase_name(text, proposal)
    if phase_detail:
        try:
            set_last_area(session_id, "phases")
        except Exception:
            pass

        # Preferir contexto de la proposal: combinar datos de la proposal con el catálogo
        method = (proposal or {}).get('methodology') or 'Scrum'
        merged = _merge_proposal_and_catalog_phase(proposal, phase_detail, method)

        # Si la pregunta es corta o corresponde a un tipo específico, devolver
        # una respuesta concisa y dirigida (solo lo pedido).
        qtype = _determine_phase_question_type(text)
        if qtype:
            try:
                short = _short_phase_response(method, phase_detail, qtype, merged if proposal else None, text)
                return short, f"Fase concreta: {phase_detail}."
            except Exception:
                # si falla el formato corto, caer al rich response
                pass

        # Fallback: devolver respuesta rica si no era una consulta corta
        try:
            resp = _render_phase_rich_response(_norm(text), merged, method, phase_detail)
            try:
                resp = _apply_method_specialist(method, _norm(text), merged, resp, proposal)
            except Exception:
                pass
            return resp, f"Fase concreta: {phase_detail}."
        except Exception:
            return _explain_specific_phase(text, proposal), f"Fase concreta: {phase_detail}."

    # Fases (sin 'por qué')
    # Si el usuario pide las fases y menciona una metodología concreta, devolver
    # el detalle estructurado de las fases desde el catálogo `METHODOLOGY_PHASES`.
    methods_in_text = _mentioned_methods(text)
    if _asks_phases_simple(text) and not _asks_why(text) and methods_in_text:
        try:
            set_last_area(session_id, "phases")
        except Exception:
            pass

        method = methods_in_text[0]
        try:
            phases = get_method_phases(method) or []
        except Exception:
            phases = []

        if not phases:
            # Fallback a la ficha de la metodología si no hay fases estructuradas
            try:
                return _method_overview_text(method), f"Fases (metodología: {method})"
            except Exception:
                return (f"No tengo definidas las fases para {method}."), f"Fases: sin datos {method}"

        lines = [f"Fases típicas en {method}:"]
        for i, ph in enumerate(phases, start=1):
            name = ph.get("name") or f"Fase {i}"
            summary = ph.get("summary") or "(sin resumen)"
            weeks = ph.get("typical_weeks") or ph.get("weeks") or ph.get("weeks_estimate") or "?"
            lines.append(f"\n{i}. {name} — {summary} (duración típica: {weeks} semanas)")

            if ph.get("goals"):
                lines.append("  Objetivos:")
                for g in ph.get("goals", [])[:5]:
                    lines.append(f"    - {g}")
            if ph.get("checklist"):
                lines.append("  Checklist:")
                for c in ph.get("checklist", [])[:6]:
                    lines.append(f"    - {c}")
            if ph.get("roles_responsibilities"):
                lines.append("  Roles clave:")
                for role, resp in (ph.get("roles_responsibilities") or {}).items():
                    lines.append(f"    - {role}: {resp}")
            if ph.get("kpis"):
                lines.append("  KPIs:")
                for kpi in ph.get("kpis", [])[:5]:
                    lines.append(f"    - {kpi}")
            if ph.get("deliverables"):
                lines.append("  Entregables:")
                for d in ph.get("deliverables", [])[:6]:
                    lines.append(f"    - {d}")

        return "\n".join(lines), f"Fases (metodología: {method})"
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

    # Alias de desglose: también muestra el detalle
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

    # Interpretar requisitos: propuesta
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

    # === MANEJO DE ACCIONES GUIADAS ===
    # Primero verificar si es una solicitud de acción específica
    action_triggers = {
        "discovery": ["descubrimiento", "alcance", "discovery", "kickoff"],
        "risks": ["riesgo", "riesgos", "risk", "mitigacion"],
        "kpis": ["kpi", "kpis", "metricas", "métricas", "objetivos", "metas"],
        "qa": ["qa", "testing", "pruebas", "calidad"],
        "deployment": ["despliegue", "deploy", "ci/cd", "release"],
        "deliverables": ["entregables", "documentación", "documentacion", "artefactos"]
    }
    
    t = _norm(text)
    for action, keywords in action_triggers.items():
        if any(k in t for k in keywords):
            if not proposal:
                # Intentar generar una propuesta provisional a partir de los requisitos
                # guardados o del propio texto de la petición (por ejemplo cuando el
                # frontend inserta un prompt al pulsar un botón). Si falla, pedir al
                # usuario que cree una propuesta explícita.
                seed = req_text or text
                try:
                    tmp = generate_proposal(seed)
                    info = METHODOLOGIES.get(tmp.get("methodology", ""), {})
                    tmp["methodology_sources"] = info.get("sources", [])
                    # Guardamos la propuesta en la sesión para que siguientes acciones
                    # la reutilicen sin regenerarla.
                    set_last_proposal(session_id, tmp, seed)
                    proposal = tmp
                except Exception:
                    return "Necesito una propuesta base para generar el detalle. Usa '/propuesta: ...' primero.", "Sin propuesta para acción."

            # Ejecutar el handler correspondiente y adaptar la respuesta según la metodología propuesta
            # Si el texto menciona explícitamente una metodología (p.ej. 'metodología XP'),
            # forzamos la metodología de la propuesta a esa opción para que la respuesta
            # esté alineada con lo que el usuario espera.
            methods_in_text = _mentioned_methods(text)
            if methods_in_text:
                try:
                    forced = methods_in_text[0]
                    proposal["methodology"] = forced
                    info = METHODOLOGIES.get(forced, {})
                    proposal["methodology_sources"] = info.get("sources", [])
                    # Persistir el cambio para próximas interacciones en la sesión
                    try:
                        set_last_proposal(session_id, proposal, req_text)
                    except Exception:
                        pass
                except Exception:
                    pass

            if action == "discovery":
                raw = handle_discovery_tasks(proposal)
                tag = "Plan de discovery"
            elif action == "risks":
                raw = handle_risk_analysis(proposal)
                tag = "Análisis de riesgos"
            elif action == "kpis":
                raw = handle_kpis_definition(proposal)
                tag = "Definición de KPIs"
            elif action == "qa":
                raw = handle_qa_plan(proposal)
                tag = "Plan de QA"
            elif action == "deployment":
                raw = handle_deployment_strategy(proposal)
                tag = "Estrategia de despliegue"
            elif action == "deliverables":
                raw = handle_deliverables(proposal)
                tag = "Plan de entregables"
            else:
                raw = ""
                tag = "acción"

            # Asegurarnos de que la salida final respete la metodología definida
            # en la `proposal` (evita desalineos si handlers usan otra fuente).
            try:
                method_display = (proposal.get("methodology") or "").strip()
                if method_display:
                    # Reemplazar formas comunes como '(metodología X)'
                    raw = re.sub(r"\(metodolog[ií]a [^\)]+\)", f"(metodología {method_display})", raw, flags=re.IGNORECASE)
                    # Reemplazar 'Metodología: X' o 'metodología: X' en líneas
                    raw = re.sub(r"(?i)metodolog[ií]a\s*[:\-]\s*[^\n\r]+", f"Metodología: {method_display}", raw)
                    # Reemplazar encabezados simples 'metodología X' sin paréntesis
                    raw = re.sub(r"(?i)\bmetodolog[ií]a\s+\w+\b", f"metodología {method_display}", raw)
            except Exception:
                pass

            # Añadir adaptación por metodología si está disponible
            try:
                method = normalize_method_name((proposal.get("methodology") or "").strip())
                minfo = METHODOLOGIES.get(method, {}) if method else {}

                def _join(xs):
                    return ", ".join(xs) if xs else "(no especificadas)"

                extras: List[str] = []
                # Contexto del proyecto (metodología, presupuesto, equipo breve)
                ctx = _project_context_summary(proposal)

                if minfo:
                    # Encabezado contextual
                    extras.append(f"Adaptación según metodología: {method}")

                # Siempre anteponer el contexto del proyecto
                if ctx:
                    extras.insert(0, "Contexto del proyecto: " + ctx)

                    # Prácticas y riesgos generales
                    pract = minfo.get("practicas") or []
                    riesgos = minfo.get("riesgos") or []
                    if pract:
                        extras.append("Prácticas clave: " + _join(pract))
                    if riesgos:
                        extras.append("Riesgos a vigilar: " + "; ".join(riesgos))

                    # Recomendaciones específicas por acción
                    if action == "discovery":
                        if method.lower() == "scrum":
                            extras.append("- En Scrum: planifica un Sprint 0 o un Kick-off de 1–2 semanas para alinear backlog, Definition of Ready y criterios de aceptación.")
                        elif method.lower() == "xp":
                            extras.append("- En XP: incorpora prácticas técnicas desde el inicio (TDD, pair programming) para validar hipótesis técnicas tempranas.")
                        elif method.lower() == "kanban":
                            extras.append("- En Kanban: prioriza por flujo y coste de retraso; usa políticas explícitas de entrada para las actividades de discovery.")
                        else:
                            extras.append("- Asegúrate de adaptar workshops y duración al ritmo de la metodología elegida.")

                    if action == "risks":
                        extras.append("- Prioriza riesgos por probabilidad × impacto y alínea mitigaciones con la cadencia del equipo.")
                        if method.lower() in ("scrum", "scrumban"):
                            extras.append("- En Scrum: revisa riesgos cada sprint review/retrospective y asigna owners para mitigaciones.")
                        if method.lower() == "xp":
                            extras.append("- En XP: mitiga con pruebas automáticas, TDD y revisiones de diseño tempranas.")

                    if action == "kpis":
                        # Sugerir KPIs según metodología
                        if method.lower() == "scrum":
                            extras.append("- KPIs sugeridos (Scrum): velocidad del equipo, sprint completion rate, lead time por historia, defect escape rate.")
                        elif method.lower() == "kanban":
                            extras.append("- KPIs sugeridos (Kanban): cycle time, lead time, throughput, WIP per column.")
                        elif method.lower() == "xp":
                            extras.append("- KPIs sugeridos (XP): cobertura de tests, defect density, tiempo medio de entrega, tiempo de restauración tras fallo.")
                        else:
                            extras.append("- KPIs técnicos y de negocio: mezcla métricas de calidad, entrega y adopción. Ajusta según tu metodología.")

                    if action == "qa":
                        if method.lower() == "xp":
                            extras.append("- En XP: enfatiza TDD, integración continua y pair programming. Integrar suites de tests en cada commit.")
                        elif method.lower() == "scrum":
                            extras.append("- En Scrum: integra QA dentro del sprint; automatiza tests y corre en CI antes del merge.")
                        elif method.lower() == "kanban":
                            extras.append("- En Kanban: pruebas continuas y monitorización; establece gates de calidad en el flujo.")
                        else:
                            extras.append("- Define niveles de testing (unit/integration/e2e/performance) y automatízalos en CI.")

                    if action == "deployment":
                        extras.append("- Estrategias generales: CI/CD, despliegues canary/blue-green y rollback automatizado.")
                        if method.lower() in ("devops",):
                            extras.append("- En DevOps: Infrastructure as Code, pipelines reproducibles y observabilidad desde el día 1.")
                        if method.lower() == "safe":
                            extras.append("- En SAFe: coordina Program Increments y alineamiento entre equipos; añade runbooks y escalado de alertas.")

                    if action == "deliverables":
                        if method.lower() == "scrum":
                            extras.append("- Entregables clave (Scrum): Incremento potencialmente entregable, Definition of Done, backlog priorizado, release notes por sprint.")
                        elif method.lower() == "kanban":
                            extras.append("- Entregables (Kanban): flujo de artefactos, pipeline de entrega y documentación de políticas de entrada/salida.")
                        elif method.lower() == "xp":
                            extras.append("- Entregables (XP): código con cobertura de tests, ADRs, scripts de despliegue y documentación mínima pero suficiente.")

                    # Añadir fuentes metodológicas si existen
                    fuentes = minfo.get("fuentes") or []
                    if fuentes:
                        extras.append("Fuentes y referencias:")
                        for f in fuentes[:3]:
                            autor = f.get("autor", "")
                            titulo = f.get("titulo", "")
                            anio = f.get("anio", "")
                            url = f.get("url", "")
                            extras.append(f"- {autor}: {titulo} ({anio}) — {url}")

                if extras:
                    raw = raw + "\n\n---\n\n" + "\n".join(extras)
            except Exception:
                # no fallar si algo del formato no cuadra
                pass

            return raw, tag

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
