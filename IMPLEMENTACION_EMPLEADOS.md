# Implementación del Sistema de Empleados

## 📋 Resumen

Se ha implementado un sistema completo de gestión de empleados que se integra con el flujo de propuestas del asistente. Cuando el usuario acepta una propuesta, el sistema le pregunta si quiere usar empleados guardados o introducir la plantilla manualmente.

## 🔧 Cambios Implementados

### 1. Backend - Base de Datos (`backend/memory/state_store.py`)

**Nuevo modelo `Employee`:**
```python
class Employee(Base):
    id: int
    user_id: int
    name: str
    role: str  # Backend, QA, Frontend, etc.
    skills: str  # CSV: "Python, Django, AWS"
    seniority: str  # Junior, Mid, Senior, etc.
    availability_pct: int  # 0-100
    created_at: datetime
    updated_at: datetime
```

**Funciones CRUD agregadas:**
- `create_employee()` - Crear empleado
- `list_employees()` - Listar empleados del usuario
- `get_employee()` - Obtener empleado por ID
- `update_employee()` - Actualizar empleado
- `delete_employee()` - Eliminar empleado

### 2. Backend - API REST (`backend/routers/user.py`)

**Nuevos endpoints:**
- `GET /user/employees` - Listar todos los empleados del usuario
- `POST /user/employees` - Crear nuevo empleado
- `GET /user/employees/{id}` - Obtener empleado específico
- `PUT /user/employees/{id}` - Actualizar empleado
- `DELETE /user/employees/{id}` - Eliminar empleado

**Modelos Pydantic:**
- `EmployeeIn` - Validación de datos de entrada
- `EmployeeUpdate` - Validación de actualización parcial
- `EmployeeOut` - Respuesta con datos del empleado

### 3. Backend - Lógica de Conversación (`backend/engine/brain.py`)

**Flujo de aceptación de propuesta:**

1. **Usuario acepta propuesta** → Sistema pregunta método de staffing:
   ```
   ¿Qué prefieres?
   - 'usar empleados guardados' → Carga automática desde BD
   - 'manual' → Introducir plantilla manualmente
   ```

2. **Usuario elige "usar empleados guardados"** → Sistema pide JSON:
   ```
   Perfecto, envíame la lista de empleados en formato JSON...
   ```

3. **Frontend envía JSON automáticamente** → Sistema procesa y asigna:
   ```
   ✅ He cargado 4 empleados de tu base de datos.
   
   Asignación por rol (mejor persona y por qué)
   - PM: Ana Ruiz (Senior, 100%) → seniority Senior
   - Backend Dev: Carlos López (Mid, 100%) → skills afines...
   ```

**Mejoras en detección:**
- `_accepts_proposal()` ahora acepta patrones cortos: "acepto", "ok", "vale"
- Verificación de `awaiting_employees_data` ANTES de auto-generación de propuestas
- Conversión automática de JSON a formato staff interno

### 4. Frontend - Chat (`frontend/src/components/Chat.jsx`)

**Auto-detección y carga automática:**

Cuando el asistente responde con texto que contiene:
- "envíame la lista de empleados"
- "envíame json"
- "empleados" + "json"

El frontend automáticamente:
1. Llama a `GET /user/employees`
2. Convierte datos al formato esperado
3. Envía JSON por WebSocket
4. Muestra mensaje: "📋 Cargando X empleados guardados..."

```javascript
// Auto-detectar si el backend pide JSON de empleados
if (normalized.includes('envíame la lista de empleados') || 
    normalized.includes('empleados') && normalized.includes('json')) {
  
  // Cargar empleados de la API
  const { data } = await axios.get(`${base}/user/employees`, { headers })
  
  // Convertir y enviar automáticamente
  const employeesJson = data.map(emp => ({
    name: emp.name,
    role: emp.role,
    skills: emp.skills,
    seniority: emp.seniority,
    availability_pct: emp.availability_pct
  }))
  
  ws.send(JSON.stringify(employeesJson, null, 2))
}
```

### 5. Frontend - Empleados (`frontend/src/components/Employees.jsx`)

**Ya existía** pero se verificó que:
- Usa la API `/user/employees` correctamente
- Tiene fallback a localStorage si la API falla
- CRUD completo funcionando
- Búsqueda por nombre, rol y skills

## 🔄 Flujo Completo

