# backend/app.py
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import importlib

# Routers principales
from backend.routers import chat, projects

# Router de feedback (puede no existir aún; lo cargamos de forma segura)
try:
    from backend.routers import feedback
except Exception:
    feedback = None  # si no está, la app sigue arrancando

app = FastAPI(title="TFG Consultoría Assistant (Inteligencia + Memoria)")

# --- CORS DEV AMPLIO (en local) ---
ALLOWED_ORIGINS = [
    "http://localhost:5173",
    "http://127.0.0.1:5173",
    "*"  # en local vale; para prod usa dominios concretos y quita "*"
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- Rutas ---
app.include_router(chat.router,     prefix="/chat",     tags=["chat"])
app.include_router(projects.router, prefix="/projects", tags=["projects"])
if feedback:
    app.include_router(feedback.router, prefix="/projects", tags=["feedback"])

# --- Startup: inicializa BD y calienta índice de "similares" si está disponible ---
@app.on_event("startup")
def on_startup():
    # init_db compatible con cualquier versión de state_store
    try:
        store = importlib.import_module("backend.memory.state_store")
        if hasattr(store, "init_db"):
            store.init_db()
        elif hasattr(store, "Base") and hasattr(store, "engine"):
            store.Base.metadata.create_all(store.engine)
    except Exception as e:
        print(f"[startup] DB init skipped: {e}")

    # refresca índice de proyectos similares si existe el módulo
    try:
        sim_mod = importlib.import_module("backend.retrieval.similarity")
        if hasattr(sim_mod, "get_retriever"):
            sim_mod.get_retriever().refresh()
    except Exception:
        pass

@app.get("/health")
def health():
    return {
        "status": "ok",
        "app": "TFG Consultoría Assistant",
        "routers": {
            "chat": True,
            "projects": True,
            "feedback": bool(feedback)
        }
    }
