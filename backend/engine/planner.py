# backend/engine/planner.py
from typing import Dict, Any, List
import math

from backend.knowledge.methodologies import (
    recommend_methodology,
    explain_methodology_choice,
    METHODOLOGIES,
    detect_signals,
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

    # 2) Detectar señales de industria y necesidades técnicas
    signals = detect_signals(requirements_text)
    req = requirements_text.lower()
    
    # Necesidades técnicas específicas
    need_mobile = any(k in req for k in ["mobile", "móvil", "android", "ios", "app"]) or signals.get("mobile", 0.0) == 1.0
    need_admin  = any(k in req for k in ["admin", "backoffice", "panel", "administración", "administracion", "dashboard"])
    need_pay    = any(k in req for k in ["pago", "pagos", "stripe", "checkout", "pasarela"]) or signals.get("payments", 0.0) == 1.0
    need_realtime = signals.get("realtime", 0.0) == 1.0
    need_ml     = signals.get("ml_ai", 0.0) == 1.0
    need_iot    = signals.get("iot", 0.0) == 1.0
    need_high_availability = signals.get("high_availability", 0.0) == 1.0
    
    # Detectar industria/dominio
    is_fintech = signals.get("fintech", 0.0) == 1.0
    is_insurtech = signals.get("insurtech", 0.0) == 1.0
    is_healthtech = signals.get("healthtech", 0.0) == 1.0
    is_edtech = signals.get("edtech", 0.0) == 1.0
    is_logistics = signals.get("logistics", 0.0) == 1.0
    is_retail = signals.get("retail", 0.0) == 1.0
    is_travel = signals.get("travel", 0.0) == 1.0
    is_food_delivery = signals.get("food_delivery", 0.0) == 1.0
    is_gaming = signals.get("gaming", 0.0) == 1.0
    is_media = signals.get("media", 0.0) == 1.0
    is_erp = signals.get("erp", 0.0) == 1.0
    is_legal = signals.get("legal_tech", 0.0) == 1.0
    is_startup = signals.get("startup", 0.0) == 1.0
    is_enterprise = signals.get("large_org", 0.0) == 1.0
    
    # Equipo base
    team: List[Dict[str, Any]] = [
        {"role": "PM",           "count": 0.5},
        {"role": "Tech Lead",    "count": 0.5},
        {"role": "Backend Dev",  "count": 2.0},
        {"role": "Frontend Dev", "count": 1.0},
        {"role": "QA",           "count": 1.0},
        {"role": "UX/UI",        "count": 0.5},
    ]
    
    # Ajustes por necesidades técnicas
    if need_admin:
        team.append({"role": "Frontend Dev", "count": 0.5})
    if need_pay:
        team.append({"role": "Backend Dev", "count": 0.5})
    if need_ml:
        team.append({"role": "ML Engineer", "count": 0.5})
    if need_iot:
        team.append({"role": "IoT Engineer", "count": 0.5})
    if need_high_availability:
        team.append({"role": "DevOps", "count": 0.5})
    
    # Ajustes por industria crítica (más QA, seguridad, compliance)
    if is_fintech:
        team.append({"role": "QA", "count": 1.0})  # Doble QA
        team.append({"role": "Security Engineer", "count": 0.5})
        team.append({"role": "Compliance", "count": 0.25})
    elif is_insurtech:
        team.append({"role": "QA", "count": 0.5})
        team.append({"role": "Compliance", "count": 0.25})
    elif is_healthtech:
        team.append({"role": "QA", "count": 0.5})
        team.append({"role": "Security Engineer", "count": 0.5})
        team.append({"role": "HIPAA Compliance", "count": 0.25})
    elif is_legal:
        team.append({"role": "Security Engineer", "count": 0.5})
    
    # Ajustes por gaming/media (más DevOps)
    if is_gaming or is_media:
        team.append({"role": "DevOps", "count": 0.5})
        if is_gaming:
            team.append({"role": "Game Designer", "count": 0.5})
    
    # Ajustes por ERP/Enterprise (más PM, arquitecto)
    if is_erp or is_enterprise:
        team.append({"role": "PM", "count": 0.5})
        team.append({"role": "Architect", "count": 0.5})
        team.append({"role": "Backend Dev", "count": 1.0})
    
    # Ajustes por startup (reducir overhead)
    if is_startup and not is_enterprise:
        # Reducir PM y Tech Lead para startups
        for r in team:
            if r["role"] in ["PM", "Tech Lead"]:
                r["count"] = max(0.25, r["count"] - 0.25)

    # 3) Fases (ajustadas por metodología e industria)
    # Base de fases por metodología
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
    elif chosen == "SAFe":
        phases = [
            {"name": "Program Increment Planning", "weeks": 3},
            {"name": "PI Execution (5 sprints)", "weeks": 10},
            {"name": "Innovation & Planning", "weeks": 2},
            {"name": "Release & Deploy", "weeks": 1},
        ]
    else:
        phases = [
            {"name": "Discovery", "weeks": 2},
            {"name": "Implementación iterativa", "weeks": 6},
            {"name": "QA & Hardening", "weeks": 2},
            {"name": "Release & Handover", "weeks": 1},
        ]
    
    # Ajustar duración según industria/complejidad
    duration_multiplier = 1.0
    
    if is_erp or is_enterprise:
        duration_multiplier = 1.4  # +40% para enterprise
    elif is_fintech or is_healthtech or is_insurtech:
        duration_multiplier = 1.2  # +20% para industrias reguladas (más hardening)
    elif is_gaming and chosen == "DevOps":
        duration_multiplier = 0.9  # -10% para gaming con CI/CD (releases rápidos)
    elif is_startup and not (is_fintech or is_healthtech):
        duration_multiplier = 0.8  # -20% para startups (MVP rápido)
    
    # Aplicar multiplicador a todas las fases
    for phase in phases:
        phase["weeks"] = max(1, round(phase["weeks"] * duration_multiplier))

    # 4) Presupuesto dinámico por tarifa/rol ajustado por industria
    # Tarifas base por rol (EUR/semana)
    base_role_rates = {
        "PM": 1200.0, "Tech Lead": 1400.0,
        "Backend Dev": 1100.0, "Frontend Dev": 1000.0,
        "QA": 900.0, "UX/UI": 1000.0, "ML Engineer": 1400.0,
        "Security Engineer": 1500.0, "Compliance": 1300.0,
        "HIPAA Compliance": 1400.0, "DevOps": 1200.0,
        "IoT Engineer": 1300.0, "Game Designer": 1100.0,
        "Architect": 1500.0,
    }
    
    # Multiplicador de tarifas por industria
    rate_multiplier = 1.0
    industry_note = ""
    
    if is_fintech:
        rate_multiplier = 1.30  # +30% fintech (regulación, seguridad crítica)
        industry_note = "Fintech (regulación PCI-DSS, fraude, seguridad crítica)"
    elif is_insurtech:
        rate_multiplier = 1.25  # +25% insurtech (cálculos críticos, compliance)
        industry_note = "InsurTech (compliance, cálculos actuariales)"
    elif is_healthtech:
        rate_multiplier = 1.30  # +30% healthtech (HIPAA, datos sensibles)
        industry_note = "HealthTech (HIPAA, datos médicos sensibles)"
    elif is_legal:
        rate_multiplier = 1.20  # +20% legal (precisión crítica)
        industry_note = "LegalTech (precisión crítica en contratos)"
    elif is_gaming:
        rate_multiplier = 1.15  # +15% gaming (talento especializado)
        industry_note = "Gaming (talento especializado, game design)"
    elif is_media:
        rate_multiplier = 1.10  # +10% media (streaming, CDN)
        industry_note = "Media/Streaming (infraestructura CDN)"
    elif is_erp or is_enterprise:
        rate_multiplier = 1.12  # +12% enterprise (experiencia en sistemas complejos)
        industry_note = "Enterprise/ERP (sistemas complejos multi-módulo)"
    elif is_logistics or is_retail or is_travel:
        rate_multiplier = 0.95  # -5% (mercado competitivo)
        industry_note = "Logistics/Retail/Travel (mercado competitivo)"
    elif is_startup and not (is_fintech or is_healthtech):
        rate_multiplier = 0.90  # -10% startup (equity compensation)
        industry_note = "Startup (equity compensation, riesgo compartido)"
    
    # Aplicar multiplicador a tarifas
    role_rates = {role: rate * rate_multiplier for role, rate in base_role_rates.items()}
    
    project_weeks = sum(p["weeks"] for p in phases)
    by_role = {}
    for r in team:
        role = r["role"]; cnt = r["count"]
        rate = role_rates.get(role, 1000.0 * rate_multiplier)
        by_role.setdefault(role, 0.0)
        by_role[role] += cnt * project_weeks * rate

    labor = _round_money(sum(by_role.values()))
    
    # Contingencia ajustada: más alta para industrias críticas
    contingency_pct = 0.10  # 10% base
    if is_fintech or is_healthtech or is_insurtech:
        contingency_pct = 0.15  # 15% para industrias reguladas
    elif is_erp or is_enterprise:
        contingency_pct = 0.12  # 12% para enterprise
    elif is_startup:
        contingency_pct = 0.20  # 20% para startups (más incertidumbre)
    
    contingency = _round_money(contingency_pct * labor)
    total = _round_money(labor + contingency)

    budget = {
        "labor_estimate_eur": labor,
        "contingency_pct": f"{int(contingency_pct*100)}%",
        "contingency_eur": contingency,
        "total_eur": total,
        "by_role": by_role,
        "assumptions": {
            "project_weeks": project_weeks,
            "base_role_rates_eur_pw": base_role_rates,
            "industry_rate_multiplier": rate_multiplier,
            "industry_note": industry_note if industry_note else "Industria estándar",
            "contingency_pct": contingency_pct,
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
