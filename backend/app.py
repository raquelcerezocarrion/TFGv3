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
import math

# ---------------- REPORT inline: portada + transcripción + análisis profundo + propuesta final ----------------
from reportlab.lib.pagesizes import A4
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, PageBreak, ListFlowable, ListItem, Table, TableStyle
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_LEFT, TA_RIGHT, TA_CENTER
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
        "coverTitle": ParagraphStyle("CoverTitle", parent=styles["Title"], alignment=TA_CENTER, fontSize=24, spaceAfter=4),
        "coverSub":   ParagraphStyle("CoverSub", parent=styles["Heading2"], alignment=TA_CENTER, textColor=colors.grey, spaceAfter=16),
        "coverMeta":  ParagraphStyle("CoverMeta", parent=styles["Normal"], alignment=TA_CENTER, textColor=colors.darkgray, spaceAfter=6),
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
        "quote": ParagraphStyle("Quote", parent=styles["Italic"], leftIndent=6, textColor=colors.darkslategray, spaceBefore=2, spaceAfter=6),
    }
    return st

# ---------------- Parsers y heurísticas ----------------
_money_re = re.compile(r"(\d{1,3}(?:\.\d{3})*(?:,\d{2})?)")
_pct_re   = re.compile(r"(\d+(?:\.\d+)?)\s*%")
role_fte_re = re.compile(r"([A-Za-zÁÉÍÓÚáéíóúñ/ ]+)\s*x\s*([0-9]+(?:\.[0-9]+)?)")

def _parse_money_eu(s: str) -> Optional[float]:
    m = _money_re.search(s)
    if not m: return None
    val = m.group(1).replace(".", "").replace(",", ".")
    try: return float(val)
    except: return None

def _parse_pct(s: str) -> Optional[float]:
    m = _pct_re.search(s)
    if not m: return None
    try: return float(m.group(1))
    except: return None

def _parse_team_list(team_str: str) -> Dict[str, float]:
    team = {}
    for part in team_str.split(","):
        part = part.strip()
        m = role_fte_re.search(part)
        if m:
            role = m.group(1).strip()
            fte  = float(m.group(2))
            team[role] = fte
    return team

# “Fichas” del asistente:
_re_final_method = re.compile(r"^\s*[■•-]\s*Metodolog[ií]a:\s*(.+)$", re.I)
_re_final_budget = re.compile(r"^\s*[■•-]\s*Presupuesto:\s*(.+)$", re.I)
_re_final_team   = re.compile(r"^\s*[■•-]\s*Equipo:\s*(.+)$", re.I)
_re_final_phases = re.compile(r"^\s*[■•-]\s*Fases:\s*(.+)$", re.I)
_re_final_risks  = re.compile(r"^\s*[■•-]{1,2}\s*Riesgos:\s*(.+)$", re.I)
_re_weeks_total  = re.compile(r"^\s*[■•-]?\s*Semanas totales:\s*([0-9]+(?:\.[0-9]+)?)", re.I)

def parse_snapshot_from_text(txt: str) -> Optional[Dict[str, Any]]:
    snap = {"metodologia": None, "equipo": None, "fases": None, "presupuesto_total": None,
            "contingencia_pct": None, "riesgos": None, "weeks_total": None, "raw": txt}
    found = False
    for line in txt.splitlines():
        if (mm := _re_final_method.match(line)):
            snap["metodologia"] = mm.group(1).strip(); found = True
        if (tt := _re_final_team.match(line)):
            snap["equipo"] = _parse_team_list(tt.group(1)); found = True
        if (pp := _re_final_phases.match(line)):
            snap["fases"] = pp.group(1).strip(); found = True
        if (bb := _re_final_budget.match(line)):
            presu_str = bb.group(1)
            snap["presupuesto_total"] = _parse_money_eu(presu_str)
            snap["contingencia_pct"]  = _parse_pct(presu_str); found = True
        if (rr := _re_final_risks.match(line)):
            snap["riesgos"] = rr.group(1).strip(); found = True
        if (ww := _re_weeks_total.match(line)):
            try: snap["weeks_total"] = float(ww.group(1)); found = True
            except: pass
    return snap if found else None

