"""C3 Evidence retrieval: (contract spans, hypothesis) → spans ranked by relevance.

Tool component (no LLM), local models only:
- `bm25`      lexical baseline, query = hypothesis text
- `dense`     bi-encoder (bge-small) cosine similarity to the hypothesis
- `exemplar`  data-driven: similarity to the *train-split* gold evidence spans of that hypothesis
              (mean of the top-3 cosine similarities), i.e. "spans that look like evidence seen before"
- `hybrid`    reciprocal-rank fusion of bm25 + exemplar
Used for UI highlighting, the small-model baselines (512-token limit) and the retrieval ablation of C4.
"""

from __future__ import annotations

import logging
import os
import re
import threading
from functools import lru_cache
from typing import Literal

import numpy as np

from nda_review.config import EMBED_MODEL, PROCESSED_DIR
from nda_review.schemas import Contract, Hypothesis, RetrievalHit, RetrievalResult

log = logging.getLogger(__name__)
Method = Literal["bm25", "dense", "exemplar", "hybrid"]
QUERY_PREFIX = "Represent this sentence for searching relevant passages: "
_STOP = set(
    [
        "a",
        "an",
        "the",
        "of",
        "to",
        "in",
        "on",
        "for",
        "by",
        "and",
        "or",
        "any",
        "some",
        "shall",
        "may",
        "be",
        "is",
        "are",
        "with",
        "from",
        "that",
        "this",
        "its",
        "as",
        "at",
        "such",
        "other",
        "all",
        "not",
        "no",
        "than",
        "which",
        "who",
        "whom",
    ]
)


def _tokens(text: str) -> list[str]:
    return [t for t in re.findall(r"[a-z]+", text.lower()) if t not in _STOP]


_LOCK = threading.RLock()  # models are loaded once and used from worker threads


@lru_cache(maxsize=1)
def _embedder():
    from sentence_transformers import SentenceTransformer

    # CPU by default: the small model is fast enough and parallel eval processes can't exhaust a
    # 2 GB GPU. Set NDA_EMBED_DEVICE=cuda to use the GPU.
    model = SentenceTransformer(EMBED_MODEL, device=os.environ.get("NDA_EMBED_DEVICE", "cpu"))
    model.max_seq_length = 256
    return model


def embed(texts: list[str], query: bool = False) -> np.ndarray:
    texts = [QUERY_PREFIX + t if query else t for t in texts]
    with _LOCK:
        return _embedder().encode(
            texts, batch_size=64, normalize_embeddings=True, show_progress_bar=False
        )


def _exemplars() -> dict[str, np.ndarray]:
    with _LOCK:
        return _load_exemplars()


@lru_cache(maxsize=1)
def _load_exemplars() -> dict[str, np.ndarray]:
    """Embeddings of train gold evidence spans per hypothesis (cached on disk)."""
    path = PROCESSED_DIR / f"exemplars_{EMBED_MODEL.replace('/', '_')}.npz"
    if path.exists():
        data = np.load(path)
        return {k: data[k] for k in data.files}
    from nda_review.data import load_split  # train split only: no dev/test leakage

    texts: dict[str, list[str]] = {}
    for doc in load_split("train"):
        for h, ids in doc.evidence.items():
            if doc.labels[h] != "NotMentioned":
                texts.setdefault(h, []).extend(doc.contract.spans[i].text.strip() for i in ids)
    out = {h: embed(sorted(set(t))) for h, t in texts.items()}
    path.parent.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(path, **out)
    log.info("built exemplar index: %s", {h: len(v) for h, v in out.items()})
    return out


def _bm25_scores(contract: Contract, hyps: list[Hypothesis]) -> dict[str, np.ndarray]:
    from rank_bm25 import BM25Okapi

    bm25 = BM25Okapi([_tokens(s.text) or ["_"] for s in contract.spans])
    return {h.id: np.asarray(bm25.get_scores(_tokens(h.text))) for h in hyps}


def _dense_scores(span_emb: np.ndarray, hyps: list[Hypothesis]) -> dict[str, np.ndarray]:
    q = embed([h.text for h in hyps], query=True)
    return {h.id: span_emb @ q[i] for i, h in enumerate(hyps)}


def _exemplar_scores(span_emb: np.ndarray, hyps: list[Hypothesis]) -> dict[str, np.ndarray]:
    ex = _exemplars()
    out = {}
    for h in hyps:
        sims = span_emb @ ex[h.id].T  # (n_spans, n_exemplars)
        k = min(3, sims.shape[1])
        out[h.id] = np.sort(sims, axis=1)[:, -k:].mean(axis=1)
    return out


def _rrf(*score_sets: np.ndarray, k: int = 60) -> np.ndarray:
    total = np.zeros_like(score_sets[0], dtype=float)
    for s in score_sets:
        ranks = np.empty(len(s))
        ranks[np.argsort(-s)] = np.arange(len(s))
        total += 1.0 / (k + ranks + 1)
    return total


def score_spans(
    contract: Contract, hyps: list[Hypothesis], method: Method = "exemplar"
) -> dict[str, np.ndarray]:
    """Relevance score of every span for every hypothesis."""
    if not contract.spans:
        return {h.id: np.zeros(0) for h in hyps}
    if method == "bm25":
        return _bm25_scores(contract, hyps)
    span_emb = embed([s.text for s in contract.spans])
    if method == "dense":
        return _dense_scores(span_emb, hyps)
    ex = _exemplar_scores(span_emb, hyps)
    if method == "exemplar":
        return ex
    bm = _bm25_scores(contract, hyps)
    return {h.id: _rrf(bm[h.id], ex[h.id]) for h in hyps}


def retrieve(
    contract: Contract, hyps: list[Hypothesis], k: int = 10, method: Method = "exemplar"
) -> dict[str, RetrievalResult]:
    """C3 entry point: top-k spans per hypothesis, best first."""
    scores = score_spans(contract, hyps, method)
    out = {}
    for h in hyps:
        s = scores[h.id]
        order = np.argsort(-s)[:k]
        out[h.id] = RetrievalResult(
            hypothesis_id=h.id,
            hits=[RetrievalHit(span_id=contract.spans[i].id, score=float(s[i])) for i in order],
        )
    return out
