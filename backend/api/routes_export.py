# -*- coding: utf-8 -*-
from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from typing import List, Dict, Any, Optional
from datetime import datetime
from io import BytesIO

from backend.engine.pdf_exporter import render_chat_pdf

router = APIRouter(prefix="/export", tags=["export"])

class ChatMessage(BaseModel):
    role: str
    content: str
    ts: Optional[str] = None
    name: Optional[str] = None

class ChatExportIn(BaseModel):
    conversation_id: Optional[str] = None
    title: Optional[str] = "Conversación"
    messages: Optional[List[ChatMessage]] = None

@router.post("/chat.pdf")
def export_chat_pdf(payload: ChatExportIn):
    # Si en tu sistema puedes recuperar los mensajes por conversation_id, hazlo aquí.
    # Ejemplo (pseudo):
    # if not payload.messages and payload.conversation_id:
    #     payload.messages = load_messages_from_store(payload.conversation_id)

    msgs: List[Dict[str, Any]] = [m.dict() for m in (payload.messages or [])]
    if not msgs:
        raise HTTPException(status_code=400, detail="No hay mensajes para exportar.")

    title = payload.title or "Conversación"
    pdf_bytes = render_chat_pdf(msgs, title=title)

    fname = f"chat_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.pdf"
    return StreamingResponse(
        BytesIO(pdf_bytes),
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'attachment; filename="{fname}"'
        }
    )
