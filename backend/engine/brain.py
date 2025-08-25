import re
from typing import Tuple, Dict, Any, List, Optional
from backend.engine.planner import generate_proposal
from backend.engine.context import get_last_proposal, set_last_proposal

# memoria BD (best-effort)
try:
    from backend.memory.state_store import save_proposal, log_message
except Exception:
    def save_proposal(*a, **k): return None
    def log_message(*a, **k): return None

# NLU opcional
try:
    from backend.nlu.intents import IntentsRuntime
    _INTENTS = IntentsRuntime()
except Exception:
    _INTENTS = None

# Similaridad (k-NN TF-IDF) opcional
try:
    from backend.retrieval.similarity import get_retriever
    _SIM = get_retriever()
except Exception:
    _SIM = None

def _norm(text: str) -> str: return text.lower()

# --- Detectores ---
def _is_greeting(text: str) -> bool:
    return bool(re.search(r"\b(hola|buenas|hey|hello|qué tal|que tal)\b", text, re.I))
def _is_farewell(text: str) -> bool:
    return bool(re.search(r"\b(ad[ií]os|hasta luego|nos vemos|chao)\b", text, re.I))
def _is_thanks(text: str) -> bool:
    return bool(re.search(r"\b(gracias|thank[s]?|mil gracias)\b", text, re.I))
def _is_help(text: str) -> bool:
    t = _norm(text); return "ayuda" in t or "qué puedes hacer" in t or "que puedes hacer" in t
def _asks_methodology(text: str) -> bool:
    return bool(re.search(r"\b(scrum|kanban|scrumban|xp|lean|crystal|fdd|dsdm|safe|devops|metodolog[ií]a)\b", text, re.I))
def _asks_budget(text: str) -> bool:
    return bool(re.search(r"\b(presupuesto|coste|costos|estimaci[oó]n|precio)\b", text, re.I))
def _asks_team(text: str) -> bool:
    return bool(re.search(r"\b(equipo|roles|perfiles|staffing|personal|plantilla|dimension)\b", text, re.I))
def _asks_risks_simple(text: str) -> bool:
    t = _norm(text); return ("riesgo" in t or "riesgos" in t)
def _asks_why(text: str) -> bool:
    t = _norm(text); return ("por qué" in t) or ("por que" in t) or ("porque" in t) or ("justifica" in t) or ("explica" in t) or ("motivo" in t)
def _asks_why_phases(text: str) -> bool:
    t = _norm(text); return ("fase" in t or "fases" in t or "hitos" in t or "timeline" in t) and _asks_why(t)
def _asks_why_team_general(text: str) -> bool:
    t = _norm(text); return _asks_why(t) and ("equipo" in t or "roles" in t or "personal" in t or "plantilla" in t or "dimension" in t)
def _asks_why_role_count(text: str) -> Optional[Tuple[str, float]]:
    t = _norm(text)
    m = re.search(r"(\d+(?:[.,]\d+)?)\s*(pm|project manager|tech\s*lead|arquitect[oa]|backend|frontend|qa|tester|quality|ux|ui|ml|data)", t)
    if not m: return None
    num_str, role_raw = m.groups()
    num = float(num_str.replace(",", "."))
    return (_canonical_role(role_raw), num)
def _looks_like_requirements(text: str) -> bool:
    kw = ["app","web","api","panel","admin","pagos","login","usuarios","microservicios","ios","android","realtime","tiempo real","ml","ia","modelo","dashboard","reportes","integraci"]
    score = sum(1 for k in kw if k in _norm(text)); return score >= 2 or len(text.split()) >= 12
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
        if k in t: return v
    return role_text.strip().title()
def _extract_roles_from_text(text: str) -> List[str]:
    t = _norm(text); found = set()
    for k, v in _ROLE_SYNONYMS.items():
        if k in t: found.add(v)
    return list(found)
def _find_role_count_in_proposal(proposal: Dict[str, Any], role: str) -> Optional[float]:
    for r in proposal.get("team", []):
        if _norm(r["role"]) == _norm(role): return float(r["count"])
    return None

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

def _explain_role(role: str, requirements: Optional[str]) -> List[str]:
    t = _norm(requirements or "")
    if role == "QA":
        base = ["Reduce fuga de defectos y coste de corrección en producción.","Automatiza regresión y asegura criterios de aceptación."]
        if "pagos" in t or "stripe" in t: base.append("Necesarias pruebas de integración con pasarela y anti-fraude.")
        return base
    if role == "UX/UI":
        base = ["Mejora conversión y usabilidad; reduce retrabajo de frontend."]
        if "panel" in t or "admin" in t or "mobile" in t or "app" in t: base.append("Define flujos y componentes reutilizables (design system).")
        return base
    if role == "Tech Lead": return ["Define arquitectura, estándares y CI/CD; desbloquea al equipo y controla deuda técnica."]
    if role == "PM": return ["Gestiona alcance, riesgos y stakeholders; protege al equipo y vigila plazos."]
    if role == "Backend Dev":
        base = ["Implementa APIs, dominio y seguridad; rendimiento y mantenibilidad del servidor."]
        if "pagos" in t: base.append("Integra pasarela de pagos, idempotencia y auditoría.")
        return base
    if role == "Frontend Dev": return ["Construye la UX final (React), estado y accesibilidad; integra con backend y diseño."]
    if role == "ML Engineer": return ["Prototipa/productiviza modelos; evalúa drift y sesgos; integra batch/online."]
    return ["Aporta valor específico al alcance detectado."]

