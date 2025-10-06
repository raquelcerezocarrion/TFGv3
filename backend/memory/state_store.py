from __future__ import annotations
import json, os
from datetime import datetime
from pathlib import Path
from typing import List, Optional, Dict, Any

from sqlalchemy import (
    create_engine, Column, Integer, String, DateTime, Text, JSON, ForeignKey, Boolean
)
from sqlalchemy.orm import declarative_base, sessionmaker, relationship

# --- Ruta y engine ---
DATA_DIR = Path("data"); DATA_DIR.mkdir(parents=True, exist_ok=True)
DB_URL = f"sqlite:///{(DATA_DIR / 'app.db').as_posix()}"

engine = create_engine(DB_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)
Base = declarative_base()

# --- Modelos ---
class ConversationMessage(Base):
    __tablename__ = "conversation_messages"
    id = Column(Integer, primary_key=True, autoincrement=True)
    session_id = Column(String, index=True, nullable=False)
    role = Column(String, nullable=False)   # "user" | "assistant"
    content = Column(Text, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

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

# --- Usuario / Auth (simple)
class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True, autoincrement=True)
    email = Column(String, unique=True, index=True, nullable=False)
    hashed_password = Column(String, nullable=False)
    full_name = Column(String, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)


Base.metadata.create_all(engine)

# --- Conversación (compatibilidad con tu código) ---
def log_message(session_id: str, role: str, content: str) -> None:
    with SessionLocal() as db:
        db.add(ConversationMessage(session_id=session_id, role=role, content=content))
        db.commit()

def list_messages(session_id: str, limit: int = 50) -> List[ConversationMessage]:
    with SessionLocal() as db:
        q = db.query(ConversationMessage).filter(ConversationMessage.session_id == session_id)\
              .order_by(ConversationMessage.created_at.desc()).limit(limit).all()
        return list(reversed(q))  # cronológico

# --- Propuestas ---
def save_proposal(session_id: str, requirements: str, proposal: Dict[str, Any]) -> int:
    with SessionLocal() as db:
        row = ProposalLog(session_id=session_id, requirements=requirements, proposal_json=proposal)
        db.add(row); db.commit(); db.refresh(row)
        return int(row.id)

def get_last_proposal_row(session_id: str) -> Optional[ProposalLog]:
    with SessionLocal() as db:
        row = db.query(ProposalLog).filter(ProposalLog.session_id == session_id)\
               .order_by(ProposalLog.created_at.desc()).first()
        return row

# --- Feedback ---
def save_feedback(session_id: str, accepted: bool, score: Optional[int] = None, notes: Optional[str] = None) -> Optional[int]:
    """Registra feedback sobre la ÚLTIMA propuesta de esa sesión. Devuelve id de feedback o None si no hay propuesta."""
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

# --- Users helpers
def get_user_by_email(email: str) -> Optional[User]:
    with SessionLocal() as db:
        return db.query(User).filter(User.email == email).first()

def create_user(email: str, hashed_password: str, full_name: Optional[str] = None) -> User:
    with SessionLocal() as db:
        user = User(email=email, hashed_password=hashed_password, full_name=full_name)
        db.add(user); db.commit(); db.refresh(user)
        return user
