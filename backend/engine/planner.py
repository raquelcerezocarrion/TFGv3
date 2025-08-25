# backend/engine/planner.py
from typing import Dict, Any, List
import math

from backend.knowledge.methodologies import (
    recommend_methodology,
    explain_methodology_choice,
    METHODOLOGIES,
)

def _round_money(x: float) -> float:
    return round(x, 2)

def generate_proposal(requirements_text: str) -> Dict[str, Any]:
    """
    Genera una propuesta simple pero completa y, ahora, con
    - decision_log por área (team, phases, budget, risks, methodology)
    - methodology_sources para poder citar siempre.
    """
    # 1) Elegir metodología
    chosen, score, scored = recommend_methodology(requirements_text)
    method_info = METHODOLOGIES.get(chosen, {})
    methodology_sources = method_info.get("sources", [])

    # 2) Equipo base (muy simple, derivado del alcance por keywords)
    req = requirements_text.lower()
    need_mobile = any(k in req for k in ["mobile", "móvil", "android", "ios", "app"])
    need_admin  = any(k in req for k in ["admin", "backoffice", "panel"])
    need_pay    = any(k in req for k in ["pago", "pagos", "stripe", "checkout"])
    need_realtime = any(k in req for k in ["tiempo real", "realtime", "websocket"])
    need_ml     = any(k in req for k in ["ml", "ia", "modelo", "machine learning"])

    team: List[Dict[str, Any]] = [
        {"role": "PM",           "count": 0.5},
        {"role": "Tech Lead",    "count": 0.5},
        {"role": "Backend Dev",  "count": 2.0},
        {"role": "Frontend Dev", "count": 1.0},
        {"role": "QA",           "count": 1.0},
        {"role": "UX/UI",        "count": 0.5},
    ]
    if need_admin:
        team.append({"role": "Frontend Dev", "count": 0.5})
    if need_pay:
        team.append({"role": "Backend Dev", "count": 0.5})
    if need_ml:
        team.append({"role": "ML Engineer", "count": 0.5})

    # 3) Fases (ligeras por metodología)
    if chosen == "Kanban":
        phases = [
            {"name": "Descubrimiento & Diseño", "weeks": 2},
            {"name": "Implementación flujo continuo (WIP/Columnas)", "weeks": 4},
            {"name": "QA continuo & Observabilidad", "weeks": 2},
            {"name": "Estabilización & Puesta en Producción", "weeks": 1},
        ]
    elif chosen == "XP":
        phases = [
            {"name": "Discovery + Historias & CRC", "weeks": 2},
            {"name": "Iteraciones con TDD/Refactor/CI", "weeks": 6},
            {"name": "Hardening & Pruebas de Aceptación", "weeks": 2},
            {"name": "Release & Handover", "weeks": 1},
        ]
    elif chosen == "Scrum":
        phases = [
            {"name": "Incepción & Plan de Releases", "weeks": 2},
            {"name": "Sprints de Desarrollo (2w)", "weeks": 6},
            {"name": "QA/Hardening Sprint", "weeks": 2},
            {"name": "Despliegue & Transferencia", "weeks": 1},
        ]
    else:
        phases = [
            {"name": "Discovery", "weeks": 2},
            {"name": "Implementación iterativa", "weeks": 6},
            {"name": "QA & Hardening", "weeks": 2},
            {"name": "Release & Handover", "weeks": 1},
        ]

    # 4) Presupuesto sencillo por tarifa/rol
    role_rates = {
        "PM": 1200.0, "Tech Lead": 1400.0,
        "Backend Dev": 1100.0, "Frontend Dev": 1000.0,
        "QA": 900.0, "UX/UI": 1000.0, "ML Engineer": 1400.0,
    }
    project_weeks = sum(p["weeks"] for p in phases)
    by_role = {}
    for r in team:
        role = r["role"]; cnt = r["count"]
        rate = role_rates.get(role, 1000.0)
        by_role.setdefault(role, 0.0)
        by_role[role] += cnt * project_weeks * rate

    labor = _round_money(sum(by_role.values()))
    contingency = _round_money(0.10 * labor)
    total = _round_money(labor + contingency)

    budget = {
        "labor_estimate_eur": labor,
        "contingency_10pct": contingency,
        "total_eur": total,
        "by_role": by_role,
        "assumptions": {
            "project_weeks": project_weeks,
            "role_rates_eur_pw": role_rates
        }
    }

    # 5) Riesgos rápidos
    risks = [
        "Cambios de alcance sin prioridad clara",
        "Dependencias externas (APIs/terceros)",
        "Datos insuficientes para pruebas de rendimiento/escalado",
    ]
    if need_pay:
        risks += ["PCI-DSS, fraude/chargebacks, idempotencia en cobros"]
    if need_realtime:
        risks += ["Latencia/picos → colas/cachés y observabilidad"]
    if need_mobile:
        risks += ["Aprobación en tiendas y compatibilidad de dispositivos"]
    if need_ml:
        risks += ["Calidad de datos, sesgo y monitorización de modelos"]

    # 6) decision_log con FUENTES por área
    decision_log: List[Dict[str, Any]] = []

    # Metodología
    decision_log.append({
        "area": "methodology",
        "why": explain_methodology_choice(requirements_text, chosen),
        "sources": methodology_sources,
    })

    # Equipo
    decision_log.append({
        "area": "team",
        "why": ["Cobertura completa de funciones", "Dimensionado por módulos y riesgos"],
        "sources": [
            {"autor": "Forsgren, Humble, Kim", "titulo": "Accelerate", "anio": 2018,
             "url": "https://itrevolution.com/accelerate/"},
            {"autor": "Skelton, Pais", "titulo": "Team Topologies", "anio": 2019,
             "url": "https://teamtopologies.com/"},
            {"autor": "DeMarco, Lister", "titulo": "Peopleware", "anio": 1999,
             "url": "https://www.oreilly.com/library/view/peopleware-productive-projects/9780133440707/"},
        ],
    })

    # Fases
    decision_log.append({
        "area": "phases",
        "why": ["Descubrimiento→Entrega para reducir incertidumbre", "Inspección/adaptación continua"],
        "sources": [
            {"autor": "Jeff Patton", "titulo": "User Story Mapping", "anio": 2014,
             "url": "http://jpattonassociates.com/user-story-mapping/"},
            {"autor": "Jez Humble, David Farley", "titulo": "Continuous Delivery", "anio": 2010,
             "url": "https://continuousdelivery.com/"},
            {"autor": "Schwaber, Sutherland", "titulo": "The Scrum Guide", "anio": 2020,
             "url": "https://scrumguides.org/"},
        ],
    })

    # Presupuesto
    decision_log.append({
        "area": "budget",
        "why": ["Estimación proporcional a personas×semanas×tarifa + contingencia"],
        "sources": [
            {"autor": "Steve McConnell", "titulo": "Software Estimation", "anio": 2006,
             "url": "https://www.construx.com/resources/software-estimation/"},
            {"autor": "Boehm", "titulo": "Cone of Uncertainty", "anio": 1981,
             "url": "https://en.wikipedia.org/wiki/Cone_of_Uncertainty"},
        ],
    })

    # Riesgos
    decision_log.append({
        "area": "risks",
        "why": ["Riesgos típicos de pagos/realtime/mobile/ML"],
        "sources": [
            {"autor": "OWASP", "titulo": "Web Security Testing Guide", "anio": 2021,
             "url": "https://owasp.org/www-project-wstg/"},
            {"autor": "PCI Council", "titulo": "PCI DSS", "anio": 2024,
             "url": "https://www.pcisecuritystandards.org/"},
        ],
    })

    return {
        "methodology": chosen,
        "methodology_score": score,
        "team": team,
        "phases": phases,
        "budget": budget,
        "risks": risks,
        "explanation": explain_methodology_choice(requirements_text, chosen),
        "decision_log": decision_log,
        "methodology_sources": methodology_sources,  # <-- clave para citar siempre
    }
