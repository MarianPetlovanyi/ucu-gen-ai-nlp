"use client";

import { Fragment, useEffect, useMemo, useRef, useState } from "react";
import { download } from "@/lib/format";
import { applyRedlines, planRedlines } from "@/lib/redlines";
import { baseName, citingFindings, LABEL_TEXT, sortFindings, worstStatus, type RedlineState } from "@/lib/review";
import { STATUS_META } from "@/lib/status";
import type { Finding, Redline, ReviewResponse } from "@/lib/types";
import { Button, Count, SeverityTag, SpanRef, StatusBadge, StatusIcon, Tooltip, useTip } from "./ui";

export interface Focus {
  spans: number[];
  ruleId?: string;
  key: number;
}

interface Props {
  resp: ReviewResponse;
  states: RedlineState[];
  setStates: (s: RedlineState[]) => void;
  focus: Focus | null;
  onFocus: (spans: number[], ruleId?: string) => void;
}

export function ContractPreview({ resp, states, setStates, focus, onFocus }: Props) {
  const { contract, report } = resp.result;
  const redlines = useMemo(() => resp.result.redlines?.redlines ?? [], [resp]);
  const docRef = useRef<HTMLDivElement>(null);
  const { tip, show, hide } = useTip();
  const [showEvidence, setShowEvidence] = useState(true);
  const [showChanges, setShowChanges] = useState(true);

  // Track changes show exactly what the download produces: every redline that is not rejected.
  const activeIdx = useMemo(() => redlines.map((_, i) => i).filter((i) => states[i] !== "rejected"), [redlines, states]);
  const plan = useMemo(() => planRedlines(activeIdx.map((i) => redlines[i])), [activeIdx, redlines]);
  const toOrig = (planIndex: number) => activeIdx[planIndex];
  const cps = useMemo(() => Array.from(contract.text), [contract.text]);
  const citing = useMemo(() => citingFindings(report.findings), [report.findings]);
  const focused = useMemo(() => new Set(focus?.spans ?? []), [focus]);
  const rules = useMemo(() => new Map(resp.playbook.rules.map((r) => [r.id, r])), [resp]);

  useEffect(() => {
    if (!focus || focus.spans.length === 0) return;
    const els = focus.spans
      .map((id) => document.getElementById(`span-${id}`))
      .filter((e): e is HTMLElement => e !== null);
    els[0]?.scrollIntoView({ behavior: "smooth", block: "center" });
    els.forEach((e) => {
      e.classList.remove("tc-flash");
      void e.offsetWidth;
      e.classList.add("tc-flash");
    });
  }, [focus]);

  const slice = (a: number, b: number) => cps.slice(a, b).join("");
  const setOne = (i: number, s: RedlineState) => setStates(states.map((v, j) => (j === i ? s : v)));
  const nActive = activeIdx.length;
  const revisedName = `${baseName(resp)}_revised.txt`;
  const issues = sortFindings(report.findings.filter((f) => f.status !== "OK" && f.status !== "INFO"));

  const changeTag = (origIdx: number) => {
    const r = redlines[origIdx];
    const st = states[origIdx];
    return (
      <span className="mx-1 inline-flex select-none items-center gap-1 whitespace-nowrap rounded border border-line bg-surface px-1 align-middle font-sans text-[11px] not-italic text-ink-2 no-underline">
        <span title={rules.get(r.rule_id)?.title}>✎ {r.rule_id}</span>
        {st === "accepted" ? (
          <span className="text-good-ink">accepted</span>
        ) : (
          <button className="rounded px-1 hover:bg-surface-2" onClick={() => setOne(origIdx, "accepted")} title="Accept change">
            ✓
          </button>
        )}
        <button className="rounded px-1 hover:bg-surface-2" onClick={() => setOne(origIdx, "rejected")} title="Reject change">
          ✕
        </button>
      </span>
    );
  };

  const renderSpan = (sId: number, text: string) => {
    const cites = citing.get(sId);
    const ring = focused.has(sId) ? "outline outline-2 outline-offset-2 outline-accent rounded-sm" : "";
    if (!showEvidence || !cites) {
      return (
        <span id={`span-${sId}`} className={ring} data-span={sId}>
          {text}
        </span>
      );
    }
    const st = worstStatus(cites);
    const color = STATUS_META[st].color;
    return (
      <span
        id={`span-${sId}`}
        data-span={sId}
        className={`cursor-pointer rounded-sm ${ring}`}
        style={{ background: `color-mix(in srgb, ${color} 16%, transparent)` }}
        onMouseMove={(e) =>
          show(
            e,
            <div className="space-y-1">
              <div className="text-muted">§{sId} cited by</div>
              {cites.map((f) => (
                <div key={f.rule_id} className="flex items-center gap-1.5">
                  <StatusIcon status={f.status} size={12} />
                  <span>
                    <b>{STATUS_META[f.status].label}</b> · {f.title}{" "}
                    <span className="text-muted">({LABEL_TEXT[f.label]})</span>
                  </span>
                </div>
              ))}
            </div>,
          )
        }
        onMouseLeave={hide}
        onClick={() => onFocus(cites[0].evidence, cites[0].rule_id)}
      >
        <StatusIcon status={st} size={11} />
        {text}
      </span>
    );
  };

  const body = contract.spans.map((s, k) => {
    const gap = slice(k === 0 ? 0 : contract.spans[k - 1].end, s.start);
    const original = slice(s.start, s.end);
    const rep = plan.replaceAt.get(s.id);
    const removedBy = plan.remove.get(s.id);
    const inserts = plan.insertAfter.get(s.id) ?? [];
    let core;
    if (showChanges && rep) {
      core = (
        <>
          <span id={`span-${s.id}`} data-span={s.id} className={`tc-del ${focused.has(s.id) ? "outline outline-2 outline-accent" : ""}`}>
            {original}
          </span>
          <ins className="tc-ins">{rep.text}</ins>
          {changeTag(toOrig(rep.index))}
        </>
      );
    } else if (showChanges && removedBy !== undefined) {
      core = (
        <span id={`span-${s.id}`} data-span={s.id} className="tc-del">
          {original}
        </span>
      );
    } else {
      core = renderSpan(s.id, original);
    }
    return (
      <Fragment key={s.id}>
        {gap}
        {core}
        {showChanges &&
          inserts.map((ins) => (
            <Fragment key={`ins-${ins.index}`}>
              <ins className="tc-ins">{"\n" + ins.text}</ins>
              {changeTag(toOrig(ins.index))}
            </Fragment>
          ))}
      </Fragment>
    );
  });
  const tail = slice(contract.spans.length ? contract.spans[contract.spans.length - 1].end : 0, cps.length);

  return (
    <div className="grid gap-4 lg:grid-cols-[minmax(0,1fr)_360px]">
      <div className="min-w-0 rounded-xl border border-line bg-surface">
        <div className="flex flex-wrap items-center gap-3 border-b border-line px-4 py-2 text-xs text-ink-2">
          <label className="inline-flex items-center gap-1.5">
            <input type="checkbox" checked={showEvidence} onChange={(e) => setShowEvidence(e.target.checked)} />
            Evidence highlights
          </label>
          <label className="inline-flex items-center gap-1.5">
            <input type="checkbox" checked={showChanges} onChange={(e) => setShowChanges(e.target.checked)} />
            Track changes
          </label>
          <span className="inline-flex items-center gap-1">
            <span className="tc-del px-1">deleted</span>
            <span className="tc-ins px-1">inserted</span>
          </span>
          <span className="ml-auto text-muted">
            {contract.spans.length} spans · {resp.source.name}
          </span>
        </div>
        <div
          ref={docRef}
          className="max-h-[calc(100vh-220px)] min-h-[400px] overflow-y-auto whitespace-pre-wrap break-words px-6 py-5 font-serif text-[15px] leading-7 text-ink"
        >
          {body}
          {tail}
        </div>
      </div>

      <aside className="space-y-4 lg:max-h-[calc(100vh-180px)] lg:overflow-y-auto">
        <section className="rounded-xl border border-line bg-surface p-3">
          <h3 className="mb-2 flex items-center gap-2 text-sm font-semibold">
            Findings to act on <Count n={issues.length} />
          </h3>
          {issues.length === 0 && <p className="text-xs text-muted">No issues: every rule is OK or informational.</p>}
          <ul className="space-y-1">
            {issues.map((f) => (
              <FindingRow key={f.rule_id} f={f} redlines={redlines} onFocus={onFocus} active={focus?.ruleId === f.rule_id} />
            ))}
          </ul>
        </section>

        {resp.result.redlines && (
          <section className="rounded-xl border border-line bg-surface p-3">
            <div className="mb-2 flex items-center gap-2">
              <h3 className="flex items-center gap-2 text-sm font-semibold">
                Redlines <Count n={redlines.length} />
              </h3>
              <div className="ml-auto flex gap-1">
                <Button small variant="ghost" onClick={() => setStates(redlines.map(() => "accepted"))}>
                  Accept all
                </Button>
                <Button small variant="ghost" onClick={() => setStates(redlines.map(() => "rejected"))}>
                  Reject all
                </Button>
              </div>
            </div>
            <Button
              variant="primary"
              small
              onClick={() => download(revisedName, applyRedlines(contract, activeIdx.map((i) => redlines[i])))}
            >
              Download revised text ({nActive} of {redlines.length} changes)
            </Button>
            <p className="mt-1 text-[11px] text-muted">Pending and accepted changes are applied; rejected ones are not.</p>
            <ul className="mt-3 space-y-2">
              {redlines.map((r, i) => (
                <RedlineCard
                  key={i}
                  r={r}
                  title={rules.get(r.rule_id)?.title ?? r.rule_id}
                  state={states[i]}
                  onState={(s) => setOne(i, s)}
                  onFocus={onFocus}
                />
              ))}
            </ul>
          </section>
        )}
      </aside>
      <Tooltip tip={tip} />
    </div>
  );
}

