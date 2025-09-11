# backend/app.py
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from typing import List, Optional, Dict, Any
from datetime import datetime
from io import BytesIO
import importlib

# ---------------- PDF mínimo inline (evita problemas de import) ----------------
# Requiere: pip install reportlab
from reportlab.lib.pagesizes import A4
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_LEFT, TA_RIGHT
from reportlab.lib import colors
from reportlab.lib.units import mm

def _fmt_dt(ts: Optional[str]) -> str:
    if not ts:
        return ""
    try:
        dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
        return dt.astimezone().strftime("%Y-%m-%d %H:%M")
    except Exception:
        return ts

def _escape(s: str) -> str:
    return (s or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

def render_chat_pdf_inline(messages: List[Dict[str, Any]], title: str = "Conversación") -> bytes:
    buf = BytesIO()
    doc = SimpleDocTemplate(
        buf, pagesize=A4,
        leftMargin=18*mm, rightMargin=18*mm, topMargin=16*mm, bottomMargin=16*mm,
        title=title
    )
    styles = getSampleStyleSheet()
    h1 = ParagraphStyle("H1", parent=styles["Heading1"], fontName="Helvetica-Bold", fontSize=18, spaceAfter=6)
    meta = ParagraphStyle("Meta", parent=styles["Normal"], textColor=colors.grey, fontSize=9, spaceAfter=8)
    s_user = ParagraphStyle("User", parent=styles["BodyText"], backColor=colors.whitesmoke,
                            borderColor=colors.lightgrey, borderWidth=0.5, borderPadding=(6,6,6,6),
                            spaceAfter=6, leading=14, alignment=TA_RIGHT)
    s_assi = ParagraphStyle("Asst", parent=styles["BodyText"], backColor=colors.Color(0.96,0.99,1.0),
                            borderColor=colors.Color(0.75,0.85,0.95), borderWidth=0.5, borderPadding=(6,6,6,6),
                            spaceAfter=6, leading=14, alignment=TA_LEFT)
    s_sys  = ParagraphStyle("Sys",  parent=styles["BodyText"], textColor=colors.darkgray,
                            backColor=colors.Color(0.97,0.97,0.97), borderColor=colors.Color(0.85,0.85,0.85),
                            borderWidth=0.5, borderPadding=(6,6,6,6), spaceAfter=6, leading=14, alignment=TA_LEFT)

    story = [Paragraph(title, h1), Paragraph("Exportado automáticamente", meta), Spacer(1, 4*mm)]

    for m in messages or []:
        role = (m.get("role") or "").lower().strip()
        who = m.get("name") or ("Usuario" if role == "user" else ("Asistente" if role == "assistant" else "Sistema"))
        ts = _fmt_dt(m.get("ts"))
        header = f"<b>{_escape(who)}</b>" + (f" · {ts}" if ts else "")
        raw = _escape(str(m.get("content") or "")).replace("\n", "<br/>")
        style = s_user if role == "user" else (s_assi if role == "assistant" else s_sys)
        story.append(Paragraph(header, meta))
        story.append(Paragraph(raw, style))
        story.append(Spacer(1, 2*mm))

    doc.build(story)
    pdf = buf.getvalue()
    buf.close()
    return pdf
# -------------------------------------------------------------------------------

# Routers principales existentes
from backend.routers import chat, projects

# Router de feedback (puede no existir)
try:
    from backend.routers import feedback
except Exception:
    feedback = None

app = FastAPI(title="TFG Consultoría Assistant (Inteligencia + Memoria)")

# --- CORS DEV AMPLIO (en local) ---
ALLOWED_ORIGINS = [
    "http://localhost:5173",
    "http://127.0.0.1:5173",
    "*"  # en local; para prod restringe
]
app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- Rutas existentes ---
app.include_router(chat.router,     prefix="/chat",     tags=["chat"])
app.include_router(projects.router, prefix="/projects", tags=["projects"])
if feedback:
    app.include_router(feedback.router, prefix="/projects", tags=["feedback"])

# ---------------- NUEVO: endpoint directo para /export/chat.pdf ----------------
class ChatMessage(BaseModel):
    role: str
    content: str
    ts: Optional[str] = None
    name: Optional[str] = None

class ChatExportIn(BaseModel):
    title: Optional[str] = "Conversación"
    messages: Optional[List[ChatMessage]] = None

@app.post("/export/chat.pdf", tags=["export"])
def export_chat_pdf(payload: ChatExportIn):
    msgs: List[Dict[str, Any]] = [m.dict() for m in (payload.messages or [])]
    if not msgs:
        raise HTTPException(status_code=400, detail="No hay mensajes para exportar.")
    pdf_bytes = render_chat_pdf_inline(msgs, title=payload.title or "Conversación")
    fname = f"chat_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.pdf"
    return StreamingResponse(BytesIO(pdf_bytes),
                             media_type="application/pdf",
                             headers={"Content-Disposition": f'attachment; filename=\"{fname}\"'})
# -----------------------------------------------------------------------------

# --- Startup ---
@app.on_event("startup")
def on_startup():
    # init_db si está
    try:
        store = importlib.import_module("backend.memory.state_store")
        if hasattr(store, "init_db"):
            store.init_db()
        elif hasattr(store, "Base") and hasattr(store, "engine"):
            store.Base.metadata.create_all(store.engine)
    except Exception as e:
        print(f"[startup] DB init skipped: {e}")

    # refresca índice si existe
    try:
        sim_mod = importlib.import_module("backend.retrieval.similarity")
        if hasattr(sim_mod, "get_retriever"):
            sim_mod.get_retriever().refresh()
    except Exception:
        pass

    # DEBUG: muestra rutas montadas (útil para evitar 404)
    try:
        print("[startup] Rutas montadas:")
        for r in app.router.routes:
            print(f"  {getattr(r, 'methods', ['GET'])} {getattr(r, 'path', '')}")
    except Exception:
        pass

@app.get("/health")
def health():
    return {
        "status": "ok",
        "app": "TFG Consultoría Assistant",
        "routers": {
            "chat": True,
            "projects": True,
            "feedback": bool(feedback),
            "export": True  # ya montado inline
        }
    }
