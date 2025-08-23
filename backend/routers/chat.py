# backend/routers/chat.py
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from pydantic import BaseModel
from typing import Optional, Dict, Any

from backend.engine.brain import generate_reply

router = APIRouter()

class ChatIn(BaseModel):
    message: str
    session_id: Optional[str] = None

def _reply(payload: ChatIn) -> Dict[str, Any]:
    sid = payload.session_id or "default"
    text, debug = generate_reply(sid, payload.message)
    return {"reply": text, "debug": debug, "session_id": sid}

# --- Endpoints HTTP (cubrimos varios paths habituales) ---
@router.post("/")
async def chat_root(payload: ChatIn):
    return _reply(payload)

@router.post("/send")
async def chat_send(payload: ChatIn):
    return _reply(payload)

@router.post("/message")
async def chat_message(payload: ChatIn):
    return _reply(payload)

# --- WebSocket opcional (el frontend puede intentar ws y hacer fallback) ---
@router.websocket("/ws")
async def chat_ws(ws: WebSocket):
    await ws.accept()
    sid = "ws"
    try:
        while True:
            msg = await ws.receive_text()
            text, _ = generate_reply(sid, msg)
            await ws.send_text(text)
    except WebSocketDisconnect:
        # conexión cerrada por el cliente
        return
