# MÓDULO DE APRENDIZAJE - ARQUITECTURA Y FUNCIONAMIENTO LÓGICO

## 📋 ÍNDICE
1. [Visión general](#visión-general)
2. [Flujo de usuario: entrada al modo aprendizaje](#flujo-de-usuario)
3. [Arquitectura del módulo](#arquitectura-del-módulo)
4. [Componentes principales](#componentes-principales)
5. [Gestión de estado conversacional](#gestión-de-estado-conversacional)
6. [Base de conocimiento estructurada](#base-de-conocimiento-estructurada)
7. [Algoritmos de detección y generación](#algoritmos-de-detección-y-generación)
8. [Ejemplos prácticos](#ejemplos-prácticos)
9. [Limitaciones y futuras mejoras](#limitaciones-y-futuras-mejoras)

---

## 1. VISIÓN GENERAL

El **módulo de aprendizaje** es un subsistema educativo interactivo integrado en el brain que permite a usuarios aprender conceptos sobre **metodologías ágiles** (Scrum, Kanban, XP, Lean, etc.) de forma guiada y nivelada.

**Objetivos principales:**
- Permitir que usuarios sin experiencia aprendan conceptos fundamentales
- Ofrecer profundidad progresiva según nivel (principiante → intermedio → experto)
- Proporcionar respuestas específicas y contextualizadas a preguntas del usuario
- Mantener al usuario en el "modo formación" hasta que decida salir

**Diferencia con el generador de propuestas:**
- **Generador:** Usuario proporciona requisitos → Sistema genera propuesta automatizada
- **Aprendizaje:** Usuario tiene cuestionamiento exploratorio → Sistema enseña conceptos paso a paso

---

## 2. FLUJO DE USUARIO: ENTRADA AL MODO APRENDIZAJE

### 2.1 Activación del modo formación

```
Usuario: "Quiero formarme" o "Quiero aprender"
           ↓
[Brain] _wants_training(text)
           ↓
Detecta palabras clave: "formarme", "aprender", "enseña", "training"
           ↓
_enter_training(session_id)
  ├─ Crear estado de entrenamiento en memoria
  ├─ Marcar sesión como "active training"
  └─ Retornar prompt inicial
           ↓
Sistema: "Modo formación activado.
          ¿Cuál es tu nivel?
          - principiante
          - intermedio
          - experto"
```

**Código clave:**
```python
def _wants_training(text: str) -> bool:
    t = _norm(text)
    return any(k in t for k in ["formarme", "aprender", "enseña", "training", "formación", "formacion"])

def _enter_training(session_id: str) -> None:
    set_context_value(session_id, "training_active", True)
    set_context_value(session_id, "training_level", None)
    set_context_value(session_id, "training_history", [])
```

### 2.2 Selección de nivel

```
Usuario: "principiante"
           ↓
[Brain] _parse_level(text)
           ↓
Retorna: "beginner" | "intermediate" | "expert"
           ↓
Guardar en training_state
           ↓
Sistema retorna _training_intro(level):
  "Nivel seleccionado: principiante.
   Temas disponibles: metodologías, fases, roles, métricas...
   Ejemplos:
   - quiero aprender sobre Kanban
   - fases de Scrum
   - roles del equipo en XP"
```

### 2.3 Pedido de aprendizaje específico

```
Usuario: "Quiero aprender sobre Scrum"
           ↓
[Brain] En modo training → _training_topic_and_method(text)
           ↓
Detectar:
  - topic = "quees" (qué es)
  - method_in_text = "Scrum"
           ↓
Retorna: _training_define_card("beginner", "Scrum")
           ↓
Sistema: "Scrum — mini formación (principiante)
         Qué es: Marco para gestionar complejidad mediante 
                 inspección y adaptación en iteraciones cortas.
         Rituales típicos: Sprint Planning, Daily, Review, Retro
         Roles recomendados: PO, Scrum Master, Dev, QA...
         Consejo: visualiza el trabajo y pide feedback frecuente."
```

---

## 3. ARQUITECTURA DEL MÓDULO

### 3.1 Capas de arquitectura

```
┌─────────────────────────────────────────────────────────┐
│          INTERFAZ DE USUARIO (Frontend React)           │
│              Chat.jsx renderiza en "modo"              │
└─────────────────┬───────────────────────────────────────┘
                  │
┌─────────────────↓───────────────────────────────────────┐
│      ORCHESTRATOR (Backend - brain.generate_reply)       │
│                                                          │
│  Si está en training:                                    │
│  ├─ _wants_training(text) → activar?                    │
│  ├─ _training_exit(text) → salir?                       │
│  ├─ _training_topic_and_method(text) → parseador        │
│  └─ Rutear a handlers específicos                        │
└─────────────────┬───────────────────────────────────────┘
                  │
    ┌─────────────┴──────────────────┬──────────────────┐
    │                                │                  │
┌───↓──────────────┐  ┌──────────────↓───┐  ┌───────────↓────┐
│  PARSEADORES    │  │  GENERADORES    │  │  PERSISTENCIA │
│                 │  │  DE RESPUESTA   │  │               │
├─────────────────┤  ├─────────────────┤  ├────────────────┤
│_parse_level()   │  │_training_intro()│  │Context: state  │
│_parse_topic()   │  │_training_card() │  │SessionLocal:   │
│_training_exit() │  │_short_response()│  │  training_log  │
│_match_phase()   │  │_expand_kpis()   │  │                │
│_match_phase_    │  │_expand_deliv.   │  │                │
│  user_intent()  │  │_training_method │  │                │
│                 │  │  _specialist()  │  │                │
└─────────────────┘  └─────────────────┘  └────────────────┘
                  │
    ┌─────────────↓──────────────────┐
    │     BASE DE CONOCIMIENTO       │
    │                                │
    ├─────────────────────────────────┤
    │ METHODOLOGIES dict (9 métodos)  │
    │ _TRAIN_METHOD dict (componentes)│
    │ PHASE_SHORT_RESPONSES (lookup)  │
    │ DELIVERABLE_DEFINITIONS (glos.) │
    │ QUICK_EXAMPLES_RESPONSES        │
    └─────────────────────────────────┘
```

### 3.2 Flujo de generación de respuesta (en modo training)

```
Input: user_text, session_id

  1. Obtener state de training
     ├─ ¿Activo?
     └─ ¿Nivel asignado?
     
  2. Detectar intención del usuario
     ├─ _training_exit(text) → salir?
     ├─ _parse_level(text) → nivel si no hay?
     └─ _training_topic_and_method(text) → tema + método?
     
  3. Según tema + método:
     ├─ "fases" + "Scrum" → _training_phases_card()
     ├─ "roles" + "XP" → _training_roles_card()
     ├─ "métricas" + "Kanban" → _training_metrics_card()
     ├─ "qué es" + "DevOps" → _training_define_card()
     ├─ "ventajas" + "Lean" → _training_benefits_card()
     ├─ "metodologías" (sin método) → _training_catalog()
     └─ Otras preguntas → help genérico
     
  4. Formatear respuesta
     ├─ Adaptar a nivel (beginner < intermediate < expert)
     ├─ Incluir ejemplos y consejos prácticos
     └─ Sugerir próximos temas
     
  5. Guardar en contexto de sesión
     └─ Actualizar training_history
     
Output: respuesta_formativa + resumen_accion
```

---

## 4. COMPONENTES PRINCIPALES

### 4.1 PARSER: Detección de nivel

**Función:** `_parse_level(text: str) -> Optional[str]`

```python
def _parse_level(text: str) -> Optional[str]:
    t = _norm(text)
    if any(k in t for k in ["principiante", "basico", "basico", "basix", "newbie", "beginner"]):
        return "beginner"
    if any(k in t for k in ["intermedio", "intermediate", "medio"]):
        return "intermediate"
    if any(k in t for k in ["experto", "expert", "avanzado", "advanced", "senior"]):
        return "expert"
    return None
```

**Ejemplo:**
```
Input: "Yo soy principiante"
Output: "beginner"
```

---

### 4.2 PARSER: Detección de tema y método

**Función:** `_training_topic_and_method(text: str) -> Tuple[Optional[str], Optional[str]]`

Devuelve `(topic, method_name)` donde:
- `topic` ∈ `{"fases", "roles", "métricas", "quees", "ventajas", "metodologías", ...}`
- `method_name` ∈ `{"Scrum", "Kanban", "XP", "Lean", ...}`

```python
def _training_topic_and_method(text: str) -> Tuple[Optional[str], Optional[str]]:
    t = _norm(text)
    # 1) Detectar método mencionado
    method = None
    for m in ["Scrum", "Kanban", "XP", "Lean", "Crystal", "FDD", "DSDM", "SAFe", "DevOps"]:
        if _norm(m) in t:
            method = m
            break
    
    # 2) Detectar tema
    topic = None
    if any(k in t for k in ["fases", "fase"]):
        topic = "fases"
    elif any(k in t for k in ["roles", "rol", "responsabilidades", "responsabilidad"]):
        topic = "roles"
    elif any(k in t for k in ["métricas", "metricas", "kpi", "indicador", "indicadores"]):
        topic = "metricas"
    elif any(k in t for k in ["qué es", "que es", "definición", "definicion", "ventajas"]):
        if "ventaj" in t:
            topic = "ventajas"
        else:
            topic = "quees"
    elif any(k in t for k in ["metodologías", "metodologias"]):
        topic = "metodologias"
    
    return topic, method
```

**Ejemplos:**
```
Input: "fases de Scrum"
Output: ("fases", "Scrum")

Input: "Cuéntame sobre Kanban"
Output: (None, "Kanban")  # detecta método sin tema específico

Input: "Rolesin XP"
Output: ("roles", "XP")
```

---

### 4.3 GENERADOR: Card de formación para una metodología

**Función:** `_training_method_card(method: str, level: str) -> str`

Devuelve una "tarjeta" educativa con info de 1 página sobre la metodología.

**Estructura por nivel:**
- **Principiante:** Qué es, rituales, roles, consejo
- **Intermedio:** Qué es, fases, métricas clave
- **Experto:** Qué es, métricas clave, prácticas avanzadas

```python
def _training_method_card(method: str, level: str) -> str:
    m = normalize_method_name(method)
    info_m = _TRAIN_METHOD.get(m, {})
    overview = _one_liner_from_info(METHODOLOGIES.get(m, {}), m)

    lines = [f"{m} — mini formación ({_level_label(level)})"]
    lines.append(f"Qué es: {overview}")

    if level == "beginner":
        if info_m.get("rituales"):
            lines.append("Rituales típicos: " + ", ".join(info_m["rituales"]))
        if info_m.get("roles"):
            lines.append("Roles recomendados: " + ", ".join(info_m["roles"]))
        lines.append("Consejo: visualiza el trabajo y pide feedback frecuente.")
    elif level == "intermediate":
        if info_m.get("fases"):
            lines.append("Fases típicas: " + " → ".join(info_m["fases"]))
        if info_m.get("metrics"):
            lines.append("Métricas útiles: " + ", ".join(info_m["metrics"]))
    else:  # expert
        if info_m.get("metrics"):
            lines.append("Métricas clave: " + ", ".join(info_m["metrics"]))
        if info_m.get("avanzado"):
            lines.append("Prácticas avanzadas: " + ", ".join(info_m["avanzado"]))

    lines.append('Pide "fases", "roles", "métricas" o escribe "salir de la formación".')
    return "\n".join(lines)
```

**Ejemplo:**
```
Input: ("Scrum", "beginner")
Output:
"""
Scrum — mini formación (principiante)
Qué es: Marco para gestionar complejidad mediante inspección y adaptación en iteraciones cortas.
Rituales típicos: Sprint Planning, Daily, Review, Retro
Roles recomendados: PO, Scrum Master, Dev Team, QA
Consejo: visualiza el trabajo y pide feedback frecuente.
Pide "fases", "roles", "métricas" o escribe "salir de la formación".
"""
```

---

### 4.4 GENERADOR: Respuesta corta para preguntas específicas

**Función:** `_short_phase_response(method: str, phase_name: str, qtype: str, proposal: Optional[Dict], user_text: Optional[str]) -> str`

Devuelve respuesta concisa según tipo de pregunta.

```python
def _short_phase_response(method, phase_name, qtype, proposal=None, user_text=None):
    """
    qtype ∈ {"definition", "objective", "deliverables", "practices", 
               "kpis", "checklist", "owners", "timeline", "risks", "deliverable_def"}
    """
    # Si es definiición de entregable → buscar en diccionario
    if qtype == "deliverable_def":
        key = _find_deliverable_key(user_text or phase_name or "")
        if key and key in DELIVERABLE_DEFINITIONS:
            return DELIVERABLE_DEFINITIONS[key]
    
    # Si hay entrada en PHASE_SHORT_RESPONSES → retornar esa
    method_norm = normalize_method_name(method)
    if method_norm in PHASE_SHORT_RESPONSES:
        phases_map = PHASE_SHORT_RESPONSES[method_norm]
        for ph in phases_map.keys():
            if _norm_simple(ph) in _norm_simple(phase_name):
                resp = phases_map[ph].get(qtype)
                if resp:
                    return resp
    
    # Fallback: generar respuesta genérica
    return _explain_specific_phase(phase_name, proposal or {"methodology": method})
```

---

### 4.5 EXPANSIÓN: KPIs detallados

**Función:** `_expand_kpis_for_phase(phase_info: Dict, proposal: Optional[Dict]) -> List[str]`

Por cada KPI en phase_info, devuelve línea con: medición, frecuencia, owner, objetivo.

```python
def _expand_kpis_for_phase(phase_info, proposal=None):
    """
    Genera para cada KPI:
    - Descripción: cómo medirlo
    - Frecuencia: semanal, por sprint, etc.
    - Owner sugerido: PM, Tech Lead, QA, etc.
    - Objetivo inicial: basado en tipo de métrica
    """
    out = []
    kpis = phase_info.get('kpis') or []
    out.append('DETALLE DE KPIs (medición, frecuencia, owner, objetivo inicial):')
    
    for k in kpis:
        kk = k.strip()
        # Heurísticas para inferir tipo de métrica
        if 'lead time' in _norm(kk):
            meas = 'Tiempo medio (días) desde creación hasta despliegue'
            freq = 'Diaria / semanal agregada'
            owner = 'Tech Lead / DevOps'
            target = 'Reducir un 10–20% en 2–3 sprints'
        elif 'velocidad' in _norm(kk):
            meas = 'Puntos de historia completados por sprint'
            freq = 'Por sprint'
            owner = 'PO / Scrum Master'
            target = 'Establecer baseline y estabilizar (+/- 10%)'
        elif 'defecto' in _norm(kk):
            meas = 'Número de defectos críticos en producción'
            freq = 'Por release / semanal'
            owner = 'QA / Tech Lead'
            target = 'Minimizar a 0–1 críticos por release'
        
        out.append(f"- {kk}: {meas}; Frecuencia: {freq}; Owner: {owner}; Objetivo: {target}")
    
    return out
```

**Ejemplo:**
```
Input: phase_info con kpis=["Lead time", "Velocidad", "Defect escape rate"]
Output:
[
  "DETALLE DE KPIs (medición, frecuencia, owner, objetivo inicial):",
  "- Lead time: Tiempo medio (días) desde creación hasta despliegue; Frecuencia: Diaria/semanal; Owner: Tech Lead/DevOps; Objetivo: Reducir 10-20% en 2-3 sprints",
  "- Velocidad: Puntos de historia completados por sprint; Frecuencia: Por sprint; Owner: PO/Scrum Master; Objetivo: Establecer baseline y estabilizar (+/- 10%)",
  "- Defect escape rate: Número de defectos críticos en producción; Frecuencia: Por release/semanal; Owner: QA/Tech Lead; Objetivo: Minimizar a 0-1 críticos"
]
```

---

### 4.6 EXPANSIÓN: Entregables con criterios de aceptación

**Función:** `_expand_deliverables_for_phase(phase_info: Dict, proposal: Optional[Dict]) -> List[str]`

```python
def _expand_deliverables_for_phase(phase_info, proposal=None):
    """
    Por cada entregable:
    - Descripción
    - Criterios de aceptación contextualizados
    - Responsible sugerido
    """
    dels = phase_info.get('deliverables') or []
    out = []
    out.append('ENTREGABLES — descripción, criterios de aceptación y responsable:')
    
    for d in dels:
        name = d if isinstance(d, str) else str(d)
        
        # Heurísticas contextuales
        if 'roadmap' in _norm(name) or 'backlog' in _norm(name):
            owner = 'Product Owner (PO)'
            criteria = 'Priorizar ítems, estimar historias, validar alcance con stakeholders'
        elif 'definition of done' in _norm(name):
            owner = 'Tech Lead + PO'
            criteria = 'Documento firmado con checklist verificable'
        elif 'historias' in _norm(name) or 'story' in _norm(name):
            owner = 'PO / Dev Team'
            criteria = 'Historias estimadas, priorizadas, con DoR y criterios de aceptación claros'
        else:
            owner = 'PM / Equipo responsable'
            criteria = 'Entregable completo, pruebas asociadas, documentación mínima'
        
        out.append(f"- {name}: {criteria}; Responsable: {owner}")
    
    return out
```

---

## 5. GESTIÓN DE ESTADO CONVERSACIONAL

### 5.1 Variables de estado de training

```python
# Guardadas con set_context_value / get_context_value en sesión

training_active: bool          # ¿En modo training?
training_level: str            # "beginner" | "intermediate" | "expert"
training_history: List[str]   # Temas ya cubiertos
last_method: Optional[str]    # Última metodología mencionada
last_topic: Optional[str]     # Último tema consultado
```

### 5.2 Transiciones de estado

```
[IDLE]
  ↓ usuario dice "quiero formarme"
[TRAINING - AWAITING LEVEL]
  ├─ usuario dice "principiante"
  └─→ [TRAINING - ACTIVE]
       ├─ usuario pide "fases de Scrum" → responde + permanece en TRAINING
       ├─ usuario pide "roles" → responde + permanece en TRAINING
       ├─ usuario pide "salir de la formación" → [IDLE]
       └─ usuario dice "terminar formación" → [IDLE]
```

### 5.3 Recuperación de contexto

```python
def _get_training_state(session_id: str) -> Dict:
    return {
        "active": get_context_value(session_id, "training_active", False),
        "level": get_context_value(session_id, "training_level"),
        "history": get_context_value(session_id, "training_history", []),
    }

def _set_training_state(session_id: str, state: Dict) -> None:
    set_context_value(session_id, "training_active", state.get("active", False))
    set_context_value(session_id, "training_level", state.get("level"))
    set_context_value(session_id, "training_history", state.get("history", []))
```

---

## 6. BASE DE CONOCIMIENTO ESTRUCTURADA

### 6.1 Diccionario de metodologías: `_TRAIN_METHOD`

```python
_TRAIN_METHOD = {
    "Scrum": {
        "rituales": ["Sprint Planning", "Daily", "Review", "Retro"],
        "fases": ["Incepción & Plan", "Sprints de Desarrollo", "QA/Hardening", "Release"],
        "roles": ["PO", "Scrum Master", "Dev Team"],
        "metrics": ["Velocidad", "Lead time", "Defect escape rate"],
        "avanzado": ["Scaled Scrum", "Nexus", "SAFe"]
    },
    "Kanban": {
        "rituales": ["Daily", "Replenishment", "Retro"],
        "fases": ["Descubrimiento & Diseño", "Flujo continuo", "QA", "Producción"],
        "roles": ["Product Manager", "Flow Manager"],
        "metrics": ["Lead time", "Cycle time", "WIP"],
        "avanzado": ["WIP dinámico", "Políticas por rol"]
    },
    "XP": {
        "rituales": ["Pair Programming", "Standup", "Planning", "Release"],
        "fases": ["Discovery", "Iteraciones TDD", "Hardening", "Release"],
        "roles": ["Tech Lead", "Pair Programmers"],
        "metrics": ["Defects", "Test coverage", "Refactoring health"],
        "avanzado": ["Extreme Quality", "Continuous Integration Mastery"]
    },
    # ... más metodologías
}
```

### 6.2 Respuestas cortas por fase: `PHASE_SHORT_RESPONSES`

Lookup de 2 niveles: `[método][fase][tipo_pregunta]`

```python
PHASE_SHORT_RESPONSES = {
    "Scrum": {
        "Incepción & Plan de Releases": {
            "definition": "Incepción / Discovery: fase inicial...",
            "objective": "Alinear stakeholders, priorizar...",
            "deliverables": "ENTREGABLES PRINCIPALES:\n- Backlog...",
            "practices": "Workshops, mapping, priorización...",
            "kpis": "% historias listas; claridad de alcance...",
            "checklist": "Checklist inicial: 1) Entrevistas; 2) Mapa...",
            "owners": "Responsables: PM (coordinación), PO (priorización)...",
            "timeline": "1–2 semanas típicamente",
            "risks": "Alcance insuficiente, dependencias no identificadas..."
        },
        "Sprints de Desarrollo (2w)": { ... },
        # ... más fases
    },
    "Kanban": { ... },
    # ... más metodologías
}
```

### 6.3 Glosario de entregables: `DELIVERABLE_DEFINITIONS`

```python
DELIVERABLE_DEFINITIONS = {
    "backlog priorizado": "Backlog priorizado: lista ordenada de ítems (épicas, historias) priorizados por valor y riesgo; incluye estimaciones, criterios de aceptación y dependencias, y sirve como fuente para planificar sprints/releases.",
    
    "roadmap de releases": "Roadmap de releases: calendario de alto nivel con hitos y releases previstos, objetivos por release y fechas/marcos temporales aproximados.",
    
    "definition of done": "Definition of Done: conjunto de criterios mínimos que debe cumplir una historia para considerarse completa (tests, documentación, revisión de código, despliegue, etc.).",
    
    "runbook operativo": "Runbook operativo: documento paso a paso para operar el servicio en producción (checks, comandos de restauración, responsables y contactos).",
    
    # ... más definiciones
}
```

---

## 7. ALGORITMOS DE DETECCIÓN Y GENERACIÓN

### 7.1 Algoritmo de detección de tipo de pregunta

**Función:** `_determine_phase_question_type(text: str) -> Optional[str]`

Mapea una pregunta a un tipo de respuesta predefinido.

```python
def _determine_phase_question_type(text: str) -> Optional[str]:
    t = _norm(text)
    
    # Orden de prioridad: más específico primero
    if any(k in t for k in ["qué es", "que es", "definición", "definicion"]):
        if _find_deliverable_key(t):
            return "deliverable_def"
        return "definition"
    
    if any(k in t for k in ["objetivo", "propósito", "para qué"]):
        return "objective"
    
    if any(k in t for k in ["entregables", "artefacto", "documentación"]):
        return "deliverables"
    
    if any(k in t for k in ["prácticas", "practicas", "cómo hacerlo"]):
        return "practices"
    
    if any(k in t for k in ["kpi", "kpis", "métricas", "metricas", "indicadores"]):
        return "kpis"
    
    if any(k in t for k in ["checklist", "lista", "tareas inmediatas"]):
        return "checklist"
    
    if any(k in t for k in ["responsable", "owner", "owners", "roles", "quién"]):
        return "owners"
    
    if any(k in t for k in ["duración", "duracion", "semanas", "plazo"]):
        return "timeline"
    
    if any(k in t for k in ["riesgo", "riesgos", "mitig"]):
        return "risks"
    
    # Fallback: si es pregunta corta (≤6 palabras), asumir "definition"
    if len(text.split()) <= 6 or "?" in text:
        return "definition"
    
    return None
```

### 7.2 Adaptación por nivel

**Principio:** La profundidad de la respuesta crece con el nivel.

```python
# BEGINNER: Definiciones simples, ejemplos visuales, consejos prácticos
"""
Roles en Scrum (principiante):
- Product Owner: gestiona prioridades
- Scrum Master: facilita sprints
- Dev Team: construye el producto
Consejo: asegura prioridades claras y poca multitarea.
"""

# INTERMEDIATE: Flujos, responsabilidades concretas, artefactos asociados
"""
Roles en Scrum (intermedio):
- Product Owner: responsabilidades (priorizar backlog, criterios aceptación), 
  artefactos (backlog, release plan)
- Scrum Master: facilitador de sprints, impedimentos, retros
- Dev Team: estimación, ejecución, quality gates
Evita handoffs largos; pairing y Definition of Done compartido.
"""

# EXPERT: Riesgos, anti-patrones, optimizaciones, scaling
"""
Roles en Scrum (experto):
- Product Owner: gestiona descubrimiento de producto, combina input del mercado
  con restricciones técnicas; anti-patrón: PO distante o sin poder de decisión
- Scrum Master: coaching transformacional, emergencia de equipos auto-organizados
- Dev Team: ownership de calidad técnica, deuda técnica consciente
Mide carga y throughput del equipo; optimiza WIP según contexto.
"""
```

### 7.3 Algoritmo de expansión contextual

Si el usuario pregunta con palabras como "amplía", "detalla", "desglosza", el sistema genera:

```
Usuario: "Cuéntame más sobre los KPIs de la fase discovery"
           ↓
[Brain] Detecta trigger: "más", "detalla"
           ↓
[Brain] Detecta tipo: "kpis"
           ↓
Llama: _expand_kpis_for_phase(phase_info)
           ↓
Retorna para cada KPI:
  - Medición: cómo medirlo
  - Frecuencia: cuán a menudo
  - Owner: quién es responsable
  - Objetivo inicial: baseline sugerido
```

---

## 8. EJEMPLOS PRÁCTICOS

### 8.1 Flujo completo: Usuario principiante aprende Scrum

```
┌─ PASO 1: Usuario entra en formación ─┐
User: "Quiero aprender sobre metodologías ágiles"
Bot: "Modo formación activado. ¿Cuál es tu nivel?
     - principiante
     - intermedio
     - experto"

┌─ PASO 2: Usuario selecciona nivel ─┐
User: "Soy principiante"
Bot: "Nivel seleccionado: principiante.
     Temas disponibles: metodologías, fases, roles, métricas...
     Ejemplos:
     - quiero aprender sobre Kanban
     - fases de Scrum
     - roles del equipo en XP"

┌─ PASO 3: Usuario pregunta por metodología específica ─┐
User: "Quiero aprender sobre Scrum"
[Brain] Detecta: topic="quees", method="Scrum", level="beginner"
Bot: "Scrum — mini formación (principiante)
     Qué es: Marco para gestionar complejidad mediante inspección y 
             adaptación en iteraciones cortas.
     Rituales típicos: Sprint Planning, Daily, Review, Retro
     Roles recomendados: PO, Scrum Master, Dev Team
     Consejo: visualiza el trabajo y pide feedback frecuente.
     Pide 'fases', 'roles', 'métricas' o escribe 'salir de la formación'."

┌─ PASO 4: Usuario pregunta por sub-tema ─┐
User: "¿Cuáles son los rituales de Scrum?"
[Brain] Detecta: topic="rituales" (mapped to "roles"), method="Scrum"
Bot: "RITUALES EN SCRUM (principiante):
     - Sprint Planning (inicio de sprint): alinear qué se hará en 2 semanas
     - Daily Standup (cada día): 15 min para impedimentos y coordinación
     - Sprint Review (fin de sprint): demo + feedback de stakeholders
     - Sprint Retrospective (fin de sprint): cómo mejorar el proceso
     Consejo: hazlos visuales y con tiempo fijo."

┌─ PASO 5: Usuario pregunta detalles ─┐
User: "¿Cómo ejecutar un Daily efectivamente?"
[Brain] Detecta: trigger de expansión, tema="Daily", tipo="practices"
Bot: "EJECUTAR UN DAILY EFECTIVAMENTE (Scrum / principiante):

     PASOS CONCRETOS:
     1) Preparación: Reunir al equipo en tablero físico/virtual (15 min antes)
     2) Ejecución: Cada persona responde 3 preguntas en <2 min:
        - ¿Qué hiciste ayer?
        - ¿Qué harás hoy?
        - ¿Qué impedimentos hay?
     3) Formalizar: Actualizar tablero, asignar owners para bloqueos

     CHECKLIST MÍNIMA:
     - Hora fija y lugar visible
     - Todos presentes (o video si remoto)
     - 15 minutos máximo
     - Actualizar estado en tablero

     RESPONSABLE: Scrum Master (facilita + cronometra)
     DURACIÓN: ~10-15 minutos"

┌─ PASO 6: Usuario sale del modo formación ─┐
User: "Salir de la formación"
Bot: "Salgo del modo formación. ¿Generamos una propuesta? Usa /propuesta: ..."
```

### 8.2 Búsqueda de definición de entregable

```
User: "¿Qué es un 'backlog priorizado'?"
      ↓
[Brain] Detecta: qtype="deliverable_def", key="backlog priorizado"
      ↓
[Brain] Busca en DELIVERABLE_DEFINITIONS[key]
      ↓
Bot: "Backlog priorizado: lista ordenada de ítems (épicas, historias) 
     priorizados por valor y riesgo; incluye estimaciones, criterios de 
     aceptación y dependencias, y sirve como fuente para planificar 
     sprints/releases."
```

### 8.3 Expansión de KPIs para una fase

```
User (en training): "Explícame los KPIs de la fase discovery en Scrum"
      ↓
[Brain] topic="kpis", method="Scrum", phase="discovery"
[Brain] trigger="explícame" → expansión completa
      ↓
Bot: "DETALLE DE KPIs — DESCUBRIMIENTO & PLAN DE RELEASES (Scrum/principiante):

     1. % historias listas para primer sprint
        - Medición: (total historias con DoR / total historias) * 100
        - Frecuencia: al final de la fase de discovery
        - Owner: Product Owner + Tech Lead
        - Objetivo inicial: >80% de historias listas

     2. Claridad de alcance consensuada
        - Medición: Stakeholders firman que entienden y aceptan alcance
        - Frecuencia: una sola vez (inicio)
        - Owner: PM + PO
        - Objetivo: 100% de stakeholders clave han aprobado

     3. Riesgos identificados y owners asignados
        - Medición: (riesgos con owner / riesgos totales) * 100
        - Frecuencia: al final de discovery
        - Owner: Tech Lead + PM
        - Objetivo: 100% de riesgos con owner y plan de mitigation

     RESUMEN: Una buena fase de discovery deja el backlog listo, 
              alcance claro y riesgos bajo control."
```

---

## 9. LIMITACIONES Y FUTURAS MEJORAS

### 9.1 Limitaciones actuales

| Limitación | Impacto | Mitigation |
|-----------|--------|-----------|
| No hay persistencia multi-sesión de progress | Usuario pierde historia de aprendizaje en nuevo chat | Guardar training_history en BD |
| Base de conocimiento hardcodeada | Difícil de actualizar/escalar | Integrar CMS o importar de BD |
| No hay cuestionarios/evaluación | No validamos aprendizaje | Añadir preguntas tipo test |
| Respuestas genéricas por nivel | Menos personalización | Análisis de errores del usuario → recomendaciones |
| Sin recomendaciones contextuales | Usuario no sabe "qué aprender después" | Análisis de brechas vs. propuesta actual |
| No hay interacción con propuesta viva | Learning desacoplado de planificación | Sugerir "aprende sobre metodología de tu propuesta" |

### 9.2 Mejoras futuras

**Corto plazo:**
1. **Persistencia de progreso:** Guardar training_history en BD para continuidad
2. **Cuestionarios auto-evaluables:** "¿Cuáles son los 3 rituales de Scrum?" → validar respuesta
3. **Búsqueda mejora:** Full-text search en base de conocimiento

**Mediano plazo:**
1. **Generación con LLM:** Usar Claude/GPT para respuestas más naturales y contextuales
2. **Rutas de aprendizaje:** Sugerir "después de Scrum, aprende SAFe para escalar"
3. **Integración con propuesta:** "Tu propuesta usa Kanban, ¿quieres aprender sobre WIP?"
4. **Recomendaciones por rol:** Si usuario selecciona "PM", priorizar temas de PO/PM

**Largo plazo:**
1. **Aprendizaje adaptativo:** Según respuestas del usuario, ajustar dificultad
2. **Certificaciones light:** "Completa 3 módulos y obtén badge de 'Scrum fundamentals'"
3. **Integración con recursos externos:** Links a wikis, libros, videos
4. **Community learning:** Usuarios compartir notas y tips sobre metodologías

---

## CONCLUSIÓN

El **módulo de aprendizaje** de TFGv3 proporciona un subsistema educativo **modular, escalable y guiado** que permite a usuarios sin experiencia aprender metodologías ágiles de forma progresiva. La arquitectura se basa en:

- **Detección inteligente** de nivel y tema mediante NLP
- **Base de conocimiento estructurada** con respuestas adaptadas por nivel
- **Generadores contextuales** que expanden conceptos bajo demanda
- **Gestión de estado** que mantiene continuidad durante la sesión

Esta design permite un aprendizaje natural ("teach me about Scrum" → propuesta completa) que complementa el módulo de generación de propuestas, creando una **experiencia educativa + operativa** integrada.

---

**Archivos clave en el codebase:**
- [backend/engine/brain.py](backend/engine/brain.py#L3050) - Funciones de training, parsing y generación
- [backend/engine/context.py](backend/engine/context.py) - Persistencia de estado de training
- [backend/memory/state_store.py](backend/memory/state_store.py) - BD para historial
- [backend/knowledge/methodologies.py](backend/knowledge/methodologies.py) - Base de metodologías

