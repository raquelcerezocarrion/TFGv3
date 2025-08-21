# backend/engine/brain.py
import re
from typing import Tuple, Dict, Any, List, Optional
from backend.engine.planner import generate_proposal
from backend.engine.context import get_last_proposal

# ---------- Helpers de intención ----------

def _norm(text: str) -> str:
    return text.lower()

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
    return bool(re.search(r"\b(scrum|kanban|scrumban|metodolog[ií]a)\b", text, re.I))

def _asks_budget(text: str) -> bool:
    return bool(re.search(r"\b(presupuesto|coste|costos|estimaci[oó]n)\b", text, re.I))

def _asks_team(text: str) -> bool:
    return bool(re.search(r"\b(equipo|roles|perfiles|staffing)\b", text, re.I))

def _asks_why(text: str) -> bool:
    t = _norm(text)
    return ("por qué" in t) or ("por que" in t) or ("porque" in t) or ("justifica" in t) or ("explica" in t) or ("por que recomiendas" in t) or ("por qué recomiendas" in t)

def _asks_expand_risks(text: str) -> bool:
    t = _norm(text)
    return ("riesgo" in t or "riesgos" in t) and ("ampl" in t or "detall" in t or "profund" in t or "más" in t or "mas" in t)

def _looks_like_requirements(text: str) -> bool:
    kw = [
        "app","web","api","panel","admin","pagos","login","usuarios","microservicios",
        "ios","android","realtime","tiempo real","ml","ia","modelo","dashboard","reportes","integraci"
    ]
    score = sum(1 for k in kw if k in _norm(text))
    return score >= 2 or len(text.split()) >= 12

# ---------- Pretty ----------

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

# ---------- Explicabilidad ----------

def _extract_role(text: str) -> Optional[str]:
    t = _norm(text)
    mapping = {
        "qa": "QA",
        "quality": "QA",
        "tester": "QA",
        "ux": "UX/UI",
        "ui": "UX/UI",
        "diseñ": "UX/UI",
        "pm": "PM",
        "project manager": "PM",
        "tech lead": "Tech Lead",
        "arquitect": "Tech Lead",
        "backend": "Backend Dev",
        "frontend": "Frontend Dev",
        "ml": "ML Engineer",
        "data": "ML Engineer",
    }
    for k, v in mapping.items():
        if k in t:
            return v
    return None

def _target_methodology(text: str, current: Optional[str]) -> Optional[str]:
    t = _norm(text)
    for m in ["scrum", "kanban", "scrumban"]:
        if m in t:
            return m.capitalize()
    if "metodolog" in t:
        return current
    return None

def _explain_methodology(methodology: str, requirements: Optional[str]) -> List[str]:
    t = _norm(requirements or "")
    reasons: List[str] = []
    if methodology == "Scrum":
        if any(k in t for k in ["incertidumbre", "cambiante", "iteraci", "mvp", "descubrimiento"]):
            reasons.append("Los requisitos son cambiantes/incertidumbre alta → sprints cortos y feedback frecuente.")
        reasons += [
            "Marco con eventos y roles claros para priorizar y reducir riesgos tempranos.",
            "Permite inspección y adaptación en cada sprint, alineando al cliente con el producto."
        ]
    elif methodology == "Kanban":
        if any(k in t for k in ["24/7","operación","soporte","mantenimiento","flujo continuo","tiempo real","realtime"]):
            reasons.append("Trabajo de flujo continuo/operación → límites de WIP y lead-time corto.")
        reasons += [
            "Visualiza el flujo y elimina cuellos de botella sin imponer sprints fijos.",
            "Útil cuando entran peticiones con distinta prioridad y tamaño."
        ]
    else:  # Scrumban
        reasons += [
            "Combina planificación ligera de Scrum con el control de flujo de Kanban.",
            "Adecuado cuando hay mezcla de desarrollo nuevo y mantenimiento/operación."
        ]
    if not reasons:
        reasons.append("Se ajusta mejor a los patrones detectados en tus requisitos frente a alternativas.")
    return reasons

