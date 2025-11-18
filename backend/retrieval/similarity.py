from __future__ import annotations
from typing import List, Dict, Any, Optional
from pathlib import Path
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.neighbors import NearestNeighbors
import threading

from backend.memory.state_store import SessionLocal, ProposalLog


class SimilarityRetriever:
    """
    k-NN sobre requisitos guardados en la BD para encontrar casos similares.
    No requiere entrenamiento offline: aprende de lo que haya en app.db.
    """
    def __init__(self, max_items: int = 500):
        self.max_items = max_items
        self.vectorizer = TfidfVectorizer(ngram_range=(1,2), max_features=5000)
        self.nn = NearestNeighbors(n_neighbors=3, metric="cosine")
        self.docs: List[str] = []
        self.meta: List[Dict[str, Any]] = []
        self._fitted = False
        self.refresh()

    def refresh(self) -> None:
        # Intentar leer la BD; si falla, dejar el índice vacío
        try:
            with SessionLocal() as db:
                rows = db.query(ProposalLog).order_by(ProposalLog.created_at.desc()).limit(self.max_items).all()
                self.docs = []
                self.meta = []
                for r in rows:
                    req = r.requirements or ""
                    pj = r.proposal_json or {}
                    meta = {
                        "id": r.id,
                        "requirements": req,
                        "methodology": pj.get("methodology"),
                        "budget": pj.get("budget", {}),
                        "team": pj.get("team", []),
                        "phases": pj.get("phases", []),
                    }
                    self.docs.append(req)
                    self.meta.append(meta)
        except Exception:
            # si hay problema con la BD, no romper la app; dejar vacío
            self.docs = []
            self.meta = []

        if self.docs:
            X = self.vectorizer.fit_transform(self.docs)
            self.nn.fit(X)
            self._fitted = True
        else:
            self._fitted = False

    def retrieve(self, query: str, top_k: int = 3) -> List[Dict[str, Any]]:
        if not self._fitted:
            return []
        q = self.vectorizer.transform([query])
        dist, idx = self.nn.kneighbors(q, n_neighbors=min(top_k, len(self.docs)))
        res = []
        for d, i in zip(dist[0], idx[0]):
            meta = dict(self.meta[int(i)])
            meta["similarity"] = float(1.0 - d)
            res.append(meta)
        return res

# Singleton global para que planner/brain compartan el mismo índice
_GLOBAL: Optional[SimilarityRetriever] = None
_LOCK = threading.Lock()


def get_retriever() -> SimilarityRetriever:
    """Devuelve un singleton thread-safe del retriever."""
    global _GLOBAL
    if _GLOBAL is None:
        with _LOCK:
            if _GLOBAL is None:
                _GLOBAL = SimilarityRetriever()
    return _GLOBAL
