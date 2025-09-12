# backend/app.py
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from typing import List, Optional, Dict, Any
from datetime import datetime
from io import BytesIO
import importlib
import re

# ---------------- REPORT inline: transcripción + análisis de decisiones ----------------
# Requiere: pip install reportlab
from reportlab.lib.pagesizes import A4
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, PageBreak, ListFlowable, ListItem
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

def _mk_styles():
    styles = getSampleStyleSheet()
    st = {
        "h1": ParagraphStyle("H1", parent=styles["Heading1"], fontName="Helvetica-Bold", fontSize=18, spaceAfter=8),
        "h2": ParagraphStyle("H2", parent=styles["Heading2"], fontName="Helvetica-Bold", fontSize=15, spaceAfter=6),
        "h3": ParagraphStyle("H3", parent=styles["Heading3"], fontName="Helvetica-Bold", fontSize=12, spaceAfter=4),
        "meta": ParagraphStyle("Meta", parent=styles["Normal"], textColor=colors.grey, fontSize=9, spaceAfter=8),
        "p": ParagraphStyle("P", parent=styles["BodyText"], leading=14, spaceAfter=4),
        "user": ParagraphStyle("User", parent=styles["BodyText"], backColor=colors.whitesmoke,
                               borderColor=colors.lightgrey, borderWidth=0.5, borderPadding=(6,6,6,6),
                               spaceAfter=6, leading=14, alignment=TA_RIGHT),
        "asst": ParagraphStyle("Asst", parent=styles["BodyText"], backColor=colors.Color(0.96,0.99,1.0),
                               borderColor=colors.Color(0.75,0.85,0.95), borderWidth=0.5, borderPadding=(6,6,6,6),
                               spaceAfter=6, leading=14, alignment=TA_LEFT),
        "sys":  ParagraphStyle("Sys",  parent=styles["BodyText"], textColor=colors.darkgray,
                               backColor=colors.Color(0.97,0.97,0.97), borderColor=colors.Color(0.85,0.85,0.85),
                               borderWidth=0.5, borderPadding=(6,6,6,6), spaceAfter=6, leading=14, alignment=TA_LEFT),
    }
    return st

# Heurísticas: detecta propuestas de cambio y aceptación simple ("si"/"sí")
_re_change_header = re.compile(r"Propones cambiar\s+\*\*(.*?)\*\*|Propones cambiar a\s+([A-Za-zÁÉÍÓÚáéíóúñ/ ]+)", re.I)
_re_bulletish      = re.compile(r"^\s*(?:[-•■]\s+.+)$")
_re_yes            = re.compile(r"^\s*(si|sí)\s*$", re.I)

def extract_decision_events(messages: List[Dict[str, Any]]):
    events = []
    i = 0
    while i < len(messages):
        m = messages[i]
        if (m.get("role") == "assistant") and isinstance(m.get("content"), str):
            txt = m["content"]
            mh = _re_change_header.search(txt)
            if mh:
                summary = (mh.group(1) or mh.group(2) or "Cambio propuesto").strip()
                impact_lines = []
                for line in txt.splitlines():
                    if _re_bulletish.search(line) or "impacto" in line.lower() or "evaluación" in line.lower():
                        impact_lines.append(line.strip(" -•■"))
                accepted = False
                accepted_at = None
                # Busca respuesta de usuario en las 5 siguientes
                for j in range(1, 6):
                    if i + j >= len(messages): break
                    uj = messages[i + j]
                    if uj.get("role") == "user" and isinstance(uj.get("content"), str):
                        if _re_yes.search(uj["content"]):
                            accepted = True
                            accepted_at = uj.get("ts")
                            break
                        elif uj["content"].strip().lower() == "no":
                            accepted = False
                            accepted_at = uj.get("ts")
                            break
                events.append({
                    "summary": summary,
                    "proposed_at": m.get("ts"),
                    "accepted": accepted,
                    "accepted_at": accepted_at,
                    "impact": impact_lines[:20],
                    "raw": txt,
                })
        i += 1
    return events

# Captura un "estado final" básico de la última ficha/resumen del asistente
_re_final_method = re.compile(r"^\s*[■•-]\s*Metodolog[ií]a:\s*(.+)$", re.I)
_re_final_budget = re.compile(r"^\s*[■•-]\s*Presupuesto:\s*(.+)$", re.I)
_re_final_team   = re.compile(r"^\s*[■•-]\s*Equipo:\s*(.+)$", re.I)
_re_final_phases = re.compile(r"^\s*[■•-]\s*Fases:\s*(.+)$", re.I)
_re_final_risks  = re.compile(r"^\s*[■•-]{1,2}\s*Riesgos:\s*(.+)$", re.I)

def extract_final_state(messages: List[Dict[str, Any]]):
    final = {"metodologia": None, "equipo": None, "fases": None, "presupuesto": None, "riesgos": None}
    for m in messages:
        if m.get("role") != "assistant":
            continue
        txt = m.get("content") or ""
        for line in txt.splitlines():
            if (mm := _re_final_method.match(line)): final["metodologia"] = mm.group(1).strip()
            if (bb := _re_final_budget.match(line)): final["presupuesto"]  = bb.group(1).strip()
            if (tt := _re_final_team.match(line)):   final["equipo"]       = tt.group(1).strip()
            if (pp := _re_final_phases.match(line)): final["fases"]        = pp.group(1).strip()
            if (rr := _re_final_risks.match(line)):  final["riesgos"]      = rr.group(1).strip()
    return final

