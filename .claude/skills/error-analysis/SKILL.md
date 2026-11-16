---
name: error-analysis
description: Analyse the failures in the latest eval result of a component, group them into error categories with counts, and propose the next CRISP-DM step. Use after every eval run, and when a score is lower than expected or has to be explained.
---

# Error analysis

1. Load the newest `evals/results/<component>/*_dev.json`. Use the per-example records, never the aggregate alone.
2. Build the confusion view that fits the component: a confusion matrix for classification, misses@k by rule for
   retrieval, unfixed violations for redlines.
3. Read **at least 15 failures** (or all of them, if there are fewer), chosen at random with a fixed seed. Don't
   cherry-pick. For each, write one line: id, what went wrong, and the suspected cause.
4. Group the failures into categories and count them. Typical categories here:
   - negation or exception scope ("except as required by law")
   - definitional clauses mistaken for obligations
   - evidence split across several spans
   - gold-label noise (cite the span to justify it)
   - segmentation or ingestion errors upstream
   - output-format or parsing failures
5. Separate **our errors** from **upstream errors** (caused by an earlier component) and from **label noise**.
   - "Label noise" or "annotation convention" is a claim about the data. **Check it on train label counts**
     (e.g. "contracts with pattern X are labelled N in 77/117 train docs") before writing it down or turning it
     into a prompt rule. Never adopt a convention from one dev example (iteration 5 overfit this way).
   - If many failures of an LLM-judged metric share one shape (e.g. absence claims without citations), first
     ask whether the **metric** is wrong for that shape (iteration 9), before blaming the component.
   - Every cause you write in the docs must come from records you inspected in this session, with the count
     and example ids. Don't write plausible-sounding causes from memory.
6. Propose at most 3 concrete changes, ranked by expected impact. For each, give the CRISP-DM phase it sends us
   back to (data prep or modeling) and how we'll measure it.
7. Write the findings to the component's section of `docs/crisp-dm/05-evaluation.md` under "Failure analysis".
