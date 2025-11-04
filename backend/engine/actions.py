"""
Módulo para manejar las acciones sugeridas en el seguimiento de proyectos.

Cada handler acepta una `proposal` (dict) y devuelve un texto en Markdown.
Los handlers ahora incorporan adaptaciones por metodología y observaciones
en función del presupuesto cuando es relevante.
"""

from typing import Dict, Any, List, Optional
from datetime import datetime, date
import re

from backend.knowledge.methodologies import normalize_method_name, METHODOLOGIES


def _budget_brief(p: Dict[str, Any]) -> str:
    b = (p.get("budget") or {})
    total = b.get("total_eur")
    cont = float(((b.get("assumptions") or {}).get("contingency_pct", 0)))
    try:
        total_fmt = f"{float(total):,.2f} €".replace(",", "X").replace(".", ",").replace("X", ".") if total is not None else "(no estimado)"
    except Exception:
        total_fmt = str(total) or "(no estimado)"
    return f"Presupuesto estimado: {total_fmt} (contingencia {cont:.0f}%);"


def _method_intro(p: Dict[str, Any]) -> str:
    meth = p.get("methodology") or "(no definida)"
    info = METHODOLOGIES.get(normalize_method_name(meth), {})
    lines = [f"Metodología: {meth}", _budget_brief(p)]
    if info:
        pract = info.get("practicas") or []
        if pract:
            lines.append("Prácticas recomendadas: " + ", ".join(pract[:5]))
    return "\n".join(lines)


def handle_discovery_tasks(proposal: Dict[str, Any]) -> str:
    """Genera respuesta detallada para el desglose de tareas de Discovery,
    adaptada a la metodología y presupuesto del proyecto.
    """
    method = normalize_method_name(proposal.get("methodology") or "")
    team = proposal.get("team", [])
    phases = proposal.get("phases", [])

    discovery_phase = next((ph for ph in phases if "discover" in ph.get("name", "").lower() or "discovery" in ph.get("name", "").lower()), None)
    discovery_weeks = discovery_phase.get("weeks") if discovery_phase else 2

    out: List[str] = []
    out.append(_method_intro(proposal))
    out.append(f"## Plan detallado para la fase de Discovery ({discovery_weeks} semanas)")
    out.append("### Objetivos principales:")
    out += [
        "- Definir alcance y límites del proyecto",
        "- Identificar riesgos técnicos y de negocio",
        "- Establecer decisiones técnicas y arquitectura inicial (ADRs)",
        "- Crear backlog inicial y priorizar MVP"
    ]

    out.append("### Workshops y sesiones clave:")
    if method.lower() == "scrum":
        out += [
            "- Sprint 0 / Kick-off (1–2 semanas): alinear Product Backlog y Definition of Ready",
            "- Workshop de Priorización con PO y stakeholders",
            "- Sesión técnica: spike para riesgos críticos"
        ]
    elif method.lower() == "xp":
        out += [
            "- Kick-off técnico con prototipos rápidos y spikes TDD",
            "- Sesiones de pair-programming para validar enfoques técnicos"
        ]
    elif method.lower() == "kanban":
        out += [
            "- Taller de policies y entrada de trabajo para discovery",
            "- Mapear flujo de trabajo y dependencias"
        ]
    else:
        out += [
            "- Kick-off con stakeholders y equipo técnico",
            "- Workshop de historias de usuario y priorización"
        ]

    out.append("### Entregables esperados:")
    out += [
        "- Documento de visión y alcance",
        "- Backlog priorizado (historias con criterios de aceptación)",
        "- ADRs con decisiones técnicas críticas",
        "- Plan de releases y riesgos identificados"
    ]

    out.append("### Responsabilidades (según roles detectados):")
    for member in team:
        role = member.get("role", "").strip()
        if not role:
            continue
        if "pm" in role.lower() or role == "PM":
            out.append("- PM: lidera stakeholders, prioriza backlog y asegura decisiones de negocio")
        elif "tech" in role.lower() or "lead" in role.lower():
            out.append("- Tech Lead: define estrategia técnica, coordina spikes y ADRs")
        elif "backend" in role.lower():
            out.append("- Backend: analizar integraciones, APIs y requisitos no funcionales")
        elif "frontend" in role.lower():
            out.append("- Frontend: prototipado rápido, validar UX y componentes críticos")
        elif "qa" in role.lower():
            out.append("- QA: preparar criterios de aceptación y estrategia de pruebas desde el inicio")

    # Nota sobre ajuste a presupuesto
    b = proposal.get("budget", {})
    if b:
        out.append(f"\nNota: { _budget_brief(proposal) } Ajusta el alcance de Discovery si el presupuesto es limitado.")

    return "\n".join(out)


