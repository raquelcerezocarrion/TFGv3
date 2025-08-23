# backend/memory/state_store.py
from __future__ import annotations

import os
from pathlib import Path
from datetime import datetime
from typing import Optional, Dict, Any, Tuple, List

from sqlalchemy import (
    create_engine, Column, String, DateTime, Integer, ForeignKey, Text, JSON, Float, Boolean
)
from sqlalchemy.orm import declarative_base, sessionmaker, relationship

# -------------------------------------------------------------------
# Configuración DB (sin pydantic_settings)
# -------------------------------------------------------------------
# Usa DATABASE_URL si existe; por defecto SQLite local ./data/app.db
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./data/app.db")

# Crear carpeta data/ si es SQLite local
if DATABASE_URL.startswith("sqlite:///"):
    Path("./data").mkdir(parents=True, exist_ok=True)

# Para SQLite multihilo en Uvicorn
engine = create_engine(
    DATABASE_URL,
    echo=False,
    future=True,
    connect_args={"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}
)

SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)
Base = declarative_base()

# -------------------------------------------------------------------
# Modelos
# -------------------------------------------------------------------

class DbSession(Base):
    __tablename__ = "sessions"
    id = Column(String, primary_key=True)        # session_id del chat
    started_at = Column(DateTime, default=datetime.utcnow)
    meta_json = Column(JSON, nullable=True)

    messages = relationship("MessageLog", back_populates="session", cascade="all, delete-orphan")
    proposals = relationship("ProposalLog", back_populates="session", cascade="all, delete-orphan")


class MessageLog(Base):
    __tablename__ = "messages"
    id = Column(Integer, primary_key=True, autoincrement=True)
    session_id = Column(String, ForeignKey("sessions.id", ondelete="CASCADE"), index=True, nullable=False)
    role = Column(String, nullable=False)        # "user" | "assistant"
    text = Column(Text, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, index=True)

    session = relationship("DbSession", back_populates="messages")


class ProposalLog(Base):
    __tablename__ = "proposals"
    id = Column(Integer, primary_key=True, autoincrement=True)
    session_id = Column(String, ForeignKey("sessions.id", ondelete="CASCADE"), index=True, nullable=False)
    requirements = Column(Text, nullable=False)
    proposal_json = Column(JSON, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, index=True)
    accepted = Column(Boolean, default=None)
    notes = Column(Text, nullable=True)

    session = relationship("DbSession", back_populates="proposals")


class ModelRegistry(Base):
    __tablename__ = "model_registry"
    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String, index=True)            # "intents" | "methodology" | "effort"
    version = Column(String, default="0")
    path = Column(String)
    metrics_json = Column(JSON, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, index=True)

# -------------------------------------------------------------------
# API del store
# -------------------------------------------------------------------

def init_db() -> None:
    Base.metadata.create_all(bind=engine)

def _ensure_session(db, session_id: str) -> DbSession:
    s = db.get(DbSession, session_id)
    if s is None:
        s = DbSession(id=session_id, started_at=datetime.utcnow())
        db.add(s)
        db.flush()
    return s

def log_message(session_id: str, role: str, text: str) -> None:
    with SessionLocal() as db:
        _ensure_session(db, session_id)
        msg = MessageLog(session_id=session_id, role=role, text=text)
        db.add(msg)
        db.commit()

def save_proposal(session_id: str, requirements: str, proposal: Dict[str, Any]) -> int:
    with SessionLocal() as db:
        _ensure_session(db, session_id)
        row = ProposalLog(session_id=session_id, requirements=requirements, proposal_json=proposal)
        db.add(row)
        db.commit()
        db.refresh(row)
        return int(row.id)

def load_last_proposal(session_id: str) -> Tuple[Optional[Dict[str, Any]], Optional[str]]:
    with SessionLocal() as db:
        row = (
            db.query(ProposalLog)
            .filter(ProposalLog.session_id == session_id)
            .order_by(ProposalLog.created_at.desc())
            .first()
        )
        if not row:
            return None, None
        return row.proposal_json, row.requirements

def feedback_proposal(proposal_id: int, accepted: Optional[bool], notes: Optional[str] = None) -> None:
    with SessionLocal() as db:
        row = db.query(ProposalLog).filter(ProposalLog.id == proposal_id).first()
        if not row:
            return
        row.accepted = accepted
        if notes:
            row.notes = notes
        db.commit()

def list_messages(session_id: str, limit: int = 50) -> List[Dict[str, Any]]:
    with SessionLocal() as db:
        rows = (
            db.query(MessageLog)
            .filter(MessageLog.session_id == session_id)
            .order_by(MessageLog.created_at.desc())
            .limit(limit)
            .all()
        )
        return [
            {"role": r.role, "text": r.text, "created_at": r.created_at.isoformat()}
            for r in rows
        ]