def _explain_role(role: str, requirements: Optional[str]) -> List[str]:
    t = _norm(requirements or "")
    if role == "QA":
        base = [
            "Reduce fuga de defectos y coste de corrección en producción.",
            "Permite automatizar regresión y asegurar criterios de aceptación."
        ]
        if "pagos" in t or "stripe" in t:
            base.append("Nec. pruebas de integración con pasarela y controles anti-fraude.")
        return base
    if role == "UX/UI":
        base = ["Mejora conversión y usabilidad; reduce retrabajo de frontend."]
        if "panel" in t or "admin" in t or "mobile" in t or "app" in t:
            base.append("Diseña flujos y componentes reutilizables (design system).")
        return base
    if role == "Tech Lead":
        return ["Define arquitectura, estándares y CI/CD; desbloquea al equipo y controla la deuda técnica."]
    if role == "PM":
        return ["Gestiona alcance, riesgos y stakeholders; protege al equipo de interrupciones y controla plazos."]
    if role == "Backend Dev":
        base = ["Implementa APIs, dominios y seguridad; rendimiento y mantenibilidad del servidor."]
        if "pagos" in t:
            base.append("Integra pasarela de pagos y asegura idempotencia y auditoría.")
        return base
    if role == "Frontend Dev":
        return ["Construye la UX final (React), estado y accesibilidad; integra con backend y diseño."]
    if role == "ML Engineer":
        return ["Prototipa y productiviza modelos; evalúa drift y sesgos; integra batch/online."]
    return ["Aporta valor específico al alcance detectado."]

def _explain_budget(proposal: Dict[str, Any]) -> List[str]:
    b = proposal["budget"]
    reasons = [
        f"Estimación = (headcount_equivalente × semanas × tarifa_media).",
        f"Contingencia del 10% para incertidumbre técnica/alcance.",
        f"Total estimado: {b['total_eur']} € (labor {b['labor_estimate_eur']} € + contingencia {b['contingency_10pct']} €)."
    ]
    return reasons

def _expand_risks(requirements: Optional[str], methodology: Optional[str]) -> List[str]:
    t = _norm(requirements or "")
    risks: List[str] = []
    # Comunes
    risks += [
        "Cambios de alcance sin versionado ni control de prioridad.",
        "Retrasos por dependencias externas (APIs/pagos/terceros).",
        "Datos insuficientes para pruebas de rendimiento/escalado."
    ]
    # Específicos
    if "pagos" in t or "stripe" in t:
        risks += ["Cumplimiento PCI-DSS y gestión de fraude/chargebacks.", "Flujos de reintento e idempotencia en cobros."]
    if "admin" in t or "panel" in t:
        risks += ["Control de acceso (RBAC), auditoría y hardening de paneles de administración."]
    if "mobile" in t or "ios" in t or "android" in t or "app" in t:
        risks += ["Revisión de App Store/Play Store y compatibilidad de dispositivos."]
    if "tiempo real" in t or "realtime" in t or "websocket" in t:
        risks += ["Latencia, escalabilidad horizontal y tolerancia a picos (colas/cachés)."]
    if "ml" in t or "ia" in t or "modelo" in t:
        risks += ["Calidad de datos, sesgo y drift del modelo; explainability y monitoreo ML."]
    if methodology == "Scrum":
        risks += ["Riesgo de scope creep por mala definición de DoR/DoD; disciplina de backlog necesaria."]
    if methodology == "Kanban":
        risks += ["Riesgo de multitarea si no se respetan límites de WIP; medir lead/cycle time."]
    return risks

# ---------- Núcleo de respuesta ----------

