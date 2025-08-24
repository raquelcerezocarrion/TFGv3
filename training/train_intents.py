from __future__ import annotations
from pathlib import Path
from typing import List, Tuple
import joblib
from sklearn.pipeline import Pipeline
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.model_selection import train_test_split
from sklearn.metrics import classification_report, accuracy_score

MODELS_DIR = Path("backend/models"); MODELS_DIR.mkdir(parents=True, exist_ok=True)
OUT = MODELS_DIR / "intents.joblib"

INTENTS = {
    "greet": ["hola", "buenas", "hey", "hola que tal", "buenas tardes", "holaaa"],
    "goodbye": ["adios", "hasta luego", "nos vemos", "chao", "me despido"],
    "thanks": ["gracias", "mil gracias", "muchas gracias", "ok gracias"],
    "help": ["ayuda", "que puedes hacer", "como me ayudas", "necesito ayuda"],
    "ask_budget": ["cual es el presupuesto", "precio estimado", "coste del proyecto", "estimacion de coste"],
    "ask_methodology": ["que metodologia es mejor", "scrum o kanban", "metodologia recomendada", "hablame de scrum"],
    "ask_team": ["que equipo necesito", "que roles hacen falta", "dimension del equipo", "que personal"],
    "ask_risks": ["que riesgos hay", "riesgos del proyecto", "riesgos posibles"],
    "ask_why_budget": ["por que ese presupuesto", "justifica el precio", "explica el coste", "motivo del presupuesto"],
    "ask_why_methodology": ["por que kanban", "por que scrum", "explica la metodologia", "motivo de scrumban"],
    "ask_why_team": ["por que ese equipo", "explica los roles del equipo", "motivo del dimensionamiento"],
    "ask_why_role_count": ["por que 2 backend", "por que 1 qa", "por que 0.5 ux", "por que 1 pm"],
}

def _augment(samples: List[str]) -> List[str]:
    out = []
    for s in samples:
        out += [s, s.capitalize(), s + "?", "por favor " + s, s + " por favor"]
    return out

def build_dataset() -> Tuple[List[str], List[str]]:
    X, y = [], []
    for label, texts in INTENTS.items():
        for t in _augment(texts):
            X.append(t); y.append(label)
    # clase other mínima
    other = ["vale", "perfecto", "no lo se", "dame mas info", "continua", "quiero una propuesta para app con pagos", "haz un plan"]
    for s in other:
        X.append(s); y.append("other")
    return X, y

def main():
    X, y = build_dataset()
    Xtr, Xte, ytr, yte = train_test_split(X, y, test_size=0.2, random_state=42, stratify=y)
    pipe = Pipeline([
        ("tfidf", TfidfVectorizer(analyzer="char", ngram_range=(3,5))),
        ("clf", LogisticRegression(max_iter=1000))
    ])
    pipe.fit(Xtr, ytr)
    yhat = pipe.predict(Xte)
    print("[intents] accuracy:", accuracy_score(yte, yhat))
    print(classification_report(yte, yhat))
    joblib.dump(pipe, OUT)
    print(f"[intents] saved -> {OUT}")

if __name__ == "__main__":
    main()
