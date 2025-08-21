import re
from typing import Tuple, Dict, Any
from backend.engine.planner import generate_proposal

# ---------- Helpers ----------

def _is_greeting(text: str) -> bool:
    return bool(re.search(r"\b(hola|buenas|hey|hello|qué tal|que tal)\b", text, re.I))

def _is_farewell(text: str) -> bool:
    return bool(re.search(r"\b(ad[ií]os|hasta luego|nos vemos|chao)\b", text, re.I))

def _is_thanks(text: str) -> bool:
    return bool(re.search(r"\b(gracias|thank[s]?|mil gracias)\b", text, re.I))

def _is_help(text: str) -> bool:
    t = text.lower()
    return "ayuda" in t or "qué puedes hacer" in t or "que puedes hacer" in t

def _asks_methodology(text: str) -> bool:
    return bool(re.search(r"\b(scrum|kanban|scrumban|metodolog[ií]a)\b", text, re.I))

def _asks_budget(text: str) -> bool:
    return bool(re.search(r"\b(presupuesto|coste|costos|estimaci[oó]n)\b", text, re.I))

def _asks_team(text: str) -> bool:
    return bool(re.search(r"\b(equipo|roles|perfiles|staffing)\b", text, re.I))

def _looks_like_requirements(text: str) -> bool:
    # Heurística para detectar requisitos en lenguaje natural
    kw = [
        "app", "web", "api", "panel", "admin", "pagos", "login", "usuarios",
        "microservicios", "ios", "android", "realtime", "tiempo real",
        "ml", "ia", "modelo", "dashboard", "reportes", "integraci"
    ]
    score = sum(1 for k in kw if k in text.lower())
    return score >= 2 or len(text.split()) >= 12

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

# ---------- Núcleo ----------

def generate_reply(session_id: str, message: str) -> Tuple[str, str]:
    text = message.strip()

    # Comando explícito
    if text.lower().startswith("/propuesta:"):
        req = text.split(":", 1)[1].strip() or "Proyecto genérico"
        p = generate_proposal(req)
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
            "2) responder dudas de metodologías ágiles, 3) ajustar la propuesta si cambian requisitos. "
            "Dime qué necesita el cliente o usa '/propuesta: ...'."
        ), "Ayuda solicitada."

    # Preguntas frecuentes del dominio
    if _asks_methodology(text):
        return (
            "Scrum: iteraciones fijas y roles definidos (bueno para incertidumbre). "
            "Kanban: flujo continuo y límites de WIP (bueno para operación/soporte). "
            "Scrumban: híbrido cuando hay cambios pero también trabajo continuo. "
            "Si me das requisitos, elijo y justifico la mejor opción."
        ), "Explicación de metodologías."
    if _asks_budget(text):
        return (
            "Para estimar presupuesto considero: alcance → equipo → duración → tarifa media + 10% contingencia. "
            "Dime el tipo de producto y restricciones (fecha/coste) y te lo cuantifico."
        ), "Guía de presupuesto."
    if _asks_team(text):
        return (
            "Perfiles típicos: PM, Tech Lead, Backend, Frontend, QA, UX. "
            "La cantidad depende de módulos: pagos, panel admin, mobile, IA… "
            "Describe el alcance y dimensiono el equipo óptimo."
        ), "Guía de roles."

    # Detección de requisitos en texto libre
    if _looks_like_requirements(text):
        p = generate_proposal(text)
        return _pretty_proposal(p), "He interpretado tu mensaje como requisitos y he generado una propuesta inicial."

    # Fallback
    return (
        "Te he entendido. Dame un poco más de contexto del cliente (objetivo, usuarios, módulos clave) "
        "o escribe '/propuesta: ...' y te entrego un plan completo."
    ), "Fallback neutro."
