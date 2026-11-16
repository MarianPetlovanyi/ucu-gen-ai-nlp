"use client";

// Hand-rolled SVG charts. Marks follow the dataviz spec: bars <= 24px with a 4px rounded data end,
// hairline solid grids, 2px surface gaps, a legend for >= 2 series, text in text tokens only.
import { Fragment, type ReactNode } from "react";
import { fmt3, fmtN } from "@/lib/format";
import { STATUS_META, STATUS_ORDER } from "@/lib/status";
import type { Panel, Status } from "@/lib/types";
import { StatusIcon, Tooltip, useTip, useWidth } from "./ui";

const SERIES = ["var(--series-1)", "var(--series-2)"];

/** Horizontal bar with the data end rounded and the baseline end square. */
function hbar(x0: number, x1: number, y: number, h: number, r = 4): string {
  const w = Math.abs(x1 - x0);
  if (w < 0.5) return "";
  const rr = Math.min(r, w, h / 2);
  const d = x1 > x0 ? 1 : -1;
  const xe = x1 - d * rr;
  const sweep = d > 0 ? 1 : 0;
  return `M${x0},${y}H${xe}A${rr},${rr} 0 0 ${sweep} ${x1},${y + rr}V${y + h - rr}A${rr},${rr} 0 0 ${sweep} ${xe},${y + h}H${x0}Z`;
}

function niceMax(v: number): number {
  for (const s of [0.05, 0.1, 0.2, 0.25, 0.5, 1, 2, 5, 10, 20, 25, 50, 100, 200, 500, 1000]) if (v <= s) return s;
  return Math.ceil(v / 1000) * 1000;
}

function tickLabel(v: number): string {
  return String(Number(v.toFixed(3)));
}

function wrap(text: string, maxChars: number): string[] {
  const lines: string[] = [];
  let cur = "";
  for (const w of text.split(" ")) {
    if (cur && (cur + " " + w).length > maxChars) {
      lines.push(cur);
      cur = w;
    } else cur = cur ? `${cur} ${w}` : w;
  }
  if (cur) lines.push(cur);
  return lines.slice(0, 3);
}

// --- risk gauge -------------------------------------------------------------------------------
export function RiskGauge({ value, sign, reject }: { value: number; sign: number; reject: number }) {
  const W = 260;
  const cx = W / 2;
  const cy = 130;
  const r = 100;
  const sw = 18;
  const v = Math.max(0, Math.min(100, value));
  const pt = (x: number, rad = r) => {
    const a = Math.PI * (1 - x / 100);
    return [cx + rad * Math.cos(a), cy - rad * Math.sin(a)] as const;
  };
  const arc = (a: number, b: number) => {
    const [x0, y0] = pt(a);
    const [x1, y1] = pt(b);
    return `M${x0},${y0}A${r},${r} 0 0 1 ${x1},${y1}`;
  };
  const zones: { from: number; to: number; status: Status; label: string }[] = [
    { from: 0, to: sign, status: "OK", label: `Sign zone 0–${sign}` },
    { from: sign, to: reject, status: "REVIEW", label: `Negotiate zone ${sign}–${reject}` },
    { from: reject, to: 100, status: "VIOLATION", label: `Reject zone ${reject}–100` },
  ];
  const zone = v >= reject ? zones[2] : v <= sign ? zones[0] : zones[1];
  const [mx, my] = pt(v);
  return (
    <figure className="flex flex-col items-center">
      <svg
        viewBox={`0 0 ${W} 158`}
        className="w-full max-w-[300px]"
        role="img"
        aria-label={`Risk score ${value.toFixed(0)} of 100. Sign at or below ${sign}, reject at or above ${reject}.`}
      >
        {zones.map((z) => (
          <path
            key={z.status}
            d={arc(z.from, z.to)}
            fill="none"
            stroke={STATUS_META[z.status].color}
            strokeOpacity={0.22}
            strokeWidth={sw}
          />
        ))}
        {v > 0 && <path d={arc(0, v)} fill="none" stroke={STATUS_META[zone.status].color} strokeWidth={sw} />}
        {[sign, reject].map((t) => {
          const [x0, y0] = pt(t, r - sw / 2 - 4);
          const [x1, y1] = pt(t, r + sw / 2 + 4);
          const [lx, ly] = pt(t, r + sw / 2 + 14);
          return (
            <g key={t}>
              <line x1={x0} y1={y0} x2={x1} y2={y1} stroke="var(--surface)" strokeWidth={4} />
              <line x1={x0} y1={y0} x2={x1} y2={y1} stroke="var(--ink-2)" strokeWidth={1.5} />
              <text
                x={lx}
                y={ly}
                fontSize="11"
                fill="var(--ink-2)"
                textAnchor={t < 50 ? "end" : "start"}
                dominantBaseline="middle"
              >
                {t}
              </text>
            </g>
          );
        })}
        <circle cx={mx} cy={my} r={7} fill={STATUS_META[zone.status].color} stroke="var(--surface)" strokeWidth={2} />
        <text x={cx} y={cy - 22} textAnchor="middle" fontSize="44" fontWeight="600" fill="var(--ink)">
          {value.toFixed(0)}
        </text>
        <text x={cx} y={cy + 2} textAnchor="middle" fontSize="12" fill="var(--muted)">
          risk score / 100
        </text>
        <text x={cx - r} y={cy + 20} textAnchor="middle" fontSize="11" fill="var(--muted)">
          0
        </text>
        <text x={cx + r} y={cy + 20} textAnchor="middle" fontSize="11" fill="var(--muted)">
          100
        </text>
      </svg>
      <figcaption className="mt-1 flex flex-wrap justify-center gap-x-3 gap-y-1 text-xs text-ink-2">
        {zones.map((z) => (
          <span key={z.status} className="inline-flex items-center gap-1">
            <StatusIcon status={z.status} size={11} />
            {z.label}
          </span>
        ))}
      </figcaption>
    </figure>
  );
}

