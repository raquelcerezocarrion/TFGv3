from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from backend.core.config import settings
from backend.routers import chat, projects
from backend.memory.state_store import init_db

app = FastAPI(title="TFG Consultoría Assistant (Parte 1)")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.FRONTEND_ORIGIN],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(chat.router, prefix="/chat", tags=["chat"])
app.include_router(projects.router, prefix="/projects", tags=["projects"])

@app.on_event("startup")
def on_startup():
    init_db()

@app.get("/health")
def health():
    return {"status": "ok", "app": "TFG Consultoría Assistant - Parte 1"}
