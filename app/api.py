"""NDA Playbook Reviewer: HTTP API for the Next.js UI in `web/`.

Like `app/streamlit_app.py` it only calls `nda_review.pipeline`, plus read-only loaders (playbooks,
hypotheses, dev examples) and the eval result files for the dashboard. No business logic lives here.

Run: uv run uvicorn app.api:app --port 8000
"""

from __future__ import annotations

import glob
import json
import logging
import re
import tempfile
from functools import lru_cache
from pathlib import Path
from typing import Annotated, Any

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.concurrency import run_in_threadpool

from nda_review import pipeline
from nda_review.config import RESULTS_DIR
from nda_review.data import GoldDoc, list_playbooks, load_hypotheses, load_playbook, load_split
from nda_review.llm import LLMError

log = logging.getLogger(__name__)
app = FastAPI(title="NDA Playbook Reviewer API", version="1.0")

ALLOWED_SUFFIXES = {".pdf", ".htm", ".html", ".txt"}
MAX_UPLOAD_BYTES = 10 * 1024 * 1024
SYSTEM_NLI_TAG = "llm-gpt-oss-120b-nli_v4-medium-full"
COMPONENTS = [
    {"id": "C1", "name": "Ingestion", "type": "tool", "does": "PDF/HTML/TXT → text"},
    {"id": "C2", "name": "Segmentation", "type": "tool", "does": "text → numbered spans"},
    {"id": "C3", "name": "Evidence retrieval", "type": "local model", "does": "rule → top spans"},
    {
        "id": "C4",
        "name": "NLI + evidence",
        "type": "LLM",
        "does": "contract × 17 hypotheses → label + span ids",
    },
    {
        "id": "C5",
        "name": "Playbook compliance",
        "type": "deterministic",
        "does": "labels → status, risk, recommendation",
    },
    {
        "id": "C6",
        "name": "Redline drafter",
        "type": "LLM",
        "does": "issues → replacement / inserted clauses",
    },
    {"id": "C7", "name": "Negotiation memo", "type": "LLM", "does": "report → memo with citations"},
]


# --- reference data ---------------------------------------------------------------------------
def _playbook_info(name: str) -> dict[str, Any]:
    pb = load_playbook(name)
    return {
        "id": name,
        "name": pb.name,
        "perspective": pb.perspective,
        "sign_max_risk": pb.scoring.sign_max_risk,
        "reject_min_risk": pb.scoring.reject_min_risk,
        "rules": [r.model_dump() for r in pb.rules],
    }


@lru_cache(maxsize=1)
def _examples() -> dict[str, GoldDoc]:
    return {d.doc_id: d for d in load_split("dev")}


@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/api/components")
def components() -> list[dict[str, str]]:
    return COMPONENTS


@app.get("/api/playbooks")
def playbooks() -> list[dict[str, Any]]:
    return [_playbook_info(n) for n in list_playbooks()]


@app.get("/api/examples")
def examples() -> list[dict[str, str]]:
    return [
        {"id": d.doc_id, "file_name": d.file_name, "format": d.raw_path.suffix.lstrip(".").lower()}
        for d in _examples().values()
    ]


# --- review -----------------------------------------------------------------------------------
def _safe_name(name: str) -> str:
    stem = re.sub(r"[^A-Za-z0-9._-]+", "_", Path(name).name).strip("._") or "upload"
    return stem[:120]