def handle_risk_analysis(proposal: Dict[str, Any]) -> str:
    """Genera análisis detallado de riesgos técnicos y mitigaciones adaptado a la metodología.
    """
    method = normalize_method_name(proposal.get("methodology") or "")
    risks = list(proposal.get("risks") or [])
    stack = proposal.get("stack") or {}
    team = proposal.get("team") or []

    out: List[str] = []
    out.append(_method_intro(proposal))
    out.append("## Análisis de riesgos técnicos — Prioridad y mitigación")

    # Señales comunes
    if any("payment" in str(r).lower() for r in risks) or any("payment" in str(v).lower() for v in stack.values() if isinstance(v, str)):
        out.append("### Riesgo: Procesamiento de pagos — alto impacto")
        out += [
            "- Mitigaciones: idempotencia, reconciliación diaria, pruebas end-to-end en entorno staging",
            "- Monitorización de tasas de error y alertas críticas"
        ]

    # Dependencias externas
    if stack:
        stext = ' '.join(str(v).lower() for v in stack.values() if isinstance(v, str))
        if "api" in stext or "integration" in stext:
            out.append("### Riesgo: Dependencias externas / integraciones")
            out += [
                "- Mitigaciones: contratos de API, mocks y tests de contrato (Pact/contract testing)",
                "- Introducir timeouts, retrys y circuit-breakers donde proceda"
            ]

    # Performance
    out.append("### Riesgo: Rendimiento y escalabilidad")
    out += [
        "- Mitigaciones: definir SLOs, benchmarks y pruebas de carga tempranas",
        "- Plan de capacity y métricas para detectar degradación"
    ]

    # Seguridad
    out.append("### Riesgo: Seguridad y compliance")
    out += [
        "- Mitigaciones: security reviews regulares, OWASP checklist, SAST/DAST en CI",
        "- Gestión de secretos y políticas de acceso"
    ]

    # Recomendaciones por metodología
    if method.lower() == "scrum":
        out.append("\nRecomendaciones (Scrum): revisar riesgos cada sprint, asignar owners y añadir mitigaciones en el backlog como stories o spikes.")
    elif method.lower() == "xp":
        out.append("\nRecomendaciones (XP): mitigar riesgos críticos mediante TDD, pair programming y spikes técnicos cortos.")
    elif method.lower() == "kanban":
        out.append("\nRecomendaciones (Kanban): visualizar riesgos en el tablero, limitar WIP en columnas críticas y priorizar mitigaciones por flujo.")

    # Si la propuesta incluía riesgos explícitos, listarlos y priorizarlos
    if risks:
        out.append("\nRiesgos detectados en la propuesta:")
        for r in risks:
            out.append(f"- {r} — Priorizar por impacto/probabilidad y asignar owner.")

    # Presupuesto — ajuste de mitigaciones si presupuesto limitado
    b = proposal.get("budget") or {}
    if b and b.get("total_eur"):
        total = float(b.get("total_eur", 0) or 0)
        if total < 20000:
            out.append("\nNota: presupuesto reducido — prioriza mitigaciones críticas (security, pagos) y usa spikes cortos en lugar de ampliaciones de equipo.")

    return "\n".join(out)


def handle_kpis_definition(proposal: Dict[str, Any]) -> str:
    """Define KPIs técnicos y de negocio para el proyecto, adaptados a la metodología."""
    method = normalize_method_name(proposal.get("methodology") or "")
    out: List[str] = []
    out.append(_method_intro(proposal))
    out.append("## KPIs recomendados — técnicos y de negocio")

    if method.lower() == "scrum":
        out += [
            "- Velocidad del equipo (historias completadas/sprint)",
            "- Sprint completion rate",
            "- Lead time por historia",
            "- Defect escape rate (bugs en producción)"
        ]
    elif method.lower() == "kanban":
        out += [
            "- Lead time y cycle time (por tipo de trabajo)",
            "- Throughput (items completados/semana)",
            "- WIP por columna"
        ]
    elif method.lower() == "xp":
        out += [
            "- Cobertura de tests",
            "- Tiempo medio de resolución de fallos",
            "- MTTR (Mean Time to Restore)"
        ]
    else:
        out += [
            "- Métricas de adopción: usuarios activos, retención",
            "- Métricas de calidad: bugs/semana, cobertura de tests",
            "- Métricas de entrega: lead time, deploy frequency"
        ]

    # KPIs de negocio si hay indicios de producto/transaccional
    if any("payment" in str(v).lower() for v in (proposal.get("requirements") or [])) or any("payment" in str(v).lower() for v in (proposal.get("stack") or {}).values() if isinstance(v, str)):
        out.append("\nKPIs transaccionales: tasa de conversión, tasa de error en pagos, tiempo medio por transacción")

    return "\n".join(out)


