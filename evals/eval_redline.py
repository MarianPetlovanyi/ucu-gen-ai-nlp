"""C6 eval: do the redlines fix the issues without breaking anything else?

Upstream is oracle by default: issues come from the *gold* NLI labels (C4 errors excluded), so C6 is
measured in isolation. For each contract with ≥1 issue under the playbook, all redlines are applied,
the revised text is segmented with C2 and re-checked by the independent judge (Qwen, NLI prompt v3).
"Before" is the judge on the original text segmented the same way, so both sides share the pipeline.
Metrics:
- fix rate: share of issues whose rule status is OK after the redlines (judge).
  Reported on all gold issues and on judge-confirmed issues (judge-before also sees the issue), the
  cleaner number because judge/gold disagreement can't be blamed on the redline.
- collateral change rate: share of NON-targeted hypotheses whose judge label changed.
- edit ratio: 1 − word-level similarity between original and revised text (lower = more surgical).
- judge quality score (1–5) per redline (judge validated in evals/validate_judge.py).
Baseline: method=template (playbook preferred clause pasted verbatim; no LLM).
"""

from __future__ import annotations

import difflib
import logging
import statistics as st
from concurrent.futures import ThreadPoolExecutor

from tqdm import tqdm

from evals.common import SYSTEM_NLI_TAG, norm_words, parse_args, print_table, save_result
from evals.eval_playbook import load_nli
from evals.judge import judge_nli, judge_redlines
from nda_review.config import JUDGE_MODEL, SYSTEM_MODEL
from nda_review.data import load_hypotheses, load_playbook, load_split
from nda_review.llm import LLMError, load_prompt, prompt_hash
from nda_review.playbook import ISSUE_STATUSES, assess, position_text
from nda_review.redline import PROMPT as REDLINE_PROMPT
from nda_review.redline import apply_redlines, draft_redlines, template_redlines
from nda_review.schemas import NLIDecision, NLIResult
from nda_review.segment import segment

log = logging.getLogger(__name__)

# The playbook drafts with generic defined terms. A redline that uses one of them in a contract that never
# does (e.g. "Receiving Party" in a contract about the "Recipient"/"Company") introduces an undefined term.
GENERIC_TERMS = (
    "Receiving Party",
    "Disclosing Party",
    "Confidential Information",
    "Purpose",
    "Representatives",
)


def term_mismatches(new_text: str, contract_text: str) -> list[str]:
    low = contract_text.lower()
    return [t for t in GENERIC_TERMS if t in new_text and t.lower() not in low]


def edit_ratio(a: str, b: str) -> float:
    return 1 - difflib.SequenceMatcher(None, norm_words(a), norm_words(b), autojunk=False).ratio()


