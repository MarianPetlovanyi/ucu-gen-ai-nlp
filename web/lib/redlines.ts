// Port of apply_redlines() in src/nda_review/redline.py. Span offsets are Python string indices
// (code points), so the text is indexed as an array of code points, not UTF-16 units.
import type { Contract, Redline } from "./types";

/** `index` is the position of the redline in the list passed to planRedlines. */
export interface PlannedEdit {
  text: string;
  ruleId: string;
  index: number;
}

export interface RedlinePlan {
  replaceAt: Map<number, PlannedEdit>;
  remove: Map<number, number>; // span id -> index of the replacement that swallowed it
  insertAfter: Map<number, PlannedEdit[]>;
}

/** Same conflict rules as Python: when two replacements target the same first span, the first redline wins. */
export function planRedlines(redlines: Redline[]): RedlinePlan {
  const replaceAt = new Map<number, PlannedEdit>();
  const remove = new Map<number, number>();
  const insertAfter = new Map<number, PlannedEdit[]>();
  redlines.forEach((r, index) => {
    if (r.action === "replace") {
      const [first, ...rest] = [...r.target_span_ids].sort((a, b) => a - b);
      if (replaceAt.has(first) || remove.has(first)) return;
      replaceAt.set(first, { text: r.new_text.trim(), ruleId: r.rule_id, index });
      for (const i of rest) if (!replaceAt.has(i)) remove.set(i, index);
    } else {
      const k = r.target_span_ids[0];
      insertAfter.set(k, [...(insertAfter.get(k) ?? []), { text: r.new_text.trim(), ruleId: r.rule_id, index }]);
    }
  });
  return { replaceAt, remove, insertAfter };
}

/** Revised contract text with the given (accepted) redlines applied. */
export function applyRedlines(contract: Contract, redlines: Redline[]): string {
  const { replaceAt, remove, insertAfter } = planRedlines(redlines);
  const cps = Array.from(contract.text);
  const slice = (a: number, b: number) => cps.slice(a, b).join("");
  const out: string[] = [];
  let pos = 0;
  for (const s of contract.spans) {
    out.push(slice(pos, s.start));
    const rep = replaceAt.get(s.id);
    if (rep) out.push(rep.text);
    else if (!remove.has(s.id)) out.push(slice(s.start, s.end));
    for (const ins of insertAfter.get(s.id) ?? []) out.push("\n" + ins.text);
    pos = s.end;
  }
  out.push(slice(pos, cps.length));
  return out.join("");
}