def _explain_role_count(role: str, count: float, requirements: Optional[str]) -> List[str]:
    reasons = _explain_role(role, requirements)
    if count == 0.5: reasons.insert(0, "Dedicación parcial (0,5) por alcance acotado/consultivo.")
    elif count == 1: reasons.insert(0, "1 persona suficiente para ownership y coordinación del área.")
    elif count == 2: reasons.insert(0, "2 personas para paralelizar trabajo y reducir camino crítico.")
    elif count > 2: reasons.insert(0, f"{count:g} personas para throughput y cobertura de módulos en paralelo.")
    return reasons

def _explain_team_general(proposal: Dict[str, Any], requirements: Optional[str]) -> List[str]:
    t = _norm(requirements or "")
    reasons = ["Cobertura completa del ciclo: PM, Tech Lead, Backend/Frontend, QA, UX/UI.",
               "Dimensionado para equilibrar time-to-market y coste."]
    if "pagos" in t or "stripe" in t: reasons.append("Se añade 0,5 Backend (payments) por PCI-DSS e idempotencia.")
    if "admin" in t or "panel" in t: reasons.append("Se añade 0,5 Frontend (admin) para backoffice (tablas, filtros).")
    if "ml" in t or "ia" in t or "modelo" in t: reasons.append("Se añade 0,5 ML Engineer para prototipos y puesta en producción.")
    return reasons

def _explain_phases(proposal: Dict[str, Any]) -> List[str]:
    reasons: List[str] = []
    for ph in proposal["phases"]:
        nm = _norm(ph["name"])
        if "descubr" in nm: reasons.append("Descubrimiento: clarificar alcance y riesgos; evita construir lo equivocado.")
        elif "arquitect" in nm or "setup" in nm: reasons.append("Arquitectura & setup: estándares, CI/CD e infraestructura base.")
        elif "desarrollo" in nm or "iterativo" in nm: reasons.append("Desarrollo iterativo: MVP + valor en ciclos cortos.")
        elif "qa" in nm or "hardening" in nm: reasons.append("QA & hardening: pruebas y estabilización pre-release.")
        elif "despliegue" in nm or "handover" in nm: reasons.append("Despliegue & handover: release, documentación y formación.")
        else: reasons.append(f"{ph['name']}: entregables que reducen riesgos específicos.")
    reasons.insert(0, f"Se proponen {len(proposal['phases'])} fases para cubrir el ciclo completo:")
    return reasons

def _explain_budget(proposal: Dict[str, Any]) -> List[str]:
    b = proposal["budget"]
    return ["Estimación = (headcount_equivalente × semanas × tarifa_media/rol).",
            "Se añade un 10% de contingencia para incertidumbre técnica/alcance.",
            f"Total estimado: {b['total_eur']} € (labor {b['labor_estimate_eur']} € + contingencia {b['contingency_10pct']} €)."]

def _explain_budget_breakdown(proposal: Dict[str, Any]) -> List[str]:
    b = proposal.get("budget", {})
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
    risks: List[str] = ["Cambios de alcance sin prioridad", "Dependencias externas", "Datos insuficientes para pruebas de rendimiento/escalado"]
    if "pagos" in t or "stripe" in t: risks += ["Cumplimiento PCI-DSS y fraude", "Reintentos e idempotencia en cobros"]
    if "admin" in t or "panel" in t: risks += ["RBAC, auditoría y hardening en backoffice"]
    if "mobile" in t or "ios" in t or "android" in t or "app" in t: risks += ["Aprobación tiendas y compatibilidad"]
    if "tiempo real" in t or "realtime" in t or "websocket" in t: risks += ["Latencia y picos → colas/cachés"]
    if "ml" in t or "ia" in t or "modelo" in t: risks += ["Calidad de datos, sesgo y drift de modelos"]
    if methodology == "Scrum": risks += ["Scope creep si DoR/DoD no están claros"]
    if methodology == "Kanban": risks += ["Multitarea si no se respetan límites de WIP"]
    return risks