def build_snapshots(messages: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    snaps = []
    for m in messages:
        if m.get("role") != "assistant": 
            continue
        txt = m.get("content") or ""
        snap = parse_snapshot_from_text(txt)
        if snap:
            snaps.append({"ts": m.get("ts"), "snap": snap})
    return snaps

def find_last_proposal_text(messages: List[Dict[str, Any]]) -> Optional[str]:
    last = None
    for m in messages:
        if m.get("role") == "assistant":
            snap = parse_snapshot_from_text(m.get("content") or "")
            if snap:
                last = m.get("content")
    return last

def nearest_snapshot(snaps, ts, direction="before"):
    if not ts or not snaps: return None
    try: pivot = datetime.fromisoformat(ts.replace("Z", "+00:00")).timestamp()
    except: return None
    best = None; best_dt = None
    for s in snaps:
        if not s.get("ts"): continue
        try: st = datetime.fromisoformat(s["ts"].replace("Z", "+00:00")).timestamp()
        except: continue
        if direction == "before" and st <= pivot:
            if (best_dt is None) or (st > best_dt): best_dt = st; best = s
        if direction == "after" and st >= pivot:
            if (best_dt is None) or (st < best_dt): best_dt = st; best = s
    return best

# Decisiones
_re_change_any   = re.compile(r"Propones cambiar", re.I)
_re_change_kind  = re.compile(r"Propones cambiar\s+\*\*(\w+)\*\*", re.I)
_re_change_to    = re.compile(r"Propones cambiar a\s+([A-Za-zÁÉÍÓÚáéíóúñ/ ]+)", re.I)
_re_bulletish    = re.compile(r"^\s*(?:[-•■]\s+.+)$")
_re_yes          = re.compile(r"^\s*(si|sí)\s*$", re.I)

def detect_decision_kind(text: str) -> str:
    km = _re_change_kind.search(text)
    if km:
        k = km.group(1).lower()
        if k in {"team","budget","risks","governance","timeline","phases"}: return k
        return k
    tm = _re_change_to.search(text)
    if tm: return "methodology"
    return "other"

def parse_proposal_details(kind: str, text: str) -> Dict[str, Any]:
    details = {"raw": text}
    if kind == "team":
        changes = {}
        for line in text.splitlines():
            if "→" in line and "fte" in line.lower():
                try:
                    left, right = line.split("→", 1)
                    role = left.split()[-1].lower().strip(":").strip()
                    fte = float(right.lower().replace("fte","").strip())
                    changes[role] = fte
                except: pass
        if changes: details["team_changes"] = changes
    elif kind == "budget":
        for line in text.splitlines():
            if "contingencia" in line.lower() and "→" in line:
                pct = _parse_pct(line)
                if pct is not None: details["contingencia_pct"] = pct
        labor_before = None; labor_after = None; total_before = None; total_after = None
        for line in text.splitlines():
            if "labor" in line.lower():
                vals = _money_re.findall(line)
                if len(vals) >= 2:
                    labor_before = _parse_money_eu(vals[0]); labor_after = _parse_money_eu(vals[1])
            if "total con contingencia" in line.lower():
                vals = _money_re.findall(line)
                if len(vals) >= 2:
                    total_before = _parse_money_eu(vals[0]); total_after = _parse_money_eu(vals[1])
        details["metrics"] = {"labor_before": labor_before, "labor_after": labor_after,
                              "total_before": total_before, "total_after": total_after}
    elif kind in {"risks","governance"}:
        items = [line.strip(" -•■") for line in text.splitlines() if _re_bulletish.search(line)]
        if items: details["items"] = items
    elif kind == "methodology":
        m = _re_change_to.search(text)
        if m: details["to"] = m.group(1).strip()
        details["not_recommended"] = ("no aconsejo" in text.lower())
    return details

def extract_decision_events(messages: List[Dict[str, Any]]):
    events = []
    for i, m in enumerate(messages):
        if m.get("role") != "assistant": 
            continue
        txt = m.get("content") or ""
        if not _re_change_any.search(txt): continue
        kind = detect_decision_kind(txt)
        summary = "Cambio propuesto"
        if kind == "methodology":
            mm = _re_change_to.search(txt); summary = (mm.group(1) if mm else "metodología")
        elif kind in {"team","budget","risks","governance","timeline","phases"}:
            summary = kind
        impact_lines = []
        for line in txt.splitlines():
            if _re_bulletish.search(line) or ("impacto" in line.lower()) or ("evaluación" in line.lower()):
                impact_lines.append(line.strip(" -•■"))
        accepted = False; accepted_at = None
        for j in range(1, 6):
            if i + j >= len(messages): break
            uj = messages[i + j]
            if uj.get("role") == "user" and isinstance(uj.get("content"), str):
                if _re_yes.search(uj["content"]):
                    accepted = True; accepted_at = uj.get("ts"); break
                if uj["content"].strip().lower() == "no":
                    accepted = False; accepted_at = uj.get("ts"); break
        details = parse_proposal_details(kind, txt)
        events.append({
            "kind": kind, "summary": summary, "proposed_at": m.get("ts"),
            "accepted": accepted, "accepted_at": accepted_at,
            "impact": impact_lines[:50], "details": details, "raw": txt,
        })
    return events

def sum_fte(team: Optional[Dict[str, float]]) -> Optional[float]:
    if not team: return None
    try: return round(sum(team.values()), 2)
    except: return None

def compare_snapshots(before: Optional[Dict[str, Any]], after: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    def safe(v): return v if (v is not None) else None
    delta = {
        "metodologia": (safe(before and before.get("metodologia")), safe(after and after.get("metodologia"))),
        "fte_total": (safe(sum_fte(before and before.get("equipo"))), safe(sum_fte(after and after.get("equipo")))),
        "presupuesto_total": (safe(before and before.get("presupuesto_total")), safe(after and after.get("presupuesto_total"))),
        "contingencia_pct": (safe(before and before.get("contingencia_pct")), safe(after and after.get("contingencia_pct"))),
        "weeks_total": (safe(before and before.get("weeks_total")), safe(after and after.get("weeks_total"))),
    }
    team_diff = {}
    bt = (before and before.get("equipo")) or {}
    at = (after and after.get("equipo")) or {}
    for role in set(list(bt.keys()) + list(at.keys())):
        team_diff[role] = (bt.get(role), at.get(role))
    delta["team_roles"] = team_diff
    return delta

def conclude_decision(kind: str, delta: Dict[str, Any], event: Dict[str, Any]) -> str:
    def fmtmoney(x): return f"{x:,.2f} €".replace(",", "X").replace(".", ",").replace("X", ".")
    if kind == "methodology":
        to = event.get("details", {}).get("to", "n/d")
        notrec = event.get("details", {}).get("not_recommended", False)
        base, out = delta["metodologia"]
        if notrec:
            return f"Cambio a {to} aceptado pese a recomendación en contra: conviene SOLO si priorizas cadencia/gobernanza sobre prácticas técnicas (TDD/CI). En pagos/PCI, XP podía ser más segura."
        return f"Cambio a {to} aceptado: razonable si el equipo domina Scrum y mantiene disciplina técnica (tests/refactor)."
    if kind == "team":
        b,a = delta["fte_total"]; tb = b or 0; ta = a or 0
        met = event.get("details", {}).get("metrics", {})
        labor_b = met.get("labor_before"); labor_a = met.get("labor_after")
        if labor_b is not None and labor_a is not None and labor_a > labor_b and ta > tb:
            return f"Aumenta capacidad (FTE {tb}→{ta}) y coste (labor {fmtmoney(labor_b)}→{fmtmoney(labor_a)}): conviene si hay cuello de botella o se exige acelerar entregas; si el presupuesto es rígido, es trade-off."
        if ta > tb: return f"Más FTE ( {tb}→{ta} ) con mismo calendario: útil para throughput/riesgo; vigilar sobreasignación."
        return "Cambio de equipo sin métricas claras; revisar roles críticos y disponibilidad."
    if kind == "budget":
        total_b, total_a = delta["presupuesto_total"]; cont_b, cont_a = delta["contingencia_pct"]
        met = event.get("details", {}).get("metrics", {})
        tb = met.get("total_before", total_b); ta = met.get("total_after", total_a)
        cb = cont_b; ca = cont_a or event.get("details", {}).get("contingencia_pct")
        if tb and ta and ca:
            if ta > tb:
                return f"Sube el total por mayor contingencia ({cb or 'n/d'}%→{ca}%): más colchón de riesgo (pagos/PCI, dependencias) a costa de +{fmtmoney(ta - tb)}. Conviene en alta incertidumbre."
        return "Ajuste de presupuesto sin cuantía definida; valida GUARDRAILS (riesgo vs coste)."
    if kind == "risks":
        items = event.get("details", {}).get("items", [])
        if items: return "Se añaden controles/mitigaciones sin impacto directo en coste: recomendable para reducir riesgo operativo, cumplimiento y fraude."
        return "Cambio de riesgos sin lista de controles; revisar definición."
    if kind == "governance":
        return "Mejora de gobierno (canales, cadencias, artefactos) sin impacto presupuestario: recomendable para transparencia y predictibilidad."
    return "Cambio aceptado: razonable, pero faltan métricas para valoración cuantitativa."

def extract_final_state(messages: List[Dict[str, Any]]):
    final = {"metodologia": None, "equipo": None, "fases": None, "presupuesto": None, "riesgos": None}
    last = None
    for m in messages:
        if m.get("role") != "assistant": continue
        snap = parse_snapshot_from_text(m.get("content") or "")
        if snap: last = snap
    if last:
        final["metodologia"] = last.get("metodologia")
        final["equipo"] = ", ".join([f"{k} x{v}" for k,v in (last.get("equipo") or {}).items()]) or None
        final["fases"] = last.get("fases")
        if last.get("presupuesto_total") is not None:
            final["presupuesto"] = f"{last['presupuesto_total']:,.2f} €".replace(",", "X").replace(".", ",").replace("X", ".")
            if last.get("contingencia_pct") is not None:
                final["presupuesto"] += f" (incluye {last['contingencia_pct']}% contingencia)"
        final["riesgos"] = last.get("riesgos")
    return final


def _build_dafo(final_state: Dict[str, Any], messages: List[Dict[str, Any]]) -> Dict[str, List[str]]:
    """Construye un DAFO (SWOT) simple a partir del estado final y de heurísticas sobre los mensajes.
    Devuelve dict con keys: strengths, weaknesses, opportunities, threats (listas de strings).
    """
    strengths = []
    weaknesses = []
    opportunities = []
    threats = []

    # Fortalezas: elementos bien definidos en el estado final
    if final_state.get("metodologia"):
        strengths.append(f"Metodología definida: {final_state['metodologia']}")
    if final_state.get("equipo"):
        strengths.append(f"Equipo: {final_state['equipo']}")
    if final_state.get("presupuesto"):
        strengths.append(f"Presupuesto estimado: {final_state['presupuesto']}")

    # Debilidades: campos no definidos o vacíos
    if not final_state.get("metodologia"):
        weaknesses.append("Metodología no definida o insuficiente detalle")
    if not final_state.get("equipo"):
        weaknesses.append("Asignación de equipo no definida")
    if not final_state.get("presupuesto"):
        weaknesses.append("Presupuesto sin cuantificar")

    # Amenazas: riesgos explícitos en final_state o menciones en mensajes
    if final_state.get("riesgos"):
        # separar por ; o , o nuevas líneas
        raw = final_state["riesgos"]
        parts = [p.strip() for p in re.split(r"[;\n,]", raw) if p.strip()]
        for p in parts:
            threats.append(p)
    # buscar menciones a 'riesgo' en mensajes
    for m in messages:
        if (m.get("role") == "assistant") and isinstance(m.get("content"), str):
            txt = m["content"].lower()
            if "riesgo" in txt or "amenaza" in txt:
                # extraer la línea con riesgo
                for line in m["content"].splitlines():
                    if "riesgo" in line.lower() or "amenaza" in line.lower():
                        cand = line.strip(" -•■")
                        if cand and cand not in threats:
                            threats.append(cand)

    # Oportunidades: buscar 'oportunidad' o palabras positivas en assistant messages
    for m in messages:
        if (m.get("role") == "assistant") and isinstance(m.get("content"), str):
            txt = m["content"].lower()
            if "oportunidad" in txt or "oportunidades" in txt:
                for line in m["content"].splitlines():
                    if "oportunidad" in line.lower() or "oportunidades" in line.lower():
                        cand = line.strip(" -•■")
                        if cand and cand not in opportunities:
                            opportunities.append(cand)
            # heurística simple: frases que contienen 'ventaja', 'mejor', 'oportuno'
            for token in ("ventaja", "oportuno", "mejor", "potencial"):
                if token in txt:
                    for line in m["content"].splitlines():
                        if token in line.lower():
                            cand = line.strip(" -•■")
                            if cand and cand not in opportunities:
                                opportunities.append(cand)

    # Limitar longitud
    for k in (strengths, weaknesses, opportunities, threats):
        if len(k) > 6:
            del k[6:]

    # Mejor heurística para Debilidades: buscar menciones de falta/insuficiencia, prioridades no claras,
    # dependencias o datos insuficientes en assistant messages y estado final.
    weak_tokens = ["insuficiente", "sin datos", "no definido", "no definida", "sin definir", "falta", "poca", "limitado", "escaso", "baja", "impreciso", "sin prioridad", "sin prioridad clara", "dependencia", "dependencias", "datos insuficientes", "deuda técnica", "sin pruebas", "no probado"]
    # From final_state: missing phases or equipo small
    if not final_state.get("fases"):
        if "Fases" not in weaknesses and "Fases no definidas" not in weaknesses:
            weaknesses.append("Fases del proyecto no definidas")
    # inferir FTE total pequeño si equipo string contiene x0 or total < 1
    try:
        if final_state.get("equipo"):
            # buscar patrones x0.5, x0.25, etc. y sumar
            parts = re.findall(r"x(0(?:\.[0-9]+)?)|x([0-9]+(?:\.[0-9]+)?)", final_state["equipo"])
            vals = []
            for a,b in parts:
                if a:
                    try: vals.append(float(a))
                    except: pass
                elif b:
                    try: vals.append(float(b))
                    except: pass
            total_fte = sum(vals) if vals else None
            if total_fte is not None and total_fte < 1.5:
                weaknesses.append(f"Capacidad reducida: equipo total estimado {total_fte} FTE (posible cuello de botella)")
    except Exception:
        pass

    # scan assistant messages for weakness tokens and dependency mentions
    for m in messages:
        if m.get("role") != "assistant":
            continue
        txt = (m.get("content") or "").lower()
        # tokens
        for tok in weak_tokens:
            if tok in txt:
                # extract the line that contains the token
                for line in m.get("content", "").splitlines():
                    if tok in line.lower():
                        cand = line.strip(" -•■")
                        if cand and cand not in weaknesses:
                            weaknesses.append(cand)
        # specific: dependencias, APIs, terceros
        if "api" in txt or "tercer" in txt or "dependencia" in txt:
            for line in m.get("content", "").splitlines():
                if "api" in line.lower() or "tercer" in line.lower() or "dependencia" in line.lower():
                    cand = line.strip(" -•■")
                    if cand and cand not in weaknesses:
                        weaknesses.append(cand)

    # eliminar duplicados manteniendo orden
    def _uniq(seq):
        seen = set(); out = []
        for x in seq:
            if x not in seen:
                seen.add(x); out.append(x)
        return out

    strengths = _uniq(strengths)
    weaknesses = _uniq(weaknesses)
    opportunities = _uniq(opportunities)
    threats = _uniq(threats)

    return {
        "strengths": strengths,
        "weaknesses": weaknesses,
        "opportunities": opportunities,
        "threats": threats,
    }

def _explain_impacts(delta: Dict[str, Any]) -> List[str]:
    out = []
    ft_b, ft_a = delta["fte_total"]
    wk_b, wk_a = delta["weeks_total"]
    tb_b, tb_a = delta["presupuesto_total"]
    pc_b, pc_a = delta["contingencia_pct"]
    if ft_a is not None and ft_b is not None:
        if ft_a > ft_b: out.append("Capacidad ↑ (más FTE) → potencialmente más throughput y menor tiempo de ciclo.")
        elif ft_a < ft_b: out.append("Capacidad ↓ (menos FTE) → throughput menor; considerar foco/priorización.")
    if wk_a is not None and wk_b is not None:
        if wk_a > wk_b: out.append("Plazo ↑ (más semanas) → menor presión pero latería el time-to-market.")
        elif wk_a < wk_b: out.append("Plazo ↓ (menos semanas) → entrega más rápida; vigilar deuda técnica.")
    if tb_a is not None and tb_b is not None:
        if tb_a > tb_b: out.append("Coste total ↑ → más inversión para reducir riesgo/ganar velocidad.")
        elif tb_a < tb_b: out.append("Coste total ↓ → ahorro; confirmar que no afecta a calidad/alcance.")
    if pc_a is not None and pc_b is not None:
        if pc_a > pc_b: out.append("Contingencia ↑ → mejor colchón ante incertidumbre.")
        elif pc_a < pc_b: out.append("Contingencia ↓ → mayor exposición a desvíos.")
    if not out:
        out.append("Sin métricas suficientes: documenta supuestos y define KPIs de seguimiento.")
    return out

# ---------------- Personalización: tipografía y narrativa ----------------
def _font_base_from_options(opts: Optional[Dict[str, Any]]) -> str:
    name = (opts or {}).get("font_name", "").lower().strip()
    if "times" in name: return "Times-Roman"
    if "courier" in name or "mono" in name: return "Courier"
    return "Helvetica"

def _apply_font_to_styles(styles_dict: Dict[str, ParagraphStyle], base_font: str):
    for k, st in styles_dict.items():
        if hasattr(st, "fontName"):
            # negrita para titulares si hay variante
            if k in ("h1","h2","h3","coverTitle"):
                st.fontName = base_font + ("-Bold" if base_font == "Helvetica" else "")
            else:
                st.fontName = base_font

def _narrative_for_decision(idx: int, e: Dict[str, Any], delta: Dict[str, Any]) -> List[str]:
    paras = []
    kind = e.get("kind","otro")
    prop_at = _fmt_dt(e.get("proposed_at")) or "sin fecha"
    accepted = e.get("accepted", False)

    mt_b, mt_a = delta["metodologia"]
    ft_b, ft_a = delta["fte_total"]
    tb_b, tb_a = delta["presupuesto_total"]
    pc_b, pc_a = delta["contingencia_pct"]
    wk_b, wk_a = delta["weeks_total"]

    intro = f"Decisión {idx}. En {prop_at}, se planteó un cambio sobre «{e.get('summary','cambio')}». "
    intro += "La propuesta fue aceptada y posteriormente aplicada." if accepted else "La propuesta no llegó a aplicarse (pendiente o rechazada)."
    paras.append(intro)

    if kind == "methodology":
        to = e.get("details",{}).get("to","otra metodología")
        nr = e.get("details",{}).get("not_recommended", False)
        txt = f"La propuesta consistía en evolucionar la metodología hacia {to}. "
        if nr: txt += "El asistente advirtió que este cambio no era aconsejable en ese momento."
        paras.append(txt)
    elif kind == "team":
        ch = e.get("details",{}).get("team_changes",{})
        if ch:
            roles = ", ".join([f"{r.upper()}→{v} FTE" for r,v in ch.items()])
            paras.append(f"Se propuso reajustar la asignación del equipo: {roles}.")
    elif kind == "budget":
        met = e.get("details",{}).get("metrics",{}); cb  = e.get("details",{}).get("contingencia_pct")
        txt = "La propuesta afectaba al presupuesto"
        if cb is not None: txt += f" incrementando la contingencia al {cb}%"
        if met.get("total_before") is not None and met.get("total_after") is not None:
            txt += f", con un total estimado que pasaría de {met['total_before']:,.2f} € a {met['total_after']:,.2f} €".replace(",", "X").replace(".", ",").replace("X", ".")
        paras.append(txt + ".")
    elif kind in {"risks","governance"}:
        items = e.get("details",{}).get("items",[])
        if items:
            paras.append("Incluía medidas específicas en riesgos/gobernanza, por ejemplo: " + "; ".join(items[:5]) + ("…" if len(items) > 5 else "."))

    lines = []
    if mt_b or mt_a:
        lines.append(f"Metodología: {mt_b or '—'} → {mt_a or '—'}")
    if ft_b is not None or ft_a is not None:
        lines.append(f"FTE total: {ft_b if ft_b is not None else '—'} → {ft_a if ft_a is not None else '—'}")
    if tb_b is not None or tb_a is not None:
        fb = f"{tb_b:,.2f} €".replace(",","X").replace(".",",").replace("X",".") if tb_b is not None else "—"
        fa = f"{tb_a:,.2f} €".replace(",","X").replace(".",",").replace("X",".") if tb_a is not None else "—"
        lines.append(f"Presupuesto total: {fb} → {fa}")
    if pc_b is not None or pc_a is not None:
        lines.append(f"Contingencia: {pc_b if pc_b is not None else '—'}% → {pc_a if pc_a is not None else '—'}%")
    if wk_b is not None or wk_a is not None:
        lines.append(f"Semanas totales: {wk_b if wk_b is not None else '—'} → {wk_a if wk_a is not None else '—'}")

    if lines:
        paras.append("En términos cuantitativos, los principales deltas observados fueron: " + "; ".join(lines) + ".")

    expl = _explain_impacts(delta)
    if expl:
        paras.append("Implicaciones esperadas sobre alcance/tiempo/coste/calidad/riesgo: " + " ".join([x if x.endswith(".") else x + "." for x in expl]))

    concl = conclude_decision(kind, delta, e)
    paras.append("Conclusión de la decisión: " + concl)
    return paras

def _overall_evaluation(events: List[Dict[str, Any]], final_state: Dict[str, Any]) -> List[str]:
    accepted = [e for e in events if e.get("accepted")]
    paras = []
    paras.append(
        f"En conjunto, se abordaron {len(events)} decisiones, de las cuales {len(accepted)} fueron aceptadas. "
        "La propuesta final consolida un enfoque coherente con los objetivos del proyecto y la capacidad del equipo."
    )
    if final_state.get("presupuesto"):
        paras.append(f"El presupuesto final queda estimado en {final_state['presupuesto']}, que debe contrastarse con el valor generado y el riesgo residual.")
    if final_state.get("metodologia"):
        paras.append(f"Metodológicamente, se cierra en {final_state['metodologia']}, siempre que se preserven prácticas de calidad (tests, CI/CD).")
    if final_state.get("riesgos"):
        paras.append("En riesgo, se consideran principales: " + final_state["riesgos"] + ". Recomendamos indicadores tempranos y revisiones quincenales.")
    if len(accepted) >= max(1, len(events)//2):
        paras.append("Valoración global: los cambios parecen razonables y alineados con previsibilidad y control. Merecen la pena si se mantiene disciplina operativa.")
    else:
        paras.append("Valoración global: el paquete de cambios no alcanza consenso; proponemos piloto acotado con KPIs antes de escalar.")
    return paras

def render_chat_report_inline(
    messages: List[Dict[str, Any]],
    title: str = "Informe de la conversación",
    report_meta: Optional[Dict[str, Any]] = None,
    report_options: Optional[Dict[str, Any]] = None
) -> bytes:
    # opciones (qué incluir, profundidad, tipografía)
    opts = report_options or {}
    include_cover = opts.get("include_cover", True)
    include_transcript = opts.get("include_transcript", True)
    include_analysis = opts.get("include_analysis", True)
    include_final = opts.get("include_final_proposal", True)
    depth = (opts.get("analysis_depth") or "standard").lower()  # "brief" | "standard" | "deep"

    base_font = _font_base_from_options(opts)
    st = _mk_styles()
    _apply_font_to_styles(st, base_font)

    buf = BytesIO()
    doc = SimpleDocTemplate(
        buf, pagesize=A4,
        leftMargin=18*mm, rightMargin=18*mm, topMargin=16*mm, bottomMargin=16*mm,
        title=title
    )
    story = []

    # ---------------- Portada ----------------
    if include_cover:
        meta = report_meta or {}
        story.append(Spacer(1, 30*mm))
        story.append(Paragraph(title, st["coverTitle"]))
        story.append(Paragraph(meta.get("subtitle") or "Análisis detallado de conversación y decisiones", st["coverSub"]))
        story.append(Spacer(1, 4*mm))
        cover_lines = [
            f"Proyecto: {meta.get('project') or '—'}",
            f"Cliente: {meta.get('client') or '—'}",
            f"Autor: {meta.get('author') or 'Asistente'}",
            f"Sesión: {meta.get('session_id') or '—'}",
            f"Fecha de generación: {datetime.now().strftime('%Y-%m-%d %H:%M')}",
        ]
        for line in cover_lines:
            story.append(Paragraph(_escape(line), st["coverMeta"]))
        story.append(PageBreak())

    # ---------------- Parte A — Transcripción ----------------
    if include_transcript:
        story.append(Paragraph("PARTE A — Transcripción completa", st["h2"]))
        story.append(Paragraph("Diálogo íntegro entre usuario y asistente para trazabilidad.", st["meta"]))
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
        story.append(PageBreak())

    # ---------------- Parte B — Análisis profundo (narrativo) ----------------
    if include_analysis:
        story.append(Paragraph("PARTE B — Análisis de decisiones y cambios", st["h2"]))
        if depth == "deep":
            story.append(Paragraph("Análisis narrativo detallado de decisiones, impactos y valoración.", st["meta"]))
        else:
            story.append(Paragraph("Análisis narrativo de decisiones con impactos clave y valoración.", st["meta"]))
        story.append(Spacer(1, 2*mm))

        events = extract_decision_events(messages)
        snaps  = build_snapshots(messages)
        final  = extract_final_state(messages)

        # Resumen ejecutivo (breve o más extenso)
        story.append(Paragraph("Resumen ejecutivo", st["h3"]))
        accepted_count = sum(1 for e in events if e["accepted"])
        if depth == "brief":
            summary_text = f"Se identifican {len(events)} decisiones (aceptadas {accepted_count}). El plan final es coherente con objetivos y capacidad."
            story.append(Paragraph(_escape(summary_text), st["p"]))
        else:
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

        # Línea temporal (opcional según profundidad)
        if events and depth != "brief":
            story.append(Paragraph("Línea temporal de decisiones", st["h3"]))
            tl = []
            for e in events:
                when = _fmt_dt(e.get("proposed_at"))
                status = "✅ aceptada" if e["accepted"] else "⏳ pendiente / rechazada"
                tl.append(f"[{when or 's/f'}] {e['summary']} — {status}")
            story.append(ListFlowable([ListItem(Paragraph(_escape(x), st["p"])) for x in tl],
                                      bulletType="1", leftPadding=10))
            story.append(Spacer(1, 3*mm))

        # Detalle por decisión en narrativa
        for idx, e in enumerate(events, 1):
            before = nearest_snapshot(snaps, e.get("proposed_at"), "before")
            after  = nearest_snapshot(snaps, e.get("accepted_at") or e.get("proposed_at"), "after") if e["accepted"] else None
            delta  = compare_snapshots(before and before["snap"], after and after["snap"])

            story.append(Paragraph(f"Decisión {idx}: {e['summary']}", st["h3"]))
            paras = _narrative_for_decision(idx, e, delta)

            # Acortar en modo brief
            if depth == "brief":
                paras = paras[:2] + paras[-1:]
            elif depth == "standard":
                paras = paras

            for para in paras:
                story.append(Paragraph(_escape(para), st["p"]))
                story.append(Spacer(1, 1*mm))

        # Conclusión ejecutiva global
        story.append(Spacer(1, 2*mm))
        story.append(Paragraph("Conclusión ejecutiva", st["h3"]))
        for para in _overall_evaluation(events, final):
            story.append(Paragraph(_escape(para), st["p"]))
            story.append(Spacer(1, 1*mm))

        # Estado final consolidado (si no es brief)
        if depth != "brief":
            story.append(Paragraph("Estado final del plan", st["h3"]))
            fin_list = []
            for k, label in [("metodologia","Metodología"), ("equipo","Equipo"), ("fases","Fases"),
                            ("presupuesto","Presupuesto"), ("riesgos","Riesgos")]:
                fin_list.append(f"{label}: {final.get(k) or '—'}")
            story.append(ListFlowable([ListItem(Paragraph(_escape(x), st["p"])) for x in fin_list],
                                    bulletType="bullet", leftPadding=10))

    # ---------------- Parte C — Propuesta final completa ----------------
    if include_final:
        last_block = find_last_proposal_text(messages)
        if last_block:
            story.append(PageBreak())
            story.append(Paragraph("PARTE C — Propuesta final completa", st["h2"]))
            story.append(Paragraph("Reproducción íntegra del último bloque de propuesta del asistente.", st["meta"]))
            story.append(Spacer(1, 2*mm))
            for para in (last_block or "").split("\n\n"):
                story.append(Paragraph(_escape(para).replace("\n", "<br/>"), st["p"]))
                story.append(Spacer(1, 1*mm))

    # ---------------- Parte D — DAFO / SWOT ----------------
    # Construimos el DAFO a partir del estado final y mensajes si hay datos
    try:
        dafo = _build_dafo(final, messages)
        # solo añadir si hay algún elemento
        if any(dafo.get(k) for k in ("strengths","weaknesses","opportunities","threats")):
            story.append(PageBreak())
            story.append(Paragraph("PARTE D — DAFO (Análisis FODA / SWOT)", st["h2"]))
            story.append(Paragraph("Síntesis de Fortalezas, Debilidades, Oportunidades y Amenazas basadas en la conversación.", st["meta"]))
            story.append(Spacer(1, 2*mm))

            # Construimos una tabla 2x2 con cabeceras coloreadas y contenido en cada cuadrante,
            # usando tablas anidadas para controlar header+contenido por celda.
            def _cell_table(title: str, items: list):
                # header paragraph
                hdr_style = ParagraphStyle("DAFOHeader", parent=st["h3"], alignment=TA_CENTER, textColor=colors.white, fontSize=12)
                hdr = Paragraph(_escape(title), hdr_style)
                # content as bullets (puede ser vacío)
                if items:
                    bullets = "<br/>".join([f"• {_escape(x)}" for x in items])
                else:
                    bullets = "—"
                content = Paragraph(bullets, st["p"])
                # nested table: header row + content row
                nested = Table([[hdr], [content]], colWidths=[(doc.width / 2.0)])
                nested.setStyle(TableStyle([
                    ("BACKGROUND", (0,0), (0,0), colors.HexColor("#f8a8a8")),
                    ("ALIGN", (0,0), (0,0), "CENTER"),
                    ("VALIGN", (0,0), (-1,-1), "TOP"),
                    ("LEFTPADDING", (0,0), (-1,-1), 6),
                    ("RIGHTPADDING", (0,0), (-1,-1), 6),
                    ("TOPPADDING", (0,0), (-1,-1), 6),
                    ("BOTTOMPADDING", (0,0), (-1,-1), 6),
                ]))
                return nested

            # preparar las cuatro celdas
            c_fort = _cell_table("Fortalezas", dafo.get("strengths") or [])
            c_opp  = _cell_table("Oportunidades", dafo.get("opportunities") or [])
            c_weak = _cell_table("Debilidades", dafo.get("weaknesses") or [])
            c_thrt = _cell_table("Amenazas", dafo.get("threats") or [])

            outer = Table([[c_fort, c_opp], [c_weak, c_thrt]], colWidths=[doc.width / 2.0, doc.width / 2.0], rowHeights=None)
            outer.setStyle(TableStyle([
                ("BOX", (0,0), (-1,-1), 6, colors.HexColor("#211146")),
                ("INNERGRID", (0,0), (-1,-1), 0.5, colors.HexColor("#211146")),
                ("VALIGN", (0,0), (-1,-1), "TOP"),
            ]))

            story.append(outer)
            story.append(Spacer(1, 3*mm))
    except Exception:
        # si algo falla, no rompemos la generación del informe
        pass

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
try:
    from backend.routers import auth
    app.include_router(auth.router, prefix="/auth", tags=["auth"])
except Exception:
    pass
try:
    from backend.routers import user
    app.include_router(user.router, prefix="/user", tags=["user"])
except Exception:
    pass
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
    report_meta: Optional[Dict[str, Any]] = None      # metadatos portada (project, client, author, session_id, subtitle)
    report_options: Optional[Dict[str, Any]] = None   # opciones de exportación (partes, profundidad, font_name)

@app.post("/export/chat.pdf", tags=["export"])
def export_chat_pdf(payload: ChatExportIn):
    msgs: List[Dict[str, Any]] = [m.dict() for m in (payload.messages or [])]
    if not msgs:
        raise HTTPException(status_code=400, detail="No hay mensajes para exportar.")
    pdf_bytes = render_chat_report_inline(
        msgs,
        title=payload.title or "Informe de la conversación",
        report_meta=payload.report_meta,
        report_options=payload.report_options
    )
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
