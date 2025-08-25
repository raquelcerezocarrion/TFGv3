# backend/engine/context.py
from typing import Dict, Tuple, Optional, Any

# Memoria en proceso (por sesión). Para TFG es suficiente.
_LAST_PROPOSAL: Dict[str, Tuple[Dict[str, Any], str]] = {}
_PENDING_CHANGE: Dict[str, Dict[str, str]] = {}  # p.ej. {"target_method": "Scrum"}

def get_last_proposal(session_id: str) -> Tuple[Optional[Dict[str, Any]], Optional[str]]:
    """Devuelve (propuesta, requisitos) de la sesión o (None, None)."""
    return _LAST_PROPOSAL.get(session_id, (None, None))

def set_last_proposal(session_id: str, proposal: Dict[str, Any], requirements: str) -> None:
    """Guarda la última propuesta y los requisitos asociados."""
    _LAST_PROPOSAL[session_id] = (proposal, requirements)

# --- Cambio de metodología pendiente (sí/no) ---
def set_pending_change(session_id: str, target_method: str) -> None:
    _PENDING_CHANGE[session_id] = {"target_method": target_method}

def get_pending_change(session_id: str) -> Optional[Dict[str, str]]:
    return _PENDING_CHANGE.get(session_id)

def clear_pending_change(session_id: str) -> None:
    _PENDING_CHANGE.pop(session_id, None)
