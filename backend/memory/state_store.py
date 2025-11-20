from __future__ import annotations
import json, os
from datetime import datetime
from pathlib import Path
from typing import List, Optional, Dict, Any

from sqlalchemy import (
    create_engine, Column, Integer, String, DateTime, Text, JSON, ForeignKey, Boolean
)
from sqlalchemy.pool import StaticPool
from sqlalchemy.orm import declarative_base, sessionmaker, relationship

# --- Base de datos y engine ---
# Uso SQLite aquí para que sea fácil ejecutar el proyecto en local. Si esto
# fuera una app en producción, migraríamos a una base de datos más robusta
# y usaríamos migraciones (alembic) en lugar de create_all.
DATA_DIR = Path("data"); DATA_DIR.mkdir(parents=True, exist_ok=True)
# Allow configuring the database via environment (useful for tests and production).
# Default continues to be a local SQLite file for easy development.
DB_URL = os.getenv("DATABASE_URL", f"sqlite:///{(DATA_DIR / 'app.db').as_posix()}")

# For SQLite we need the `check_same_thread` connect arg in this sync codepath.
connect_args = {}
if DB_URL.startswith("sqlite"):
    connect_args = {"check_same_thread": False}

# If using in-memory SQLite for tests, use StaticPool so the same
# in-memory database is reused across connections within the process.
if DB_URL == "sqlite:///:memory:":
    engine = create_engine(DB_URL, connect_args=connect_args, poolclass=StaticPool)
else:
    engine = create_engine(DB_URL, connect_args=connect_args)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)
Base = declarative_base()

# --- Modelos (tablas) ---
class ConversationMessage(Base):
    __tablename__ = "conversation_messages"
    id = Column(Integer, primary_key=True, autoincrement=True)
    session_id = Column(String, index=True, nullable=False)
    role = Column(String, nullable=False)   # "user" | "assistant"
    content = Column(Text, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    # Mensajes de conversación guardados por sesión. Lo usamos para historial
    # o para auditar lo que pasó durante una sesión concreta.

class ProposalLog(Base):
    __tablename__ = "proposal_logs"
    id = Column(Integer, primary_key=True, autoincrement=True)
    session_id = Column(String, index=True, nullable=False)
    requirements = Column(Text, nullable=False)
    proposal_json = Column(JSON, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    feedbacks = relationship("ProposalFeedback", back_populates="proposal", cascade="all, delete-orphan")

class ProposalFeedback(Base):
    __tablename__ = "proposal_feedbacks"
    id = Column(Integer, primary_key=True, autoincrement=True)
    proposal_id = Column(Integer, ForeignKey("proposal_logs.id"), index=True, nullable=False)
    session_id = Column(String, index=True, nullable=False)
    accepted = Column(Boolean, nullable=False)               # True = aceptada
    score = Column(Integer, nullable=True)                   # 1..5 opcional
    notes = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    proposal = relationship("ProposalLog", back_populates="feedbacks")

class ProposalView(Base):
    __tablename__ = "proposal_views"
    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, index=True, nullable=False)
    proposal_id = Column(Integer, index=True, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

# --- Usuario / Auth (simple)
class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True, autoincrement=True)
    email = Column(String, unique=True, index=True, nullable=False)
    hashed_password = Column(String, nullable=False)
    full_name = Column(String, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)


# --- Saved chats per user
class SavedChat(Base):
    __tablename__ = "saved_chats"
    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, index=True, nullable=False)
    title = Column(String, nullable=True)
    content = Column(Text, nullable=False)   # JSON or plain text representing the chat
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, nullable=False)


# --- Empleados (employees) por usuario
class Employee(Base):
    __tablename__ = "employees"
    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, index=True, nullable=False)
    name = Column(String, nullable=False)
    role = Column(String, nullable=False)  # Backend, QA, Frontend, etc.
    skills = Column(Text, nullable=False)  # CSV o JSON de skills
    seniority = Column(String, nullable=True)  # Junior, Mid, Senior, etc.
    availability_pct = Column(Integer, nullable=False, default=100)  # 0-100
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, nullable=False)


# --- Catálogos genéricos (metodologías, roles, skills, tasks) ---
class Catalog(Base):
    __tablename__ = "catalogs"
    id = Column(Integer, primary_key=True, autoincrement=True)
    kind = Column(String, index=True, nullable=False)   # e.g., 'methodology', 'role', 'skill', 'task'
    key = Column(String, nullable=False)
    value = Column(JSON, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)




