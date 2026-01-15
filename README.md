# TFG

🎯 **TFG — Asistente de propuestas**


Este programa se trata de una aplicación full‑stack desarrollada como Trabajo de Fin de Grado. Combina un backend en FastAPI (Python) y un frontend SPA en React (Vite) para ofrecer un asistente conversacional que genera propuestas de proyecto automáticamente a partir de requerimientos textuales. Soporta gestión de usuarios, guardado de chats/propuestas, gestión de empleados, generación de propuestas (metodología, equipo, fases, presupuesto) y exportación a PDF.

🔗 Despliegue público (Render)

La instancia desplegada y pública está disponible en:

https://tfgv3-version2.onrender.com

Al hacer click en este enlace, se desplegará la aplicación.







### Tecnologías y dónde se usan

| Tecnología | Uso principal | Archivos / componentes clave |
| - | - | - |
| Python 3.11 | Lenguaje del backend; lógica de negocio, APIs y generación de PDF | `backend/app.py`, `backend/engine/brain.py` |
| FastAPI | Framework web para las APIs REST y rutas | `backend/app.py`, `backend/routers/` |
| Uvicorn | Servidor ASGI para ejecución | `docker/Dockerfile.backend` (CMD), comandos de arranque en README |
| SQLAlchemy | ORM y capa de persistencia | `backend/memory/state_store.py` |
| SQLite (por defecto) | Base de datos ligera para desarrollo | `backend/core/config.py` (`DATABASE_URL`), `.env.example` |
| PostgreSQL (opcional) | Recomendado para producción; se configura con `DATABASE_URL` | `backend/core/config.py`, README |
| React | Frontend SPA (UI del chat y componentes) | `frontend/src/components/Chat.jsx`, `frontend/src/components/Sidebar.jsx` |
| Vite | Bundler / dev server para frontend | `frontend/package.json`, comandos `npm run build` |
| Tailwind CSS | Estilos y utilidades CSS | Clases en JSX dentro de `frontend/src/` |
| Axios | Cliente HTTP en frontend | `frontend/src/components/Chat.jsx` |
| WebSockets (nativo) | Comunicación en tiempo real y handshake de empleados | `frontend/src/components/Chat.jsx`, handlers en `backend/routers/` |
| joblib / scikit-learn | Modelos/transformers para NLU / retrieval | `models/intents.joblib`, `backend/retrieval/similarity.py` |
| ReportLab | Generación de PDF de propuestas | `backend/app.py` (export PDF) |
| Node.js / npm | Entorno y gestor de paquetes frontend y e2e | `frontend/package.json`, `e2e/` |
| Playwright | Pruebas E2E automatizadas (UI) | `e2e/tests/`, `e2e/playwright.config.ts` |
| pytest | Tests unitarios / integración backend (TDD) | `TDD/backend_tests/`, `backend/tests/` |
| Docker | Imagen multi-stage (build frontend + runtime Python) | `docker/Dockerfile.backend`, `docker/docker-compose.yml` |
| Render (PaaS) | Plataforma de despliegue (Git → Render) | README (URL pública), configuración en Render UI |

- frontend/: SPA en React (Vite). Componentes principales: `Chat.jsx` (UI del asistente), `Employees.jsx`, `Auth.jsx`, `Sidebar.jsx`.

### Despliegue en Render (detalle)

