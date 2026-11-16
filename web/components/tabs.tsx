"use client";

import { useMemo, useState } from "react";
import { download, fmtInt, fmtSec, fmtUsd } from "@/lib/format";
import { baseName, LABEL_TEXT, memoMarkdown, sortFindings, STANCE_LABEL, statusCounts } from "@/lib/review";
import { REC_META, SEVERITY_ORDER, STATUS_META, STATUS_ORDER } from "@/lib/status";
import type { Finding, ReviewResponse, Severity, Status } from "@/lib/types";
import { HBars, RiskGauge, StatusDistribution } from "./charts";
import {
  Button,
  Card,
  RecommendationBadge,
  SeverityTag,
  SpanRef,
  StatTile,
  StatusBadge,
  StatusIcon,
} from "./ui";

type FocusFn = (spans: number[], ruleId?: string) => void;

// --- Overview ---------------------------------------------------------------------------------
export function Overview({
  resp,
  onFocus,
  onFilter,
}: {
  resp: ReviewResponse;
  onFocus: FocusFn;
  onFilter: (s: Status) => void;
}) {
  const { report, ingest } = resp.result;
  const counts = statusCounts(report.findings);
  const rec = REC_META[report.recommendation];
  const pb = resp.playbook;
  return (
    <div className="space-y-4">
      <div className="grid gap-4 lg:grid-cols-[1.1fr_1fr_1.2fr]">
        <Card title="Recommendation" subtitle={`Playbook: ${pb.name}`}>
          <RecommendationBadge rec={report.recommendation} large />
          <p className="mt-3 text-sm text-ink-2">{rec.text}</p>
          <p className="mt-2 text-xs text-muted">
            Rule from the playbook, not from the LLM: reject if risk ≥ {pb.reject_min_risk}; sign if no high or
            medium issue and risk ≤ {pb.sign_max_risk}; otherwise negotiate.
          </p>
          <dl className="mt-3 grid grid-cols-[auto_1fr] gap-x-3 gap-y-1 text-xs">
            <dt className="text-muted">Source</dt>
            <dd className="truncate text-ink-2">{resp.source.name}</dd>
            <dt className="text-muted">Format</dt>
            <dd className="text-ink-2">
              {ingest ? `${ingest.source_format.toUpperCase()}${ingest.n_pages ? ` · ${ingest.n_pages} pages` : ""}` : "text"}
            </dd>
            <dt className="text-muted">Spans</dt>
            <dd className="text-ink-2">{resp.result.contract.spans.length}</dd>
          </dl>
        </Card>
        <Card title="Risk score" subtitle="Severity-weighted share of rules with an issue">
          <RiskGauge value={report.risk_score} sign={pb.sign_max_risk} reject={pb.reject_min_risk} />
        </Card>
        <div className="grid grid-cols-2 gap-3">
          <StatTile
            label="Issues to negotiate"
            value={counts.VIOLATION + counts.MISSING}
            sub={`of ${report.findings.length} rules`}
          />
          <StatTile label="Violations" value={counts.VIOLATION} status="VIOLATION" sub="contract says the opposite" />
          <StatTile label="Missing" value={counts.MISSING} status="MISSING" sub="required clause absent" />
          <StatTile label="OK" value={counts.OK} status="OK" sub={`${counts.REVIEW} to review · ${counts.INFO} info`} />
        </div>
      </div>

      {ingest && ingest.warnings.length > 0 && (
        <Card title="Ingestion warnings">
          <ul className="space-y-1 text-sm text-ink-2">
            {ingest.warnings.map((w) => (
              <li key={w} className="flex items-center gap-2">
                <StatusIcon status="REVIEW" size={12} /> {w}
              </li>
            ))}
          </ul>
        </Card>
      )}

      <Card title="Status of all rules" subtitle="Click a block to filter the findings table">
        <StatusDistribution counts={counts} onPick={onFilter} />
      </Card>

      <Card title="Rules by severity and status" subtitle="Click a rule to see its evidence in the contract">
        <SeverityGrid findings={report.findings} onFocus={onFocus} />
      </Card>
    </div>
  );
}

