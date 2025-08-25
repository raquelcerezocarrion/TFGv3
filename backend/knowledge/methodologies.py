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
