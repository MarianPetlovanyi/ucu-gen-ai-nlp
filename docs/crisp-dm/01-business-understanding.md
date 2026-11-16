# Phase 1: Business understanding
Status: closed 2026-11-14 (to be reopened if evaluation shows the targets are unrealistic)

## Business context
**Lumen Robotics** (fictional) is a 40-person hardware start-up that signs roughly 10 NDAs a month with manufacturers,
suppliers and investors. Today every NDA goes to one external lawyer: about 1 hour and €150–250 per review, and
a 2–5 day turnaround that delays partner meetings. Most NDAs are routine. What the company needs is a fast
**first-pass review** that checks the contract against *its own* negotiating positions (the playbook), points to the
exact clauses, and drafts the fixes, so the lawyer only has to confirm.

**Users**
- *Operations / legal generalist* (primary): uploads the NDA, reads the risk summary, sends the redlines.
- *External lawyer* (secondary): receives the memo and the redlines instead of the raw contract.

The company sits on both sides of NDAs, so the playbook depends on the **perspective**:
- `playbooks/disclosing_party.yaml`: we share prototypes and want strong protection (main scenario).
- `playbooks/receiving_party.yaml`: we evaluate a supplier's technology and want freedom to operate.

The same contract can be compliant from one perspective and risky from the other. That's why the business logic
is configuration (the playbook) and not code.

## Business objectives → success criteria
| Business objective | Measured by | Target (dev) |
|---|---|---|
| Don't miss problems (a missed issue is the expensive error) | issue-detection **recall** (VIOLATION + MISSING) | ≥ 0.85 |
| Don't waste the lawyer's time on false alarms | issue-detection precision | ≥ 0.70 |
| Every finding is checkable | evidence-span F1 against gold evidence | ≥ 0.60 |
| Fixes actually fix the problem | redline fix rate (independent judge re-check) | ≥ 0.80 |
| Fixes don't break other things | collateral label changes on other rules | ≤ 5 % |
| The memo is trustworthy | coverage of detected issues / citation validity | 100 % / ≥ 0.95 |
| Faster and cheaper than a lawyer's first pass | wall time / API cost per contract | < 2 min / < $0.02 |

## Scope
**In scope**
- English NDAs (PDF, HTML or TXT upload, or pasted text).
- The 17 contract concepts annotated in ContractNLI.
- Two playbooks (perspectives) with 17 rules each.
- Per-rule verdicts with evidence, a risk score, redlines, a negotiation memo, and a Streamlit UI with traces.

**Out of scope**
- Other contract types.
- Concepts beyond the 17 hypotheses (custom free-text rules are a stretch goal).
- Legal advice: the output is a draft for a human lawyer.
- DOCX track-changes export.
- Negotiating with the counterparty.

## Data mining goals (business → NLP tasks)
| Business need | NLP task | Component |
|---|---|---|
| Read any NDA file | document ingestion / text extraction | C1 |
| Address individual clauses | sentence and list-item segmentation | C2 |
| Find where a topic is regulated | evidence retrieval (rule → ranked spans) | C3 |
| Decide what the contract says on each topic | document-level NLI (entailment / contradiction / not mentioned) + evidence identification | C4 |
| Apply company policy | rule-based compliance + risk scoring over NLI output | C5 |
| Fix the contract | controlled clause rewriting / insertion | C6 |
| Explain to a human | grounded summarisation with citations | C7 |

## Resources
- **Data:** ContractNLI (CC BY 4.0). See phase 2.
- **LLMs (Groq, developer tier):** `openai/gpt-oss-120b` runs the system. `qwen/qwen3.8-27b` is the independent
  judge (a different model family, to avoid self-preference bias).
- **Local (GTX 1050 2 GB, CPU):** sentence embeddings, a cross-encoder reranker, and a zero-shot NLI baseline.
- **Colab (T4):** fine-tuning a DeBERTa NLI baseline on the ContractNLI train split.
- **Human time:** none available for labelling. Judge validation uses gold-derived known-good and known-bad cases,
  plus Claude Code as a second annotator (reported as a model annotator, not a human).

## Risks and mitigations
| Risk | Mitigation |
|---|---|
| Gold-label noise (single annotator per contract) | report it in the error analysis; quote the clause when we believe the gold label is wrong |
| Hallucinated evidence | the LLM may only cite span ids; ids are validated; evidence F1 is measured |
| Legally wrong redlines | the preferred language comes from the playbook; the judge re-checks the fix; the UI marks output as a draft |
| LLM-judge bias | judge from another model family, validated on known cases before use |
| API outage during the demo | disk cache of all LLM calls; demo contracts pre-run |
| Very short timeline (deadline Monday) | core pipeline first, extras only after every component has an eval |

## Project plan
| When | What |
|---|---|
| Sat afternoon | phases 1–2, C1–C3 + evals, Colab fine-tune started |
| Sat evening | C4 (LLM + baselines) + eval, C5 + eval |
| Sun | C6, C7 + judge validation, UI, CRISP-DM iteration 2 on the weakest component |
| Mon morning | test-split numbers, report and diagrams, README, video |