@app.post("/api/review")
async def review(
    playbook: Annotated[str, Form()],
    with_redlines: Annotated[bool, Form()] = True,
    with_memo: Annotated[bool, Form()] = True,
    example_id: Annotated[str | None, Form()] = None,
    text: Annotated[str | None, Form()] = None,
    file: Annotated[UploadFile | None, File()] = None,
) -> dict[str, Any]:
    if playbook not in list_playbooks():
        raise HTTPException(400, f"unknown playbook {playbook!r}")
    sources = [example_id, text and text.strip(), file]
    if sum(bool(s) for s in sources) != 1:
        raise HTTPException(400, "give exactly one of example_id, text or file")
    kw = {"with_redlines": with_redlines, "with_memo": with_memo}
    try:
        if example_id:
            doc = _examples().get(example_id)
            if doc is None:
                raise HTTPException(404, f"unknown example {example_id!r}")
            res = await run_in_threadpool(pipeline.review_file, doc.raw_path, playbook, **kw)
            source = {"kind": "example", "name": doc.file_name, "id": doc.doc_id}
        elif file is not None:
            name = _safe_name(file.filename or "upload.txt")
            if Path(name).suffix.lower() not in ALLOWED_SUFFIXES:
                raise HTTPException(400, "upload a PDF, HTML or TXT file")
            data = await file.read()
            if len(data) > MAX_UPLOAD_BYTES:
                raise HTTPException(413, "file larger than 10 MB")
            with tempfile.TemporaryDirectory() as tmp:
                path = Path(tmp) / name
                path.write_bytes(data)
                res = await run_in_threadpool(pipeline.review_file, path, playbook, **kw)
            source = {"kind": "file", "name": name}
        else:
            res = await run_in_threadpool(pipeline.review_text, text, playbook, "pasted", **kw)
            source = {"kind": "text", "name": "pasted text"}
    except LLMError as e:
        log.warning("review failed: %s", str(e)[:300])
        raise HTTPException(502, f"LLM call failed: {str(e)[:300]}") from e
    return {
        "result": res.model_dump(),
        "cost_usd": res.cost_usd,
        "source": source,
        "playbook": _playbook_info(playbook),
        "hypotheses": {h.id: h.model_dump() for h in load_hypotheses()},
        "components": COMPONENTS,
    }


# --- evaluation dashboard ---------------------------------------------------------------------
def _latest(component: str, pattern: str) -> dict | None:
    files = sorted(glob.glob(str(RESULTS_DIR / component / pattern)))
    return json.loads(Path(files[-1]).read_text()) if files else None


def _latest_with_key(component: str, split: str, key: str) -> dict | None:
    """Newest result of `split` whose metrics contain `key` (playbook results mix NLI tags)."""
    for f in sorted(glob.glob(str(RESULTS_DIR / component / f"*_{split}*.json")), reverse=True):
        d = json.loads(Path(f).read_text())
        if key in d["metrics"]:
            return d
    return None


def _v(value: Any, n: Any) -> dict | None:
    return None if value is None else {"value": round(float(value), 4), "n": n}


def _get(d: dict | None, *path: str) -> Any:
    for p in path:
        if not isinstance(d, dict) or p not in d:
            return None
        d = d[p]
    return d


def _split_series() -> list[dict[str, str]]:
    return [{"key": "dev", "label": "Dev"}, {"key": "test", "label": "Test"}]


def _panel(pid, title, unit_note, rows, *, better="higher", target=None, series=None) -> dict:
    return {
        "id": pid,
        "title": title,
        "note": unit_note,
        "better": better,
        "target": target,
        "series": series or _split_series(),
        "rows": [r for r in rows if any(v is not None for v in r["values"].values())],
    }


def _row(label: str, kind: str, values: dict[str, dict | None]) -> dict:
    return {"label": label, "kind": kind, "values": values}


