# backend/routers/chat.py
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from pydantic import BaseModel
from typing import Optional, Dict, Any
import logging

from backend.engine.brain import generate_reply, _project_context_summary
from backend.engine.context import get_last_proposal

logger = logging.getLogger(__name__)
router = APIRouter()

class ChatIn(BaseModel):
    message: str
    session_id: Optional[str] = None
    # Optional phase context sent by the frontend when the chat is scoped to a phase
    phase: Optional[str] = None

def _reply(payload: ChatIn) -> Dict[str, Any]:
    sid = payload.session_id or "default"
    # Si el frontend proporciona el contexto de fase, anteponerlo al texto
    # para que el motor (brain) lo use en su proceso de matching.
    msg = payload.message or ""
    if getattr(payload, 'phase', None):
        try:
            msg = f"Fase seleccionada: {payload.phase}\n" + msg
        except Exception:
            pass

    # Aquí delego en el "brain" para que piense la respuesta.
    # generate_reply devuelve una tupla (texto, info_debug)
    # es el texto para mostrar al usuario y algo de info por si el frontend
    # quiere mostrar detalles de diagnóstico.
    text, debug = generate_reply(sid, msg)
    # Si hay una propuesta asociada a la sesión, añadimos un resumen de contexto
    try:
        prop, _ = get_last_proposal(sid)
        if prop:
            ctx = _project_context_summary(prop)
            if ctx and "Contexto del proyecto:" not in text:
                text = text + "\n\nContexto del proyecto: " + ctx
    except Exception:
        pass
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
    # intentar leer session_id de la querystring si existe
    sid = "ws"
    try:
        qs = ws.scope.get("query_string", b"").decode()
        from urllib.parse import parse_qs
        params = parse_qs(qs)
        sid = params.get("session_id", [sid])[0]
    except Exception:
        pass
    try:
        while True:
            raw = await ws.receive_text()
            logger.info(f"[WS {sid}] Recibido raw: {raw[:100]}...")  # Primeros 100 chars
            
            # aceptar tanto texto plano como JSON con {message, phase}
            msg_text = raw
            
            # Validar que no sea "[object Object]" (error común del frontend)
            if raw.strip() == "[object Object]":
                error_msg = "⚠️ Error: El mensaje recibido está vacío o mal formateado. Por favor, envía un mensaje válido."
                logger.warning(f"[WS {sid}] {error_msg}")
                await ws.send_text(error_msg)
                continue
            
            try:
                import json as _json
                parsed = _json.loads(raw)
                logger.info(f"[WS {sid}] JSON parseado: {parsed}")
                
                if isinstance(parsed, dict):
                    # Intentar extraer el mensaje de diferentes campos posibles
                    msg_text = (parsed.get('message') or 
                               parsed.get('text') or 
                               parsed.get('content') or '')
                    
                    # Si aún está vacío, intentar convertir el objeto completo a string
                    if not msg_text and parsed:
                        msg_text = str(parsed)
                    
                    if parsed.get('phase'):
                        msg_text = f"Fase seleccionada: {parsed.get('phase')}\n" + msg_text
                elif isinstance(parsed, str):
                    msg_text = parsed
            except Exception as e:
                # no es JSON válido, tratamos como texto plano
                logger.info(f"[WS {sid}] No es JSON, usando raw como texto: {e}")
                msg_text = raw
            
            # Validación final: si el mensaje está vacío o sigue siendo "[object Object]", avisar
            if not msg_text.strip() or msg_text.strip() == "[object Object]":
                error_msg = "⚠️ Error: El mensaje está vacío. Por favor, escribe algo."
                logger.warning(f"[WS {sid}] {error_msg}")
                await ws.send_text(error_msg)
                continue
            
            logger.info(f"[WS {sid}] Procesando mensaje: {msg_text[:100]}...")
            text, _ = generate_reply(sid, msg_text)
            # añadir contexto si existe propuesta para esta sesión
            try:
                prop, _ = get_last_proposal(sid)
                if prop:
                    ctx = _project_context_summary(prop)
                    if ctx and "Contexto del proyecto:" not in text:
                        text = text + "\n\nContexto del proyecto: " + ctx
            except Exception:
                pass
            await ws.send_text(text)
    except WebSocketDisconnect:
        # cliente se desconectó
        return
