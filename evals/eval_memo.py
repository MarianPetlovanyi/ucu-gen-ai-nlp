"""C7 eval: is the memo complete, correctly cited and faithful?

Upstream: C4 (gpt-oss-120b, prompt v3) predictions → C5 report, i.e. the real pipeline. The memo is
compared with the report it was written from, so C4 errors don't count against C7.
Metrics:
- coverage: share of report issues (VIOLATION/MISSING) that have a memo item (target 100%).
- spurious items: memo items for rules that are not issues.
- citation validity: share of cited span ids that are relevant: in the finding's evidence or in the
  top-5 C3 spans for that hypothesis (the raw "exists" check is enforced in code).
- VIOLATION items with ≥1 citation (a violation claim must be checkable).
- faithfulness of cited claims: share of items *with citations* that the judge (Qwen) marks as
  supported by the cited spans.
- absence-claim accuracy: an item without citations for a MISSING rule claims "the contract is silent
  on X". Cited text can't support silence, so the judge can't check it (iteration 9). It is checked
  against gold: correct iff the gold label of that hypothesis is NotMentioned.
- recommendation consistency with the playbook decision (deterministic, should be 100%).
- invented clause references: share of items that write "Clause/Section/Article/Paragraph N" where N is
  not a section number printed in the contract (typically an internal span id), or that mention "span N".
  Deterministic (iteration 12).
"""

from __future__ import annotations

import logging
import re
import statistics as st
from concurrent.futures import ThreadPoolExecutor

from tqdm import tqdm

from evals.common import SYSTEM_NLI_TAG, parse_args, print_table, save_result
from evals.eval_playbook import load_nli
from evals.judge import judge_faithfulness
from nda_review.config import JUDGE_MODEL, SYSTEM_MODEL
from nda_review.data import load_hypotheses, load_playbook, load_split
from nda_review.llm import LLMError, load_prompt, prompt_hash
from nda_review.memo import PROMPT as MEMO_PROMPT
from nda_review.memo import write_memo
from nda_review.playbook import ISSUE_STATUSES, assess
from nda_review.retrieve import retrieve

log = logging.getLogger(__name__)

NLI_TAG = SYSTEM_NLI_TAG


_REF = re.compile(r"\b(clause|section|paragraph|article|span)\s+(\d+(?:\.\d+)*)", re.IGNORECASE)


def invented_refs(text: str, contract_text: str) -> list[str]:
    """Clause references in memo text that don't exist in the contract's own numbering."""
    bad = []
    for kind, num in _REF.findall(text):
        n = re.escape(num)
        printed = re.search(rf"(?:^|\n)\s*{n}(?:[.)]|\s)", contract_text) or re.search(
            rf"\b(?:clause|section|paragraph|article)\s+{n}\b", contract_text, re.IGNORECASE
        )
        if kind.lower() == "span" or not printed:
            bad.append(f"{kind} {num}")
    return bad