def _eval_summary() -> dict[str, Any]:
    S = ("dev", "test")
    ing = {s: _latest("ingest", f"*_{s}.json") for s in S}
    seg = {s: _latest("segment", f"*_{s}.json") for s in S}
    ret = {s: _latest("retrieve", f"*_{s}.json") for s in S}
    nli_tags = {
        "majority": ("Majority per hypothesis", "baseline"),
        "zeroshot": ("Zero-shot DeBERTa", "baseline"),
        "finetuned": ("Fine-tuned DeBERTa", "baseline"),
        SYSTEM_NLI_TAG: ("gpt-oss-120b (system)", "system"),
    }
    nli = {(t, s): _latest("nli", f"*_{s}_{t}.json") for t in nli_tags for s in S}
    red = {s: _latest("redline", f"*_{s}_disclosing_party-gold.json") for s in S}
    memo = {s: _latest("memo", f"*_{s}_disclosing_party.json") for s in S}
    e2e = {s: _latest("e2e", f"*_{s}_disclosing_party.json") for s in S}

    def ingest_row(method, label, kind, metric, n_key="evidence_n"):
        return _row(
            label,
            kind,
            {
                s: _v(
                    _get(ing[s], "metrics", method, "all", metric),
                    _get(ing[s], "metrics", method, "all", n_key),
                )
                for s in S
            },
        )

    def seg_row(key, label, kind):
        return _row(
            label,
            kind,
            {
                s: _v(
                    _get(seg[s], "metrics", key, "evidence_recall"),
                    _get(seg[s], "metrics", key, "n_evidence_spans"),
                )
                for s in S
            },
        )

    def ret_row(key, label, kind, metric):
        return _row(
            label,
            kind,
            {
                s: _v(_get(ret[s], "metrics", key, metric), _get(ret[s], "metrics", key, "n_pairs"))
                for s in S
            },
        )

    def nli_row(tag, metric_path):
        label, kind = nli_tags[tag]
        vals = {}
        for s in S:
            m = _get(nli[(tag, s)], "metrics")
            n = (
                _get(m, "evidence", "n_pairs")
                if metric_path[0] == "evidence"
                else _get(m, "n_pairs")
            )
            vals[s] = _v(_get(m, *metric_path), n)
        return _row(label, kind, vals)

    def c5_row(tag, pb, metric):
        label, kind = nli_tags[tag]
        vals = {}
        for s in S:
            m = _get(_latest_with_key("playbook", s, f"{tag}/{pb}"), "metrics", f"{tag}/{pb}")
            vals[s] = _v(_get(m, metric), _get(m, "n_gold_issues"))
        return _row(label, kind, vals)

    def red_row(method, label, kind, metric):
        return _row(
            label,
            kind,
            {
                s: _v(
                    _get(red[s], "metrics", method, metric),
                    _get(red[s], "metrics", method, "n_issues"),
                )
                for s in S
            },
        )

    def memo_row(label, metric, n_key):
        return _row(
            label,
            "metric",
            {s: _v(_get(memo[s], "metrics", metric), _get(memo[s], "metrics", n_key)) for s in S},
        )

    e2e_series = [
        {"key": "oracle", "label": "Gold upstream (oracle)"},
        {"key": "e2e", "label": "End to end"},
    ]

    def e2e_panel(split: str) -> dict | None:
        m = _get(e2e[split], "metrics")
        if m is None:
            return None
        n_docs = _get(m, "n_contracts")
        rows = [
            _row(
                "C4 macro-F1",
                "metric",
                {
                    "oracle": _v(_get(m, "c4_oracle", "macro_f1"), _get(m, "c4_oracle", "n_pairs")),
                    "e2e": _v(_get(m, "c4_e2e", "macro_f1"), _get(m, "c4_e2e", "n_pairs")),
                },
            ),
        ]
        for pb, short in (("disclosing_party", "disclosing"), ("receiving_party", "receiving")):
            rows.append(
                _row(
                    f"C5 issue recall, {short}",
                    "metric",
                    {
                        "oracle": _v(
                            _get(m, f"c5_oracle/{pb}", "issue_r"),
                            _get(m, f"c5_oracle/{pb}", "n_gold_issues"),
                        ),
                        "e2e": _v(
                            _get(m, f"c5_e2e/{pb}", "issue_r"),
                            _get(m, f"c5_e2e/{pb}", "n_gold_issues"),
                        ),
                    },
                )
            )
        rows.append(
            _row(
                "Gold issues resolved (raised and fixed)",
                "metric",
                {
                    "oracle": None,
                    "e2e": _v(
                        _get(m, "c6_e2e", "gold_issues_resolved"),
                        _get(m, "c6_e2e", "n_gold_issues"),
                    ),
                },
            )
        )
        return _panel(
            f"e2e-{split}",
            f"Whole pipeline from the original file · {split} ({n_docs} contracts)",
            "Oracle: the same system with gold spans. End to end: original PDF/HTML/TXT through C1→C7, no gold input.",
            rows,
            series=e2e_series,
            target={"value": 0.85, "label": "recall target 0.85"},
        )

    comps = [
        {
            "id": "C1",
            "name": "Ingestion",
            "type": "tool",
            "question": "Does the extracted text keep every clause that can be cited?",
            "panels": [
                _panel(
                    "c1-rec",
                    "Evidence recoverability",
                    "Share of gold evidence spans whose words all survive extraction, in order.",
                    [
                        ingest_row(
                            "naive", "Naive extraction", "baseline", "evidence_recoverability"
                        ),
                        ingest_row(
                            "reflow", "Reflow (system)", "system", "evidence_recoverability"
                        ),
                    ],
                ),
                _panel(
                    "c1-line",
                    "Line F1 (paragraph structure)",
                    "Paragraph boundaries recovered; C2 needs them.",
                    [
                        ingest_row("naive", "Naive extraction", "baseline", "line_f1", "n_docs"),
                        ingest_row("reflow", "Reflow (system)", "system", "line_f1", "n_docs"),
                    ],
                ),
            ],
        },
        {
            "id": "C2",
            "name": "Segmentation",
            "type": "tool",
            "question": "Are the clauses that must be cited reproduced exactly?",
            "panels": [
                _panel(
                    "c2-ev",
                    "Evidence-span recall",
                    "Gold evidence spans reproduced exactly (oracle: gold text; end to end: C1 output).",
                    [
                        seg_row("oracle/lines", "One span per line", "baseline"),
                        seg_row("oracle/rules", "Rules (system), gold text", "system"),
                        seg_row("e2e/rules", "Rules (system), after C1", "alternative"),
                    ],
                )
            ],
        },
        {
            "id": "C3",
            "name": "Evidence retrieval",
            "type": "local model",
            "question": "Is the right clause among the top 10 for each rule?",
            "panels": [
                _panel(
                    "c3-r10",
                    "Recall@10",
                    "Gold evidence spans found in the top 10, pairs with evidence.",
                    [
                        ret_row("bm25", "BM25", "baseline", "recall@10"),
                        ret_row("dense", "Dense query", "alternative", "recall@10"),
                        ret_row("hybrid", "Hybrid", "alternative", "recall@10"),
                        ret_row("exemplar", "Exemplar kNN (system)", "system", "recall@10"),
                    ],
                ),
                _panel(
                    "c3-mrr",
                    "MRR",
                    "Mean reciprocal rank of the first gold span.",
                    [
                        ret_row("bm25", "BM25", "baseline", "mrr"),
                        ret_row("exemplar", "Exemplar kNN (system)", "system", "mrr"),
                    ],
                ),
            ],
        },
        {
            "id": "C4",
            "name": "NLI + evidence",
            "type": "LLM",
            "question": "What does the contract say on each of the 17 topics, and where?",
            "panels": [
                _panel(
                    "c4-f1",
                    "Macro-F1 (Entailment / Contradiction / NotMentioned)",
                    "Classes are imbalanced, so every class counts equally. n = contract–hypothesis pairs.",
                    [nli_row(t, ("macro_f1",)) for t in nli_tags],
                ),
                _panel(
                    "c4-c",
                    "Contradiction-F1",
                    "The costliest miss: the contract says the opposite of our position.",
                    [nli_row(t, ("contradiction_f1",)) for t in nli_tags],
                ),
                _panel(
                    "c4-ev",
                    "Evidence F1 (micro)",
                    "Cited span ids vs gold evidence, pairs labelled E or C.",
                    [nli_row(t, ("evidence", "micro_f1")) for t in nli_tags],
                    target={"value": 0.6, "label": "target 0.60"},
                ),
            ],
        },
        {
            "id": "C5",
            "name": "Playbook compliance",
            "type": "deterministic",
            "question": "Are the real issues flagged (the business metric)?",
            "panels": [
                _panel(
                    f"c5-{metric}-{pb}",
                    f"Issue {'recall' if metric == 'issue_r' else 'precision'}, {pb.replace('_', ' ')} playbook",
                    "Issue = VIOLATION or MISSING, vs status derived from gold labels. n = gold issues.",
                    [c5_row(t, pb, metric) for t in nli_tags],
                    target={"value": 0.85, "label": "target 0.85"}
                    if metric == "issue_r"
                    else {"value": 0.7, "label": "target 0.70"},
                )
                for pb in ("disclosing_party", "receiving_party")
                for metric in ("issue_r", "issue_p")
            ],
        },
        {
            "id": "C6",
            "name": "Redline drafter",
            "type": "LLM",
            "question": "Does the redline fix the issue without breaking anything else?",
            "panels": [
                _panel(
                    "c6-fix",
                    "Fix rate",
                    "Issues gone after the redline, re-checked by an independent judge (Qwen). n = issues.",
                    [
                        red_row("template", "Paste playbook clause", "baseline", "fix_rate"),
                        red_row("llm", "gpt-oss-120b (system)", "system", "fix_rate"),
                    ],
                    target={"value": 0.8, "label": "target 0.80"},
                ),
                _panel(
                    "c6-col",
                    "Collateral change rate",
                    "Other rules whose status changed. Lower is better.",
                    [
                        red_row("template", "Paste playbook clause", "baseline", "collateral_rate"),
                        red_row("llm", "gpt-oss-120b (system)", "system", "collateral_rate"),
                    ],
                    better="lower",
                    target={"value": 0.05, "label": "max 0.05"},
                ),
                _panel(
                    "c6-term",
                    "Term mismatch",
                    "Redlines using a defined term the contract doesn't use. Lower is better.",
                    [
                        red_row(
                            "template", "Paste playbook clause", "baseline", "term_mismatch_rate"
                        ),
                        red_row("llm", "gpt-oss-120b (system)", "system", "term_mismatch_rate"),
                    ],
                    better="lower",
                ),
            ],
        },
        {
            "id": "C7",
            "name": "Negotiation memo",
            "type": "LLM",
            "question": "Is the memo complete, correctly cited and faithful?",
            "panels": [
                _panel(
                    "c7",
                    "Memo quality (system)",
                    "Deterministic checks and a validated judge. n differs per metric.",
                    [
                        memo_row("Coverage of issues", "coverage", "n_issues"),
                        memo_row("Citation relevance", "citation_relevance", "n_citations"),
                        memo_row(
                            "Faithfulness of cited claims (judge)", "faithfulness_cited", "n_judged"
                        ),
                        memo_row(
                            "Absence-claim accuracy (vs gold)",
                            "absence_claim_accuracy",
                            "n_absence_claims",
                        ),
                    ],
                )
            ],
        },
    ]
    judge = _latest("judge_validation", "*T135721_dev.json")
    judge_d = _latest("judge_validation", "*T135822_dev.json")
    judge_panel = _panel(
        "judge",
        "Judge validation: Cohen's κ (dev)",
        "Agreement beyond chance. A1: vs gold labels. D: vs Claude Code labels on real outputs.",
        [
            _row(
                "NLI judge vs gold (A1)",
                "metric",
                {
                    "dev": _v(
                        _get(judge, "metrics", "A1_kappa_vs_gold"),
                        _get(judge, "metrics", "A1_n_pairs"),
                    )
                },
            ),
            _row(
                "System vs gold, for reference",
                "baseline",
                {
                    "dev": _v(
                        _get(judge, "metrics", "A1_system_kappa_vs_gold"),
                        _get(judge, "metrics", "A1_n_pairs"),
                    )
                },
            ),
            _row(
                "Memo faithfulness judge (D)",
                "metric",
                {
                    "dev": _v(
                        _get(judge_d, "metrics", "D_memo_kappa"),
                        _get(judge_d, "metrics", "D_memo_n"),
                    )
                },
            ),
            _row(
                "Redline quality judge (D)",
                "metric",
                {
                    "dev": _v(
                        _get(judge_d, "metrics", "D_redline_kappa"),
                        _get(judge_d, "metrics", "D_redline_n"),
                    )
                },
            ),
        ],
        series=[{"key": "dev", "label": "Dev"}],
    )
    e2e_panels = [p for p in (e2e_panel("dev"), e2e_panel("test")) if p]
    return {"components": comps, "e2e": e2e_panels, "judge": judge_panel}


@app.get("/api/eval-summary")
def eval_summary() -> dict[str, Any]:
    return _eval_summary()
