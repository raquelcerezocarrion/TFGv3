# backend/knowledge/methodologies.py
# Conocimiento “humano” sobre metodologías + reglas de decisión explicables
from __future__ import annotations
from typing import Dict, List, Tuple
import re

def _norm(s: str) -> str:
    return s.lower().strip()

# --- Catálogo de metodologías: visión, cuándo conviene, riesgos, prácticas, fuentes ---
METHODOLOGIES: Dict[str, Dict] = {
    "Scrum": {
        "vision": "Marco para gestionar complejidad mediante inspección y adaptación en iteraciones cortas.",
        "mejor_si": [
            "Requisitos cambiantes, descubrimiento de producto y MVP",
            "Alto contacto con stakeholders y feedback frecuente"
        ],
        "evitar_si": [
            "Plazos y alcance rígidos sin margen de negociación",
            "Necesidad de operación 24/7 con interrupciones constantes"
        ],
        "practicas": ["Sprints", "Daily", "Review", "Retros", "Product Backlog", "Definition of Done"],
        "riesgos": ["Scope creep si no hay DoR/DoD claros", "Ritualismo sin foco en valor"],
        "fuentes": [
            {
                "autor": "Ken Schwaber & Jeff Sutherland",
                "titulo": "The Scrum Guide (2020)",
                "anio": 2020,
                "url": "https://scrumguides.org/docs/scrumguide/v2020/2020-Scrum-Guide-US.pdf"
            }
        ]
    },
    "Kanban": {
        "vision": "Método evolutivo para mejorar flujo, limitar WIP y acortar tiempos de entrega.",
        "mejor_si": [
            "Operación/soporte 24x7, trabajo de tamaño variable e interrupciones",
            "Necesidad de visualizar cuellos de botella y mejorar lead time"
        ],
        "evitar_si": ["Se requieren compromisos por sprint/fecha fija estricta"],
        "practicas": ["Tablero de flujo", "Límites WIP", "Lead/Cycle time", "Políticas explícitas"],
        "riesgos": ["Si no se respetan WIP → multitarea y bloqueos", "Falta de cadencia si el contexto la exige"],
        "fuentes": [
            {
                "autor": "David J. Anderson",
                "titulo": "Kanban: Successful Evolutionary Change for Your Technology Business",
                "anio": 2010,
                "url": "https://books.google.com/books/about/Kanban.html?id=RJ0VUkfUWZkC"
            },
            {
                "autor": "David J. Anderson",
                "titulo": "Principles and General Practices of Kanban",
                "anio": 2019,
                "url": "https://djaa.com/revisiting-the-principles-and-general-practices-of-the-kanban-method/"
            }
        ]
    },
    "Scrumban": {
        "vision": "Híbrido: planificación ligera de Scrum + control de flujo de Kanban.",
        "mejor_si": [
            "Mezcla de desarrollo nuevo + mantenimiento/soporte",
            "Cambios frecuentes sin perder visibilidad del flujo"
        ],
        "evitar_si": ["Contextos que exigen gobernanza pesada/escala corporativa formal"],
        "practicas": ["Backlog ligero", "Tablero con WIP", "Revisiones periódicas"],
        "riesgos": ["Ambigüedad de cadencia si no se define una mínima"],
        "fuentes": [
            {
                "autor": "Corey Ladas",
                "titulo": "Scrumban",
                "anio": 2009,
                "url": "https://leansoftwareengineering.com/ksse/scrumban/"
            }
        ]
    },
    "XP": {  # Extreme Programming
        "vision": "Prácticas técnicas que elevan la calidad y la velocidad con seguridad.",
        "mejor_si": ["Calidad/fiabilidad crítica (pagos/seguridad/tiempo real)", "Necesidad de feedback técnico muy rápido"],
        "evitar_si": ["Organizaciones que no aceptan prácticas técnicas intensivas"],
        "practicas": ["TDD", "Pair Programming", "Refactorización continua", "Integración Continua"],
        "riesgos": ["Requiere disciplina y cultura de ingeniería madura"],
        "fuentes": [
            {
                "autor": "Kent Beck",
                "titulo": "Extreme Programming Explained (2nd ed.)",
                "anio": 2004,
                "url": "https://ptgmedia.pearsoncmg.com/images/9780321278654/samplepages/9780321278654.pdf"
            }
        ]
    },
    "Lean": {
        "vision": "Eliminar desperdicio y acelerar aprendizaje (Construir–Medir–Aprender).",
        "mejor_si": ["Hipótesis de negocio con alta incertidumbre (producto/mercado)"],
        "evitar_si": ["Gobernanza rígida que impide iteraciones y experimentación"],
        "practicas": ["MVP", "Métricas accionables", "Kaizen", "Mapas de valor"],
        "riesgos": ["Mala interpretación de MVP → calidad insuficiente"],
        "fuentes": [
            {
                "autor": "Mary & Tom Poppendieck",
                "titulo": "Lean Software Development: An Agile Toolkit",
                "anio": 2003,
                "url": "https://ptgmedia.pearsoncmg.com/images/9780321150783/samplepages/0321150783.pdf"
            },
            {
                "autor": "Eric Ries",
                "titulo": "The Lean Startup",
                "anio": 2011,
                "url": "https://en.wikipedia.org/wiki/The_Lean_Startup"
            }
        ]
    },
    "Crystal": {
        "vision": "Familia de procesos ligeros centrados en personas y comunicación.",
        "mejor_si": ["Equipos pequeños, riesgo moderado, alta comunicación directa"],
        "evitar_si": ["Necesidad de escalado o coordinación multi-equipo formal"],
        "practicas": ["Ajuste del proceso según tamaño y criticidad", "Énfasis en comunicación"],
        "riesgos": ["Poca estructura para contextos complejos o regulados"],
        "fuentes": [
            {
                "autor": "Alistair Cockburn",
                "titulo": "Crystal Clear",
                "anio": 2004,
                "url": "https://www.amazon.com/Books-Alistair-Cockburn/s?rh=n%3A283155%2Cp_27%3AAlistair%2BCockburn"
            }
        ]
    },
    "FDD": {  # Feature-Driven Development
        "vision": "Planificación y entrega orientadas a 'features' con modelado de dominio.",
        "mejor_si": ["Dominios con muchas funcionalidades discretas y claras"],
        "evitar_si": ["Altísima incertidumbre o descubrimiento de producto"],
        "practicas": ["Lista de features", "Plan por feature", "Diseño por feature"],
        "riesgos": ["Puede ser rígido si el alcance cambia continuamente"],
        "fuentes": [
            {
                "autor": "Jeff De Luca & Peter Coad",
                "titulo": "FDD (entrevista/historia)",
                "anio": 1997,
                "url": "https://www.it-agile.de/fileadmin/docs/FDD-Interview_en_final.pdf"
            },
            {
                "autor": "Major Seminar",
                "titulo": "Major Seminar on FDD (resumen académico)",
                "anio": 2003,
                "url": "https://csis.pace.edu/~marchese/CS616/Agile/FDD/fdd.pdf"
            }
        ]
    },
    "DSDM": {
        "vision": "Timeboxing fuerte con alcance negociable; énfasis en gobernanza.",
        "mejor_si": ["Plazo y presupuesto fijos; priorización MoSCoW; negocio muy implicado"],
        "evitar_si": ["Alcance 100% innegociable sin flexibilidad"],
        "practicas": ["Timeboxes", "MoSCoW", "Colaboración intensiva del negocio"],
        "riesgos": ["Necesita compromiso fuerte del negocio en priorización"],
        "fuentes": [
            {
                "autor": "Agile Business Consortium",
                "titulo": "DSDM Agile Project Framework",
                "anio": 2014,
                "url": "https://www.agilebusiness.org/business-agility/what-is-dsdm.html"
            }
        ]
    },
    "SAFe": {
        "vision": "Marco para escalar Agile con coordinación a nivel programa/portafolio.",
        "mejor_si": ["Múltiples equipos/áreas, coordinación corporativa, cumplimiento/regulación"],
        "evitar_si": ["Proyectos pequeños de un solo equipo (sobrecoste)"],
        "practicas": ["Program Increments", "ARTs", "Lean-Agile Mindset"],
        "riesgos": ["Sobrecarga de procesos si el contexto no lo requiere"],
        "fuentes": [
            {
                "autor": "Scaled Agile, Inc. (Dean Leffingwell y otros)",
                "titulo": "Scaled Agile Framework (SAFe)",
                "anio": 2023,
                "url": "https://framework.scaledagile.com/about/"
            }
        ]
    },
    "DevOps": {
        "vision": "Prácticas para acelerar flujo, feedback y aprendizaje en entrega de software.",
        "mejor_si": ["Despliegues frecuentes, fiabilidad y seguridad; integración continua"],
        "evitar_si": ["N/A: DevOps se combina con Scrum/Kanban/SAFe"],
        "practicas": ["CI/CD", "Infra as Code", "Observabilidad", "Shift-left de seguridad"],
        "riesgos": ["Requiere inversión cultural y técnica sostenida"],
        "fuentes": [
            {
                "autor": "Nicole Forsgren, Jez Humble, Gene Kim",
                "titulo": "Accelerate",
                "anio": 2018,
                "url": "https://itrevolution.com/product/accelerate/"
            },
            {
                "autor": "Gene Kim, Jez Humble, Patrick Debois, John Willis; N. Forsgren (2ª ed.)",
                "titulo": "The DevOps Handbook (Second Edition)",
                "anio": 2021,
                "url": "https://itrevolution.com/product/the-devops-handbook-second-edition/"
            }
        ]
    }
}

