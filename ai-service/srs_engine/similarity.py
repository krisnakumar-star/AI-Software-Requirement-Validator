"""Requirement similarity.

Default backend: TF-IDF cosine similarity over stemmed, terminology-normalised
unigrams and bigrams, implemented in pure Python (no model, no download).

Optional backend: a local sentence-transformers model, enabled only when
SRS_SEMANTIC_MODEL points at a model that was installed beforehand (see
setup_models.py). It is loaded lazily on first use with local files only, so
the service never downloads a model at startup or during a request.
"""
from __future__ import annotations

import logging
import math
import os
import threading
from collections import Counter

from .text import content_terms

logger = logging.getLogger("srs-analyzer.similarity")


def _features(text: str) -> list[str]:
    terms = content_terms(text)
    return terms + [f"{a}_{b}" for a, b in zip(terms, terms[1:])]


class TfidfIndex:
    def __init__(self, texts: list[str]):
        docs = [Counter(_features(t)) for t in texts]
        n = len(docs)
        df = Counter(term for doc in docs for term in doc)
        self.idf = {term: math.log((1 + n) / (1 + count)) + 1 for term, count in df.items()}
        self.vectors = []
        for doc in docs:
            vec = {term: (1 + math.log(tf)) * self.idf[term] for term, tf in doc.items()}
            norm = math.sqrt(sum(v * v for v in vec.values())) or 1.0
            self.vectors.append({term: v / norm for term, v in vec.items()})
        self.terms = [set(doc) for doc in docs]

    def cosine(self, i: int, j: int) -> float:
        a, b = self.vectors[i], self.vectors[j]
        if len(a) > len(b):
            a, b = b, a
        return sum(v * b.get(term, 0.0) for term, v in a.items())

    def shared_terms(self, i: int, j: int) -> list[str]:
        return sorted(t for t in self.terms[i] & self.terms[j] if "_" not in t)


class SemanticBackend:
    """Optional local embedding model with graceful fallback."""

    def __init__(self):
        self._model = None
        self._lock = threading.Lock()
        self._error: str | None = None
        self.model_path = os.getenv("SRS_SEMANTIC_MODEL", "").strip()
        self.enabled = bool(self.model_path) and os.getenv("SRS_SEMANTIC_BACKEND", "auto").lower() != "off"

    def status(self) -> dict:
        if not self.enabled:
            return {"backend": "tfidf", "semantic_model": None, "semantic_status": "disabled (SRS_SEMANTIC_MODEL not set)"}
        if self._error:
            return {"backend": "tfidf", "semantic_model": self.model_path, "semantic_status": f"unavailable: {self._error}"}
        return {"backend": "tfidf+sentence-transformers", "semantic_model": self.model_path,
                "semantic_status": "loaded" if self._model is not None else "configured (loads on first use)"}

    def _load(self):
        if self._model is not None or self._error or not self.enabled:
            return self._model
        with self._lock:
            if self._model is not None or self._error:
                return self._model
            try:
                from sentence_transformers import SentenceTransformer  # optional dependency
                os.environ.setdefault("HF_HUB_OFFLINE", "1")
                self._model = SentenceTransformer(self.model_path, device="cpu", local_files_only=True)
                logger.info("Loaded local semantic model from %s", self.model_path)
            except ImportError:
                self._error = "sentence-transformers is not installed"
            except Exception as exc:  # model missing/corrupt: keep the lightweight engine working
                self._error = f"{type(exc).__name__}: could not load the local model"
                logger.warning("Semantic model unavailable, using TF-IDF only: %s", exc)
        return self._model

    def matrix(self, texts: list[str]) -> list[list[float]] | None:
        model = self._load()
        if model is None or len(texts) < 2:
            return None
        try:
            embeddings = model.encode(texts, batch_size=32, normalize_embeddings=True, show_progress_bar=False)
            return (embeddings @ embeddings.T).tolist()
        except Exception as exc:
            logger.warning("Semantic similarity failed, using TF-IDF only: %s", exc)
            return None


SEMANTIC = SemanticBackend()


class Similarity:
    def __init__(self, texts: list[str]):
        self.tfidf = TfidfIndex(texts)
        self.semantic = SEMANTIC.matrix(texts) if len(texts) <= 2000 else None
        self.backend = "tfidf+sentence-transformers" if self.semantic else "tfidf"

    def score(self, i: int, j: int) -> float:
        lexical = self.tfidf.cosine(i, j)
        if self.semantic is None:
            return lexical
        return 0.5 * lexical + 0.5 * max(0.0, float(self.semantic[i][j]))

    def shared_terms(self, i: int, j: int) -> list[str]:
        return self.tfidf.shared_terms(i, j)