// --- status distribution (tall segmented bar) ------------------------------------------------
export function StatusDistribution({
  counts,
  onPick,
}: {
  counts: Record<Status, number>;
  onPick?: (s: Status) => void;
}) {
  const { tip, show, hide } = useTip();
  const total = STATUS_ORDER.reduce((a, s) => a + counts[s], 0);
  const parts = STATUS_ORDER.filter((s) => counts[s] > 0);
  const fits = (s: Status) => counts[s] / total >= 0.07;
  return (
    <div>
      <div
        className="flex h-7 w-full gap-[2px]"
        role="img"
        aria-label={parts.map((s) => `${STATUS_META[s].label} ${counts[s]}`).join(", ")}
      >
        {parts.map((s) => (
          <button
            key={s}
            onClick={() => onPick?.(s)}
            onMouseMove={(e) =>
              show(
                e,
                <span className="flex items-center gap-1.5">
                  <StatusIcon status={s} size={12} />
                  <b>{STATUS_META[s].label}</b>: {counts[s]} of {total} rules ({Math.round((counts[s] / total) * 100)}
                  %)
                </span>,
              )
            }
            onMouseLeave={hide}
            onFocus={(e) => {
              const r = e.currentTarget.getBoundingClientRect();
              show({ clientX: r.left, clientY: r.bottom - 10 }, `${STATUS_META[s].label}: ${counts[s]} of ${total}`);
            }}
            onBlur={hide}
            className="flex h-full items-center rounded px-2 text-xs font-semibold"
            style={{ width: `${(counts[s] / total) * 100}%`, background: STATUS_META[s].color, color: STATUS_META[s].onFill }}
            aria-label={`${STATUS_META[s].label}: ${counts[s]}`}
          >
            {fits(s) ? counts[s] : ""}
          </button>
        ))}
      </div>
      <div className="mt-2 flex flex-wrap gap-x-4 gap-y-1 text-xs text-ink-2">
        {parts.map((s) => (
          <span key={s} className="inline-flex items-center gap-1.5">
            <StatusIcon status={s} size={12} />
            {STATUS_META[s].label}
            {!fits(s) && <span className="text-muted">({counts[s]})</span>}
          </span>
        ))}
      </div>
      <Tooltip tip={tip} />
    </div>
  );
}

