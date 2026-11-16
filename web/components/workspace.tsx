"use client";

import { useEffect, useEffectEvent, useRef, useState } from "react";
import { getExamples, getPlaybooks, review, type ReviewRequest } from "@/lib/api";
import type { RedlineState } from "@/lib/review";
import { ISSUE_STATUSES } from "@/lib/status";
import type { Example, PlaybookInfo, ReviewResponse, Status } from "@/lib/types";
import { ContractPreview, type Focus } from "./preview";
import { FindingsTable, MemoView, Overview, PipelineView } from "./tabs";
import { Button, Count, ErrorBox, Tabs } from "./ui";

type Mode = "example" | "upload" | "paste";
type Tab = "overview" | "preview" | "findings" | "memo" | "pipeline";
const TABS: Tab[] = ["overview", "preview", "findings", "memo", "pipeline"];

const STEPS = [
  "C1 Ingestion",
  "C2 Segmentation",
  "C3 Evidence retrieval",
  "C4 NLI + evidence",
  "C5 Playbook compliance",
  "C6 Redlines",
  "C7 Memo",
];

export default function Workspace() {
  const [playbooks, setPlaybooks] = useState<PlaybookInfo[]>([]);
  const [examples, setExamples] = useState<Example[]>([]);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [playbook, setPlaybook] = useState("disclosing_party");
  const [mode, setMode] = useState<Mode>("example");
  const [exampleId, setExampleId] = useState("");
  const [file, setFile] = useState<File | null>(null);
  const [text, setText] = useState("");
  const [withRedlines, setWithRedlines] = useState(true);
  const [withMemo, setWithMemo] = useState(true);

  const [loading, setLoading] = useState(false);
  const [startedAt, setStartedAt] = useState(0);
  const [now, setNow] = useState(0);
  const [error, setError] = useState<string | null>(null);
  const [resp, setResp] = useState<ReviewResponse | null>(null);
  const [states, setStates] = useState<RedlineState[]>([]);
  const [tab, setTab] = useState<Tab>("overview");
  const [focus, setFocus] = useState<Focus | null>(null);
  const [statusFilter, setStatusFilter] = useState<Set<Status>>(new Set());
  const abort = useRef<AbortController | null>(null);

  // Deep link for demos: /?example=dev/3&playbook=disclosing_party&tab=preview runs that review on load.
  const autoRun = useEffectEvent((pbs: PlaybookInfo[], exs: Example[]) => {
    const q = new URLSearchParams(window.location.search);
    const ex = q.get("example");
    const pbq = q.get("playbook");
    const pbId = pbq && pbs.some((p) => p.id === pbq) ? pbq : playbook;
    setPlaybook(pbId);
    if (!ex || !exs.some((x) => x.id === ex)) return;
    setExampleId(ex);
    const t = q.get("tab") as Tab | null;
    void run({ playbook: pbId, withRedlines, withMemo, exampleId: ex }, t && TABS.includes(t) ? t : "overview");
  });

  useEffect(() => {
    Promise.all([getPlaybooks(), getExamples()])
      .then(([pbs, exs]) => {
        setPlaybooks(pbs);
        setExamples(exs);
        if (exs.length) setExampleId(exs[0].id);
        autoRun(pbs, exs);
      })
      .catch((e: Error) =>
        setLoadError(`Cannot reach the API (${e.message}). Start it with: uv run uvicorn app.api:app --port 8000`),
      );
  }, []);

  useEffect(() => {
    if (!loading) return;
    const t = setInterval(() => setNow(Date.now()), 250);
    return () => clearInterval(t);
  }, [loading]);

  const ready =
    !loading &&
    playbooks.length > 0 &&
    ((mode === "example" && exampleId) || (mode === "upload" && file) || (mode === "paste" && text.trim().length > 50));

  async function run(req: ReviewRequest, openTab: Tab = "overview") {
    abort.current?.abort();
    const ctrl = new AbortController();
    abort.current = ctrl;
    setLoading(true);
    setError(null);
    setStartedAt(Date.now());
    setNow(Date.now());
    try {
      const r = await review(req, ctrl.signal);
      setResp(r);
      setStates((r.result.redlines?.redlines ?? []).map(() => "pending"));
      setFocus(null);
      setStatusFilter(new Set());
      setTab(openTab);
    } catch (e) {
      if ((e as Error).name !== "AbortError") setError((e as Error).message);
    } finally {
      if (abort.current === ctrl) setLoading(false);
    }
  }

  function runFromForm() {
    void run({
      playbook,
      withRedlines,
      withMemo,
      exampleId: mode === "example" ? exampleId : undefined,
      file: mode === "upload" && file ? file : undefined,
      text: mode === "paste" ? text : undefined,
    });
  }

  function cancel() {
    abort.current?.abort();
    setLoading(false);
  }

  const onFocus = (spans: number[], ruleId?: string) => {
    setFocus({ spans, ruleId, key: Date.now() });
    setTab("preview");
  };
  const onFilter = (s: Status) => {
    setStatusFilter(new Set([s]));
    setTab("findings");
  };

  const elapsed = Math.max(0, (now - startedAt) / 1000);
  const pb = playbooks.find((p) => p.id === playbook);
  const nIssues = resp ? resp.result.report.findings.filter((f) => ISSUE_STATUSES.includes(f.status)).length : 0;

  return (
    <div className="mx-auto grid max-w-[1500px] gap-5 px-4 py-5 lg:grid-cols-[300px_minmax(0,1fr)]">
      <aside className="space-y-4 lg:sticky lg:top-4 lg:self-start">
        <section className="rounded-xl border border-line bg-surface p-4">
          <h2 className="text-sm font-semibold">Review a contract</h2>
          <label className="mt-3 block text-xs font-medium text-ink-2" htmlFor="playbook">
            Playbook (our position)
          </label>
          <select
            id="playbook"
            className="mt-1 w-full rounded-md border border-line bg-surface px-2 py-1.5 text-sm"
            value={playbook}
            onChange={(e) => setPlaybook(e.target.value)}
          >
            {playbooks.map((p) => (
              <option key={p.id} value={p.id}>
                {p.name}
              </option>
            ))}
          </select>
          {pb && (
            <p className="mt-1 text-[11px] text-muted">
              {pb.rules.length} rules · we are the {pb.perspective.replace("_", " ")}
            </p>
          )}

          <div className="mt-4 text-xs font-medium text-ink-2">Contract</div>
          <div className="mt-1 grid grid-cols-3 rounded-md border border-line p-0.5 text-xs" role="radiogroup">
            {(["example", "upload", "paste"] as Mode[]).map((m) => (
              <button
                key={m}
                role="radio"
                aria-checked={mode === m}
                onClick={() => setMode(m)}
                className={`rounded px-2 py-1 ${mode === m ? "bg-surface-2 font-medium text-ink" : "text-ink-2 hover:text-ink"}`}
              >
                {m === "example" ? "Example" : m === "upload" ? "Upload" : "Paste"}
              </button>
            ))}
          </div>
          <div className="mt-2">
            {mode === "example" && (
              <>
                <select
                  aria-label="Example contract"
                  className="w-full rounded-md border border-line bg-surface px-2 py-1.5 text-sm"
                  value={exampleId}
                  onChange={(e) => setExampleId(e.target.value)}
                >
                  {examples.map((x) => (
                    <option key={x.id} value={x.id}>
                      {x.id.replace("dev/", "#")} · {x.file_name.length > 42 ? x.file_name.slice(0, 40) + "…" : x.file_name}
                    </option>
                  ))}
                </select>
                <p className="mt-1 text-[11px] text-muted">
                  {examples.length} contracts from the ContractNLI dev split (original PDF/HTML/TXT files).
                </p>
              </>
            )}
            {mode === "upload" && (
              <>
                <input
                  type="file"
                  accept=".pdf,.htm,.html,.txt"
                  onChange={(e) => setFile(e.target.files?.[0] ?? null)}
                  className="block w-full text-xs text-ink-2 file:mr-2 file:rounded-md file:border file:border-line file:bg-surface-2 file:px-2 file:py-1 file:text-xs file:text-ink"
                />
                <p className="mt-1 text-[11px] text-muted">PDF, HTML or TXT, up to 10 MB.</p>
              </>
            )}
            {mode === "paste" && (
              <textarea
                aria-label="Contract text"
                value={text}
                onChange={(e) => setText(e.target.value)}
                rows={8}
                placeholder="Paste the full NDA text…"
                className="w-full rounded-md border border-line bg-surface px-2 py-1.5 font-mono text-xs"
              />
            )}
          </div>

          <div className="mt-4 space-y-1.5 text-sm text-ink-2">
            <label className="flex items-center gap-2">
              <input type="checkbox" checked={withRedlines} onChange={(e) => setWithRedlines(e.target.checked)} />
              Draft redlines (C6)
            </label>
            <label className="flex items-center gap-2">
              <input type="checkbox" checked={withMemo} onChange={(e) => setWithMemo(e.target.checked)} />
              Write negotiation memo (C7)
            </label>
          </div>

          <div className="mt-4 flex gap-2">
            <Button variant="primary" onClick={runFromForm} disabled={!ready}>
              {loading ? "Reviewing…" : "Review"}
            </Button>
            {loading && (
              <Button variant="ghost" onClick={cancel}>
                Cancel
              </Button>
            )}
          </div>
          {loading && (
            <div className="mt-3" aria-live="polite">
              <div className="h-1 overflow-hidden rounded-full bg-surface-2">
                <div className="h-full w-1/3 animate-[progress_1.2s_ease-in-out_infinite] rounded-full bg-accent" />
              </div>
              <p className="mt-1.5 text-[11px] text-muted">
                Running C1 → C7 · {elapsed.toFixed(0)} s. Cached contracts return in seconds; a new one takes about a
                minute (three LLM calls).
              </p>
            </div>
          )}
        </section>
        {loadError && <ErrorBox>{loadError}</ErrorBox>}
        {error && <ErrorBox>Review failed: {error}</ErrorBox>}
      </aside>

      <div className="min-w-0">
        {!resp ? (
          <EmptyState />
        ) : (
          <div className={`space-y-4 ${loading ? "opacity-60" : ""}`}>
            <Tabs<Tab>
              value={tab}
              onChange={setTab}
              tabs={[
                { id: "overview", label: "Overview" },
                {
                  id: "preview",
                  label: "Contract preview",
                  badge: resp.result.redlines ? <Count n={resp.result.redlines.redlines.length} /> : undefined,
                },
                { id: "findings", label: "Findings table", badge: <Count n={nIssues} /> },
                { id: "memo", label: "Memo" },
                { id: "pipeline", label: "Pipeline & traces" },
              ]}
            />
            {tab === "overview" && <Overview resp={resp} onFocus={onFocus} onFilter={onFilter} />}
            {tab === "preview" && (
              <ContractPreview resp={resp} states={states} setStates={setStates} focus={focus} onFocus={onFocus} />
            )}
            {tab === "findings" && (
              <FindingsTable
                resp={resp}
                onFocus={onFocus}
                statusFilter={statusFilter}
                setStatusFilter={setStatusFilter}
              />
            )}
            {tab === "memo" && <MemoView resp={resp} onFocus={onFocus} />}
            {tab === "pipeline" && <PipelineView resp={resp} />}
          </div>
        )}
      </div>
    </div>
  );
}

function EmptyState() {
  return (
    <div className="rounded-xl border border-line bg-surface p-8">
      <h1 className="text-xl font-semibold text-ink">First-pass NDA review against your playbook</h1>
      <p className="mt-2 max-w-2xl text-sm text-ink-2">
        For each playbook rule the system decides whether the contract says it, says the opposite or doesn’t mention
        it, cites the clauses, scores the risk, drafts redlines and writes a negotiation memo. Pick a contract on the
        left and press Review.
      </p>
      <ol className="mt-6 flex flex-wrap items-center gap-2 text-xs">
        {STEPS.map((s, i) => (
          <li key={s} className="flex items-center gap-2">
            <span className="rounded-md border border-line bg-surface-2 px-2 py-1 text-ink-2">{s}</span>
            {i < STEPS.length - 1 && <span className="text-muted">→</span>}
          </li>
        ))}
      </ol>
      <p className="mt-6 text-xs text-muted">
        Output is a draft for a lawyer, not legal advice. The Evaluation page shows how well each step works.
      </p>
    </div>
  );
}
