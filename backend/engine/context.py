# backend/engine/context.py
from typing import Dict, Any, Optional, Tuple

_STATE: Dict[str, Dict[str, Any]] = {}

def set_last_proposal(session_id: str, proposal: Dict[str, Any], requirements: str) -> None:
    """Guarda la última propuesta generada para esta sesión."""
    _STATE[session_id] = {"proposal": proposal, "requirements": requirements}

def get_last_proposal(session_id: str) -> Tuple[Optional[Dict[str, Any]], Optional[str]]:
    """Devuelve (proposal, requirements) o (None, None) si no hay."""
    data = _STATE.get(session_id)
    if not data:
        return None, None
    return data.get("proposal"), data.get("requirements")
