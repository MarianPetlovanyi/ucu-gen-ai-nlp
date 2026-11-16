"use client";

import { useEffect, useState } from "react";
import { getEvalSummary } from "@/lib/api";
import type { EvalComponent, EvalSummary, Panel } from "@/lib/types";
import { EvalChart } from "./charts";
import { Card, ErrorBox } from "./ui";

export default function EvaluationDashboard() {
  const [data, setData] = useState<EvalSummary | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    getEvalSummary()
      .then(setData)
      .catch((e: Error) => setError(`Cannot load eval results (${e.message}). Is the API running on port 8000?`));
  }, []);

  return (
    <div className="mx-auto max-w-[1500px] px-4 py-6">
      <header className="mb-6 max-w-3xl">
        <h1 className="text-2xl font-semibold text-ink">Evaluation of every component</h1>
        <p className="mt-2 text-sm text-ink-2">
          Each component (C1–C7) has its own eval against ContractNLI gold labels and spans, compared with a simple
          baseline. Dev is the split we iterated on; test was run once at the end for the final numbers. The last
          section runs the whole pipeline from the original files with no gold input. Numbers come from the latest
          result files in <code className="rounded bg-surface-2 px-1 text-xs">evals/results/</code>; n is shown next to
          every value.
        </p>
      </header>
      {error && <ErrorBox>{error}</ErrorBox>}
      {!data && !error && <p className="text-sm text-muted">Loading eval results…</p>}
      {data && (
        <div className="space-y-10">
          <nav className="flex flex-wrap gap-2 text-xs">
            {data.components.map((c) => (
              <a
                key={c.id}
                href={`#${c.id}`}
                className="rounded-full border border-line bg-surface px-2.5 py-1 text-ink-2 hover:text-ink"
              >
                {c.id} {c.name}
              </a>
            ))}
            <a href="#e2e" className="rounded-full border border-line bg-surface px-2.5 py-1 text-ink-2 hover:text-ink">
              End to end
            </a>
            <a href="#judge" className="rounded-full border border-line bg-surface px-2.5 py-1 text-ink-2 hover:text-ink">
              Judge validation
            </a>
          </nav>
          {data.components.map((c) => (
            <ComponentSection key={c.id} c={c} />
          ))}
          <section id="e2e" className="scroll-mt-4">
            <SectionHeader
              id="E2E"
              name="Whole pipeline, end to end"
              type="C1→C7"
              question="Does the system still work when nothing upstream is gold?"
            />
            {data.e2e.length === 0 ? (
              <p className="text-sm text-muted">No end-to-end result files yet.</p>
            ) : (
              <PanelGrid panels={data.e2e} />
            )}
          </section>
          <section id="judge" className="scroll-mt-4">
            <SectionHeader
              id="J"
              name="LLM judge validation"
              type="Qwen judge"
              question="Can the judge metrics be trusted? κ ≥ 0.6 is substantial agreement."
            />
            <PanelGrid panels={[data.judge]} />
            <p className="mt-2 max-w-3xl text-xs text-muted">
              The redline judge agreed with a second annotator on real outputs at only κ ≈ 0.02, so the redline quality
              score is not reported as a headline number; C6 relies on the deterministic fix-rate and collateral checks
              instead.
            </p>
          </section>
        </div>
      )}
    </div>
  );
}

function SectionHeader({ id, name, type, question }: { id: string; name: string; type: string; question: string }) {
  return (
    <div className="mb-3 flex flex-wrap items-baseline gap-x-3 gap-y-1">
      <h2 className="text-lg font-semibold text-ink">
        <span className="text-muted">{id}</span> {name}
      </h2>
      <span className="rounded bg-surface-2 px-1.5 py-0.5 text-[11px] text-ink-2">{type}</span>
      <p className="w-full text-sm text-ink-2">{question}</p>
    </div>
  );
}

function ComponentSection({ c }: { c: EvalComponent }) {
  return (
    <section id={c.id} className="scroll-mt-4">
      <SectionHeader id={c.id} name={c.name} type={c.type} question={c.question} />
      <PanelGrid panels={c.panels} />
    </section>
  );
}

function PanelGrid({ panels }: { panels: Panel[] }) {
  return (
    <div className="grid gap-4 md:grid-cols-2 2xl:grid-cols-3">
      {panels.map((p) => (
        <Card key={p.id} title={p.title} subtitle={p.note}>
          {p.rows.length === 0 ? <p className="text-xs text-muted">No result file found.</p> : <EvalChart panel={p} />}
        </Card>
      ))}
    </div>
  );
}