# Sinónimos aceptados
SYNONYMS = {
    "extreme programming": "XP",
    "xp": "XP",
    "scrumban": "Scrumban",
    "lean startup": "Lean",
    "crystal clear": "Crystal",
    "feature driven development": "FDD",
    "fdd": "FDD",
    "dsdm": "DSDM",
    "safe": "SAFe",
    "scaled agile": "SAFe",
}

def normalize_method_name(name: str) -> str:
    t = _norm(name)
    return SYNONYMS.get(t, name.strip().title() if t not in SYNONYMS else SYNONYMS[t])

# Señales desde requisitos
def detect_signals(text: str) -> Dict[str, float]:
    t = _norm(text)
    def has(*words): return any(w in t for w in words)
    return {
        "uncertainty": 1.0 if has("incertidumbre","cambiante","mvp","hipótesis","descubrimiento","prototipo") else 0.0,
        "ops_flow": 1.0 if has("operación","soporte","24/7","flujo continuo","incidencias","tickets") else 0.0,
        "fixed_deadline": 1.0 if has("fecha límite","plazo fijo","deadline") else 0.0,
        "fixed_budget": 1.0 if has("presupuesto fijo","tope de presupuesto","coste cerrado") else 0.0,
        "regulated": 1.0 if has("pci","gdpr","hipaa","iso 27001","regulado","auditor") else 0.0,
        "realtime": 1.0 if has("tiempo real","realtime","websocket","baja latencia") else 0.0,
        "payments": 1.0 if has("pagos","stripe","redsys","paypal") else 0.0,
        "integrations": 1.0 if has("api","apis","webhook","integración") else 0.0,
        "mobile": 1.0 if has("app","android","ios","móvil","mobile") else 0.0,
        "ml_ai": 1.0 if has("ml","machine learning","ia","modelo") else 0.0,
        "large_org": 1.0 if has("varios equipos","escala","portafolio","program increment","safe") else 0.0,
        "many_features": 1.0 if has("módulos","features","catálogo","muchas funcionalidades") else 0.0,
        "quality_critical": 1.0 if has("seguridad","fraude","crítico","alta calidad","tdd") else 0.0,
        "small_project": 1.0 if has("proyecto pequeño","alcance reducido","equipo pequeño") else 0.0,
    }

