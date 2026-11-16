// Mirrors the pydantic models in src/nda_review/schemas.py and the payloads of app/api.py.

export type Status = "VIOLATION" | "MISSING" | "REVIEW" | "OK" | "INFO";
export type Label = "Entailment" | "Contradiction" | "NotMentioned";
export type Severity = "high" | "medium" | "low";
export type Recommendation = "sign" | "negotiate" | "reject";

export interface Span {
  id: number;
  start: number;
  end: number;
  text: string;
}

export interface Contract {
  doc_id: string;
  text: string;
  spans: Span[];
}

export interface Finding {
  rule_id: string;
  hypothesis_id: string;
  title: string;
  stance: string;
  severity: Severity;
  label: Label;
  status: Status;
  evidence: number[];
  rationale: string;
}

export interface Report {
  doc_id: string;
  playbook: string;
  findings: Finding[];
  risk_score: number;
  recommendation: Recommendation;
}

export interface Redline {
  rule_id: string;
  action: "replace" | "insert";
  target_span_ids: number[];
  new_text: string;
  explanation: string;
}

export interface MemoIssue {
  rule_id: string;
  headline: string;
  explanation: string;
  ask: string;
  fallback: string;
  citations: number[];
}

export interface Memo {
  summary: string;
  recommendation: Recommendation;
  issues: MemoIssue[];
}

export interface Trace {
  ts?: string;
  component: string;
  model: string;
  cache_hit: boolean;
  latency_s: number;
  prompt_tokens: number;
  completion_tokens: number;
  cost_usd: number;
}

export interface ReviewResult {
  playbook: string;
  ingest: { text: string; source_format: string; n_pages: number | null; warnings: string[] } | null;
  contract: Contract;
  nli: {
    doc_id: string;
    method: string;
    decisions: { hypothesis_id: string; label: Label; evidence: number[]; rationale: string }[];
  };
  report: Report;
  redlines: { doc_id: string; redlines: Redline[] } | null;
  revised_text: string | null;
  memo: Memo | null;
  timings_s: Record<string, number>;
  traces: Trace[];
}

export interface Rule {
  id: string;
  hypothesis: string;
  title: string;
  stance: string;
  severity: Severity;
  rationale: string;
  preferred_clause: string | null;
  fallback: string | null;
}

export interface PlaybookInfo {
  id: string;
  name: string;
  perspective: string;
  sign_max_risk: number;
  reject_min_risk: number;
  rules: Rule[];
}

export interface ComponentInfo {
  id: string;
  name: string;
  type: string;
  does: string;
}

export interface Hypothesis {
  id: string;
  short: string;
  text: string;
}

export interface ReviewResponse {
  result: ReviewResult;
  cost_usd: number;
  source: { kind: "example" | "file" | "text"; name: string; id?: string };
  playbook: PlaybookInfo;
  hypotheses: Record<string, Hypothesis>;
  components: ComponentInfo[];
}

export interface Example {
  id: string;
  file_name: string;
  format: string;
}

// --- evaluation dashboard ---
export interface Val {
  value: number;
  n: number | null;
}

export interface PanelRow {
  label: string;
  kind: "baseline" | "system" | "alternative" | "metric";
  values: Record<string, Val | null>;
}

export interface Panel {
  id: string;
  title: string;
  note: string;
  better: "higher" | "lower";
  target: { value: number; label: string } | null;
  series: { key: string; label: string }[];
  rows: PanelRow[];
}

export interface EvalComponent {
  id: string;
  name: string;
  type: string;
  question: string;
  panels: Panel[];
}

export interface EvalSummary {
  components: EvalComponent[];
  e2e: Panel[];
  judge: Panel;
}