Base.metadata.create_all(engine)

# Creo las tablas si no existen. Es práctico en desarrollo; en producción
# preferiría controlarlas con migraciones.

# --- Conversación (compatibilidad con tu código) ---
def log_message(session_id: str, role: str, content: str) -> None:
    # Guarda un mensaje en la tabla de mensajes. Simple y directo.
    with SessionLocal() as db:
        db.add(ConversationMessage(session_id=session_id, role=role, content=content))
        db.commit()

def list_messages(session_id: str, limit: int = 50) -> List[ConversationMessage]:
    # Devuelve los últimos mensajes de una sesión en orden cronológico.
    with SessionLocal() as db:
        q = db.query(ConversationMessage).filter(ConversationMessage.session_id == session_id)\
              .order_by(ConversationMessage.created_at.desc()).limit(limit).all()
        return list(reversed(q))  # cronológico

# --- Propuestas ---
def save_proposal(session_id: str, requirements: str, proposal: Dict[str, Any]) -> int:
    # Guardamos la propuesta tal cual (JSON) y devolvemos la id de fila.
    try:
        with SessionLocal() as db:
            row = ProposalLog(session_id=session_id, requirements=requirements, proposal_json=proposal)
            db.add(row)
            db.commit()
            db.refresh(row)
            return int(row.id)
    except Exception as e:
        import traceback
        print(f"[save_proposal ERROR] {e}", flush=True)
        print(f"[save_proposal TRACEBACK] {traceback.format_exc()}", flush=True)
        raise

def get_last_proposal_row(session_id: str) -> Optional[ProposalLog]:
    # Devuelve la última propuesta asociada a la sesión (o None si no hay).
    with SessionLocal() as db:
        row = db.query(ProposalLog).filter(ProposalLog.session_id == session_id)\
               .order_by(ProposalLog.created_at.desc()).first()
        return row

# --- Feedback ---
def save_feedback(session_id: str, accepted: bool, score: Optional[int] = None, notes: Optional[str] = None) -> Optional[int]:
    """Registra feedback sobre la ÚLTIMA propuesta de esa sesión.
    Devuelve id de feedback o None si no hay propuesta previa."""
    last = get_last_proposal_row(session_id)
    if not last:
        return None
    with SessionLocal() as db:
        fb = ProposalFeedback(
            proposal_id=last.id, session_id=session_id,
            accepted=bool(accepted), score=score, notes=notes
        )
        db.add(fb); db.commit(); db.refresh(fb)
        return int(fb.id)

# --- Proposal views (para recomendaciones personalizadas)
def log_proposal_view(user_id: int, proposal_id: int) -> int:
    with SessionLocal() as db:
        from sqlalchemy import func
        # Evitar duplicados consecutivos: si el último view es el mismo, no duplicar
        last = db.query(ProposalView).filter(ProposalView.user_id == user_id).order_by(ProposalView.created_at.desc()).first()
        if not last or last.proposal_id != proposal_id:
            v = ProposalView(user_id=user_id, proposal_id=proposal_id)
            db.add(v); db.commit(); db.refresh(v)
            return int(v.id)
        return int(last.id)

def list_recent_views(user_id: int, limit: int = 10) -> List[ProposalView]:
    with SessionLocal() as db:
        return db.query(ProposalView).filter(ProposalView.user_id == user_id).order_by(ProposalView.created_at.desc()).limit(limit).all()

# --- Users helpers
def get_user_by_email(email: str) -> Optional[User]:
    # Busca un usuario por email; devuelve None si no existe.
    with SessionLocal() as db:
        return db.query(User).filter(User.email == email).first()

def create_user(email: str, hashed_password: str, full_name: Optional[str] = None) -> User:
    # Crea y devuelve un nuevo usuario.
    with SessionLocal() as db:
        user = User(email=email, hashed_password=hashed_password, full_name=full_name)
        db.add(user); db.commit(); db.refresh(user)
        return user

# --- SavedChat helpers
def create_saved_chat(user_id: int, title: Optional[str], content: str) -> SavedChat:
    # Guarda un chat para el usuario; content suele ser JSON con mensajes.
    with SessionLocal() as db:
        sc = SavedChat(user_id=user_id, title=title, content=content)
        db.add(sc); db.commit(); db.refresh(sc)
        return sc