# Puntuación explicable por metodología (reglas sencillas)
def score_methodologies(text: str) -> List[Tuple[str, float, List[str]]]:
    s = detect_signals(text)
    out: List[Tuple[str, float, List[str]]] = []

    def add(name: str, base: float, rules: List[Tuple[bool, float, str]]):
        score = base; why: List[str] = []
        for cond, w, msg in rules:
            if cond:
                score += w; why.append(msg)
        out.append((name, round(score, 2), why))

    add("Scrum", 0.0, [
        (s["uncertainty"]==1.0, +2.0, "Requisitos cambiantes/descubrimiento"),
        (s["ml_ai"]==1.0, +0.5, "Prototipos/validación iterativa"),
        (s["fixed_deadline"]==1.0, -0.8, "Plazo rígido reduce flexibilidad"),
        (s["ops_flow"]==1.0, -0.5, "Operación 24/7 encaja mejor con Kanban")
    ])
    add("Kanban", 0.0, [
        (s["ops_flow"]==1.0, +2.0, "Operación/soporte con flujo continuo"),
        (s["realtime"]==1.0, +0.7, "Lead time corto con variabilidad"),
        (s["fixed_deadline"]==1.0, -0.4, "Fechas rígidas piden timeboxing")
    ])
    add("Scrumban", 0.0, [
        (s["uncertainty"]==1.0 and s["ops_flow"]==1.0, +2.0, "Mix desarrollo+operación"),
        (s["uncertainty"]==1.0 and s["ops_flow"]==0.0, +0.8, "Cambios frecuentes con control de flujo"),
        (s["ops_flow"]==1.0 and s["uncertainty"]==0.0, +0.6, "WIP + planificación ligera")
    ])
    add("XP", 0.0, [
        (s["quality_critical"]==1.0, +2.0, "Calidad/fiabilidad crítica"),
        (s["payments"]==1.0 or s["realtime"]==1.0, +1.0, "Dominios sensibles"),
    ])
    add("Lean", 0.0, [
        (s["uncertainty"]==1.0, +1.5, "Hipótesis y aprendizaje"),
        (s["small_project"]==1.0, +0.3, "Experimentación ligera")
    ])
    add("Crystal", 0.0, [
        (s["small_project"]==1.0, +1.0, "Equipos pequeños, foco en personas")
    ])
    add("FDD", 0.0, [
        (s["many_features"]==1.0, +1.2, "Dominio modelable por features"),
        (s["uncertainty"]==1.0, -0.5, "Descubrimiento continuo no encaja")
    ])
    add("DSDM", 0.0, [
        (s["fixed_deadline"]==1.0 or s["fixed_budget"]==1.0, +2.0, "Timeboxing y alcance negociable"),
        (s["regulated"]==1.0, +0.5, "Más gobernanza")
    ])
    add("SAFe", 0.0, [
        (s["large_org"]==1.0, +2.0, "Coordinación multi-equipo/portafolio"),
        (s["regulated"]==1.0, +0.5, "Necesidad de gobernanza")
    ])
    add("DevOps", 0.0, [
        (s["integrations"]==1.0 or s["realtime"]==1.0, +0.5, "Despliegues y feedback continuos"),
        (True, +0.3, "Prácticas compatibles con Scrum/Kanban/SAFe")
    ])

    out.sort(key=lambda x: x[1], reverse=True)
    return out

