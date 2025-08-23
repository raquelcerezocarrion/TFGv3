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
    rows = list_messages(session_id, limit=limit)  # viene DESC
    rows = list(reversed(rows))                   # lo pasamos a ASC
    return [ConversationMessage(**r) for r in rows]

