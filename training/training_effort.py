from __future__ import annotations
from typing import List, Dict, Any, Tuple
from pathlib import Path
import math
import joblib
import numpy as np

from sklearn.pipeline import Pipeline
from sklearn.feature_extraction import DictVectorizer
from sklearn.linear_model import LinearRegression
from sklearn.metrics import mean_squared_error

from backend.memory.state_store import SessionLocal, ProposalLog, ProposalFeedback
from backend.ml.runtime import extract_features

OUT_PATH = Path("backend/models/effort.joblib")
OUT_PATH.parent.mkdir(parents=True, exist_ok=True)

def _effort_from_proposal(p: Dict[str, Any]) -> float | None:
    b = (p or {}).get("budget", {})
    ass = (b or {}).get("assumptions", {})
    v = ass.get("effort_person_weeks")
    if v is not None:
        try:
            return float(v)
        except Exception:
            pass
    try:
        heads = float(ass.get("heads_equivalent", 0))
        weeks = float(ass.get("project_weeks", 0))
        if heads > 0 and weeks > 0:
            return heads * weeks
    except Exception:
        pass
    return None

def _weight_from_feedbacks(fbs: List[ProposalFeedback]) -> float:
    if not fbs:
        return 1.0  # sin opinión → peso neutro
    w = 1.0
    for fb in fbs:
        if fb.accepted:
            w += 1.0
        else:
            w = max(0.3, w - 0.5)
        if fb.score is not None:
            # centra en 3: (5→+1), (1→-1)
            w += 0.25 * (int(fb.score) - 3)
    # evita pesos extremos
    return float(max(0.1, min(5.0, round(w, 2))))

def load_training_data() -> Tuple[List[Dict[str, float]], List[float], List[float]]:
    X_dicts: List[Dict[str, float]] = []
    y: List[float] = []
    w: List[float] = []
    with SessionLocal() as db:
        rows = db.query(ProposalLog).all()
        for r in rows:
            eff = _effort_from_proposal(r.proposal_json)
            if eff is None:
                continue
            feats = extract_features(r.requirements or "")
            fbs = db.query(ProposalFeedback).filter(ProposalFeedback.proposal_id == r.id).all()
            weight = _weight_from_feedbacks(fbs)
            X_dicts.append(feats)
            y.append(float(eff))
            w.append(weight)
    return X_dicts, y, w

def main():
    X_dicts, y, w = load_training_data()
    n = len(y)
    if n < 4:
        print(f"[train_effort] Muy pocos datos ({n}). Genera más propuestas y feedback.")
        return
    pipe = Pipeline([
        ("dv", DictVectorizer(sparse=False)),
        ("lr", LinearRegression())
    ])
    pipe.fit(X_dicts, y, **({"lr__sample_weight": np.array(w)} if hasattr(LinearRegression, "fit") else {}))
    preds = pipe.predict(X_dicts)
    rmse = math.sqrt(mean_squared_error(y, preds, sample_weight=np.array(w)))
    joblib.dump(pipe, OUT_PATH)
    print(f"[train_effort] Guardado {OUT_PATH}  N={n}  RMSE≈{rmse:.2f}")

if __name__ == "__main__":
    main()
