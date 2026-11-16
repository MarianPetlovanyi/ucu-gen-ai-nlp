---
name: run-eval
description: Run one or all component evaluations of the NDA reviewer, compare with the previous run, and record the result in the CRISP-DM iteration log. Use after any change to a component, prompt, model id or playbook, and for the final test-split numbers.
---

# Run evals

1. Decide the scope: the changed component **plus everything downstream of it**
   (C1→C2→C3→C4→C5→C6→C7). A change to C3 means re-running C3, C4, C5, C6 and C7.
   Always finish with `evals.eval_e2e` (the whole pipeline from the original files, no gold input): a
   component gain that disappears end to end is not a gain for the user.
2. Run on **dev**: `uv run python -m evals.eval_<component> --split dev`.
   - Use `--limit N` only for smoke tests, and never report limited runs as results.
   - The LLM cache makes re-runs of unchanged prompts free. A prompt change invalidates the cache automatically
     (the cache key includes the prompt text).
3. Compare with the previous result JSON in `evals/results/<component>/`. Report metric deltas and how many
   examples changed outcome. For C4 use `uv run python -m evals.compare_runs <tag_a> <tag_b>` (paired
   bootstrap over documents). A change whose 95% CI includes 0 is **noise**: adopt it only if the business
   metric (C5 issue recall/precision) improves, and say so in the log.
   - Also check the per-hypothesis/per-rule table: a prompt change perturbs *every* output, so look for
     regressions outside the targeted hypothesis.
4. If an LLM judge is involved, check that the judge-validation result is current (same judge model and rubric).
   If it isn't, re-run `evals/validate_judge.py` first. Part D (agreement with a second annotator on *real*
   outputs) counts: a judge that only passes synthetic cases is reported as a secondary number with a caveat.
5. Append one row to the iteration log in `docs/crisp-dm/05-evaluation.md`:
   `| date | component | change | metric before → after | n | decision |`
6. **Test split** runs only when the user asks for final numbers, or at the end of the project. Run them all in one
   go and record them in the final results table.
7. Never delete old result files. They are the evidence of the CRISP-DM iterations.
8. A run must not die on one failed LLM call: the evals record `n_failed_docs`. Report it next to n. If it is
   > 0, re-run (failures aren't cached, so only the failed calls are repeated).
9. Don't run more than two LLM-heavy evals in parallel. They share the Groq per-model rate limit, and the
   Qwen judge is the bottleneck.
