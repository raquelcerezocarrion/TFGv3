from __future__ import annotations
from dataclasses import dataclass
from typing import List

from backend.memory.state_store import log_message, list_messages

@dataclass
class ConversationMessage:
    role: str
    text: str
    created_at: str  # ISO-8601

def save_message(session_id: str, role: str, text: str) -> None:
    log_message(session_id, role, text)

def get_history(session_id: str, limit: int = 50) -> List[ConversationMessage]:
    # `list_messages` devuelve objetos ORM ordenados cronológicamente (ASC).
    rows = list_messages(session_id, limit=limit)
    out: List[ConversationMessage] = []
    for r in rows:
        # r es una instancia ORM; construimos el dataclass usando atributos
        try:
            created = r.created_at.isoformat() if getattr(r, 'created_at', None) else ''
        except Exception:
            created = str(getattr(r, 'created_at', ''))
        out.append(ConversationMessage(role=getattr(r, 'role', ''), text=getattr(r, 'content', ''), created_at=created))
    return out