def generate_reply(session_id: str, message: str) -> Tuple[str, str]:
    text = message.strip()
    proposal, req_text = get_last_proposal(session_id)

    # Comando explícito
    if text.lower().startswith("/propuesta:"):
        req = text.split(":", 1)[1].strip() or "Proyecto genérico"
        p = generate_proposal(req)
        # NOTA: el guardado se hace en /projects/proposal; aquí solo mostramos
        return _pretty_proposal(p), "He detectado el comando /propuesta y he generado una propuesta basada en los requisitos."

    # Intenciones básicas
    if _is_greeting(text):
        return "¡Hola! ¿En qué te ayudo con tu proyecto? Puedes describirme los requisitos y te preparo una propuesta.", "Saludo detectado."
    if _is_farewell(text):
        return "¡Hasta luego! Si quieres, deja aquí los requisitos y seguiré trabajando en la propuesta.", "Despedida detectada."
    if _is_thanks(text):
        return "¡A ti! Si necesitas un presupuesto o un plan de equipo, dime los requisitos.", "Agradecimiento detectado."
    if _is_help(text):
        return (
            "Puedo: 1) generar una propuesta completa (equipo, tareas, metodología, presupuesto), "
            "2) explicar por qué tomo cada decisión, 3) ajustar la propuesta si cambian requisitos. "
            "Dime qué necesita el cliente o usa '/propuesta: ...'."
        ), "Ayuda solicitada."

    # Preguntas frecuentes del dominio
    if _asks_methodology(text) and not _asks_why(text):
        return (
            "Scrum: iteraciones fijas y roles definidos (bueno para incertidumbre). "
            "Kanban: flujo continuo y límites de WIP (bueno para operación/soporte). "
            "Scrumban: híbrido cuando hay cambios pero también trabajo continuo. "
            "Si me das requisitos, elijo y justifico la mejor opción."
        ), "Explicación de metodologías."
    if _asks_budget(text) and not _asks_why(text):
        if proposal:
            return ("\n".join(_explain_budget(proposal)), "Desglose del presupuesto actual.")
        return (
            "Para estimar presupuesto considero: alcance → equipo → duración → tarifa media + 10% contingencia. "
            "Dime el tipo de producto y restricciones (fecha/coste) y te lo cuantifico."
        ), "Guía de presupuesto."
    if _asks_team(text) and not _asks_why(text):
        return (
            "Perfiles típicos: PM, Tech Lead, Backend, Frontend, QA, UX. "
            "La cantidad depende de módulos: pagos, panel admin, mobile, IA… "
            "Describe el alcance y dimensiono el equipo óptimo."
        ), "Guía de roles."

    # --- Explicaciones "¿por qué...?" ---
    if _asks_why(text):
        # ¿Metodología?
        current_method = proposal["methodology"] if proposal else None
        target_m = _target_methodology(text, current_method)
        if target_m:
            reasons = _explain_methodology(target_m, req_text)
            return ("¿Por qué **{}**?\n- ".format(target_m) + "\n- ".join(reasons)), "Explicación de metodología basada en la última propuesta y requisitos."

        # ¿Rol?
        r = _extract_role(text)
        if r:
            reasons = _explain_role(r, req_text)
            return ("¿Por qué **{}**?\n- ".format(r) + "\n- ".join(reasons)), "Explicación de rol basada en la última propuesta y requisitos."

        # ¿Presupuesto/coste?
        if _asks_budget(text) and proposal:
            return ("Presupuesto:\n- " + "\n- ".join(_explain_budget(proposal))), "Explicación del presupuesto actual."

        # Si no detecto objetivo, da pauta y usa contexto si lo hay
        if proposal:
            generic = [
                f"Metodología propuesta: {proposal['methodology']} → " + "; ".join(_explain_methodology(proposal['methodology'], req_text)),
                "Equipo y roles en función de módulos detectados en los requisitos.",
                "Presupuesto = headcount × semanas × tarifa media + 10% de contingencia."
            ]
            return ("Explicación general:\n- " + "\n- ".join(generic)), "Explicación general de la propuesta."
        else:
            return ("Puedo justificar metodología, roles y presupuesto; dame requisitos o genera una propuesta con '/propuesta: ...' y te explico cada decisión."), "No hay propuesta previa en sesión."

    # --- Ampliar riesgos ---
    if _asks_expand_risks(text):
        risks = _expand_risks(req_text, proposal.get("methodology") if proposal else None)
        return ("Riesgos ampliados:\n- " + "\n- ".join(risks)), "Ampliación de riesgos basada en requisitos detectados."

    # Detección de requisitos en texto libre → generar propuesta al vuelo (view only)
    if _looks_like_requirements(text):
        p = generate_proposal(text)
        return _pretty_proposal(p), "He interpretado tu mensaje como requisitos y he generado una propuesta inicial."

    # Fallback
    return (
        "Te he entendido. Dame un poco más de contexto del cliente (objetivo, usuarios, módulos clave) "
        "o escribe '/propuesta: ...' y te entrego un plan completo con justificación de decisiones."
    ), "Fallback neutro."