def main() -> None:
    args = parse_args(
        __doc__,
        [
            ("--playbook", {"default": "disclosing_party"}),
            ("--workers", {"type": int, "default": 6}),
        ],
    )
    docs = load_split(args.split, args.limit)
    hyps = load_hypotheses()
    pb = load_playbook(args.playbook)
    pred = load_nli(args.split, NLI_TAG)

    def one(doc):
        report = assess(pred[doc.doc_id], pb)
        memo = write_memo(doc.contract, report, pb, hyps)
        findings = {f.rule_id: f for f in report.findings}
        issues = {r for r, f in findings.items() if f.status in ISSUE_STATUSES}
        top5 = {
            h: {x.span_id for x in r.hits} for h, r in retrieve(doc.contract, hyps, k=5).items()
        }
        span_text = {s.id: " ".join(s.text.split()) for s in doc.contract.spans}
        items = [i for i in memo.issues if i.rule_id in findings]
        absence = [i for i in items if not i.citations and findings[i.rule_id].status == "MISSING"]
        absence_ok = [
            doc.labels[findings[i.rule_id].hypothesis_id] == "NotMentioned" for i in absence
        ]
        cited_items = [i for i in items if i.citations]
        verdicts = {
            v.rule_id: v
            for v in judge_faithfulness(
                [
                    {
                        "rule_id": i.rule_id,
                        "claim": f"{i.headline}. {i.explanation}",
                        "cited": [span_text[c] for c in i.citations],
                    }
                    for i in cited_items
                ]
            )
        }
        cites = []
        for i in items:
            f = findings[i.rule_id]
            relevant = set(f.evidence) | top5[f.hypothesis_id]
            cites += [c in relevant for c in i.citations]
        return {
            "doc_id": doc.doc_id,
            "n_issues": len(issues),
            "covered": len(issues & {i.rule_id for i in memo.issues}),
            "spurious": len({i.rule_id for i in memo.issues} - issues),
            "n_citations": len(cites),
            "relevant_citations": sum(cites),
            "violation_items": sum(findings[i.rule_id].status == "VIOLATION" for i in items),
            "violation_items_cited": sum(
                findings[i.rule_id].status == "VIOLATION" and bool(i.citations) for i in items
            ),
            "n_judged": len(verdicts),
            "n_absence_claims": len(absence),
            "absence_correct": sum(absence_ok),
            "absence_wrong": [
                i.rule_id for i, ok in zip(absence, absence_ok, strict=True) if not ok
            ],
            "supported": sum(v.supported for v in verdicts.values()),
            "unsupported": [
                {"rule_id": v.rule_id, "reason": v.reason}
                for v in verdicts.values()
                if not v.supported
            ],
            "recommendation_ok": memo.recommendation == report.recommendation,
            "items_invented_refs": [
                {"rule_id": i.rule_id, "refs": refs}
                for i in memo.issues
                if (
                    refs := invented_refs(
                        f"{i.headline} {i.explanation} {i.ask}", doc.contract.text
                    )
                )
            ],
            "n_items": len(memo.issues),
            "memo": memo.model_dump(),
            "words": len((memo.summary + " ".join(i.explanation for i in memo.issues)).split()),
        }

    def safe(doc):
        try:
            return one(doc)
        except LLMError as e:  # counted, not fatal
            log.warning("%s failed: %s", doc.doc_id, str(e)[:200])
            return None

    with ThreadPoolExecutor(args.workers) as ex:
        results = list(tqdm(ex.map(safe, docs), total=len(docs)))
    records = [r for r in results if r is not None]
    s = lambda k: sum(r[k] for r in records)  # noqa: E731
    metrics = {
        "n_failed_docs": len(results) - len(records),
        "coverage": s("covered") / s("n_issues") if s("n_issues") else 1.0,
        "n_issues": s("n_issues"),
        "spurious_items": s("spurious"),
        "citation_relevance": s("relevant_citations") / s("n_citations") if s("n_citations") else 0,
        "n_citations": s("n_citations"),
        "violation_items_cited": s("violation_items_cited") / s("violation_items")
        if s("violation_items")
        else 0,
        "faithfulness_cited": s("supported") / s("n_judged") if s("n_judged") else 0,
        "n_judged": s("n_judged"),
        "absence_claim_accuracy": s("absence_correct") / s("n_absence_claims")
        if s("n_absence_claims")
        else 0,
        "n_absence_claims": s("n_absence_claims"),
        "recommendation_consistency": st.mean(r["recommendation_ok"] for r in records),
        "invented_ref_rate": sum(len(r["items_invented_refs"]) for r in records) / s("n_items"),
        "mean_words": st.mean(r["words"] for r in records),
    }
    print_table([metrics])
    path = save_result(
        "memo",
        args.split,
        n=len(docs),
        metrics=metrics,
        records=records,
        tag=args.playbook,
        config={
            "playbook": args.playbook,
            "upstream_nli": NLI_TAG,
            "system_model": SYSTEM_MODEL,
            "judge_model": JUDGE_MODEL,
            "memo_prompt": MEMO_PROMPT,
            "prompt_hash": prompt_hash(load_prompt(MEMO_PROMPT)),
            "judge_prompt_hash": prompt_hash(load_prompt("judge_faithfulness")),
        },
    )
    print(f"saved {path}")


if __name__ == "__main__":
    main()
