import type { Recommendation, Severity, Status } from "./types";

export const STATUS_ORDER: Status[] = ["VIOLATION", "MISSING", "REVIEW", "OK", "INFO"];

/** Reserved status colours. Never used alone: StatusBadge/StatusIcon always add the icon and the label. */
export const STATUS_META: Record<Status, { label: string; color: string; onFill: string; hint: string }> = {
  VIOLATION: {
    label: "Violation",
    color: "var(--critical)",
    onFill: "#ffffff",
    hint: "the contract contradicts our position",
  },
  MISSING: { label: "Missing", color: "var(--serious)", onFill: "#ffffff", hint: "a clause we need is not there" },
  REVIEW: { label: "Review", color: "var(--warning)", onFill: "#0b0b0b", hint: "a lawyer should look at it" },
  OK: { label: "OK", color: "var(--good)", onFill: "#ffffff", hint: "matches the playbook" },
  INFO: { label: "Info", color: "var(--neutral)", onFill: "#ffffff", hint: "no position in the playbook" },
};

export const REC_META: Record<Recommendation, { label: string; status: Status; text: string }> = {
  sign: { label: "Sign", status: "OK", text: "Low risk: can be signed as is." },
  negotiate: { label: "Negotiate", status: "REVIEW", text: "Fix the issues below before signing." },
  reject: { label: "Reject", status: "VIOLATION", text: "Too many serious issues to negotiate cheaply." },
};

export const ISSUE_STATUSES: Status[] = ["VIOLATION", "MISSING"];
export const SEVERITY_ORDER: Severity[] = ["high", "medium", "low"];
export const SEVERITY_WEIGHT: Record<Severity, number> = { high: 3, medium: 2, low: 1 };