| Aspecto | Elemento | Descripción |
| - | - | - |
| Objetivo del despliegue | Reproducibilidad & same‑origin | El despliegue con Docker permite ejecutar el sistema completo sin instalar dependencias locales, garantizando consistencia entre los entornos de desarrollo y evaluación. El objetivo es servir frontend y backend desde la misma URL para evitar CORS. |
| Modelo de despliegue | Docker multi‑stage en Render | El sistema se construye en Render a partir de `docker/Dockerfile.backend` usando multi‑stage (Node para frontend → Python para runtime). No se emplea Docker Desktop en el flujo de entrega. |
| Orquestación | Render Web Service | Render gestiona build, runtime y escalado; la imagen se despliega como un Web Service conectado al repositorio. |
| Ubicación del Dockerfile | Estructura del repositorio | `docker/Dockerfile.backend` (Render lo lee desde el repo conectado). |
| Backend (modo runtime) | Dockerfile.backend / Python runtime | Stage final `python:3.11-slim` instala dependencias, copia `backend/` y `frontend/dist`. FastAPI sirve API, WS y archivos estáticos. |
| Arranque / CMD | Uvicorn con control de workers | CMD respeta `PORT` y `WEB_CONCURRENCY` (por defecto arrancamos 1 worker si no está). Ejemplo en Dockerfile: `uvicorn backend.app:app --host 0.0.0.0 --port ${PORT:-8000} --proxy-headers --workers $WEB_CONCURRENCY`. |
| Frontend (producción) | Build optimizado | `npm --prefix frontend run build` genera `frontend/dist`, que se copia a la imagen y se sirve desde FastAPI (same‑origin). |
| Puertos expuestos | API / UI | Interno: 8000 (FastAPI + Uvicorn). Render inyecta `PORT` público hacia la instancia. |
| Redes | Plataforma gestionada | Render enruta tráfico HTTP/HTTPS; no hay docker-compose en producción. |
| Volúmenes | Código y datos temporales | `frontend/dist` y `backend` están dentro de la imagen; disco del contenedor en Render es efímero — no usar para persistencia crítica. |
| Persistencia por defecto | SQLite (desarrollo) | `DATABASE_URL` por defecto apunta a SQLite local; solo para demo o pruebas locales. En Render usar servicio DB externo. |
| Persistencia recomendada | PostgreSQL gestionado | Provisionar Postgres y configurar `DATABASE_URL=postgresql://user:pass@host:5432/db` en Render. |
| Healthcheck / readiness | Endpoint `/health` | Usar `/health` para comprobar readiness; Render Live Tail para logs. |
| Logs / monitorización | Live Tail en Render | Revisar arranques, errores, mensajes de procesos hijos y OOM; ajustar `WEB_CONCURRENCY` según memoria. |
| WebSockets | Misma instancia/puerto | WS funcionan sobre la misma URL (Uvicorn); asegurar `--proxy-headers` habilitado y proxy compatible. |
| Seguridad / secretos | Env vars en Render UI | Guardar `SECRET_KEY`, `DATABASE_URL`, `VITE_API_BASE` (vacío para same‑origin), `WEB_CONCURRENCY`. No subir secretos al repo. |
| Rollback / despliegues | Control desde Render Dashboard | Render permite rollback a una versión anterior pública (útil en evaluación). |
| Verificación del despliegue | Qué comprobar tras deploy | Acceder a la URL pública → `/health` (200), `/docs` (Swagger), UI carga correctamente y `/projects/proposal` responde; revisar Live Tail. |
| Buenas prácticas para producción | Recomendaciones clave | Usar DB externa (Postgres), `WEB_CONCURRENCY=1` en instancias con poca RAM, habilitar HTTPS (Render gestiona TLS), no montar volúmenes de código en producción, mantener secretos fuera del repo, añadir healthchecks y alertas. |
| Notas específicas del repo | Rutas y archivos relevantes | `docker/Dockerfile.backend`, `backend/app.py` (monta `frontend/dist` y `/health`), `frontend/dist` (build output), `frontend/src/api.js` (`VITE_API_BASE` fallback). |
- TDD/backend_tests/: tests pytest que validan endpoints, state store y lógica del motor.
- e2e/: pruebas Playwright para flujos end-to-end (autenticación, crear proyecto, chat, cargar empleados, exportar, guardar).
- backend/retrieval/similarity.py: componente de búsqueda semántica (TF-IDF + k-NN).

---