def render_chat_report_inline(messages: List[Dict[str, Any]], title: str = "Informe de la conversación") -> bytes:
    st = _mk_styles()
    buf = BytesIO()
    doc = SimpleDocTemplate(
        buf, pagesize=A4,
        leftMargin=18*mm, rightMargin=18*mm, topMargin=16*mm, bottomMargin=16*mm,
        title=title
    )

    story = []
    # Portada ligera
    story.append(Paragraph(title, st["h1"]))
    story.append(Paragraph("Generado automáticamente", st["meta"]))
    story.append(Spacer(1, 4*mm))

    # ---------------- Parte A: Transcripción ----------------
    story.append(Paragraph("PARTE A — Transcripción completa", st["h2"]))
    story.append(Spacer(1, 2*mm))
    for m in messages or []:
        role = (m.get("role") or "").lower().strip()
        who = m.get("name") or ("Usuario" if role == "user" else ("Asistente" if role == "assistant" else "Sistema"))
        ts = _fmt_dt(m.get("ts"))
        header = f"<b>{_escape(who)}</b>" + (f" · {ts}" if ts else "")
        raw = _escape(str(m.get("content") or "")).replace("\n", "<br/>")
        style = st["user"] if role == "user" else (st["asst"] if role == "assistant" else st["sys"])
        story.append(Paragraph(header, st["meta"]))
        story.append(Paragraph(raw, style))
        story.append(Spacer(1, 2*mm))

    # Salto a la Parte B
    story.append(PageBreak())

    # ---------------- Parte B: Análisis de decisiones ----------------
    story.append(Paragraph("PARTE B — Análisis de decisiones y cambios", st["h2"]))
    story.append(Spacer(1, 2*mm))

    events = extract_decision_events(messages)
    final = extract_final_state(messages)

    # Resumen ejecutivo
    story.append(Paragraph("Resumen ejecutivo", st["h3"]))
    accepted_count = sum(1 for e in events if e["accepted"])
    resumen = [
        f"Decisiones detectadas: {len(events)} (aceptadas: {accepted_count}, otras: {len(events)-accepted_count})",
        f"Metodología final: {final.get('metodologia') or '—'}",
        f"Equipo final: {final.get('equipo') or '—'}",
        f"Fases (plan): {final.get('fases') or '—'}",
        f"Presupuesto final: {final.get('presupuesto') or '—'}",
        f"Riesgos principales: {final.get('riesgos') or '—'}",
    ]
    story.append(ListFlowable([ListItem(Paragraph(_escape(x), st["p"])) for x in resumen],
                              bulletType="bullet", leftPadding=10))
    story.append(Spacer(1, 3*mm))

    # Línea temporal
    if events:
        story.append(Paragraph("Línea temporal de decisiones", st["h3"]))
        tl = []
        for e in events:
            when = _fmt_dt(e.get("proposed_at"))
            status = "✅ aceptada" if e["accepted"] else "⏳ pendiente / rechazada"
            tl.append(f"[{when or 's/f'}] {e['summary']} — {status}")
        story.append(ListFlowable([ListItem(Paragraph(_escape(x), st["p"])) for x in tl],
                                  bulletType="1", leftPadding=10))
        story.append(Spacer(1, 3*mm))

    # Detalle por decisión
    for idx, e in enumerate(events, 1):
        story.append(Paragraph(f"Decisión {idx}: {e['summary']}", st["h3"]))
        meta_lines = [
            f"Propuesto: {_fmt_dt(e.get('proposed_at')) or '—'}",
            f"Resultado: {'Aceptada' if e['accepted'] else 'Pendiente/Rechazada'}" + (f" ({_fmt_dt(e.get('accepted_at'))})" if e.get('accepted_at') else ""),
        ]
        story.append(ListFlowable([ListItem(Paragraph(_escape(x), st["p"])) for x in meta_lines],
                                  bulletType="bullet", leftPadding=10))
        if e["impact"]:
            story.append(Paragraph("Impacto y justificación (extraído del chat):", st["p"]))
            story.append(ListFlowable([ListItem(Paragraph(_escape(l), st["p"])) for l in e["impact"]],
                                      bulletType="bullet", leftPadding=16))
        story.append(Spacer(1, 2*mm))

    # Estado final
    story.append(Spacer(1, 2*mm))
    story.append(Paragraph("Estado final del plan", st["h3"]))
    fin_list = []
    for k, label in [("metodologia","Metodología"), ("equipo","Equipo"), ("fases","Fases"),
                     ("presupuesto","Presupuesto"), ("riesgos","Riesgos")]:
        fin_list.append(f"{label}: {final.get(k) or '—'}")
    story.append(ListFlowable([ListItem(Paragraph(_escape(x), st["p"])) for x in fin_list],
                              bulletType="bullet", leftPadding=10))

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

# ---------------- Endpoint: /export/chat.pdf (usa el REPORT inline) ----------------
class ChatMessage(BaseModel):
    role: str
    content: str
    ts: Optional[str] = None
    name: Optional[str] = None

class ChatExportIn(BaseModel):
    title: Optional[str] = "Informe de la conversación"
    messages: Optional[List[ChatMessage]] = None

@app.post("/export/chat.pdf", tags=["export"])
def export_chat_pdf(payload: ChatExportIn):
    msgs: List[Dict[str, Any]] = [m.dict() for m in (payload.messages or [])]
    if not msgs:
        raise HTTPException(status_code=400, detail="No hay mensajes para exportar.")
    pdf_bytes = render_chat_report_inline(msgs, title=payload.title or "Informe de la conversación")
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

    # DEBUG: muestra rutas montadas
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
            "export": True
        }
    }