```
1. Usuario: "Necesito una app bancaria..."
   ↓
2. Sistema: Genera propuesta (XP, 163k€, 12 semanas)
   ↓
3. Usuario: "acepto la propuesta"
   ↓
4. Sistema: "¿Usar empleados guardados o manual?"
   ↓
5. Usuario: "usar empleados guardados"
   ↓
6. Sistema: "Envíame JSON..."
   ↓
7. Frontend: Carga empleados automáticamente desde /user/employees
   ↓
8. Frontend: Envía JSON [Ana, Luis, María, Carlos]
   ↓
9. Sistema: Procesa empleados y genera:
   - Asignación por rol
   - Asignación por fase
   - Plan de formación (gaps detectados)
   - Plan de trabajo detallado
```

## ✅ Tests

**Test completo:** `scripts/test_complete_employee_flow.py`

Verificaciones:
- ✅ Creación de empleados en BD
- ✅ Generación de propuesta
- ✅ Aceptación detectada
- ✅ Pregunta por método de staffing
- ✅ Procesamiento de JSON
- ✅ Asignación de roles
- ✅ Todos los empleados aparecen en la respuesta

**Resultado:**
```
📊 Total empleados en BD: 4
✅ Propuesta generada correctamente
✅ Aceptación detectada
✅ Opción de empleados guardados funcionando
✅ JSON procesado y asignación generada
📊 4/4 empleados aparecen en la asignación
```

## 🎯 Características Implementadas

### Backend
- ✅ Modelo de datos `Employee` con SQLAlchemy
- ✅ API REST completa (GET/POST/PUT/DELETE)
- ✅ Validación con Pydantic
- ✅ Autenticación por usuario (JWT)
- ✅ Flujo conversacional inteligente
- ✅ Detección de JSON y conversión a formato staff
- ✅ Asignación automática por skills y seniority

### Frontend
- ✅ Componente Employees con CRUD completo
- ✅ Auto-carga de empleados cuando el backend lo solicita
- ✅ Fallback a localStorage si API falla
- ✅ Búsqueda y filtrado
- ✅ Edición inline
- ✅ Interfaz responsive

### Integración
- ✅ Chat detecta automáticamente la solicitud de empleados
- ✅ Carga datos de la API sin intervención del usuario
- ✅ Envío automático por WebSocket
- ✅ Feedback visual ("📋 Cargando X empleados...")
- ✅ Manejo de errores (si no hay empleados, sugiere "manual")

## 🚀 Uso

1. **Registrar empleados en la sección "Empleados":**
   - Ir a la sección Empleados
   - Añadir: Nombre, Rol, Skills, Disponibilidad%
   - Opcionalmente: Seniority

2. **Generar propuesta en el Chat:**
   - Describir el proyecto
   - Aceptar la propuesta generada

3. **Elegir método de asignación:**
   - "usar empleados guardados" → Carga automática
   - "manual" → Introducir plantilla manualmente

4. **Ver asignación:**
   - Asignación por rol (mejor candidato + alternativas)
   - Asignación por fase
   - Plan de formación para gaps
   - Desglose de tareas por persona

## 📝 Notas Técnicas

### Formato de Skills
Los skills se guardan como string CSV:
```
"Python, Django, PostgreSQL, REST APIs"
```

El backend los convierte automáticamente a array cuando procesa:
```python
skills = [s.strip() for s in skills_raw.split(",") if s.strip()]
```

### Seniority Levels
- Junior
- Mid
- Semi Senior
- Senior

Si no se especifica, default es "Mid".

### Availability
Porcentaje de 0 a 100 que indica la disponibilidad del empleado para el proyecto.
Default: 100%

### Matching de Skills
El sistema hace matching difuso por palabras clave:
- "Python" → match con "python", "django" (frameworks Python)
- "React" → match con "javascript", "typescript", "frontend"
- "QA" → match con "testing", "pytest", "selenium"

## 🔐 Seguridad

- ✅ Los empleados están asociados a `user_id`
- ✅ Endpoints protegidos con JWT
- ✅ Solo el propietario puede ver/editar sus empleados
- ✅ Validación de datos con Pydantic
- ✅ SQL injection prevention (SQLAlchemy ORM)

## 📊 Base de Datos

**Nueva tabla `employees`:**
```sql
CREATE TABLE employees (
    id INTEGER PRIMARY KEY,
    user_id INTEGER NOT NULL,
    name VARCHAR NOT NULL,
    role VARCHAR NOT NULL,
    skills TEXT NOT NULL,
    seniority VARCHAR,
    availability_pct INTEGER DEFAULT 100,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_employees_user_id ON employees(user_id);
```

## 🎨 UI/UX

- **Sección Empleados:** Tarjetas con edición inline
- **Chat:** Carga automática transparente
- **Feedback visual:** Emoji 📋 + contador de empleados
- **Errores:** Mensajes claros ("No tienes empleados guardados...")
