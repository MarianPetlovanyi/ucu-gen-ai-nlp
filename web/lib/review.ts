import { SEVERITY_ORDER, STATUS_ORDER } from "./status";
import type { Finding, Memo, ReviewResponse, Span, Status } from "./types";

export type RedlineState = "pending" | "accepted" | "rejected";

export const STANCE_LABEL: Record<string, string> = {
  must_entail: "Contract must say this",
  must_not_entail: "Contract must not say this",
  review_if_entailed: "Review if the contract says this",
  info: "Reported for information",
};

export const LABEL_TEXT: Record<string, string> = {
  Entailment: "Says it",
  Contradiction: "Says the opposite",
  NotMentioned: "Not mentioned",
};

export function worstStatus(findings: Finding[]): Status {
  return [...findings].sort((a, b) => STATUS_ORDER.indexOf(a.status) - STATUS_ORDER.indexOf(b.status))[0].status;
}

export function sortFindings(findings: Finding[]): Finding[] {
  return [...findings].sort(
    (a, b) =>
      STATUS_ORDER.indexOf(a.status) - STATUS_ORDER.indexOf(b.status) ||
      SEVERITY_ORDER.indexOf(a.severity) - SEVERITY_ORDER.indexOf(b.severity) ||
      a.rule_id.localeCompare(b.rule_id),
  );
}

/** span id -> findings that cite it as evidence, worst status first. */
export function citingFindings(findings: Finding[]): Map<number, Finding[]> {
  const m = new Map<number, Finding[]>();
  for (const f of sortFindings(findings)) for (const id of f.evidence) m.set(id, [...(m.get(id) ?? []), f]);
  return m;
}

export function statusCounts(findings: Finding[]): Record<Status, number> {
  const c = { VIOLATION: 0, MISSING: 0, REVIEW: 0, OK: 0, INFO: 0 } as Record<Status, number>;
  for (const f of findings) c[f.status] += 1;
  return c;
}

export function memoMarkdown(memo: Memo, docId: string, spans: Map<number, Span>): string {
  const out = [`# Negotiation memo — ${docId}`, "", `**Recommendation:** ${memo.recommendation}`, "", memo.summary, ""];
  for (const it of memo.issues) {
    out.push(`## ${it.rule_id} · ${it.headline}`, "", it.explanation, "", `**Ask:** ${it.ask}`, "");
    out.push(`**Fallback:** ${it.fallback}`, "");
    for (const c of it.citations) {
      const s = spans.get(c);
      if (s) out.push(`> [${c}] ${s.text.replace(/\s+/g, " ").trim()}`, "");
    }
  }
  return out.join("\n");
}

export function baseName(resp: ReviewResponse): string {
  return resp.source.name.replace(/\.[^.]+$/, "").replace(/[^A-Za-z0-9._-]+/g, "_") || "contract";
}
