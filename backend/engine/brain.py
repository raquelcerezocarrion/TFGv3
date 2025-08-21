import re
from typing import Tuple, Dict, Any, List, Optional
from backend.engine.planner import generate_proposal
from backend.engine.context import get_last_proposal, set_last_proposal

# ---------- Utilidades ----------

def _norm(text: str) -> str:
    return text.lower()

# ---------- Intenciones básicas ----------

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
    return bool(re.search(r"\b(presupuesto|coste|costos|estimaci[oó]n|precio)\b", text, re.I))

def _asks_team(text: str) -> bool:
    return bool(re.search(r"\b(equipo|roles|perfiles|staffing|personal|plantilla|dimension)\b", text, re.I))

def _asks_why(text: str) -> bool:
    t = _norm(text)
    return ("por qué" in t) or ("por que" in t) or ("porque" in t) or ("justifica" in t) or ("explica" in t) or ("motivo" in t)

def _asks_expand_risks(text: str) -> bool:
    t = _norm(text)
    return ("riesgo" in t or "riesgos" in t) and ("ampl" in t or "detall" in t or "profund" in t or "más" in t or "mas" in t)

def _asks_why_phases(text: str) -> bool:
    t = _norm(text)
    return ("fase" in t or "fases" in t or "hitos" in t or "timeline" in t) and _asks_why(t)

def _asks_why_team_general(text: str) -> bool:
    t = _norm(text)
    return _asks_why(t) and ("equipo" in t or "roles" in t or "personal" in t or "plantilla" in t or "dimension" in t)

def _asks_why_role_count(text: str) -> Optional[Tuple[str, float]]:
    """
    Detecta preguntas tipo:
    - "por qué 2 backend"
    - "por qué 0.5 ux"
    - "por qué hay 1 pm"
    Devuelve (ROL_CANÓNICO, CANTIDAD) o None.
    """
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

# ---------- Canonicalización / pretty ----------

def _canonical_role(role_text: str) -> str:
    t = _norm(role_text)
    mapping = {
        "qa": "QA", "quality": "QA", "tester": "QA",
        "ux": "UX/UI", "ui": "UX/UI", "diseñ": "UX/UI",
        "pm": "PM", "project manager": "PM",
        "tech lead": "Tech Lead", "arquitect": "Tech Lead",
        "backend": "Backend Dev", "frontend": "Frontend Dev",
        "ml": "ML Engineer", "data": "ML Engineer",
    }
    for k, v in mapping.items():
        if k in t:
            return v
    return role_text.strip().title()

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

# ---------- Explicabilidad de decisiones ----------

def _explain_methodology(methodology: str, requirements: Optional[str]) -> List[str]:
    t = _norm(requirements or "")
    reasons: List[str] = []
    if methodology == "Scrum":
        if any(k in t for k in ["incertidumbre", "cambiante", "iteraci", "mvp", "descubrimiento"]):
            reasons.append("Requisitos cambiantes/incertidumbre → sprints cortos y feedback frecuente.")
        reasons += [
            "Marco con eventos/roles claros que reduce riesgo y alinea al cliente.",
            "Inspección y adaptación en cada sprint para priorizar valor."
        ]
    elif methodology == "Kanban":
        if any(k in t for k in ["24/7","operación","soporte","mantenimiento","flujo continuo","tiempo real","realtime"]):
            reasons.append("Flujo continuo/operación → límites de WIP y lead time corto.")
        reasons += [
            "Visualiza el flujo y elimina cuellos de botella sin imponer sprints.",
            "Admite peticiones de distinto tamaño/prioridad con poco overhead."
        ]
    else:  # Scrumban
        reasons += [
            "Híbrido: planificación ligera de Scrum + control de flujo de Kanban.",
            "Útil cuando hay mezcla de desarrollo nuevo y mantenimiento."
        ]
    if not reasons:
        reasons.append("Se ajusta mejor a los patrones detectados frente a alternativas.")
    return reasons

def _explain_role(role: str, requirements: Optional[str]) -> List[str]:
    t = _norm(requirements or "")
    if role == "QA":
        base = [
            "Reduce fuga de defectos y coste de corrección en producción.",
            "Automatiza regresión y asegura criterios de aceptación."
        ]
        if "pagos" in t or "stripe" in t:
            base.append("Necesarias pruebas de integración con pasarela y controles anti-fraude.")
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
    """Explica por qué esos roles y cantidades en conjunto."""
    t = _norm(requirements or "")
    reasons = [
        "Cobertura completa del ciclo: dirección (PM), arquitectura (Tech Lead), desarrollo (Backend/Frontend), calidad (QA) y experiencia de usuario (UX/UI).",
        "Dimensionado para equilibrar time-to-market y coste (tarifa media y semanas previstas)."
    ]
    # Menciones específicas según keywords detectadas (coherente con planner)
    if "pagos" in t or "stripe" in t:
        reasons.append("Se añade 0,5 Backend (payments) por PCI-DSS, idempotencia y conciliación.")
    if "admin" in t or "panel" in t:
        reasons.append("Se añade 0,5 Frontend (admin) para tablas, filtros y gráficos del backoffice.")
    if "ml" in t or "ia" in t or "modelo" in t:
        reasons.append("Se añade 0,5 ML Engineer para prototipos, evaluación y puesta en producción.")
    # Incluye el desglose concreto de la propuesta
    team_lines = [f"- {t['role']} x{t['count']}: " + "; ".join(_explain_role(t['role'], requirements)) for t in proposal["team"]]
    reasons.append("Desglose por rol:")
    reasons.extend(team_lines)
    return reasons

