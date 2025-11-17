from fastapi import APIRouter, Depends, HTTPException, Header
from pydantic import BaseModel, Field
from typing import Optional, List
import jwt

from backend.core.config import settings
from backend.memory import state_store

router = APIRouter()

class UserOut(BaseModel):
    id: int
    email: str
    full_name: Optional[str]

class SavedChatIn(BaseModel):
    title: Optional[str]
    content: str = Field(..., min_length=1)


class SavedChatUpdate(BaseModel):
    """Model used for updating a saved chat: fields optional so the frontend can
    send only the title when renaming (it used to send content: '' which failed
    validation)."""
    title: Optional[str] = None
    content: Optional[str] = None

class SavedChatOut(BaseModel):
    id: int
    title: Optional[str]
    content: str
    created_at: str
    updated_at: str


class EmployeeIn(BaseModel):
    name: str = Field(..., min_length=1)
    role: str = Field(..., min_length=1)
    skills: str = Field(..., min_length=1)  # CSV: "Python, Django, AWS"
    seniority: Optional[str] = None  # "Junior", "Mid", "Senior", etc.
    availability_pct: int = Field(default=100, ge=0, le=100)


class EmployeeUpdate(BaseModel):
    name: Optional[str] = None
    role: Optional[str] = None
    skills: Optional[str] = None
    seniority: Optional[str] = None
    availability_pct: Optional[int] = Field(default=None, ge=0, le=100)


class EmployeeOut(BaseModel):
    id: int
    name: str
    role: str
    skills: str
    seniority: Optional[str]
    availability_pct: int
    created_at: str
    updated_at: str


def _decode_token(token: str):
    # Intento decodificar el JWT con la clave de la app. Si algo falla, devuelvo None
    # para que el flujo de autenticación lo capture y responda con 401.
    try:
        return jwt.decode(token, settings.APP_NAME, algorithms=["HS256"])
    except Exception:
        return None

def get_current_user(authorization: Optional[str] = Header(None)):
    # Header Authorization simple: esperamos 'Bearer <token>'. Si no está bien
    # formado, devolvemos 401.
    if not authorization:
        raise HTTPException(status_code=401, detail="Missing Authorization header")
    parts = authorization.split()
    if len(parts) != 2 or parts[0].lower() != 'bearer':
        raise HTTPException(status_code=401, detail="Invalid Authorization header")
    token = parts[1]
    payload = _decode_token(token)
    if not payload or 'user_id' not in payload:
        raise HTTPException(status_code=401, detail="Invalid token")
    # Buscamos el usuario por email (lo guardamos en 'sub' al crear el token).
    user = state_store.get_user_by_email(payload.get('sub'))
    if not user:
        raise HTTPException(status_code=401, detail="User not found")
    return user


@router.get('/me', response_model=UserOut)
def me(current_user = Depends(get_current_user)):
    return { 'id': current_user.id, 'email': current_user.email, 'full_name': current_user.full_name }


@router.get('/chats', response_model=List[SavedChatOut])
def list_chats(current_user = Depends(get_current_user)):
    # Devuelvo los chats guardados del usuario en un formato fácil de consumir
    rows = state_store.list_saved_chats(current_user.id)
    return [{ 'id': r.id, 'title': r.title, 'content': r.content, 'created_at': r.created_at.isoformat(), 'updated_at': r.updated_at.isoformat() } for r in rows]


@router.post('/chats', response_model=SavedChatOut)
def create_chat(payload: SavedChatIn, current_user = Depends(get_current_user)):
    # Creo un chat guardado con el contenido que me mandes (puede ser JSON o texto)
    sc = state_store.create_saved_chat(current_user.id, payload.title, payload.content)
    return { 'id': sc.id, 'title': sc.title, 'content': sc.content, 'created_at': sc.created_at.isoformat(), 'updated_at': sc.updated_at.isoformat() }


@router.get('/chats/{chat_id}', response_model=SavedChatOut)
def get_chat(chat_id: int, current_user = Depends(get_current_user)):
    # Recupero un chat guardado por id; si no existe, 404.
    sc = state_store.get_saved_chat(current_user.id, chat_id)
    if not sc:
        raise HTTPException(status_code=404, detail='Chat not found')
    return { 'id': sc.id, 'title': sc.title, 'content': sc.content, 'created_at': sc.created_at.isoformat(), 'updated_at': sc.updated_at.isoformat() }