def list_saved_chats(user_id: int, limit: int = 50):
    # Devuelve los chats del usuario, ordenados por fecha (más recientes primero).
    with SessionLocal() as db:
        rows = db.query(SavedChat).filter(SavedChat.user_id == user_id).order_by(SavedChat.created_at.desc()).limit(limit).all()
        return rows

def get_saved_chat(user_id: int, chat_id: int) -> Optional[SavedChat]:
    # Recupera un chat si pertenece al usuario.
    with SessionLocal() as db:
        return db.query(SavedChat).filter(SavedChat.user_id == user_id, SavedChat.id == chat_id).first()

def update_saved_chat(user_id: int, chat_id: int, title: Optional[str], content: Optional[str]) -> Optional[SavedChat]:
    # Actualiza solo los campos indicados (title y/o content) y devuelve la fila.
    with SessionLocal() as db:
        row = db.query(SavedChat).filter(SavedChat.user_id == user_id, SavedChat.id == chat_id).first()
        if not row:
            return None
        if title is not None: row.title = title
        if content is not None: row.content = content
        row.updated_at = datetime.utcnow()
        db.add(row); db.commit(); db.refresh(row)
        return row


def delete_saved_chat(user_id: int, chat_id: int) -> bool:
    # Borra un chat si pertenece al usuario; devuelve True si borró algo.
    with SessionLocal() as db:
        row = db.query(SavedChat).filter(SavedChat.user_id == user_id, SavedChat.id == chat_id).first()
        if not row:
            return False
        db.delete(row); db.commit()
        return True


# --- Employee helpers ---
def create_employee(user_id: int, name: str, role: str, skills: str, seniority: Optional[str] = None, availability_pct: int = 100) -> Employee:
    """Crea un nuevo empleado para el usuario."""
    with SessionLocal() as db:
        emp = Employee(
            user_id=user_id,
            name=name,
            role=role,
            skills=skills,
            seniority=seniority,
            availability_pct=availability_pct
        )
        db.add(emp); db.commit(); db.refresh(emp)
        return emp


def list_employees(user_id: int, limit: int = 100) -> List[Employee]:
    """Devuelve todos los empleados del usuario."""
    with SessionLocal() as db:
        return db.query(Employee).filter(Employee.user_id == user_id).order_by(Employee.created_at.desc()).limit(limit).all()


def get_employee(user_id: int, employee_id: int) -> Optional[Employee]:
    """Recupera un empleado si pertenece al usuario."""
    with SessionLocal() as db:
        return db.query(Employee).filter(Employee.user_id == user_id, Employee.id == employee_id).first()


def update_employee(user_id: int, employee_id: int, name: Optional[str] = None, role: Optional[str] = None, 
                   skills: Optional[str] = None, seniority: Optional[str] = None, availability_pct: Optional[int] = None) -> Optional[Employee]:
    """Actualiza un empleado del usuario."""
    with SessionLocal() as db:
        row = db.query(Employee).filter(Employee.user_id == user_id, Employee.id == employee_id).first()
        if not row:
            return None
        if name is not None: row.name = name
        if role is not None: row.role = role
        if skills is not None: row.skills = skills
        if seniority is not None: row.seniority = seniority
        if availability_pct is not None: row.availability_pct = availability_pct
        row.updated_at = datetime.utcnow()
        db.add(row); db.commit(); db.refresh(row)
        return row


def delete_employee(user_id: int, employee_id: int) -> bool:
    """Borra un empleado si pertenece al usuario."""
    with SessionLocal() as db:
        row = db.query(Employee).filter(Employee.user_id == user_id, Employee.id == employee_id).first()
        if not row:
            return False
        db.delete(row); db.commit()
        return True


def create_catalog_entry(kind: str, key: str, value: Optional[dict] = None):
    """Crea una entrada de catálogo (idempotente por kind+key)."""
    with SessionLocal() as db:
        existing = db.query(Catalog).filter(Catalog.kind == kind, Catalog.key == key).first()
        if existing:
            return existing
        row = Catalog(kind=kind, key=key, value=value or {})
        db.add(row)
        db.commit()
        db.refresh(row)
        return row


def list_catalog(kind: str) -> List[Catalog]:
    """Devuelve todas las entradas de un catálogo concreto."""
    with SessionLocal() as db:
        return db.query(Catalog).filter(Catalog.kind == kind).order_by(Catalog.created_at.desc()).all()


# Recrear tablas nuevas si añadimos modelos después del create_all inicial
Base.metadata.create_all(engine)
