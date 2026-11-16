"use client";

import { useEffect, useRef, useState, type ReactNode } from "react";
import { REC_META, STATUS_META } from "@/lib/status";
import type { Recommendation, Severity, Status } from "@/lib/types";

/** Shape and glyph differ per status, so the icon still reads without colour. */
export function StatusIcon({ status, size = 14 }: { status: Status; size?: number }) {
  const c = STATUS_META[status].color;
  const ink = STATUS_META[status].onFill;
  // inline-block: Tailwind's preflight makes svg a block, which would break a line inside running text.
  const p = {
    width: size,
    height: size,
    viewBox: "0 0 16 16",
    "aria-hidden": true,
    className: "inline-block shrink-0 align-[-0.125em]",
  };
  switch (status) {
    case "VIOLATION":
      return (
        <svg {...p}>
          <path d="M5 1h6l4 4v6l-4 4H5l-4-4V5z" fill={c} />
          <path d="M5.6 5.6l4.8 4.8M10.4 5.6l-4.8 4.8" stroke={ink} strokeWidth="1.7" strokeLinecap="round" />
        </svg>
      );
    case "MISSING":
      return (
        <svg {...p}>
          <circle cx="8" cy="8" r="7" fill={c} />
          <path d="M4.6 8h6.8" stroke={ink} strokeWidth="1.9" strokeLinecap="round" />
        </svg>
      );
    case "REVIEW":
      return (
        <svg {...p}>
          <path d="M8 1.3l7 12.9H1z" fill={c} strokeLinejoin="round" />
          <path d="M8 6v3.8" stroke={ink} strokeWidth="1.7" strokeLinecap="round" />
          <circle cx="8" cy="12" r="0.95" fill={ink} />
        </svg>
      );
    case "OK":
      return (
        <svg {...p}>
          <circle cx="8" cy="8" r="7" fill={c} />
          <path d="M4.7 8.3l2.2 2.2 4.4-4.6" fill="none" stroke={ink} strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" />
        </svg>
      );
    default:
      return (
        <svg {...p}>
          <circle cx="8" cy="8" r="7" fill={c} />
          <path d="M8 7.2v4" stroke={ink} strokeWidth="1.8" strokeLinecap="round" />
          <circle cx="8" cy="4.8" r="1" fill={ink} />
        </svg>
      );
  }
}

/** Status pill: icon + label in text ink, the colour lives in the icon and a light wash. */
export function StatusBadge({ status, compact = false }: { status: Status; compact?: boolean }) {
  const m = STATUS_META[status];
  return (
    <span
      className="inline-flex items-center gap-1.5 rounded-full px-2 py-0.5 text-xs font-medium text-ink whitespace-nowrap"
      style={{ background: `color-mix(in srgb, ${m.color} 14%, transparent)` }}
      title={`${m.label}: ${m.hint}`}
    >
      <StatusIcon status={status} size={compact ? 12 : 14} />
      {m.label}
    </span>
  );
}

export function SeverityTag({ severity }: { severity: Severity }) {
  const filled = severity === "high" ? 3 : severity === "medium" ? 2 : 1;
  return (
    <span className="inline-flex items-center gap-1.5 text-xs text-ink-2 whitespace-nowrap">
      <svg width="12" height="12" viewBox="0 0 12 12" aria-hidden="true">
        {[0, 1, 2].map((i) => (
          <rect
            key={i}
            x={i * 4}
            y={8 - i * 3}
            width="3"
            height={4 + i * 3}
            rx="0.8"
            fill={i < filled ? "var(--ink-2)" : "var(--grid)"}
          />
        ))}
      </svg>
      {severity[0].toUpperCase() + severity.slice(1)}
    </span>
  );
}

export function RecommendationBadge({ rec, large = false }: { rec: Recommendation; large?: boolean }) {
  const m = REC_META[rec];
  const color = STATUS_META[m.status].color;
  return (
    <span
      className={`inline-flex items-center gap-2 rounded-lg font-semibold text-ink ${large ? "px-4 py-2 text-xl" : "px-2.5 py-1 text-sm"}`}
      style={{
        background: `color-mix(in srgb, ${color} 16%, transparent)`,
        boxShadow: `inset 0 0 0 1px color-mix(in srgb, ${color} 45%, transparent)`,
      }}
    >
      <StatusIcon status={m.status} size={large ? 20 : 14} />
      {m.label}
    </span>
  );
}

export function Card({
  title,
  subtitle,
  children,
  className = "",
  actions,
}: {
  title?: ReactNode;
  subtitle?: ReactNode;
  children: ReactNode;
  className?: string;
  actions?: ReactNode;
}) {
  return (
    <section className={`rounded-xl border border-line bg-surface p-4 ${className}`}>
      {(title || actions) && (
        <div className="mb-3 flex items-start gap-3">
          <div className="min-w-0">
            {title && <h3 className="text-sm font-semibold text-ink">{title}</h3>}
            {subtitle && <p className="mt-0.5 text-xs text-muted">{subtitle}</p>}
          </div>
          {actions && <div className="ml-auto flex shrink-0 gap-2">{actions}</div>}
        </div>
      )}
      {children}
    </section>
  );
}

