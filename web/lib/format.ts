export const fmt3 = (v: number) => v.toFixed(3);
export const fmtPct = (v: number) => `${Math.round(v * 100)}%`;
export const fmtUsd = (v: number) => (v === 0 ? "$0" : v < 0.01 ? `$${v.toFixed(4)}` : `$${v.toFixed(3)}`);
export const fmtSec = (v: number) => (v < 10 ? `${v.toFixed(2)} s` : `${v.toFixed(1)} s`);
export const fmtInt = (v: number) => v.toLocaleString("en-US");
export const fmtN = (n: number | null | undefined) => (n == null ? "n = ?" : `n = ${fmtInt(n)}`);

export function download(name: string, content: string, type = "text/plain") {
  const url = URL.createObjectURL(new Blob([content], { type: `${type};charset=utf-8` }));
  const a = document.createElement("a");
  a.href = url;
  a.download = name;
  a.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}
