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

class SavedChatOut(BaseModel):
    id: int
    title: Optional[str]
    content: str
    created_at: str
    updated_at: str

def _decode_token(token: str):
    try:
        return jwt.decode(token, settings.APP_NAME, algorithms=["HS256"])
    except Exception:
        return None

def get_current_user(authorization: Optional[str] = Header(None)):
    if not authorization:
        raise HTTPException(status_code=401, detail="Missing Authorization header")
    parts = authorization.split()
    if len(parts) != 2 or parts[0].lower() != 'bearer':
        raise HTTPException(status_code=401, detail="Invalid Authorization header")
    token = parts[1]
    payload = _decode_token(token)
    if not payload or 'user_id' not in payload:
        raise HTTPException(status_code=401, detail="Invalid token")
    user = state_store.get_user_by_email(payload.get('sub'))
    if not user:
        raise HTTPException(status_code=401, detail="User not found")
    return user


@router.get('/me', response_model=UserOut)
def me(current_user = Depends(get_current_user)):
    return { 'id': current_user.id, 'email': current_user.email, 'full_name': current_user.full_name }


@router.get('/chats', response_model=List[SavedChatOut])
def list_chats(current_user = Depends(get_current_user)):
    rows = state_store.list_saved_chats(current_user.id)
    return [{ 'id': r.id, 'title': r.title, 'content': r.content, 'created_at': r.created_at.isoformat(), 'updated_at': r.updated_at.isoformat() } for r in rows]


@router.post('/chats', response_model=SavedChatOut)
def create_chat(payload: SavedChatIn, current_user = Depends(get_current_user)):
    sc = state_store.create_saved_chat(current_user.id, payload.title, payload.content)
    return { 'id': sc.id, 'title': sc.title, 'content': sc.content, 'created_at': sc.created_at.isoformat(), 'updated_at': sc.updated_at.isoformat() }


@router.get('/chats/{chat_id}', response_model=SavedChatOut)
def get_chat(chat_id: int, current_user = Depends(get_current_user)):
    sc = state_store.get_saved_chat(current_user.id, chat_id)
    if not sc:
        raise HTTPException(status_code=404, detail='Chat not found')
    return { 'id': sc.id, 'title': sc.title, 'content': sc.content, 'created_at': sc.created_at.isoformat(), 'updated_at': sc.updated_at.isoformat() }


@router.put('/chats/{chat_id}', response_model=SavedChatOut)
def update_chat(chat_id: int, payload: SavedChatIn, current_user = Depends(get_current_user)):
    sc = state_store.update_saved_chat(current_user.id, chat_id, payload.title, payload.content)
    if not sc:
        raise HTTPException(status_code=404, detail='Chat not found')
    return { 'id': sc.id, 'title': sc.title, 'content': sc.content, 'created_at': sc.created_at.isoformat(), 'updated_at': sc.updated_at.isoformat() }


@router.delete('/chats/{chat_id}')
def delete_chat(chat_id: int, current_user = Depends(get_current_user)):
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
