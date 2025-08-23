# backend/ml/runtime.py
from typing import Dict, Tuple
import re

def _norm(s: str) -> str:
    return s.lower().strip()

def _rx(t: str, pat: str) -> bool:
    return re.search(pat, t, re.I) is not None

# ---------- features simples (las usa planner.py) ----------
def extract_features(requirements: str) -> Dict[str, float]:
    t = _norm(requirements)
    feats: Dict[str, float] = {
        "has_payments":     1.0 if _rx(t, r"\b(pagos|stripe|paypal|redsys)\b") else 0.0,
        "has_mobile":       1.0 if _rx(t, r"\b(app|ios|android|m[óo]vil|mobile)\b") else 0.0,
        "has_admin":        1.0 if _rx(t, r"\b(admin|backoffice|panel|dashboard)\b") else 0.0,
        "has_realtime":     1.0 if _rx(t, r"\b(realtime|tiempo real|websocket|socket)\b") else 0.0,
        "has_ml":           1.0 if _rx(t, r"\b(ml|machine learning|ia|modelo)\b") else 0.0,
        "has_auth":         1.0 if _rx(t, r"\b(login|oauth|registro|autenticaci[óo]n)\b") else 0.0,
        "has_reports":      1.0 if _rx(t, r"\b(report(es)?|informes|metrics?)\b") else 0.0,
        "has_integrations": 1.0 if _rx(t, r"\b(api(s)?|integraci[óo]n|webhook)\b") else 0.0,
    }
    tokens = re.findall(r"\w+", t)
    feats["complexity_tokens"] = max(1.0, len(tokens) / 100.0)
    feats["complexity_sum"] = sum(feats.values())
    return feats

# ---------- runtime mínimo (solo heurísticas, sin modelos) ----------
class MLRuntime:
    def pick_methodology(self, requirements: str) -> Tuple[str, str]:
        t = _norm(requirements)
        if _rx(t, r"\b(operaci[oó]n|soporte|mantenimiento|24/7|tiempo real)\b"):
            return "Kanban", "Heurística: flujo continuo/operación."
        if _rx(t, r"\b(cambiante|incertidumbre|descubrimiento|mvp|explorar)\b"):
            return "Scrum", "Heurística: requisitos cambiantes."
        return "Scrumban", "Heurística: mezcla de desarrollo y operación."

    def estimate_effort(self, requirements: str) -> Tuple[float, str, Dict[str, float]]:
        feats = extract_features(requirements)
        base = 4.0
        weights = {
            "has_payments": 2.0, "has_mobile": 2.0, "has_admin": 1.5, "has_realtime": 1.5,
            "has_ml": 2.0, "has_auth": 0.8, "has_reports": 0.8, "has_integrations": 0.7
        }
        score = base
        parts = [("base", base)]
        for k, w in weights.items():
            if feats.get(k, 0.0) > 0:
                score += w
                parts.append((k, w))
        score *= (1.0 + 0.2 * feats["complexity_sum"])
        weeks_equiv = float(round(score, 1))
        expl = "Heurística: " + " + ".join(f"{k}({v})" for k, v in parts) + f" → ajuste complejidad ({feats['complexity_sum']:.1f})"
        return weeks_equiv, expl, feats

    def info(self):
        return {"using": "heuristics_only", "models": False}