// --- simple horizontal bars (one series) -----------------------------------------------------
export function HBars({
  rows,
  format,
  ariaLabel,
}: {
  rows: { label: string; value: number; tip?: ReactNode }[];
  format: (v: number) => string;
  ariaLabel: string;
}) {
  const { ref, width } = useWidth<HTMLDivElement>();
  const { tip, show, hide } = useTip();
  const labelW = Math.min(150, Math.max(96, width * 0.3));
  const x0 = labelW + 8;
  const x1 = Math.max(x0 + 40, width - 64);
  const max = niceMax(Math.max(...rows.map((r) => r.value), 1e-9));
  const x = (v: number) => x0 + (v / max) * (x1 - x0);
  const rowH = 28;
  const top = 4;
  const H = top + rows.length * rowH + 20;
  const ticks = [0, 0.25, 0.5, 0.75, 1].map((f) => f * max);
  return (
    <div ref={ref} className="w-full">
      {width > 0 && (
        <svg width={width} height={H} role="img" aria-label={ariaLabel}>
          {ticks.map((t) => (
            <g key={t}>
              <line x1={x(t)} x2={x(t)} y1={top} y2={H - 18} stroke={t === 0 ? "var(--axis)" : "var(--grid)"} />
              <text x={x(t)} y={H - 4} fontSize="10" fill="var(--muted)" textAnchor="middle" className="tabular">
                {format(t)}
              </text>
            </g>
          ))}
          {rows.map((r, i) => {
            const y = top + i * rowH + (rowH - 16) / 2;
            return (
              <g key={r.label}>
                <text x={labelW} y={y + 8} fontSize="12" fill="var(--ink-2)" textAnchor="end" dominantBaseline="middle">
                  {r.label}
                </text>
                <path
                  d={hbar(x(0), x(r.value), y, 16)}
                  fill="var(--series-1)"
                  onMouseMove={(e) => show(e, r.tip ?? `${r.label}: ${format(r.value)}`)}
                  onMouseLeave={hide}
                />
                <text x={x(r.value) + 5} y={y + 8} fontSize="11" fill="var(--ink-2)" dominantBaseline="middle">
                  {format(r.value)}
                </text>
              </g>
            );
          })}
        </svg>
      )}
      <Tooltip tip={tip} />
    </div>
  );
}

