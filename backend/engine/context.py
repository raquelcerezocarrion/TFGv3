# backend/engine/context.py
from typing import Tuple, Dict, Any, Optional

# Memoria simple en proceso por sesión
_SESS: Dict[str, Dict[str, Any]] = {}

def get_last_proposal(session_id: str) -> Tuple[Optional[Dict[str, Any]], Optional[str]]:
    s = _SESS.get(session_id, {})
    return s.get("proposal"), s.get("requirements")

def set_last_proposal(session_id: str, proposal: Dict[str, Any], requirements: str) -> None:
    s = _SESS.setdefault(session_id, {})
    s["proposal"] = proposal
    s["requirements"] = requirements

# ---- Petición de cambio de metodología (confirmación sí/no)
def get_pending_change(session_id: str) -> Optional[Dict[str, Any]]:
    return _SESS.get(session_id, {}).get("pending_change")

def set_pending_change(session_id: str, target_method: str) -> None:
    _SESS.setdefault(session_id, {})["pending_change"] = {"target_method": target_method}

def clear_pending_change(session_id: str) -> None:
    _SESS.setdefault(session_id, {}).pop("pending_change", None)

# ---- NUEVO: recordar el área/tema de la última respuesta
def set_last_area(session_id: str, area: Optional[str]) -> None:
    _SESS.setdefault(session_id, {})["last_area"] = area

def get_last_area(session_id: str) -> Optional[str]:
    return _SESS.get(session_id, {}).get("last_area")

# ---- NUEVO: valores genéricos de contexto
def set_context_value(session_id: str, key: str, value: Any) -> None:
    _SESS.setdefault(session_id, {})[key] = value

def get_context_value(session_id: str, key: str, default: Any = None) -> Any:
    return _SESS.get(session_id, {}).get(key, default)

def clear_context_value(session_id: str, key: str) -> None:
    _SESS.setdefault(session_id, {}).pop(key, None)
