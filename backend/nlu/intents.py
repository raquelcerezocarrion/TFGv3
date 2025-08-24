from __future__ import annotations
from pathlib import Path
from typing import Tuple
import re

try:
    import joblib
except Exception:
    joblib = None

MODELS_DIR = Path("backend/models")
MODELS_DIR.mkdir(parents=True, exist_ok=True)
INTENTS_PATH = MODELS_DIR / "intents.joblib"

INTENT_LABELS = [
    "greet", "goodbye", "thanks", "help",
    "ask_budget", "ask_methodology", "ask_team", "ask_risks",
    "ask_why_budget", "ask_why_methodology", "ask_why_team", "ask_why_role_count",
]

def _norm(s: str) -> str:
    return s.lower().strip()

class IntentsRuntime:
    """
    Clasificador de intenciones.
    - Si hay modelo (backend/models/intents.joblib) → usa ML.
    - Si no hay modelo → reglas sencillas (no rompe nada).
    """
    def __init__(self) -> None:
        self.model = None
        if joblib is not None and INTENTS_PATH.exists():
            try:
                self.model = joblib.load(INTENTS_PATH)
            except Exception:
                self.model = None

    def predict(self, text: str) -> Tuple[str, float]:
        t = _norm(text)
        if self.model is not None:
            try:
                proba = self.model.predict_proba([t])[0]
                idx = int(proba.argmax())
                label = str(self.model.classes_[idx])
                return label, float(proba[idx])
            except Exception:
                pass

        # --- Fallback por reglas (mínimo) ---
        why = ("por qué" in t) or ("por que" in t) or ("porque" in t) or ("justifica" in t) or ("explica" in t) or ("motivo" in t)
        if re.search(r"\b(hola|buenas|hello|hey|qué tal|que tal)\b", t): return "greet", 0.9
        if re.search(r"\b(ad[ií]os|hasta luego|nos vemos|chao)\b", t): return "goodbye", 0.9
        if re.search(r"\b(gracias|thank)\b", t): return "thanks", 0.9
        if "ayuda" in t or "qué puedes hacer" in t or "que puedes hacer" in t: return "help", 0.8

        if why and re.search(r"\b(presupuesto|coste|precio|estimaci[óo]n)\b", t): return "ask_why_budget", 0.8
        if why and re.search(r"\b(scrum|kanban|scrumban|metodolog[ií]a)\b", t): return "ask_why_methodology", 0.8
        if why and re.search(r"\b(equipo|roles|personal|plantilla|dimension)\b", t): return "ask_why_team", 0.8
        if why and re.search(r"(\d+(?:[.,]\d+)?)\s*(pm|project manager|tech\s*lead|arquitect[oa]|backend|frontend|qa|tester|quality|ux|ui|ml|data)", t):
            return "ask_why_role_count", 0.8

        if re.search(r"\b(presupuesto|coste|precio|estimaci[óo]n)\b", t): return "ask_budget", 0.7
        if re.search(r"\b(scrum|kanban|scrumban|metodolog[ií]a)\b", t): return "ask_methodology", 0.7
        if re.search(r"\b(equipo|roles|perfiles|staffing|personal|plantilla|dimension)\b", t): return "ask_team", 0.7
        if re.search(r"\b(riesgo|riesgos)\b", t): return "ask_risks", 0.7

        return "other", 0.3
