from __future__ import annotations
from typing import Dict, Any, List, Tuple
import math

from backend.ml.runtime import MLRuntime, extract_features
from backend.retrieval.similarity import get_retriever

# --- Modelos / Similares ---
_RT = MLRuntime()
_SIM = get_retriever()

# --- Tarifas por rol (€/persona-semana) ---
ROLE_RATES = {
    "PM": 2200.0,
    "Tech Lead": 2400.0,
    "Backend Dev": 2000.0,
    "Frontend Dev": 1900.0,
    "QA": 1600.0,
    "UX/UI": 1800.0,
    "ML Engineer": 2300.0,
}
CONTINGENCY = 0.10  # 10%

def _blend_effort_with_neighbors(requirements: str, eff_ml: float) -> Tuple[float, List[str], List[Dict[str, Any]]]:
    sims = _SIM.retrieve(requirements, top_k=3)
    notes: List[str] = []
    usable = []
    for s in sims:
        try:
            b = s.get("budget", {}) or {}
            ass = b.get("assumptions", {}) or {}
            e = float(ass.get("effort_person_weeks")
                      or (float(ass.get("heads_equivalent")) * float(ass.get("project_weeks"))))
            if e > 0:
                usable.append((e, float(s.get("similarity", 0.0)), s))
        except Exception:
            continue
    if not usable:
        return eff_ml, ["Sin casos similares suficientes; uso estimación del modelo."], sims
    num = sum(e * w for e, w, _ in usable)
    den = sum(w for _, w, _ in usable) or 1.0
    avg_nn = num / den
    blended = 0.7 * eff_ml + 0.3 * avg_nn
    notes.append(f"Mezcla esfuerzo: 70% modelo ({eff_ml:.1f}) + 30% vecinos ({avg_nn:.1f}) → {blended:.1f} pw.")
    notes += [f"Vecino #{s['id']} simil={sim:.2f} → esfuerzo={e:.1f} pw" for e, sim, s in usable]
    return float(round(blended, 1)), notes, sims

def _build_team(feats: Dict[str, float], effort_pw: float) -> List[Dict[str, Any]]:
    team: List[Dict[str, Any]] = []
    team.append({"role": "PM", "count": 0.5})
    team.append({"role": "Tech Lead", "count": 0.5})
    backend = 1.0 + (1.0 if feats["has_payments"] or feats["has_integrations"] else 0.0)
    frontend = 1.0 if (feats["has_admin"] or feats["has_mobile"]) else 0.5
    qa = 1.0 if feats["complexity_sum"] >= 2.0 else 0.5
    ux = 0.5 if (feats["has_mobile"] or feats["has_admin"]) else 0.0
    ml = 0.5 if feats["has_ml"] else 0.0
    team += [
        {"role": "Backend Dev", "count": backend},
        {"role": "Frontend Dev", "count": frontend},
        {"role": "QA", "count": qa},
    ]
    if ux > 0: team.append({"role": "UX/UI", "count": ux})
    if ml > 0: team.append({"role": "ML Engineer", "count": ml})
    if effort_pw >= 24:
        team = [
            {"role": r["role"], "count": (r["count"] + (0.5 if r["role"] in ("Backend Dev","Frontend Dev") else 0.0))}
            for r in team
        ]
    return team

def _sum_heads(team: List[Dict[str, Any]]) -> float:
    return float(sum(t["count"] for t in team))

def _build_phases(project_weeks: int) -> List[Dict[str, Any]]:
    dsc = 1 if project_weeks <= 6 else 2
    setup = 1
    dev = max(2, project_weeks - (dsc + setup + 2))
    qa = 1 if project_weeks <= 6 else 2
    rel = 1
    return [
        {"name": "Descubrimiento", "weeks": dsc},
        {"name": "Arquitectura & Setup", "weeks": setup},
        {"name": "Desarrollo Iterativo", "weeks": dev},
        {"name": "QA & Hardening", "weeks": qa},
        {"name": "Despliegue & Handover", "weeks": rel},
    ]

def _expand_risks_from_feats(feats: Dict[str, float], methodology: str) -> List[str]:
    risks: List[str] = ["Cambios de alcance", "Dependencias externas (APIs/terceros)"]
    if feats["has_payments"]: risks += ["PCI-DSS, fraude/chargebacks, idempotencia"]
    if feats["has_realtime"]: risks += ["Latencia y picos → colas/cachés, escalado"]
    if feats["has_mobile"]: risks += ["Revisión de tiendas, compatibilidad dispositivos"]
    if feats["has_ml"]: risks += ["Calidad de datos, sesgo, drift del modelo"]
    if feats["has_admin"]: risks += ["RBAC y auditoría en backoffice"]
    if methodology == "Kanban": risks += ["Respetar límites de WIP para evitar multitarea"]
    if methodology == "Scrum": risks += ["Definir DoR/DoD para evitar scope creep"]
    return risks

def _budget_by_role(team: List[Dict[str, Any]], project_weeks: int) -> Dict[str, float]:
    by_role: Dict[str, float] = {}
    for t in team:
        role, n = t["role"], float(t["count"])
        rate = ROLE_RATES.get(role, 1800.0)
        by_role[role] = round(n * project_weeks * rate, 2)
    return by_role

def generate_proposal(requirements: str) -> Dict[str, Any]:
    # 1) Metodología (con razones y fuentes)
    methodology, method_src = _RT.pick_methodology(requirements)
    try:
        from backend.knowledge.methodologies import get_method_sources, explain_methodology_choice
        method_reasons = explain_methodology_choice(requirements, methodology)
        method_sources = get_method_sources(methodology)
    except Exception:
        method_reasons = []
        method_sources = []

    # 2) Esfuerzo base
    effort_ml, effort_src, feats = _RT.estimate_effort(requirements)

    # 3) Ajuste con similares
    effort_final, blend_notes, sims = _blend_effort_with_neighbors(requirements, effort_ml)

    # 4) Equipo y semanas
    team = _build_team(feats, effort_final)
    heads = max(1.0, round(_sum_heads(team), 1))
    project_weeks = int(math.ceil(effort_final / heads))

    # 5) Presupuesto (por rol + contingencia)
    labor_by_role = _budget_by_role(team, project_weeks)
    labor = float(round(sum(labor_by_role.values()), 2))
    contingency = float(round(labor * CONTINGENCY, 2))
    total = float(round(labor + contingency, 2))

    # 6) Fases y riesgos
    phases = _build_phases(project_weeks)
    risks = _expand_risks_from_feats(feats, methodology)

    explanation: List[str] = []
    explanation.append(f"Metodología: {method_src}")
    explanation += [f"[{methodology}] {line}" for line in method_reasons]
    explanation.append(f"Esfuerzo base: {effort_src}")
    explanation += blend_notes
    explanation.append("Coste por rol basado en tarifas medias de mercado.")

    return {
        "methodology": methodology,
        "team": team,
        "phases": phases,
        "budget": {
            "total_eur": total,
            "labor_estimate_eur": labor,
            "contingency_10pct": contingency,
            "by_role": labor_by_role,
            "assumptions": {
                "effort_person_weeks": effort_final,
                "heads_equivalent": heads,
                "project_weeks": project_weeks,
                "role_rates_eur_pw": ROLE_RATES,
            },
        },
        "risks": risks,
        "explanation": explanation,
        "methodology_sources": method_sources,  # <<--- para citar autores
    }