def explain_methodology_choice(text: str, method: str) -> List[str]:
    m = METHODOLOGIES.get(method, {})
    signals = detect_signals(text)
    lines: List[str] = []
    if m.get("vision"): lines.append(f"Visión: {m['vision']}")
    if m.get("mejor_si"):
        lines.append("Encaja bien si: " + "; ".join(m["mejor_si"]))
    if m.get("evitar_si"):
        lines.append("Evitar si: " + "; ".join(m["evitar_si"]))
    if m.get("practicas"):
        lines.append("Prácticas clave: " + ", ".join(m["practicas"]))
    if m.get("riesgos"):
        lines.append("Riesgos a vigilar: " + "; ".join(m["riesgos"]))
    hits = [k for k, v in signals.items() if v == 1.0]
    if hits:
        lines.append("Señales detectadas en tus requisitos: " + ", ".join(hits))
    return lines

def compare_methods(best: str, other: str) -> List[str]:
    b = METHODOLOGIES.get(best, {}); o = METHODOLOGIES.get(other, {})
    out: List[str] = [f"Comparativa {best} vs {other}:"]
    if b.get("mejor_si") and o.get("mejor_si"):
        out.append(f"- {best} destaca en: " + "; ".join(b["mejor_si"]))
        out.append(f"- {other} destaca en: " + "; ".join(o["mejor_si"]))
    if b.get("riesgos") and o.get("riesgos"):
        out.append(f"- Riesgos de {best}: " + "; ".join(b["riesgos"]))
        out.append(f"- Riesgos de {other}: " + "; ".join(o["riesgos"]))
    return out

def get_method_sources(method: str) -> List[Dict[str, str | int]]:
    return list(METHODOLOGIES.get(method, {}).get("fuentes", []))

def recommend_methodology(text: str) -> Tuple[str, List[str], List[Tuple[str,float,List[str]]]]:
    scored = score_methodologies(text)
    best = scored[0][0]
    why = explain_methodology_choice(text, best)
    return best, why, scored