// --- evaluation panel: grouped bars, target line, table --------------------------------------
export function EvalChart({ panel }: { panel: Panel }) {
  const { ref, width } = useWidth<HTMLDivElement>();
  const { tip, show, hide } = useTip();
  const { series, rows } = panel;
  const values = rows.flatMap((r) => series.map((s) => r.values[s.key]?.value)).filter((v): v is number => v != null);
  const tgt = panel.target?.value;
  const maxV = Math.max(...values, tgt ?? 0, 1e-9);
  const minV = Math.min(0, ...values);
  const domMax = panel.better === "higher" && maxV <= 1 ? 1 : niceMax(maxV * 1.1);
  const domMin = minV < 0 ? -niceMax(-minV) : 0;
  const labelW = Math.min(190, Math.max(110, width * 0.36));
  const x0 = labelW + 10;
  const x1 = Math.max(x0 + 60, width - 46);
  const x = (v: number) => x0 + ((v - domMin) / (domMax - domMin)) * (x1 - x0);
  const barH = series.length > 1 ? 11 : 16;
  const groupH = series.length * barH + (series.length - 1) * 2;
  const maxChars = Math.max(12, Math.floor(labelW / 6.4));
  const top = tgt != null ? 20 : 6;
  const sized = rows.map((r) => {
    const lines = wrap(r.label, maxChars);
    return { r, lines, h: Math.max(groupH + 16, lines.length * 14 + 10) };
  });
  const layout = sized.map((l, i) => ({ ...l, y: top + sized.slice(0, i).reduce((a, p) => a + p.h, 0) }));
  const plotH = sized.reduce((a, l) => a + l.h, 0);
  const H = top + plotH + 22;
  const ticks = Array.from({ length: 5 }, (_, i) => domMin + ((domMax - domMin) * i) / 4);
  const labelValue = (kind: string) => kind === "system" || kind === "metric";

  return (
    <div>
      {(series.length > 1 || tgt != null) && (
        <div className="mb-2 flex flex-wrap items-center gap-x-4 gap-y-1 text-xs text-ink-2">
          {series.length > 1 &&
            series.map((s, i) => (
              <span key={s.key} className="inline-flex items-center gap-1.5">
                <span className="inline-block h-2.5 w-2.5 rounded-sm" style={{ background: SERIES[i] }} />
                {s.label}
              </span>
            ))}
          {tgt != null && (
            <span className="inline-flex items-center gap-1.5">
              <span className="inline-block h-3 w-[2px] bg-ink-2" />
              {panel.target?.label}
            </span>
          )}
          {panel.better === "lower" && <span className="text-muted">lower is better</span>}
        </div>
      )}
      <div ref={ref} className="w-full">
        {width > 0 && (
          <svg width={width} height={H} role="img" aria-label={`${panel.title}. Values are in the table below.`}>
            {ticks.map((t) => (
              <g key={t}>
                <line x1={x(t)} x2={x(t)} y1={top} y2={top + plotH} stroke={t === 0 ? "var(--axis)" : "var(--grid)"} />
                <text x={x(t)} y={H - 6} fontSize="10" fill="var(--muted)" textAnchor="middle" className="tabular">
                  {tickLabel(t)}
                </text>
              </g>
            ))}
            {layout.map(({ r, lines, h, y }) => {
              const gy = y + (h - groupH) / 2;
              return (
                <g key={r.label}>
                  {lines.map((ln, li) => (
                    <text
                      key={li}
                      x={labelW}
                      y={y + h / 2 + (li - (lines.length - 1) / 2) * 14}
                      fontSize="12"
                      fontWeight={r.kind === "system" ? 600 : 400}
                      fill={r.kind === "system" ? "var(--ink)" : "var(--ink-2)"}
                      textAnchor="end"
                      dominantBaseline="middle"
                    >
                      {ln}
                    </text>
                  ))}
                  {series.map((s, si) => {
                    const val = r.values[s.key];
                    const by = gy + si * (barH + 2);
                    if (!val)
                      return (
                        <text key={s.key} x={x(0) + 4} y={by + barH / 2} fontSize="10" fill="var(--muted)" dominantBaseline="middle">
                          {series.length > 1 ? `${s.label}: not run` : "not run"}
                        </text>
                      );
                    const tipContent = (
                      <span>
                        <b>{r.label}</b>
                        {series.length > 1 && <> · {s.label}</>}
                        <br />
                        {fmt3(val.value)} <span className="text-muted">({fmtN(val.n)})</span>
                      </span>
                    );
                    return (
                      <Fragment key={s.key}>
                        <path
                          d={hbar(x(0), x(val.value), by, barH)}
                          fill={SERIES[si]}
                          onMouseMove={(e) => show(e, tipContent)}
                          onMouseLeave={hide}
                        />
                        <rect
                          x={x0}
                          y={by - 1}
                          width={x1 - x0}
                          height={barH + 2}
                          fill="transparent"
                          onMouseMove={(e) => show(e, tipContent)}
                          onMouseLeave={hide}
                        />
                        {labelValue(r.kind) && (
                          <text
                            x={x(Math.max(0, val.value)) + 4}
                            y={by + barH / 2}
                            fontSize="11"
                            fill="var(--ink-2)"
                            dominantBaseline="middle"
                            pointerEvents="none"
                          >
                            {fmt3(val.value)}
                          </text>
                        )}
                      </Fragment>
                    );
                  })}
                </g>
              );
            })}
            {tgt != null && (
              <g pointerEvents="none">
                <line x1={x(tgt)} x2={x(tgt)} y1={top - 4} y2={top + plotH} stroke="var(--ink-2)" strokeWidth={1.5} />
                <text
                  x={x(tgt)}
                  y={top - 8}
                  fontSize="10"
                  fill="var(--ink-2)"
                  textAnchor={x(tgt) > x1 - 40 ? "end" : "middle"}
                >
                  {panel.target?.label}
                </text>
              </g>
            )}
          </svg>
        )}
      </div>
      <table className="mt-2 w-full text-xs">
        <thead>
          <tr className="border-b border-line text-left text-muted">
            <th className="py-1 pr-2 font-medium">Method</th>
            {series.map((s) => (
              <th key={s.key} className="py-1 pl-2 text-right font-medium">
                {s.label}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((r) => (
            <tr key={r.label} className="border-b border-line last:border-0">
              <td className={`py-1 pr-2 ${r.kind === "system" ? "font-semibold text-ink" : "text-ink-2"}`}>{r.label}</td>
              {series.map((s) => {
                const v = r.values[s.key];
                return (
                  <td key={s.key} className="tabular py-1 pl-2 text-right text-ink whitespace-nowrap">
                    {v ? (
                      <>
                        {fmt3(v.value)} <span className="text-muted">{fmtN(v.n)}</span>
                      </>
                    ) : (
                      <span className="text-muted">—</span>
                    )}
                  </td>
                );
              })}
            </tr>
          ))}
        </tbody>
      </table>
      <Tooltip tip={tip} />
    </div>
  );
}