def _explain_phases(proposal: Dict[str, Any]) -> List[str]:
    reasons = []
    names = [p["name"].lower() for p in proposal["phases"]]
    for ph in proposal["phases"]:
        nm = ph["name"].lower()
        if "descubr" in nm:
            reasons.append("Descubrimiento: clarificar alcance, riesgos y prioridades; evita construir lo equivocado.")
        elif "arquitect" in nm or "setup" in nm:
            reasons.append("Arquitectura y setup: definir estándares, CI/CD e infraestructura base para iterar rápido.")
        elif "desarrollo" in nm or "iterativo" in nm:
            reasons.append("Desarrollo iterativo: construir MVP y añadir valor en ciclos cortos para validar con usuarios.")
        elif "qa" in nm or "hardening" in nm:
            reasons.append("QA & hardening: pruebas funcionales/performance/seguridad y estabilización previa al release.")
        elif "despliegue" in nm or "handover" in nm:
            reasons.append("Despliegue & handover: release, documentación y formación para transferencia al cliente.")
        else:
            reasons.append(f"{ph['name']}: aporta un entregable específico y reduce un riesgo concreto.")
    reasons.insert(0, f"Se proponen {len(proposal['phases'])} fases para cubrir de principio a fin el ciclo de producto:")
    return reasons

def _explain_budget(proposal: Dict[str, Any]) -> List[str]:
    b = proposal["budget"]
    return [
        "Estimación = (headcount_equivalente × semanas × tarifa_media).",
        "Se añade un 10% de contingencia para incertidumbre técnica/alcance.",
        f"Total estimado: {b['total_eur']} € (labor {b['labor_estimate_eur']} € + contingencia {b['contingency_10pct']} €)."
    ]

def _expand_risks(requirements: Optional[str], methodology: Optional[str]) -> List[str]:
    t = _norm(requirements or "")
    risks: List[str] = []
    risks += [
        "Cambios de alcance sin versionado ni control de prioridad.",
        "Retrasos por dependencias externas (APIs/pagos/terceros).",
        "Datos insuficientes para pruebas de rendimiento/escalado."
    ]
    if "pagos" in t or "stripe" in t:
        risks += ["Cumplimiento PCI-DSS y fraude/chargebacks.", "Reintentos e idempotencia en cobros."]
    if "admin" in t or "panel" in t:
        risks += ["RBAC, auditoría y hardening en backoffice."]
    if "mobile" in t or "ios" in t or "android" in t or "app" in t:
        risks += ["Revisión App Store/Play y compatibilidad de dispositivos."]
    if "tiempo real" in t or "realtime" in t or "websocket" in t:
        risks += ["Latencia y picos → colas/cachés y escalado horizontal."]
    if "ml" in t or "ia" in t or "modelo" in t:
        risks += ["Calidad de datos, sesgo y drift; monitoreo de modelos."]
    if methodology == "Scrum":
        risks += ["Scope creep si DoR/DoD no están claros; disciplina de backlog necesaria."]
    if methodology == "Kanban":
        risks += ["Multitarea si no se respetan límites de WIP; medir lead/cycle time."]
    return risks

# ---------- Núcleo de respuesta ----------