def handle_qa_plan(proposal: Dict[str, Any]) -> str:
    """Genera plan detallado de QA y testing adaptado a la metodología y presupuesto."""
    method = normalize_method_name(proposal.get("methodology") or "")
    out: List[str] = []
    out.append(_method_intro(proposal))
    out.append("## Plan de QA y estrategia de pruebas")

    if method.lower() == "xp":
        out += [
            "- TDD como práctica central; tests en cada commit",
            "- Pair programming y code review intensivo",
            "- Automatizar E2E y contract tests en CI"
        ]
    elif method.lower() == "scrum":
        out += [
            "- Integrar QA en el sprint: criterios de aceptación claros y Definition of Done",
            "- Automatización en CI para pruebas unitarias e integración",
            "- E2E en environment de staging previo a release"
        ]
    elif method.lower() == "kanban":
        out += [
            "- Pipeline continuo de pruebas: unit, integration y smoke tests",
            "- Gates de calidad en pasos del flujo para evitar regresiones"
        ]
    else:
        out += [
            "- Definir niveles de testing: unit/integration/e2e/performance/security",
            "- Integrar suites automáticas en CI"
        ]

    # Recomendación según presupuesto
    b = proposal.get("budget") or {}
    if b and float(b.get("total_eur", 0) or 0) < 30000:
        out.append("\nNota: con presupuesto limitado prioriza smoke tests y automatización mínima para flujos críticos; externaliza tests de performance si hace falta.")

    return "\n".join(out)


def handle_deployment_strategy(proposal: Dict[str, Any]) -> str:
    """Define estrategia de despliegue y CI/CD, adaptada a metodología y stack."""
    method = normalize_method_name(proposal.get("methodology") or "")
    stack = proposal.get("stack") or {}
    out: List[str] = []
    out.append(_method_intro(proposal))
    out.append("## Estrategia de despliegue y CI/CD")

    out += [
        "- Pipelines: build → test → security → deploy",
        "- Recomendado: deploy automatizado a staging y despliegue controlado a producción (canary/blue-green)",
        "- Monitoreo: métricas de error, latencia y uso de recursos"
    ]

    if any("kubernetes" in str(v).lower() for v in stack.values() if isinstance(v, str)):
        out.append("- Detalle: K8s → usa Helm/ArgoCD; define probes, HPA y network policies")

    if method.lower() == "safe":
        out.append("- En SAFe: coordina releases por Program Increments y documenta runbooks y rollback claramente.")

    if method.lower() == "devops":
        out.append("- Enfoque DevOps: infra as code, pipelines reproducibles y observabilidad como código.")

    return "\n".join(out)


def handle_deliverables(proposal: Dict[str, Any]) -> str:
    """Define entregables por fase del proyecto con adaptaciones por metodología."""
    method = normalize_method_name(proposal.get("methodology") or "")
    phases = proposal.get("phases") or []
    out: List[str] = []
    out.append(_method_intro(proposal))
    out.append("## Entregables por fase")

    for ph in phases:
        name = ph.get("name", "Fase")
        weeks = ph.get("weeks", "?")
        out.append(f"### {name} ({weeks} semanas)")
        out.append("#### Documentación mínima:")
        out.append("- Plan de la fase; criterios de aceptación; lista de riesgos")
        out.append("#### Código / Artefactos técnicos:")
        out.append("- Repositorio con tests básicos y CI configurado")

        lname = name.lower()
        if "discover" in lname or "discovery" in lname:
            out.append("- Documento de visión; backlog priorizado; ADRs")
        elif "sprint" in lname or "desarrollo" in lname:
            out.append("- Incremento funcional entregable; API docs; migration scripts")
        elif "qa" in lname or "hardening" in lname:
            out.append("- Reports de tests, coverage y resultados de performance")
        elif "deploy" in lname or "release" in lname:
            out.append("- Release notes, runbook de despliegue, checklist pre/post")

    return "\n".join(out)