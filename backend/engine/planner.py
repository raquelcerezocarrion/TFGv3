from typing import List, Dict, Any

def _choose_methodology(req: str) -> str:
    text = req.lower()
    if any(k in text for k in ["tiempo real", "flujo continuo", "operación 24/7", "operación continua"]):
        return "Kanban"
    if any(k in text for k in ["incertidumbre alta", "requisitos cambiantes", "experimentación", "mvp"]):
        return "Scrum"
    if any(k in text for k in ["mantenimiento", "equipo pequeño", "backlog estable"]):
        return "Kanban"
    return "Scrumban"

def generate_proposal(requirements: str) -> Dict[str, Any]:
    """
    Propuesta simple pero coherente (Parte 1 mejorada).
    En Parte 2 se sustituye por NN + optimización.
    """
    methodology = _choose_methodology(requirements)

    team = [
        {"role": "PM", "count": 1, "skills": ["gestión", "stakeholders", "riesgos"]},
        {"role": "Tech Lead", "count": 1, "skills": ["arquitectura", "devops"]},
        {"role": "Backend Dev", "count": 2, "skills": ["Python", "FastAPI"]},
        {"role": "Frontend Dev", "count": 1, "skills": ["React", "Vite", "Tailwind"]},
        {"role": "QA", "count": 1, "skills": ["pruebas", "automatización"]},
        {"role": "UX/UI", "count": 0.5, "skills": ["figma", "ux research"]},
    ]

    # Ajustes muy básicos por palabras clave
    text = requirements.lower()
    if "pagos" in text or "stripe" in text:
        team.append({"role": "Backend Dev (payments)", "count": 0.5, "skills": ["PCI", "pasarelas"]})
    if "panel" in text or "admin" in text:
        team.append({"role": "Frontend Dev (admin)", "count": 0.5, "skills": ["react", "charts"]})
    if "ml" in text or "ia" in text or "modelo" in text:
        team.append({"role": "ML Engineer", "count": 0.5, "skills": ["scikit-learn", "pytorch"]})

    phases: List[Dict[str, Any]] = [
        {"name": "Descubrimiento", "weeks": 1, "deliverables": ["Alcance", "Riesgos", "Plan"]},
        {"name": "Arquitectura y setup", "weeks": 1, "deliverables": ["CI/CD", "Infra básica"]},
        {"name": "Desarrollo iterativo", "weeks": 6, "deliverables": ["MVP", "Iteraciones"]},
        {"name": "QA & hardening", "weeks": 2, "deliverables": ["Pruebas", "Performance"]},
        {"name": "Despliegue & handover", "weeks": 1, "deliverables": ["Manual", "Formación"]},
    ]

    # Presupuesto simplificado
    team_total_heads = sum(t["count"] for t in team)
    weeks = sum(p["weeks"] for p in phases)
    # tarifa media estimada (€/semana por persona)
    rate = 1200.0
    labor = team_total_heads * weeks * rate
    contingency = round(labor * 0.1, 2)
    total = round(labor + contingency, 2)

    budget = {
        "labor_estimate_eur": round(labor, 2),
        "contingency_10pct": contingency,
        "total_eur": total
    }

    risks = [
        "Cambios de alcance sin control de versiones",
        "Dependencias externas (APIs/pagos) con latencias",
        "Falta de datos reales para pruebas de carga",
    ]

    explanation = [
        f"Metodología '{methodology}' elegida por naturaleza del trabajo descrito.",
        "Equipo dimensionado en función de módulos detectados en los requisitos.",
        "Presupuesto calculado con tarifa media y 10% de contingencia.",
    ]

    return {
        "methodology": methodology,
        "team": team,
        "phases": phases,
        "budget": budget,
        "risks": risks,
        "explanation": explanation,
    }
