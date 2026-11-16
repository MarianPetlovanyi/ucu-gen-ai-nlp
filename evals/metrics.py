"""Deterministic metric functions shared by the evals (unit-tested in tests/test_metrics.py)."""

from __future__ import annotations

from collections.abc import Iterable, Sequence

from evals.common import prf

LABELS = ("Entailment", "Contradiction", "NotMentioned")


def classification_metrics(gold: Sequence[str], pred: Sequence[str], labels=LABELS) -> dict:
    """Accuracy, per-class P/R/F1 and macro-F1 over `labels`."""
    assert len(gold) == len(pred)
    out: dict = {
        "n": len(gold),
        "accuracy": sum(g == p for g, p in zip(gold, pred, strict=True)) / max(1, len(gold)),
    }
    f1s = []
    for lab in labels:
        tp = sum(g == lab and p == lab for g, p in zip(gold, pred, strict=True))
        p_, r_, f_ = prf(tp, sum(p == lab for p in pred), sum(g == lab for g in gold))
        out[lab] = {"p": p_, "r": r_, "f1": f_, "support": sum(g == lab for g in gold)}
        f1s.append(f_)
    out["macro_f1"] = sum(f1s) / len(f1s)
    return out


def confusion(gold: Sequence[str], pred: Sequence[str], labels=LABELS) -> dict[str, dict[str, int]]:
    m = {g: {p: 0 for p in labels} for g in labels}
    for g, p in zip(gold, pred, strict=True):
        m[g][p] += 1
    return m


def evidence_prf(pairs: Iterable[tuple[set[int], set[int]]]) -> dict:
    """Span-level evidence P/R/F1 over (gold, pred) id sets. Micro: pooled counts.
    Macro: mean per-pair F1 (a pair with no predicted spans has F1 = 0)."""
    pairs = list(pairs)
    tp = sum(len(g & p) for g, p in pairs)
    n_pred = sum(len(p) for _, p in pairs)
    n_gold = sum(len(g) for g, _ in pairs)
    mp, mr, mf = prf(tp, n_pred, n_gold)
    per_pair = [prf(len(g & p), len(p), len(g))[2] for g, p in pairs]
    return {
        "micro_p": mp,
        "micro_r": mr,
        "micro_f1": mf,
        "macro_f1": sum(per_pair) / len(per_pair) if per_pair else 0.0,
        "n_pairs": len(pairs),
    }