@router.put('/chats/{chat_id}', response_model=SavedChatOut)
def update_chat(chat_id: int, payload: SavedChatUpdate, current_user = Depends(get_current_user)):
    # Actualizo solo lo que venga en el payload (título y/o contenido). El
    # state_store hace la mayor parte del trabajo; aquí solo controlamos errores.
    sc = state_store.update_saved_chat(current_user.id, chat_id, payload.title, payload.content)
    if not sc:
        raise HTTPException(status_code=404, detail='Chat not found')
    return { 'id': sc.id, 'title': sc.title, 'content': sc.content, 'created_at': sc.created_at.isoformat(), 'updated_at': sc.updated_at.isoformat() }


@router.delete('/chats/{chat_id}')
def delete_chat(chat_id: int, current_user = Depends(get_current_user)):
    # Borro el chat del usuario. Devuelvo un pequeño objeto indicando éxito.
    ok = state_store.delete_saved_chat(current_user.id, chat_id)
    if not ok:
        raise HTTPException(status_code=404, detail='Chat not found')
    return { 'status': 'deleted' }


@router.post('/chats/{chat_id}/continue')
def continue_chat(chat_id: int, current_user = Depends(get_current_user)):
    sc = state_store.get_saved_chat(current_user.id, chat_id)
    if not sc:
        raise HTTPException(status_code=404, detail='Chat not found')
    # create a session id for continuing; simple approach: session_{chat_id}_{ts}
    from datetime import datetime
    session_id = f"saved-{chat_id}-{int(datetime.utcnow().timestamp())}"
    return { 'session_id': session_id }


# --- Employees endpoints ---
@router.get('/employees', response_model=List[EmployeeOut])
def list_employees(current_user = Depends(get_current_user)):
    """Devuelve todos los empleados del usuario."""
    rows = state_store.list_employees(current_user.id)
    return [{
        'id': e.id,
        'name': e.name,
        'role': e.role,
        'skills': e.skills,
        'seniority': e.seniority,
        'availability_pct': e.availability_pct,
        'created_at': e.created_at.isoformat(),
        'updated_at': e.updated_at.isoformat()
    } for e in rows]


@router.post('/employees', response_model=EmployeeOut)
def create_employee(payload: EmployeeIn, current_user = Depends(get_current_user)):
    """Crea un nuevo empleado."""
    emp = state_store.create_employee(
        user_id=current_user.id,
        name=payload.name,
        role=payload.role,
        skills=payload.skills,
        seniority=payload.seniority,
        availability_pct=payload.availability_pct
    )
    return {
        'id': emp.id,
        'name': emp.name,
        'role': emp.role,
        'skills': emp.skills,
        'seniority': emp.seniority,
        'availability_pct': emp.availability_pct,
        'created_at': emp.created_at.isoformat(),
        'updated_at': emp.updated_at.isoformat()
    }


@router.get('/employees/{employee_id}', response_model=EmployeeOut)
def get_employee(employee_id: int, current_user = Depends(get_current_user)):
    """Recupera un empleado específico."""
    emp = state_store.get_employee(current_user.id, employee_id)
    if not emp:
        raise HTTPException(status_code=404, detail='Employee not found')
    return {
        'id': emp.id,
        'name': emp.name,
        'role': emp.role,
        'skills': emp.skills,
        'seniority': emp.seniority,
        'availability_pct': emp.availability_pct,
        'created_at': emp.created_at.isoformat(),
        'updated_at': emp.updated_at.isoformat()
    }


@router.put('/employees/{employee_id}', response_model=EmployeeOut)
def update_employee(employee_id: int, payload: EmployeeUpdate, current_user = Depends(get_current_user)):
    """Actualiza un empleado existente."""
    emp = state_store.update_employee(
        user_id=current_user.id,
        employee_id=employee_id,
        name=payload.name,
        role=payload.role,
        skills=payload.skills,
        seniority=payload.seniority,
        availability_pct=payload.availability_pct
    )
    if not emp:
        raise HTTPException(status_code=404, detail='Employee not found')
    return {
        'id': emp.id,
        'name': emp.name,
        'role': emp.role,
        'skills': emp.skills,
        'seniority': emp.seniority,
        'availability_pct': emp.availability_pct,
        'created_at': emp.created_at.isoformat(),
        'updated_at': emp.updated_at.isoformat()
    }


@router.delete('/employees/{employee_id}')
def delete_employee(employee_id: int, current_user = Depends(get_current_user)):
    """Elimina un empleado."""
    ok = state_store.delete_employee(current_user.id, employee_id)
    if not ok:
        raise HTTPException(status_code=404, detail='Employee not found')
    return { 'status': 'deleted' }