# --- Fases concretas por metodología: conocimiento detallado requerido por el asistente ---
METHODOLOGY_PHASES: Dict[str, List[Dict]] = {
    "Scrum": [
        {
            "name": "Incepción & Plan de Releases",
            "summary": "Alineación inicial: visión, alcance del MVP, roadmap de releases y criterios de éxito.",
            "goals": ["Validar hipótesis principales del producto", "Definir releases y versiones iniciales", "Establecer equipo y ceremonias"],
            "typical_weeks": 1,
            "checklist": [
                "Workshop de visión con stakeholder",
                "Definir métricas de éxito (KPIs)",
                "Crear backlog inicial y priorizar epics",
                "Asignar roles: PO, SM, equipo dev"
            ],
                "practices": [
                    "Facilitar un workshop de 2h para alinear visión y formular hypotheses claras (3 hipótesis máximo)",
                    "Definir 3 KPIs principales y una métrica leading para cada uno (ej. conversión, retención, tiempo de respuesta)",
                    "Mapear dependencias técnicas y externas en un board visual (Miro/Confluence)",
                    "Crear backlog inicial con épicas + 5 historias de prioridad alta para primer sprint"
                ],
            "common_issues": [
                "Expectativas vagas del negocio sobre alcance",
                "Falta de compromiso de stakeholders para prioridades"
            ],
            "mitigations": [
                "Documentar acuerdos mínimos para MVP",
                "Acordar cadencia de refinamiento semanal con stakeholders"
            ],
            "roles_responsibilities": {
                "Product Owner": "Priorizar backlog y representar al negocio",
                "Scrum Master": "Facilitar ceremonias y remover impedimentos",
                "Equipo": "Estimación y compromisos técnicos"
            },
            "kpis": ["Lead time del backlog inicial", "% historias listas para primer sprint", "Tasa de aceptación de stakeholders"],
            "deliverables": ["Backlog priorizado", "Roadmap de releases", "Definition of Done inicial"],
            "questions_to_ask": [
                "¿Cuáles son las 3 hipótesis más críticas que debemos validar?",
                "¿Qué criterio definirá si el MVP es un éxito?",
                "¿Quién será responsable de decisiones sobre alcance en cada release?"
            ]
        },
        {
            "name": "Sprints / Desarrollo iterativo",
            "summary": "Ciclos regulares de trabajo donde se entrega incrementos de producto cada sprint.",
            "goals": ["Entregar incrementos con valor probado", "Mantener ritmo sostenible"],
            "typical_weeks": 2,
            "checklist": ["Sprint Planning efectivo", "Definition of Ready/Done aplicada", "Daily standups", "Revisión y demo al final de sprint"],
            "common_issues": ["Historias demasiado grandes (no se completan)", "Falta de criterio DoD consistente"],
            "mitigations": ["Dividir historias y usar Definition of Ready", "Automatizar tests y CI para cumplir DoD"],
            "roles_responsibilities": {"PO":"Preparar/refinar backlog","Equipo":"Entregar incrementos","SM":"Proteger al equipo de interrupciones"},
            "kpis": ["Velocity (historia puntos) por sprint", "% historias completadas vs comprometidas", "Defect escape rate"],
            "deliverables": ["Incremento potencialmente desplegable", "Reporte de sprint (learnings)"],
            "questions_to_ask": ["¿Qué impedimentos frecuentes están bloqueando el flujo?","¿Las historias cumplen DoR/DoD?","¿Qué automatizaciones faltan para garantizar calidad?"]
            ,
            "practices": [
                "Durante el Sprint Planning: descomponer épicas en historias de 1–3 días y asignar criterios de aceptación claros",
                "Daily: foco en impedimentos; el Scrum Master registra y asigna owners a cada impedimento con SLA de 48h",
                "Pull request + code review: regla mínima 1 revisor y test unitario asociado para cada PR",
                "Pipeline CI: fallo bloqueante para merge si los tests críticos fallan; automatizar smoke tests en staging"
            ],
        },
        {
            "name": "Hardening & Pruebas de aceptación",
            "summary": "Fase focalizada en asegurar que el sistema cumple requisitos no funcionales y criterios de aceptación antes del release.",
            "goals": ["Asegurar calidad de producción", "Completar pruebas de integración y aceptación"],
            "checklist": ["Pruebas de integración y e2e", "Pruebas de rendimiento básicas", "Pruebas de seguridad/pentest si procede"],
            "common_issues": ["Bugs críticos detectados tarde", "Inestabilidad en entornos de staging"],
            "mitigations": ["Establecer pipelines de CI con entornos reproducibles", "Definir criterios de exit para pruebas de carga"],
            "roles_responsibilities": {"QA":"Diseñar y ejecutar pruebas","DevOps":"Entornos reproducibles","PO":"Firmar criterios de aceptación"},
            "kpis": ["Tiempo medio para resolver regresiones", "% pruebas automatizadas"],
            "deliverables": ["Informe de pruebas", "Checklist de readiness para release"],
            "questions_to_ask": ["¿Qué fallos críticos quedan?","¿Tenemos métricas de rendimiento aceptables?","¿La automatización cubre escenarios críticos?"]
            ,
            "practices": [
                "Priorizar bugs por severidad: bloquear release si hay 1 bug crítico no resuelto",
                "Ejecutar suites e2e automatizadas nightly y revisar fallos al inicio del día",
                "Definir gates de performance: p95 respuesta < X ms, CPU/memory thresholds para pasar a release",
                "Simular cargas básicas en staging y documentar resultados en el informe de pruebas"
            ],
        },
        {
            "name": "Release & Handover",
            "summary": "Despliegue al entorno de producción con comunicación y documentación para operaciones.",
            "goals": ["Desplegar con mínimo riesgo", "Asegurar monitoring y rollback"],
            "checklist": ["Plan de despliegue y rollback", "Runbook para operaciones", "Verificación post-deploy"],
            "common_issues": ["Falta de observabilidad en producción", "Ausencia de plan de rollback"],
            "mitigations": ["Implementar dashboards y alertas", "Procedimientos de rollback ensayados"],
            "roles_responsibilities": {"DevOps":"Ejecutar despliegue","Equipo":"Verificación post-release","PO":"Comunicación a stakeholders"},
            "kpis": ["MTTR post-release", "% deployments con rollback"],
            "deliverables": ["Deployment artefacts", "Runbooks", "Report post-release"],
            "questions_to_ask": ["¿Cuál es el plan de rollback?","¿Qué alertas monitorizaremos tras el release?","¿Quién actúa en primera línea ante incidentes?"]
            ,
            "practices": [
                "Ejecutar un despliegue canario o por feature flags para minimizar blast radius",
                "Probar rollback en staging y documentar pasos con tiempos estimados",
                "Comprobar dashboards y establecer alertas principales (errores 5xx, latencia, saturación de cola)",
                "Realizar verificación post-release en 30/60/120 minutos y reportar estado al PO/operaciones"
            ]
        }
    ],
    "Kanban": [
        {
            "name": "Discovery & Prioritización",
            "summary": "Definir y priorizar ítems (tickets) para alimentar el flujo continuo.",
            "goals": ["Asegurar políticas claras de prioridad", "Tamaño de trabajo adecuado para flujo"],
            "checklist": ["Definir políticas explícitas de entrada", "Sizing/estimation ligero", "Definir límites WIP iniciales"],
            "common_issues": ["WIP excesivo", "Bloqueos no visibles"],
            "mitigations": ["Aplicar límites WIP y políticas de bloqueo","Daily board review para detectar cuellos de botella"],
            "roles_responsibilities": {"Flow Manager/Service Delivery Manager":"Monitorizar flujo","Equipo":"Reducir trabajo en curso"},
            "kpis": ["Lead time", "Cycle time", "Throughput"],
            "deliverables": ["Policies document", "Board con columnas claras"],
            "questions_to_ask": ["¿Dónde están los cuellos de botella actuales?","¿Qué tareas son candidatos a reducir o dividir?"]
        },
        {
            "name": "Ejecución & Entrega continua",
            "summary": "Flujo de trabajo con foco en minimizar tiempos de espera y sacar trabajo con calidad.",
            "goals": ["Reducir lead time", "Mantener throughput estable"],
            "checklist": ["Respetar límites WIP","Definir políticas de pull","Automatizar integración/entrega"],
            "common_issues": ["Multitarea por exceso de WIP","Falta de definición de 'Done'"],
            "mitigations": ["Reducir WIP y estabilizar políticas","Establecer DoD mínimo aplicable"],
            "roles_responsibilities": {"Equipo":"Pull de tareas","Manager":"Remover impedimentos"},
            "kpis": ["Avg lead time", "WIP by column", "Blocked time"],
            "deliverables": ["Work items entregados constantemente"],
            "questions_to_ask": ["¿Qué políticas WIP actuales están fallando?","¿Qué tareas se bloquean con frecuencia?"]
        }
    ],
    "SAFe": [
        {
            "name": "PI Planning (Program Increment)",
            "summary": "Planificación a nivel programa donde equipos sincronizan objetivos para el siguiente PI.",
            "goals": ["Alinear dependencias multi-equipo", "Definir objetivos del PI"],
            "checklist": ["Identificar dependencias", "Asignar features a ARTs", "Definir objetivos SMART por equipo"],
            "common_issues": ["Dependencias ocultas", "Objetivos demasiado optimistas"],
            "mitigations": ["Mapear dependencias y mitigaciones","Conservar buffer para incertidumbres"],
            "roles_responsibilities": {"RTE":"Facilitar PI","PO/PM":"Priorizar features"},
            "kpis": ["% objetivos PI cumplidos", "Número de dependencias mitigadas"],
            "deliverables": ["Objectives by team", "Program board with dependencies"],
            "questions_to_ask": ["¿Qué dependencias críticas existen entre equipos?","¿Qué riesgos impactan el PI?"]
        },
        {
            "name": "Iterations & System Demo",
            "summary": "Iteraciones regulares con demos integradas que muestran progreso al sistema nivel.",
            "goals": ["Mostrar progreso integrado", "Recibir feedback temprano"],
            "checklist": ["Planificación de iteración","Demo integrada al final de iteración"],
            "common_issues": ["Integraciones fallidas al final de iteración"],
            "mitigations": ["Pruebas de integración continuas","Controles automatizados en CI"]
        }
    ],
    "Devops": [
        {
            "name": "Build & CI",
            "summary": "Compilar, testear y validar artefactos automáticamente en cada cambio.",
            "goals": ["Detección temprana de errores", "Mantener artefactos fiables"],
            "checklist": ["Pipelines CI robustos","Tests unitarios y de integración automatizados","Quality gates (lint, security scans)"],
            "common_issues": ["Pipelines frágiles o lentos","Falsos positivos en tests"],
            "mitigations": ["Optimizar pipelines y cacheo","Flake handling y tests determinísticos"]
        },
        {
            "name": "Deploy & CD",
            "summary": "Entregar artefactos a entornos automáticamente con estrategias seguras (canary, blue/green).",
            "goals": ["Despliegues repetibles y reversibles", "Reducir riesgo en producción"],
            "checklist": ["Estrategia de despliegue definida","Rollback probado","Observabilidad configurada"],
            "common_issues": ["Despliegues manuales error-prone","Ausencia de rollback"],
            "mitigations": ["Automatizar despliegues","Definir runbooks y playbooks de rollback"]
        },
        {
            "name": "Operate & Observe",
            "summary": "Monitorizar, alertar y reaccionar ante incidentes en producción; retroalimentar al desarrollo.",
            "goals": ["Detectar y resolver incidentes rápido", "Aprender de fallos"],
            "checklist": ["Dashboards críticos","SLA/SLI definidos","Procedimientos de respuesta a incidentes"],
            "common_issues": ["Ruido de alertas", "Falta de runbooks"],
            "mitigations": ["Tuning de alertas","Playbooks claros y entrenamiento de on-call"]
        }
    ],
    "Scrumban": [
        {
            "name": "Preparación & Políticas",
            "summary": "Definir mezcla de cadencia y límites de flujo: qué prácticas de Scrum se mantienen y cómo se aplica WIP.",
            "goals": ["Acordar cadencia mínima (planning/review)", "Definir límites WIP y políticas de pull"],
            "typical_weeks": 1,
            "checklist": ["Documentar políticas de entrada/salida","Acordar longitud de 'mini-sprints' si aplica","Definir WIP por columna"],
            "common_issues": ["Confusión entre sprints y flujo continuo","No respetar límites WIP"],
            "mitigations": ["Protocolizar políticas y revisarlas en retros","Visualizar métricas de WIP/Lead time"],
            "roles_responsibilities": {"Product Owner":"Mantener backlog y prioridades","Flow Manager":"Monitorizar flujo y remover impedimentos"},
            "kpis": ["Lead time medio","WIP por columna"],
            "deliverables": ["Policies doc","Board inicial con columnas y WIP"],
            "questions_to_ask": ["¿Qué partes del proceso deben tener cadencia fija?","¿Qué límites WIP proponemos por columna?"]
        },
        {
            "name": "Ejecución híbrida",
            "summary": "Combina sprints cortos para nuevas entregas con flujo continuo para mantenimiento/soporte.",
            "goals": ["Mantener ritmo de entrega para nuevas features","Asegurar respuesta rápida a incidencias"],
            "typical_weeks": 2,
            "checklist": ["Alinear backlog entre pull y sprint items","Tener políticas claras de prioridad para hotfixes"],
            "common_issues": ["Conflicto entre items de soporte y sprint planificado"],
            "mitigations": ["Reservar capacidad para soporte","Usar swimlanes para separar tipos de trabajo"],
            "roles_responsibilities": {"Equipo":"Gestionar pull y sprint commitments","PO":"Priorizar entre mantenimiento y nuevas features"},
            "kpis": ["Throughput por tipo de trabajo","Tiempo medio de resolución de incidentes"],
            "deliverables": ["Incrementos entregados","Lista de incidencias resueltas"],
            "questions_to_ask": ["¿Cuánta capacidad reservar para soporte?","¿Qué criterios definen un hotfix vs trabajo planeado?"]
        }
    ],
    "XP": [
        {
            "name": "Exploración técnica & Setup",
            "summary": "Establecer prácticas técnicas (TDD, CI) y acuerdos de trabajo colaborativo antes de empezar la entrega intensiva.",
            "goals": ["Poner en marcha pipelines y tests","Acordar pair programming y definition of done técnica"],
            "typical_weeks": 1,
            "checklist": ["Configurar CI/CD","Escribir primeros tests de arquitectura","Acordar prácticas de pair/TDD"],
            "common_issues": ["Resistencia a TDD","Pipelines incompletos"],
            "mitigations": ["Capacitación inicial","Tracking de cobertura y calidad"],
            "roles_responsibilities": {"Equipo":"Practicar TDD/Refactor continuo","Tech Lead":"Facilitar decisiones técnicas"},
            "kpis": ["Cobertura de tests","Defect density por release"],
            "deliverables": ["Pipelines funcionales","Suites de tests iniciales"],
            "questions_to_ask": ["¿Qué criterios técnicos consideramos 'aceptable' para integrar?","¿Qué cobertura mínima queremos para cada módulo?"]
        },
        {
            "name": "Iteraciones cortas y feedback",
            "summary": "Ciclos muy breves con entrega continua y retroalimentación técnica y de negocio.",
            "goals": ["Entregar valor frecuentemente","Reducir deuda técnica mediante refactorizaciones"],
            "typical_weeks": 1,
            "checklist": ["Historias pequeñas, tests por historia","Pair programming en piezas críticas"],
            "common_issues": ["Historias mal definidas","Falta de disciplina en TDD"],
            "mitigations": ["Reforzar Definition of Ready/Done","Revisiones técnicas continuas"],
            "roles_responsibilities": {"PO":"Coordinar valor de negocio","Equipo":"Garantizar calidad técnica"},
            "kpis": ["Lead time por historia","Defect escape rate"],
            "deliverables": ["Incrementos con tests","Documentación mínima técnica"],
            "questions_to_ask": ["¿Qué piezas necesitamos proteger con pair programming?","¿Qué pruebas automatizadas son críticas?"]
        }
    ],
    "Lean": [
        {
            "name": "Validación de hipótesis",
            "summary": "Fase de experimentación rápida para validar supuestos de negocio con mínimos recursos.",
            "goals": ["Priorizar experimentos que reduzcan incertidumbre","Medir impacto de hipótesis"],
            "typical_weeks": 2,
            "checklist": ["Definir hipótesis y métricas","Diseñar experimento de bajo coste","Implementar y medir"],
            "common_issues": ["Mala señal por métricas mal definidas","Experimentos demasiado grandes"],
            "mitigations": ["Formular métricas accionables","Reducir alcance del experimento"],
            "roles_responsibilities": {"PM/PO":"Definir hipótesis y criterios de éxito","Equipo":"Implementar experimento rápido"},
            "kpis": ["Conversion rate del experimento","Tasa de aprendizaje por iteración"],
            "deliverables": ["Resultados del experimento","Decisión: pivot/seguir"],
            "questions_to_ask": ["¿Qué métrica define éxito del experimento?","¿Cuál es el tamaño mínimo del experimento?"]
        },
        {
            "name": "Optimización & Kaizen",
            "summary": "Mejora continua basada en datos y eliminación de desperdicio en procesos y código.",
            "goals": ["Reducir waste y handoffs","Mejorar velocidad de entrega sin perder calidad"],
            "typical_weeks": 3,
            "checklist": ["Mapear flujo de valor","Eliminar pasos sin valor","Medir antes/después"],
            "common_issues": ["Cambios superficiales sin impacto real","Resistencia al cambio operativo"],
            "mitigations": ["Pequeños experimentos de mejora (Kaizen)","Medir impacto y comunicar resultados"],
            "roles_responsibilities": {"Líder de mejora":"Coordinación Kaizen","Equipo":"Proponer y probar cambios"},
            "kpis": ["Tiempo de ciclo total","% de actividades sin valor"],
            "deliverables": ["Mapas de flujo","Experimentos de mejora implementados"],
            "questions_to_ask": ["¿Qué pasos del proceso agregan poco valor?","¿Qué métricas usaremos para validar la mejora?"]
        }
    ],
    "Crystal": [
        {
            "name": "Alineación de equipo",
            "summary": "Adaptar el proceso según tamaño del equipo y criticidad, priorizando comunicación directa.",
            "goals": ["Definir prácticas mínimas apropiadas al tamaño","Establecer canales de comunicación directa"],
            "typical_weeks": 1,
            "checklist": ["Seleccionar variante Crystal adecuada","Documentar acuerdos de comunicación","Definir cadencia mínima"],
            "common_issues": ["Subestimación del esfuerzo de coordinación","Falta de documentación cuando el equipo crece"],
            "mitigations": ["Revisar proceso al crecer el equipo","Añadir artefactos ligeros cuando sea necesario"],
            "roles_responsibilities": {"Equipo":"Comunicación y adaptación","Sponsor":"Soporte organizativo"},
            "kpis": ["Satisfacción del equipo","Velocidad relativa"],
            "deliverables": ["Acuerdos de proceso","Lista de prácticas acordadas"],
            "questions_to_ask": ["¿Cuál es el tamaño y criticidad del equipo?","¿Qué prácticas mínimas necesitamos desde el día 1?"]
        }
    ],
    "FDD": [
        {
            "name": "Modelado de dominio & Lista de features",
            "summary": "Identificar y modelar features a entregar; base para planificación por feature.",
            "goals": ["Obtener lista priorizada de features","Alinear diseño por feature"],
            "typical_weeks": 2,
            "checklist": ["Modelado de dominio inicial","Listar features y prioridades","Asignar responsables técnicos"],
            "common_issues": ["Over-design del modelo","Features mal granularizadas"],
            "mitigations": ["Iterar el modelo con feedback","Dividir features grandes"],
            "roles_responsibilities": {"Chief Architect":"Facilitar modelado","Feature Owners":"Definir criterios de aceptación"},
            "kpis": ["% features entregadas por iteración","Tamaño medio de feature"],
            "deliverables": ["Domain model","Feature list with acceptance criteria"],
            "questions_to_ask": ["¿Qué entidades del dominio son críticas?","¿Cómo medimos completitud de una feature?"]
        }
    ],
    "DSDM": [
        {
            "name": "Kickoff & Timebox setup",
            "summary": "Establecer timeboxes, acuerdos MoSCoW y gobernanza para el proyecto.",
            "goals": ["Definir timeboxes y reglas MoSCoW","Asegurar compromiso del negocio"],
            "typical_weeks": 1,
            "checklist": ["Workshop MoSCoW","Definir roles y gobernanza","Establecer cadencias de revisión"],
            "common_issues": ["Negociación MoSCoW ineficiente","Falta de compromiso del negocio"],
            "mitigations": ["Facilitar talleres de priorización","Acordar sponsors claros"],
            "roles_responsibilities": {"Business Sponsor":"Decidir prioridades","Facilitator":"Guiar timeboxes"},
            "kpis": ["% requisitos MoSCoW entregados","Cumplimiento de timeboxes"],
            "deliverables": ["Listado MoSCoW","Calendario de timeboxes"],
            "questions_to_ask": ["¿Qué elementos son Must vs Should?","¿Quién valida los entregables por timebox?"]
        }
    ],
}


def get_method_phases(method: str) -> List[Dict]:
    """Return the list of phases for a given methodology name.

    Normalizes common synonyms. Falls back to an empty list if unknown.
    """
    key = normalize_method_name(method)
    return METHODOLOGY_PHASES.get(key, [])


def get_phase_detail(method: str, phase_idx: int) -> Dict | None:
    """Return detailed info for a specific phase index (0-based) of the given methodology.

    Returns None if not found.
    """
    phases = get_method_phases(method)
    if not phases or phase_idx < 0 or phase_idx >= len(phases):
        return None
    return phases[phase_idx]