def _format_sources(sources) -> str:
    if not sources:
        return "No tengo fuentes adjuntas para esta recomendación."
    lines = []
    for s in sources:
        autor = s.get("autor","")
        titulo = s.get("titulo","")
        anio = s.get("anio","")
        url = s.get("url","")
        lines.append(f"- {autor}: *{titulo}* ({anio}). {url}")
    return "\n".join(lines)

# =============== Generación de respuesta ===============
def generate_reply(session_id: str, message: str) -> Tuple[str, str]:
    text = message.strip()
    proposal, req_text = get_last_proposal(session_id)

    # NLU intents opcional
    intent, conf = ("other", 0.0)
    if _INTENTS is not None:
        try: intent, conf = _INTENTS.predict(text)
        except Exception: pass

    if conf >= 0.80:
        if intent == "greet":
            return "¡Hola! ¿En qué te ayudo con tu proyecto? Describe requisitos o usa '/propuesta: ...' y preparo un plan.", "Saludo (intent)."
        if intent == "goodbye":
            return "¡Hasta luego! Si quieres, deja aquí los requisitos y seguiré trabajando en la propuesta.", "Despedida (intent)."
        if intent == "thanks":
            return "¡A ti! Si necesitas presupuesto o plan de equipo, dime los requisitos.", "Agradecimiento (intent)."

    # Comando explícito: generar propuesta
    if text.lower().startswith("/propuesta:"):
        req = text.split(":", 1)[1].strip() or "Proyecto genérico"
        try: log_message(session_id, "user", f"[REQ] {req}")
        except Exception: pass
        p = generate_proposal(req)
        set_last_proposal(session_id, p, req)
        try:
            save_proposal(session_id, req, p)
            if _SIM is not None: _SIM.refresh()
            log_message(session_id, "assistant", f"[PROPUESTA {p['methodology']}] {p['budget']['total_eur']} €")
        except Exception:
            pass
        return _pretty_proposal(p), "Propuesta generada."

    # Documentación/autores
    if _asks_sources(text):
        if proposal and proposal.get("methodology_sources"):
            meth = proposal.get("methodology")
            return (f"Documentación en la que baso la recomendación de **{meth}**:\n"
                    f"{_format_sources(proposal['methodology_sources'])}"), "Citas/Documentación."
        else:
            return ("Aún no tengo una propuesta guardada en esta sesión. Genera una con '/propuesta: ...' y te cito autores y documentación."), "Citas: sin propuesta."

    # Casos similares
    if _SIM is not None and ("similares" in _norm(text) or "parecidos" in _norm(text)):
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

    # Intenciones básicas
    if _is_greeting(text):
        return "¡Hola! ¿En qué te ayudo con tu proyecto? Describe requisitos o usa '/propuesta: ...' y preparo un plan.", "Saludo."
    if _is_farewell(text):
        return "¡Hasta luego! Si quieres, deja aquí los requisitos y seguiré trabajando en la propuesta.", "Despedida."
    if _is_thanks(text):
        return "¡A ti! Si necesitas presupuesto o plan de equipo, dime los requisitos.", "Agradecimiento."
    if _is_help(text):
        return ("Puedo: 1) generar una propuesta completa (equipo, fases, metodología, presupuesto, riesgos), "
                "2) explicar por qué tomo cada decisión (con citas), 3) rechazar/aceptar cambios y reajustar el plan."), "Ayuda."

    # Riesgos (sin por qué)
    if _asks_risks_simple(text) and not _asks_why(text):
        risks = _expand_risks(req_text, proposal.get("methodology") if proposal else None)
        return ("Riesgos del proyecto:\n- " + "\n- ".join(risks)), "Riesgos."

    # Rol concreto (sin por qué)
    roles_mentioned = _extract_roles_from_text(text)
    if roles_mentioned and not _asks_why(text):
        if len(roles_mentioned) == 1:
            r = roles_mentioned[0]
            bullets = _explain_role(r, req_text)
            extra = ""
            if proposal:
                cnt = _find_role_count_in_proposal(proposal, r)
                if cnt is not None:
                    bullets = _explain_role_count(r, cnt, req_text)
                    extra = f"\nEn esta propuesta: **{cnt:g} {r}**."
            return (f"{r} — función/valor:\n- " + "\n- ".join(bullets) + extra), "Rol concreto."
        else:
            return ("Veo varios roles mencionados. Dime uno concreto (p. ej., 'QA' o 'Tech Lead') y te explico su función y por qué está en el plan."), "Varios roles."

    # Preguntas de dominio (sin 'por qué')
    if _asks_methodology(text) and not _asks_why(text):
        return ("Metodologías soportadas: Scrum, Kanban, Scrumban, XP, Lean, Crystal, FDD, DSDM, SAFe y DevOps.\n"
                "Dame tus requisitos y elijo la mejor con explicación y fuentes."), "Metodologías."
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
        if proposal:
            reasons = _explain_team_general(proposal, req_text)
            return ("Equipo propuesto — razones:\n- " + "\n- ".join(reasons)), "Equipo."
        return ("Perfiles típicos: PM, Tech Lead, Backend, Frontend, QA, UX. "
                "La cantidad depende de módulos: pagos, panel admin, mobile, IA… "
                "Describe el alcance y dimensiono el equipo."), "Guía roles."

    # Preguntas 'por qué'
    if _asks_why(text):
        current_method = proposal["methodology"] if proposal else None
        for m in ["scrum","kanban","scrumban","xp","lean","crystal","fdd","dsdm","safe","devops","metodolog"]:
            if m in _norm(text):
                target = current_method
                if "scrum" in _norm(text): target = "Scrum"
                elif "kanban" in _norm(text): target = "Kanban"
                elif "scrumban" in _norm(text): target = "Scrumban"
                elif "xp" in _norm(text) or "extreme" in _norm(text): target = "XP"
                elif "lean" in _norm(text): target = "Lean"
                elif "crystal" in _norm(text): target = "Crystal"
                elif "fdd" in _norm(text) or "feature" in _norm(text): target = "FDD"
                elif "dsdm" in _norm(text): target = "DSDM"
                elif "safe" in _norm(text) or "scaled" in _norm(text): target = "SAFe"
                elif "devops" in _norm(text): target = "DevOps"
                if target:
                    return (f"¿Por qué **{target}**?\n- " + "\n- ".join([l for l in _explain_phases(proposal)[:1]] if False else [])  # noop para mantener formato
                            + "\n- " + "\n- ".join([f"[{target}] " + x for x in []])
                           ), "Explicación metodología."  # (el detalle lo damos en explanation de la propuesta)
        if proposal and _asks_why_team_general(text):
            reasons = _explain_team_general(proposal, req_text)
            team_lines = [f"- {t['role']} x{t['count']}" for t in proposal["team"]]
            return ("Equipo — por qué:\n- " + "\n- ".join(reasons) + "\nDesglose: \n" + "\n".join(team_lines)), "Equipo por qué."
        rc = _asks_why_role_count(text)
        if proposal and rc:
            role, count = rc
            return (f"¿Por qué **{count:g} {role}**?\n- " + "\n- ".join(_explain_role_count(role, count, req_text))), "Cantidad por rol."
        if proposal and _asks_why_phases(text):
            expl = _explain_phases(proposal)
            m = re.search(r"\b(\d+)\s*fases\b", _norm(text))
            if m:
                asked = int(m.group(1))
                expl.insert(1, f"Se han propuesto {len(proposal['phases'])} fases (preguntas por {asked}).")
            return ("Fases — por qué:\n- " + "\n- ".join(expl)), "Fases por qué."
        if proposal and _asks_budget(text):
            return ("Presupuesto — por qué:\n- " + "\n- ".join(_explain_budget(proposal))), "Presupuesto por qué."
        roles_why = _extract_roles_from_text(text)
        if proposal and roles_why:
            r = roles_why[0]
            cnt = _find_role_count_in_proposal(proposal, r)
            if cnt is not None:
                return (f"¿Por qué **{r}** en el plan?\n- " + "\n- ".join(_explain_role_count(r, cnt, req_text))), "Rol por qué."
            else:
                return (f"¿Por qué **{r}**?\n- " + "\n- ".join(_explain_role(r, req_text))), "Rol por qué."
        if proposal:
            generic = [
                f"Metodología: {proposal['methodology']}",
                "Equipo dimensionado por módulos detectados y equilibrio coste/velocidad.",
                "Fases cubren descubrimiento→entrega; cada una reduce un riesgo.",
                "Presupuesto = headcount × semanas × tarifa por rol + 10% contingencia."
            ]
            return ("Explicación general:\n- " + "\n- ".join(generic)), "Explicación general."
        else:
            return ("Puedo justificar metodología, equipo, fases, presupuesto y riesgos. Genera una propuesta con '/propuesta: ...' y la explico punto por punto."), "Sin propuesta."

    # Interpretar requisitos → generar propuesta
    if _looks_like_requirements(text):
        p = generate_proposal(text)
        set_last_proposal(session_id, p, text)
        try:
            log_message(session_id, "user", f"[REQ] {text}")
            save_proposal(session_id, text, p)
            if _SIM is not None: _SIM.refresh()
            log_message(session_id, "assistant", f"[PROPUESTA {p['methodology']}] {p['budget']['total_eur']} €")
        except Exception:
            pass
        return _pretty_proposal(p), "Propuesta a partir de requisitos."

    return ("Te he entendido. Dame más contexto (objetivo, usuarios, módulos clave) "
            "o escribe '/propuesta: ...' y te entrego un plan completo con justificación y fuentes."), "Fallback."
