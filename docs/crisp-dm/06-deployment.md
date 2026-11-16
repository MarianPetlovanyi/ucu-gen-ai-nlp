# Phase 6: Deployment
Status: closed 2026-11-14 (prototype deployment for the assignment; production steps listed as next steps)

## What is deployed
A local **Streamlit** app (`app/streamlit_app.py`). It calls only `nda_review.pipeline`:
- `review_file(path, playbook)` runs C1→C7 on an uploaded PDF, HTML or TXT file;
- `review_text(text, playbook)` handles pasted text;
- `review_contract(contract, playbook)` takes an already segmented contract.

The UI flow:
1. Pick the perspective (playbook) and a contract (a dev-split example, an upload, or pasted text).
2. The **Findings** tab shows the status per rule with the model's label, rationale and cited clauses. For
   MISSING rules it adds the closest clauses found by retrieval.
3. The **Contract** tab highlights the evidence spans, coloured by status.
4. The **Redlines** tab shows deletions and insertions, and the revised contract can be downloaded as .txt.
5. The **Memo** tab shows the negotiation memo with quoted citations, downloadable as .md.
6. **Pipeline & traces** shows the component table (LLM vs tool), timings per component, and every LLM call
   with its model, cache hit, latency, tokens and cost.

The demo examples come from the **dev** split, so the test split stays untouched until the final numbers.
The app was checked headless with `streamlit.testing.AppTest`: full review, no exceptions, all 5 tabs render.

## Public demo on DigitalOcean (2026-11-16)
The Next.js UI (`web/`) and its FastAPI layer (`app/api.py`) also run on one droplet at
**https://ucu.nlp.justsolution.co**. Everything is in `deploy/`:
- `deploy/terraform/` creates the droplet (`s-2vcpu-4gb`, `lon1`, Ubuntu 24.04 with Docker from cloud-init), a
  reserved IP, a firewall (22, 80, 443 inbound) and a DO project. DNS stays at the registrar (Namecheap): one
  `A` record `ucu.nlp` → the reserved IP.
- `deploy/docker-compose.yml` runs three containers: **Caddy** (HTTPS via Let's Encrypt, plain HTTP on the
  bare IP), **web** (Next.js, proxies `/api/*`) and **api** (FastAPI → `pipeline.py`, CPU-only torch, bge-small
  baked into the image).
- `deploy/set_login.sh` creates the demo login: HTTP basic auth in Caddy over the UI and `/api/*`. Only a
  bcrypt hash goes to the server; the plain password stays in the git-ignored `deploy/.credentials`.
- `deploy/deploy.sh` syncs the code, `data/`, `playbooks/` and `evals/results/` with rsync, merges the LLM
  cache (so the dev examples review instantly and for free), copies `.env` as a file readable only by root,
  and runs `docker compose up -d --build`.

```bash
export TF_VAR_do_token=...                     # never in a file in the repo
terraform -chdir=deploy/terraform init && terraform -chdir=deploy/terraform apply
deploy/set_login.sh ucu                        # demo login
deploy/deploy.sh                               # re-run after any code change
```

## Operating characteristics (measured, uncached calls from the traces, 2026-11-14)
| Step | Model | Median latency | p90 | Mean cost / call |
|---|---|---|---|---|
| C4 NLI (1 call / contract) | gpt-oss-120b | 6.3 s | 27.5 s | $0.0029 |
| C6 redlines | gpt-oss-120b | 3.7 s | 5.5 s | $0.0014 |
| C7 memo | gpt-oss-120b | 4.4 s | 5.3 s | $0.0016 |
| C1+C2 | tools | < 0.2 s | | 0 |
| C3 retrieval | bge-small, CPU | ≈ 9 s cold (model load), < 1 s warm | | 0 |

Confirmed on the **test** run (about 122 uncached calls per component), per call median / p90 / mean
cost: C4 5.8 s / 8.1 s / $0.0020; C6 3.7 s / 5.5 s / $0.0014; C7 4.4 s / 6.1 s / $0.0017. That is about
**$0.005 and ≈ 14 s of LLM time per contract**.

**One contract costs about $0.006 and takes 15–45 s end to end**, against the business targets of < $0.02 and
< 2 min (phase 1). An external first-pass review costs €150–250 and takes 2–5 days. The long C4 p90 comes from
the gpt-oss reasoning on long contracts and from Groq queueing during parallel eval runs.
Total API spend for the whole project up to the final test run (all iterations, ablations and judge runs): **$3.29** over 2 093 uncached calls (gpt-oss $1.66, Qwen judge $1.64), from the traces.

## Monitoring and maintenance
- **Traces**: every LLM call appends one JSON line to `.cache/traces/<date>.jsonl` with the component, model,
  latency, tokens, cost and cache key. The UI shows the traces of the current review.
- **Changing policy** means editing `playbooks/*.yaml` (stance, severity, weights, thresholds, preferred
  clauses). Then re-run `eval_playbook`, `eval_redline` and `eval_memo` (the `run-eval` skill). No code change.
- **Changing a prompt or model** means a new prompt file (`nli_v4.md`) or a new id in `config.py`. Every result
  stores the prompt hash, so runs can be compared. Re-run the component eval and every downstream eval.
- **Drift check**: the label distribution per hypothesis in production can be compared with the train priors
  (`nli.train_priors`). A large shift suggests a new contract style.

## Risks and mitigations
| Risk | Mitigation in the prototype | What production would need |
|---|---|---|
| A missed violation (false negative) | recall-oriented targets. MISSING counts as an issue. Every OK finding still shows its evidence | lawyer sign-off stays mandatory. Low-confidence findings flagged for review |
| A hallucinated citation | evidence and citations are span ids, validated in code. Invalid ids are dropped and counted | as now |
| A redline that changes something else or lands in the wrong place | collateral-change metric in the eval. Insertion points moved to sentence or list ends (`safe_anchor`). Redlines are shown as a diff, never auto-applied to the source | DOCX track changes so counsel can accept or reject each one |
| Confidential contract text sent to an API | Groq API with a key from `.env`. Nothing is logged except tokens and costs | a vendor DPA / zero-retention setting, or a self-hosted model |
| Scanned PDFs | C1 warns when a page has no text layer | OCR (out of scope) |
| Annotation conventions differ from the company's reading of a clause | the conventions are written in the prompt (`nli_v4`) and in phase 3 | calibrate on the company's own reviewed NDAs |

## Not done (honest scope)
- No user accounts, multi-user storage or DOCX export. The public demo has one shared basic-auth login, which
  keeps strangers from spending the Groq key (about $0.005 per uncached review). Uploaded contracts still go
  to Groq, as in the local app.
- Free-text custom rules beyond the 17 ContractNLI hypotheses are not supported. The playbook maps rules onto
  those hypotheses.
- The UI keeps results only in the session. The LLM disk cache makes re-runs instant.
