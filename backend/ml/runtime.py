from __future__ import annotations
from typing import Dict, Tuple, List
from pathlib import Path
import re

from backend.knowledge.methodologies import recommend_methodology, get_method_sources

MODELS_DIR = Path("backend/models")
MODELS_DIR.mkdir(parents=True, exist_ok=True)

try:
    import joblib
except Exception:
    joblib = None

def _norm(s: str) -> str:
    return s.lower().strip()

def _rx(t: str, pat: str) -> bool:
    return re.search(pat, t, re.I) is not None

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

class MLRuntime:
    def __init__(self) -> None:
        self.effort_model = None
        if joblib is not None:
            p = MODELS_DIR / "effort.joblib"
            if p.exists():
                try: self.effort_model = joblib.load(p)
                except Exception: self.effort_model = None
        # buffers para explicación de metodología
        self._last_method_sources: List[Dict[str,str]] = []
        self._last_method_why: List[str] = []
        self._last_method_rank = []

    # Selección explicable con reglas + fuentes
    def pick_methodology(self, requirements: str) -> Tuple[str, str]:
        method, why_lines, scored = recommend_methodology(requirements)
        self._last_method_sources = get_method_sources(method)
        self._last_method_why = why_lines
        self._last_method_rank = scored
        return method, "Reglas ponderadas por señales + documentación de autores."

    # Estimación de esfuerzo (person-weeks): modelo si existe; si no, heurística simple
    def estimate_effort(self, requirements: str) -> Tuple[float, str, Dict[str,float]]:
        feats = extract_features(requirements)
        if self.effort_model is not None:
            try:
                X = [feats]
                y = float(self.effort_model.predict(X)[0])
                return max(2.0, round(y, 1)), "Modelo ML (effort.joblib).", feats
            except Exception:
                pass
        # Heurística transparente (parece humano)
        base = 6.0
        base += 3.0 if feats["has_payments"] else 0.0
        base += 2.0 if feats["has_admin"] else 0.0
        base += 2.0 if feats["has_mobile"] else 0.0
        base += 1.5 if feats["has_realtime"] else 0.0
        base += 2.5 if feats["has_ml"] else 0.0
        base += 1.0 if feats["has_integrations"] else 0.0
        base += 0.5 * max(0.0, feats["complexity_tokens"] - 1.0)
        return round(base, 1), "Heurística por módulos y complejidad.", feats
