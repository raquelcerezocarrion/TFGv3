from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from pydantic import BaseModel, Field
from backend.memory.conversation import save_message, get_history

router = APIRouter()

class ChatRequest(BaseModel):
    session_id: str = Field(..., min_length=1)
    message: str = Field(..., min_length=1)

class ChatResponse(BaseModel):
    reply: str
    explanation: str

@router.post("/message", response_model=ChatResponse)
def chat_message(req: ChatRequest):
    save_message(req.session_id, role="user", content=req.message)
    reply = f"Entendido: «{req.message}». (Respuesta de prueba Parte 1)"
    save_message(req.session_id, role="assistant", content=reply)
    return ChatResponse(
        reply=reply,
        explanation="Eco simple para validar el flujo (Parte 1).",
    )

@router.websocket("/ws")
async def chat_ws(websocket: WebSocket, session_id: str):
    await websocket.accept()
    await websocket.send_text("👋 Hola, soy el asistente (Parte 1). Escribe y te respondo con eco.")
    try:
        while True:
            text = await websocket.receive_text()
            save_message(session_id, role="user", content=text)
            reply = f"Eco: {text}"
            save_message(session_id, role="assistant", content=reply)
            await websocket.send_text(reply)
    except WebSocketDisconnect:
        pass

@router.get("/history/{session_id}")
def history(session_id: str, limit: int = 50):
    return {"session_id": session_id, "messages": get_history(session_id, limit=limit)}