function FindingRow({
  f,
  redlines,
  onFocus,
  active,
}: {
  f: Finding;
  redlines: Redline[];
  onFocus: (spans: number[], ruleId?: string) => void;
  active: boolean;
}) {
  const fix = redlines.find((r) => r.rule_id === f.rule_id);
  const target = f.evidence.length ? f.evidence : (fix?.target_span_ids ?? []);
  return (
    <li>
      <button
        onClick={() => onFocus(target, f.rule_id)}
        className={`w-full rounded-lg px-2 py-1.5 text-left hover:bg-surface-2 ${active ? "bg-surface-2" : ""}`}
      >
        <div className="flex items-center gap-2">
          <StatusBadge status={f.status} compact />
          <SeverityTag severity={f.severity} />
        </div>
        <div className="mt-1 text-sm text-ink">{f.title}</div>
        <div className="text-[11px] text-muted">
          {f.evidence.length
            ? `Evidence §${f.evidence.join(", §")}`
            : fix
              ? `No clause found · redline ${fix.action === "insert" ? "inserts after" : "replaces"} §${fix.target_span_ids.join(", §")}`
              : "No clause found in the contract"}
        </div>
      </button>
    </li>
  );
}

function RedlineCard({
  r,
  title,
  state,
  onState,
  onFocus,
}: {
  r: Redline;
  title: string;
  state: RedlineState;
  onState: (s: RedlineState) => void;
  onFocus: (spans: number[], ruleId?: string) => void;
}) {
  const [open, setOpen] = useState(false);
  return (
    <li className={`rounded-lg border border-line p-2 ${state === "rejected" ? "opacity-60" : ""}`}>
      <div className="flex items-start gap-2">
        <div className="min-w-0">
          <div className="text-sm font-medium text-ink">{title}</div>
          <div className="mt-0.5 flex flex-wrap items-center gap-1 text-[11px] text-muted">
            {r.action === "replace" ? "Replaces" : "Inserts after"}
            {r.target_span_ids.map((id) => (
              <SpanRef key={id} id={id} onClick={() => onFocus(r.target_span_ids, r.rule_id)} />
            ))}
          </div>
        </div>
        <span className="ml-auto shrink-0 text-[11px] text-ink-2">
          {state === "pending" ? "Pending" : state === "accepted" ? "✓ Accepted" : "✕ Rejected"}
        </span>
      </div>
      <p className="mt-1 text-xs text-ink-2">{r.explanation}</p>
      <button onClick={() => setOpen(!open)} className="mt-1 text-[11px] text-accent-ink hover:underline">
        {open ? "Hide new text" : "Show new text"}
      </button>
      {open && (
        <p className="mt-1 whitespace-pre-wrap rounded border border-line p-1.5 text-xs text-ink-2">{r.new_text}</p>
      )}
      <div className="mt-2 flex gap-1">
        <Button small variant={state === "accepted" ? "primary" : "secondary"} onClick={() => onState("accepted")}>
          ✓ Accept
        </Button>
        <Button small variant={state === "rejected" ? "primary" : "secondary"} onClick={() => onState("rejected")}>
          ✕ Reject
        </Button>
        {state !== "pending" && (
          <Button small variant="ghost" onClick={() => onState("pending")}>
            Reset
          </Button>
        )}
      </div>
    </li>
  );
}

