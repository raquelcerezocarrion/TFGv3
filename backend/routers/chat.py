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
    # Aquí delego en el "brain" para que piense la respuesta.
    # generate_reply devuelve una tupla (texto, info_debug) 
    # es el texto para mostrar al usuario y algo de info por si el frontend
    # quiere mostrar detalles de diagnóstico.
    text, debug = generate_reply(sid, payload.message)
    # Devolvemos un objeto simple y predecible para el frontend.
    return {"reply": text, "debug": debug, "session_id": sid}

# --- Endpoints HTTP (cubrimos varios paths habituales) ---
@router.post("/")
async def chat_root(payload: ChatIn):
    # Punto de entrada: mando el mensaje al brain y devuelvo lo que saque.
    return _reply(payload)

@router.post("/send")
async def chat_send(payload: ChatIn):
    # Un nombre alternativo para enviar mensajes desde distintos clientes.
    # Funciona igual que el endpoint raíz.
    return _reply(payload)

@router.post("/message")
async def chat_message(payload: ChatIn):
    # Otro alias histórico: lo dejo por compatibilidad con clientes antiguos.
    return _reply(payload)

# --- WebSocket opcional (el frontend puede intentar ws y hacer fallback) ---
@router.websocket("/ws")
async def chat_ws(ws: WebSocket):
    await ws.accept()
    # WebSocket: recibo texto, consulto el brain y reenvío la respuesta.
    # No hay protocolo complejo aquí; si luego quieres añadir eventos, podemos.
    sid = "ws"
    try:
        while True:
            msg = await ws.receive_text()
            text, _ = generate_reply(sid, msg)
           
            await ws.send_text(text)
    except WebSocketDisconnect:
        # cliente se desconectó
        return