def main() -> None:
    args = parse_args(
        __doc__,
        [
            ("--playbook", {"default": "disclosing_party"}),
            ("--upstream", {"default": "gold", "choices": ["gold", "llm"]}),
            ("--methods", {"nargs": "*", "default": ["template", "llm"]}),
            ("--workers", {"type": int, "default": 6}),
        ],
    )
    docs = load_split(args.split, args.limit)
    hyps = load_hypotheses()
    pb = load_playbook(args.playbook)
    rules = {r.id: r for r in pb.rules}
    hyp_text = {h.id: h.text for h in hyps}
    pred = load_nli(args.split, SYSTEM_NLI_TAG) if args.upstream == "llm" else None

    def upstream(doc):
        if pred is not None:
            return assess(pred[doc.doc_id], pb)
        gold = NLIResult(
            doc_id=doc.doc_id,
            method="gold",
            decisions=[
                NLIDecision(hypothesis_id=h, label=lab, evidence=doc.evidence[h])
                for h, lab in doc.labels.items()
            ],
        )
        return assess(gold, pb)

    def one(doc):
        report = upstream(doc)
        issues = [f for f in report.findings if f.status in ISSUE_STATUSES]
        if not issues:
            return []
        before_c = segment(doc.contract.text, doc.doc_id)
        before = assess(judge_nli(before_c, hyps), pb)
        b_label = {f.hypothesis_id: f.label for f in before.findings}
        b_status = {f.rule_id: f.status for f in before.findings}
        out = []
        for method in args.methods:
            if method == "llm":
                rs = draft_redlines(doc.contract, report, pb, hyps)
            else:
                rs = template_redlines(doc.contract, report, pb, hyps)
            revised = apply_redlines(doc.contract, rs)
            after = assess(judge_nli(segment(revised, doc.doc_id), hyps), pb)
            a_label = {f.hypothesis_id: f.label for f in after.findings}
            a_status = {f.rule_id: f.status for f in after.findings}
            targeted = {f.hypothesis_id for f in issues}
            others = [h.id for h in hyps if h.id not in targeted]
            span_text = {s.id: s.text for s in doc.contract.spans}
            q_items = [
                {
                    "rule_id": r.rule_id,
                    "position": position_text(
                        rules[r.rule_id], hyp_text[rules[r.rule_id].hypothesis]
                    ),
                    "action": r.action,
                    "new_text": r.new_text,
                    "original": " ".join(span_text[i] for i in r.target_span_ids),
                }
                for r in rs.redlines
            ]
            scores = {s.rule_id: s for s in judge_redlines(q_items)}
            drafted = {r.rule_id: r for r in rs.redlines}
            for f in issues:
                r = drafted.get(f.rule_id)
                out.append(
                    {
                        "doc_id": doc.doc_id,
                        "method": method,
                        "rule": f.rule_id,
                        "gold_status": f.status,
                        "judge_before": b_status[f.rule_id],
                        "judge_after": a_status[f.rule_id],
                        "fixed": a_status[f.rule_id] not in ISSUE_STATUSES,
                        "drafted": r is not None,
                        "action": r.action if r else None,
                        "new_text": r.new_text if r else None,
                        "original": " ".join(span_text[i] for i in r.target_span_ids)
                        if r
                        else None,
                        "quality": scores[f.rule_id].score if f.rule_id in scores else None,
                        "quality_problems": scores[f.rule_id].problems
                        if f.rule_id in scores
                        else None,
                        "collateral_changed": [h for h in others if b_label[h] != a_label[h]],
                        "n_others": len(others),
                        "edit_ratio": edit_ratio(doc.contract.text, revised),
                        "term_mismatches": term_mismatches(r.new_text, doc.contract.text)
                        if r
                        else [],
                    }
                )
        return out

    failed: list[str] = []

    def safe(doc):
        try:
            return one(doc)
        except LLMError as e:  # a failed system or judge call is counted, not fatal
            log.warning("%s failed: %s", doc.doc_id, str(e)[:200])
            failed.append(doc.doc_id)
            return []

    with ThreadPoolExecutor(args.workers) as ex:
        records = [r for rs in tqdm(ex.map(safe, docs), total=len(docs)) for r in rs]

    metrics, rows = {}, []
    for method in args.methods:
        rs = [r for r in records if r["method"] == method]
        confirmed = [r for r in rs if r["judge_before"] in ISSUE_STATUSES]
        per_doc = {r["doc_id"]: r for r in rs}  # collateral/edit ratio are per contract
        q = [r["quality"] for r in rs if r["quality"] is not None]
        m = {
            "n_issues": len(rs),
            "n_contracts": len(per_doc),
            "fix_rate": st.mean(r["fixed"] for r in rs),
            "fix_rate_judge_confirmed": st.mean(r["fixed"] for r in confirmed) if confirmed else 0,
            "n_judge_confirmed": len(confirmed),
            "collateral_rate": sum(len(r["collateral_changed"]) for r in per_doc.values())
            / sum(r["n_others"] for r in per_doc.values()),
            "edit_ratio": st.mean(r["edit_ratio"] for r in per_doc.values()),
            "judge_quality": st.mean(q) if q else 0,
            "drafted_rate": st.mean(r["drafted"] for r in rs),
            "term_mismatch_rate": st.mean(bool(r["term_mismatches"]) for r in rs if r["drafted"]),
            "n_failed_docs": len(failed),
        }
        metrics[method] = m
        rows.append({"method": method, **m})
    print_table(rows)
    path = save_result(
        "redline",
        args.split,
        n=len(docs),
        metrics=metrics,
        records=records,
        tag=f"{args.playbook}-{args.upstream}",
        config={
            "playbook": args.playbook,
            "upstream": args.upstream,
            "system_model": SYSTEM_MODEL,
            "judge_model": JUDGE_MODEL,
            "redline_prompt": REDLINE_PROMPT,
            "prompt_hash": prompt_hash(load_prompt(REDLINE_PROMPT)),
            "judge_prompt_hash": prompt_hash(load_prompt("judge_redline")),
        },
    )
    print(f"saved {path}")


if __name__ == "__main__":
    main()