def generate_reply(session_id: str, message: str) -> Tuple[str, str]:
    text = message.strip()
    proposal, req_text = get_last_proposal(session_id)

    # Comando explícito
    if text.lower().startswith("/propuesta:"):
        req = text.split(":", 1)[1].strip() or "Proyecto genérico"
        p = generate_proposal(req)
        set_last_proposal(session_id, p, req)  # guardamos para justificar después
        return _pretty_proposal(p), "He generado una propuesta basada en tus requisitos."

    # Intenciones básicas
    if _is_greeting(text):
        return "¡Hola! ¿En qué te ayudo con tu proyecto? Describe requisitos o usa '/propuesta: ...' y preparo un plan.", "Saludo detectado."
    if _is_farewell(text):
        return "¡Hasta luego! Si quieres, deja aquí los requisitos y seguiré trabajando en la propuesta.", "Despedida detectada."
    if _is_thanks(text):
        return "¡A ti! Si necesitas presupuesto o plan de equipo, dime los requisitos.", "Agradecimiento detectado."
    if _is_help(text):
        return (
            "Puedo: 1) generar una propuesta completa (equipo, fases, metodología, presupuesto, riesgos), "
            "2) explicar por qué tomo cada decisión, 3) rechazar/aceptar cambios y reajustar el plan."
        ), "Ayuda solicitada."

    # Preguntas de dominio (sin 'por qué')
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
            "Para estimar presupuesto considero: alcance → equipo → semanas → tarifa media + 10% de contingencia."
        ), "Guía de presupuesto."
    if _asks_team(text) and not _asks_why(text):
        return (
            "Perfiles típicos: PM, Tech Lead, Backend, Frontend, QA, UX. "
            "La cantidad depende de módulos: pagos, panel admin, mobile, IA… "
            "Describe el alcance y dimensiono el equipo."
        ), "Guía de roles."

    # --- Explicaciones "¿por qué...?" ---
    if _asks_why(text):
        # 1) ¿Por qué metodología X?
        current_method = proposal["methodology"] if proposal else None
        for m in ["scrum", "kanban", "scrumban", "metodolog"]:
            if m in _norm(text):
                target = "Scrumban" if "scrumban" in _norm(text) else ("Kanban" if "kanban" in _norm(text) else ("Scrum" if "scrum" in _norm(text) else current_method))
                if target:
                    reasons = _explain_methodology(target, req_text)
                    return ("¿Por qué **{}**?\n- ".format(target) + "\n- ".join(reasons)), "Explicación de metodología."
                break

        # 2) ¿Por qué ese EQUIPO / esos ROLES (en general)?
        if proposal and _asks_why_team_general(text):
            reasons = _explain_team_general(proposal, req_text)
            return ("Equipo propuesto — razones:\n- " + "\n- ".join(reasons)), "Explicación del equipo y roles."

        # 3) ¿Por qué X Backend/QA/UX/etc.?
        rc = _asks_why_role_count(text)
        if proposal and rc:
            role, count = rc
            return (f"¿Por qué **{count:g} {role}**?\n- " + "\n- ".join(_explain_role_count(role, count, req_text))), "Explicación de cantidad por rol."

        # 4) ¿Por qué N fases / por qué esas fases?
        if proposal and _asks_why_phases(text):
            expl = _explain_phases(proposal)
            # Si el usuario menciona un número concreto, lo referenciamos
            m = re.search(r"\b(\d+)\s*fases\b", _norm(text))
            if m:
                asked = int(m.group(1))
                expl.insert(1, f"Se han propuesto {len(proposal['phases'])} fases (preguntas por {asked}). Ajusto el detalle a ese número cuando cambie el alcance.")
            return ("Fases del plan — por qué:\n- " + "\n- ".join(expl)), "Explicación de fases."

        # 5) ¿Por qué ese presupuesto?
        if proposal and _asks_budget(text):
            return ("Presupuesto — por qué:\n- " + "\n- ".join(_explain_budget(proposal))), "Explicación del presupuesto."

        # 6) ¿Por qué [ROL] genérico sin número?
        if proposal:
            # intenta detectar un rol suelto
            for r in ["pm","project manager","tech lead","arquitecto","backend","frontend","qa","tester","quality","ux","ui","ml","data"]:
                if r in _norm(text):
                    role = _canonical_role(r)
                    return ("¿Por qué **{}**?\n- ".format(role) + "\n- ".join(_explain_role(role, req_text))), "Explicación de un rol concreto."

        # 7) Resumen si no se detecta foco
        if proposal:
            generic = [
                f"Metodología: {proposal['methodology']} → " + "; ".join(_explain_methodology(proposal['methodology'], req_text)),
                "Equipo dimensionado por módulos detectados y equilibrio coste/velocidad.",
                "Fases cubren descubrimiento→entrega; cada una reduce un riesgo.",
                "Presupuesto = headcount × semanas × tarifa media + 10% contingencia."
            ]
            return ("Explicación general:\n- " + "\n- ".join(generic)), "Explicación general de la propuesta."
        else:
            return ("Puedo justificar metodología, equipo, fases, presupuesto y riesgos. Genera una propuesta con '/propuesta: ...' y la explico punto por punto."), "No hay propuesta previa."

    # --- Ampliar riesgos ---
    if _asks_expand_risks(text):
        risks = _expand_risks(req_text, proposal.get("methodology") if proposal else None)
        return ("Riesgos ampliados:\n- " + "\n- ".join(risks)), "Ampliación de riesgos."

    # Detección de requisitos en texto libre → genera y guarda propuesta
    if _looks_like_requirements(text):
        p = generate_proposal(text)
        set_last_proposal(session_id, p, text)
        return _pretty_proposal(p), "He interpretado tu mensaje como requisitos y he generado una propuesta."

    # Fallback
    return (
        "Te he entendido. Dame un poco más de contexto (objetivo, usuarios, módulos clave) "
        "o escribe '/propuesta: ...' y te entrego un plan completo con justificación de decisiones."
    ), "Fallback neutro."
