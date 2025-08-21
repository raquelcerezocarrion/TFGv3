from typing import List, Dict, Any
from sqlalchemy import select, desc
from backend.memory.state_store import get_session, ConversationMessage

def save_message(session_id: str, role: str, content: str) -> None:
    with get_session() as s:
        s.add(ConversationMessage(session_id=session_id, role=role, content=content))
        s.commit()

def get_history(session_id: str, limit: int = 50) -> List[Dict[str, Any]]:
    with get_session() as s:
        stmt = (
            select(ConversationMessage)
            .where(ConversationMessage.session_id == session_id)
            .order_by(desc(ConversationMessage.created_at))
            .limit(limit)
        )
        rows = s.execute(stmt).scalars().all()
        data = [
            {"role": r.role, "content": r.content, "created_at": r.created_at.isoformat()}
            for r in reversed(rows)
        ]
        return data
