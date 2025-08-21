# backend/app.py
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from backend.routers import chat, projects
from backend.memory.state_store import init_db

app = FastAPI(title="TFG Consultoría Assistant (Parte 1)")

# --- CORS DEV AMPLIO (para evitar bloqueos en local) ---
ALLOWED_ORIGINS = [
    "http://localhost:5173",
    "http://127.0.0.1:5173",
    "*"  # <- en local permite todo. Para prod, elimina "*" y deja dominios concretos.
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- Rutas ---
app.include_router(chat.router, prefix="/chat", tags=["chat"])
app.include_router(projects.router, prefix="/projects", tags=["projects"])

@app.on_event("startup")
def on_startup():
    init_db()

@app.get("/health")
def health():
    return {"status": "ok", "app": "TFG Consultoría Assistant - Parte 1"}