function SeverityGrid({ findings, onFocus }: { findings: Finding[]; onFocus: FocusFn }) {
  return (
    <div className="overflow-x-auto">
      <table className="w-full min-w-[720px] border-separate border-spacing-[2px] text-xs">
        <thead>
          <tr>
            <th className="w-24" />
            {STATUS_ORDER.map((s) => (
              <th key={s} className="px-2 py-1 text-left font-medium text-ink-2">
                <span className="inline-flex items-center gap-1.5">
                  <StatusIcon status={s} size={12} />
                  {STATUS_META[s].label}
                </span>
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {SEVERITY_ORDER.map((sev) => (
            <tr key={sev}>
              <th className="px-2 py-1 text-left align-top font-normal">
                <SeverityTag severity={sev} />
              </th>
              {STATUS_ORDER.map((st) => {
                const cell = findings.filter((f) => f.severity === sev && f.status === st);
                return (
                  <td
                    key={st}
                    className="rounded-md px-1.5 py-1.5 align-top"
                    style={{
                      background: cell.length
                        ? `color-mix(in srgb, ${STATUS_META[st].color} 10%, transparent)`
                        : "var(--surface-2)",
                    }}
                  >
                    {cell.length === 0 ? (
                      <span className="text-muted">–</span>
                    ) : (
                      <div className="flex flex-col gap-1">
                        {cell.map((f) => (
                          <button
                            key={f.rule_id}
                            onClick={() => onFocus(f.evidence, f.rule_id)}
                            className="rounded border border-line bg-surface px-1.5 py-1 text-left text-ink hover:border-accent"
                            title={`${f.rule_id}: ${f.title} (${LABEL_TEXT[f.label]})`}
                          >
                            <span className="text-muted">{f.rule_id}</span> {f.title}
                          </button>
                        ))}
                      </div>
                    )}
                  </td>
                );
              })}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

// --- Findings table ---------------------------------------------------------------------------
export function FindingsTable({
  resp,
  onFocus,
  statusFilter,
  setStatusFilter,
}: {
  resp: ReviewResponse;
  onFocus: FocusFn;
  statusFilter: Set<Status>;
  setStatusFilter: (s: Set<Status>) => void;
}) {
  const [sevFilter, setSevFilter] = useState<Set<Severity>>(new Set());
  const findings = resp.result.report.findings;
  const counts = statusCounts(findings);
  const rows = sortFindings(findings).filter(
    (f) => (statusFilter.size === 0 || statusFilter.has(f.status)) && (sevFilter.size === 0 || sevFilter.has(f.severity)),
  );
  const toggle = <T,>(set: Set<T>, v: T) => {
    const n = new Set(set);
    if (n.has(v)) n.delete(v);
    else n.add(v);
    return n;
  };
  const chip = (on: boolean) =>
    `inline-flex items-center gap-1.5 rounded-full border px-2.5 py-1 text-xs ${
      on ? "border-accent bg-surface-2 text-ink" : "border-line text-ink-2 hover:bg-surface-2"
    }`;
  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-center gap-2">
        <span className="text-xs text-muted">Status</span>
        {STATUS_ORDER.map((s) => (
          <button key={s} className={chip(statusFilter.has(s))} onClick={() => setStatusFilter(toggle(statusFilter, s))}>
            <StatusIcon status={s} size={12} />
            {STATUS_META[s].label}
            <span className="text-muted">{counts[s]}</span>
          </button>
        ))}
        <span className="ml-3 text-xs text-muted">Severity</span>
        {SEVERITY_ORDER.map((s) => (
          <button key={s} className={chip(sevFilter.has(s))} onClick={() => setSevFilter(toggle(sevFilter, s))}>
            <SeverityTag severity={s} />
          </button>
        ))}
        {(statusFilter.size > 0 || sevFilter.size > 0) && (
          <Button
            small
            variant="ghost"
            onClick={() => {
              setStatusFilter(new Set());
              setSevFilter(new Set());
            }}
          >
            Clear filters
          </Button>
        )}
        <span className="ml-auto text-xs text-muted">
          {rows.length} of {findings.length} rules
        </span>
      </div>
      <div className="overflow-x-auto rounded-xl border border-line bg-surface">
        <table className="w-full min-w-[900px] text-sm">
          <thead>
            <tr className="border-b border-line text-left text-xs text-muted">
              <th className="px-3 py-2 font-medium">Status</th>
              <th className="px-3 py-2 font-medium">Severity</th>
              <th className="px-3 py-2 font-medium">Rule</th>
              <th className="px-3 py-2 font-medium">Contract (NLI)</th>
              <th className="px-3 py-2 font-medium">Rationale</th>
              <th className="px-3 py-2 font-medium">Evidence</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((f) => {
              const hyp = resp.hypotheses[f.hypothesis_id];
              return (
                <tr key={f.rule_id} className="border-b border-line align-top last:border-0">
                  <td className="px-3 py-2">
                    <StatusBadge status={f.status} />
                  </td>
                  <td className="px-3 py-2">
                    <SeverityTag severity={f.severity} />
                  </td>
                  <td className="px-3 py-2">
                    <div className="font-medium text-ink">
                      <span className="text-muted">{f.rule_id}</span> {f.title}
                    </div>
                    <div className="text-xs text-muted">{STANCE_LABEL[f.stance] ?? f.stance}</div>
                    {hyp && <div className="mt-0.5 text-xs text-muted italic">“{hyp.text}”</div>}
                  </td>
                  <td className="px-3 py-2 text-ink-2 whitespace-nowrap">{LABEL_TEXT[f.label] ?? f.label}</td>
                  <td className="max-w-[420px] px-3 py-2 text-ink-2">{f.rationale || <span className="text-muted">–</span>}</td>
                  <td className="px-3 py-2">
                    <div className="flex flex-wrap gap-1">
                      {f.evidence.length === 0 && <span className="text-xs text-muted">none</span>}
                      {f.evidence.map((id) => (
                        <SpanRef key={id} id={id} onClick={() => onFocus([id], f.rule_id)} />
                      ))}
                    </div>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}

// --- Memo ------------------------------------------------------------------------------------
export function MemoView({ resp, onFocus }: { resp: ReviewResponse; onFocus: FocusFn }) {
  const memo = resp.result.memo;
  const spans = useMemo(() => new Map(resp.result.contract.spans.map((s) => [s.id, s])), [resp]);
  const findings = useMemo(() => new Map(resp.result.report.findings.map((f) => [f.rule_id, f])), [resp]);
  if (!memo) return <p className="text-sm text-muted">The memo was switched off for this review.</p>;
  const md = memoMarkdown(memo, resp.result.contract.doc_id, spans);
  return (
    <div className="mx-auto max-w-3xl space-y-4">
      <Card
        title="Negotiation memo"
        subtitle={`${memo.issues.length} items · written by gpt-oss-120b from the compliance report`}
        actions={
          <Button small onClick={() => download(`${baseName(resp)}_memo.md`, md, "text/markdown")}>
            Download .md
          </Button>
        }
      >
        <div className="flex items-center gap-3">
          <RecommendationBadge rec={memo.recommendation} />
          {memo.recommendation !== resp.result.report.recommendation && (
            <span className="text-xs text-muted">
              The playbook recommendation is “{REC_META[resp.result.report.recommendation].label}”; it takes precedence.
            </span>
          )}
        </div>
        <p className="mt-3 text-sm leading-6 text-ink">{memo.summary}</p>
      </Card>
      {memo.issues.map((it) => {
        const f = findings.get(it.rule_id);
        return (
          <Card
            key={it.rule_id}
            title={
              <span className="flex flex-wrap items-center gap-2">
                <span className="text-muted">{it.rule_id}</span> {it.headline}
              </span>
            }
            actions={f && <StatusBadge status={f.status} compact />}
          >
            <p className="text-sm leading-6 text-ink-2">{it.explanation}</p>
            <div className="mt-3 grid gap-2 sm:grid-cols-2">
              <div className="rounded-lg bg-surface-2 p-3">
                <div className="text-xs font-semibold text-ink">Ask</div>
                <p className="mt-1 text-sm text-ink-2">{it.ask}</p>
              </div>
              <div className="rounded-lg bg-surface-2 p-3">
                <div className="text-xs font-semibold text-ink">Fallback</div>
                <p className="mt-1 text-sm text-ink-2">{it.fallback}</p>
              </div>
            </div>
            {it.citations.length > 0 && (
              <div className="mt-3 space-y-1.5">
                {it.citations.map((c) => {
                  const s = spans.get(c);
                  return (
                    <div key={c} className="flex items-start gap-2 text-xs">
                      <SpanRef id={c} onClick={() => onFocus([c], it.rule_id)} />
                      <span className="line-clamp-2 text-muted">{s ? s.text : "(span not in contract)"}</span>
                    </div>
                  );
                })}
              </div>
            )}
          </Card>
        );
      })}
    </div>
  );
}

// --- Pipeline & traces -----------------------------------------------------------------------
export function PipelineView({ resp }: { resp: ReviewResponse }) {
  const { timings_s, traces } = resp.result;
  const timing = (id: string) =>
    Object.entries(timings_s).find(([k]) => k.startsWith(id + " ") || k === id)?.[1];
  const rows = resp.components
    .map((c) => ({ c, t: timing(c.id) }))
    .filter((r): r is { c: (typeof resp.components)[number]; t: number } => r.t !== undefined);
  const total = rows.reduce((a, r) => a + r.t, 0);
  const tokens = traces.reduce((a, t) => a + t.prompt_tokens + t.completion_tokens, 0);
  const hits = traces.filter((t) => t.cache_hit).length;
  const paid = traces.filter((t) => !t.cache_hit).reduce((a, t) => a + t.cost_usd, 0);
  return (
    <div className="space-y-4">
      <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
        <StatTile label="Wall time" value={fmtSec(total)} sub="sum of C1–C7" />
        <StatTile label="LLM calls" value={traces.length} sub={`${hits} served from the disk cache`} />
        <StatTile label="Tokens" value={fmtInt(tokens)} sub="prompt + completion (incl. reasoning)" />
        <StatTile
          label="API cost of this run"
          value={fmtUsd(paid)}
          sub={`${fmtUsd(resp.cost_usd)} without the cache (Groq list price)`}
        />
      </div>
      <div className="grid gap-4 lg:grid-cols-[1fr_1.2fr]">
        <Card title="Time per component" subtitle="Seconds; LLM steps dominate unless cached">
          <HBars
            ariaLabel="Seconds per pipeline component"
            format={(v) => (v === 0 ? "0" : v < 1 ? `${v.toFixed(2)}s` : `${v.toFixed(1)}s`)}
            rows={rows.map(({ c, t }) => ({
              label: `${c.id} ${c.name}`,
              value: t,
              tip: (
                <span>
                  <b>
                    {c.id} {c.name}
                  </b>{" "}
                  ({c.type})<br />
                  {c.does}
                  <br />
                  {fmtSec(t)}
                </span>
              ),
            }))}
          />
        </Card>
        <Card title="Components" subtitle="One module + one eval each">
          <ol className="space-y-1.5 text-sm">
            {resp.components.map((c) => (
              <li key={c.id} className="flex items-baseline gap-2">
                <span className="w-7 shrink-0 font-semibold text-ink">{c.id}</span>
                <span className="text-ink">{c.name}</span>
                <span className="rounded bg-surface-2 px-1.5 text-[11px] text-ink-2">{c.type}</span>
                <span className="truncate text-xs text-muted">{c.does}</span>
              </li>
            ))}
          </ol>
        </Card>
      </div>
      <Card title="LLM calls" subtitle="From the JSONL trace of nda_review.llm">
        <div className="overflow-x-auto">
          <table className="w-full min-w-[720px] text-sm">
            <thead>
              <tr className="border-b border-line text-left text-xs text-muted">
                <th className="py-2 pr-3 font-medium">Component</th>
                <th className="py-2 pr-3 font-medium">Model</th>
                <th className="py-2 pr-3 font-medium">Cache</th>
                <th className="py-2 pr-3 text-right font-medium">Prompt tok.</th>
                <th className="py-2 pr-3 text-right font-medium">Completion tok.</th>
                <th className="py-2 pr-3 text-right font-medium">Latency</th>
                <th className="py-2 text-right font-medium">Cost</th>
              </tr>
            </thead>
            <tbody>
              {traces.length === 0 && (
                <tr>
                  <td colSpan={7} className="py-3 text-muted">
                    No LLM calls.
                  </td>
                </tr>
              )}
              {traces.map((t, i) => (
                <tr key={i} className="border-b border-line last:border-0">
                  <td className="py-1.5 pr-3 text-ink">{t.component}</td>
                  <td className="py-1.5 pr-3 font-mono text-xs text-ink-2">{t.model}</td>
                  <td className="py-1.5 pr-3 text-ink-2">{t.cache_hit ? "hit" : "miss"}</td>
                  <td className="tabular py-1.5 pr-3 text-right text-ink">{fmtInt(t.prompt_tokens)}</td>
                  <td className="tabular py-1.5 pr-3 text-right text-ink">{fmtInt(t.completion_tokens)}</td>
                  <td className="tabular py-1.5 pr-3 text-right text-ink">{fmtSec(t.latency_s)}</td>
                  <td className="tabular py-1.5 text-right text-ink">{fmtUsd(t.cost_usd)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Card>
    </div>
  );
}
