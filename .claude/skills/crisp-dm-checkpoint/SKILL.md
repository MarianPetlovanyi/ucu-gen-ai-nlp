---
name: crisp-dm-checkpoint
description: Close or update a CRISP-DM phase document in docs/crisp-dm/. Use when a phase is finished, before starting the next phase, or when an evaluation result sends the project back to an earlier phase.
---

# CRISP-DM checkpoint

1. Identify the phase (1–6) and open `docs/crisp-dm/0N-*.md`. Create it from the template below if it's missing.
2. Check that the phase's exit criteria are met. If one isn't, say which, and stop. Don't move on.

| Phase | Exit criteria (all required) |
|---|---|
| 1 Business understanding | user persona, business goal, success criteria with numeric targets, scope in/out, playbook rules, risks, plan to the deadline |
| 2 Data understanding | datasets considered (existing before synthetic), chosen dataset + license, size per split, label distribution, length/token stats, quality issues found |
| 3 Data preparation | every transform listed with its reason, processed-file locations, how gold labels for derived tasks (compliance, redlines) are built |
| 4 Modeling | per component: approach, model calls vs tool calls, prompt file, alternatives/baselines tried and why rejected |
| 5 Evaluation | per component: metric + why it is the right metric, n, dev score, test score (final), failure analysis, iteration log |
| 6 Deployment | how to run, demo script, limitations, what we'd do next |

3. Write facts that come from files or eval outputs, not from memory. Link to `evals/results/...` JSON for every number.
4. At the end, add a line `Status: closed YYYY-MM-DD` or `Status: reopened YYYY-MM-DD: <reason>`.

## Template
```markdown
# Phase N: <name>
Status: in progress

## Goal of this phase
## What we did
## Findings / decisions (with evidence links)
## Open issues
```
