import type { EvalSummary, Example, PlaybookInfo, ReviewResponse } from "./types";

async function json<T>(res: Response): Promise<T> {
  if (!res.ok) {
    let detail = `${res.status} ${res.statusText}`;
    try {
      const body = await res.json();
      if (body?.detail) detail = typeof body.detail === "string" ? body.detail : JSON.stringify(body.detail);
    } catch {
      // not JSON: keep the status line
    }
    throw new Error(detail);
  }
  return res.json() as Promise<T>;
}

export const getPlaybooks = () => fetch("/api/playbooks").then((r) => json<PlaybookInfo[]>(r));
export const getExamples = () => fetch("/api/examples").then((r) => json<Example[]>(r));
export const getEvalSummary = () => fetch("/api/eval-summary").then((r) => json<EvalSummary>(r));

export interface ReviewRequest {
  playbook: string;
  withRedlines: boolean;
  withMemo: boolean;
  exampleId?: string;
  text?: string;
  file?: File;
}

export function review(req: ReviewRequest, signal?: AbortSignal): Promise<ReviewResponse> {
  const form = new FormData();
  form.set("playbook", req.playbook);
  form.set("with_redlines", String(req.withRedlines));
  form.set("with_memo", String(req.withMemo));
  if (req.exampleId) form.set("example_id", req.exampleId);
  if (req.text) form.set("text", req.text);
  if (req.file) form.set("file", req.file);
  return fetch("/api/review", { method: "POST", body: form, signal }).then((r) => json<ReviewResponse>(r));
}