export function StatTile({ label, value, sub, status }: { label: string; value: ReactNode; sub?: ReactNode; status?: Status }) {
  return (
    <div className="rounded-xl border border-line bg-surface p-4">
      <div className="flex items-center gap-1.5 text-xs text-ink-2">
        {status && <StatusIcon status={status} size={12} />}
        {label}
      </div>
      <div className="mt-1 text-3xl font-semibold text-ink">{value}</div>
      {sub && <div className="mt-0.5 text-xs text-muted">{sub}</div>}
    </div>
  );
}

export function Button({
  children,
  onClick,
  variant = "secondary",
  disabled,
  type = "button",
  title,
  small,
}: {
  children: ReactNode;
  onClick?: () => void;
  variant?: "primary" | "secondary" | "ghost";
  disabled?: boolean;
  type?: "button" | "submit";
  title?: string;
  small?: boolean;
}) {
  const base = `inline-flex items-center justify-center gap-1.5 rounded-md font-medium transition-colors disabled:cursor-not-allowed disabled:opacity-50 ${small ? "px-2 py-1 text-xs" : "px-3 py-2 text-sm"}`;
  const styles = {
    primary: "bg-accent text-white hover:brightness-110",
    secondary: "border border-line bg-surface text-ink hover:bg-surface-2",
    ghost: "text-ink-2 hover:bg-surface-2 hover:text-ink",
  }[variant];
  return (
    <button type={type} className={`${base} ${styles}`} onClick={onClick} disabled={disabled} title={title}>
      {children}
    </button>
  );
}

export function Tabs<T extends string>({
  tabs,
  value,
  onChange,
}: {
  tabs: { id: T; label: string; badge?: ReactNode }[];
  value: T;
  onChange: (id: T) => void;
}) {
  return (
    <div role="tablist" className="flex gap-1 overflow-x-auto overflow-y-hidden border-b border-line">
      {tabs.map((t) => (
        <button
          key={t.id}
          role="tab"
          aria-selected={value === t.id}
          onClick={() => onChange(t.id)}
          className={`-mb-px flex items-center gap-1.5 whitespace-nowrap border-b-2 px-3 py-2 text-sm ${
            value === t.id ? "border-accent font-medium text-ink" : "border-transparent text-ink-2 hover:text-ink"
          }`}
        >
          {t.label}
          {t.badge}
        </button>
      ))}
    </div>
  );
}

export function Count({ n }: { n: number }) {
  return <span className="rounded-full bg-surface-2 px-1.5 text-[11px] text-ink-2 tabular">{n}</span>;
}

export function SpanRef({ id, onClick }: { id: number; onClick?: (id: number) => void }) {
  return (
    <button
      onClick={() => onClick?.(id)}
      className="rounded border border-line bg-surface-2 px-1.5 py-0.5 font-mono text-[11px] text-accent-ink hover:border-accent"
      title={`Show span ${id} in the contract`}
    >
      §{id}
    </button>
  );
}

// --- tooltip ----------------------------------------------------------------------------------
export interface TipState {
  x: number;
  y: number;
  content: ReactNode;
}

export function useTip() {
  const [tip, setTip] = useState<TipState | null>(null);
  const show = (e: { clientX: number; clientY: number }, content: ReactNode) =>
    setTip({ x: e.clientX, y: e.clientY, content });
  const showAt = (el: Element, content: ReactNode) => {
    const r = el.getBoundingClientRect();
    setTip({ x: r.left + r.width / 2, y: r.top, content });
  };
  const hide = () => setTip(null);
  return { tip, show, showAt, hide };
}

export function Tooltip({ tip }: { tip: TipState | null }) {
  if (!tip) return null;
  const left = Math.max(8, Math.min(tip.x + 14, (typeof window !== "undefined" ? window.innerWidth : 1200) - 320));
  return (
    <div
      role="tooltip"
      style={{ position: "fixed", left, top: tip.y + 16, zIndex: 50 }}
      className="pointer-events-none max-w-[300px] rounded-lg border border-line bg-surface px-3 py-2 text-xs text-ink shadow-lg"
    >
      {tip.content}
    </div>
  );
}

/** Width of an element, for SVG charts whose text must stay at its real size. */
export function useWidth<T extends HTMLElement>() {
  const ref = useRef<T>(null);
  const [width, setWidth] = useState(0);
  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    const measure = () => setWidth(Math.floor(el.getBoundingClientRect().width));
    const ro = new ResizeObserver(measure);
    ro.observe(el);
    const raf = requestAnimationFrame(measure); // RO's first callback is not guaranteed for an empty box
    return () => {
      cancelAnimationFrame(raf);
      ro.disconnect();
    };
  }, []);
  return { ref, width };
}

export function ErrorBox({ children }: { children: ReactNode }) {
  return (
    <div className="flex items-start gap-2 rounded-lg border border-line bg-surface p-3 text-sm text-ink" role="alert">
      <StatusIcon status="VIOLATION" />
      <div>{children}</div>
    </div>
  );
}
