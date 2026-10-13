"use client";

import { ApiError } from "@/lib/api";
import { dmy } from "@/lib/format";
import { useT } from "@/lib/store";

/* Panels follow the global as-of unless pinned (UI_SPEC §2: asOfMode follow | pinned). */
export function usePanelAsOf(pin?: string) {
  const g = useT((s) => s.asOf);
  return pin ?? g;
}

export function PanelState({ q, children, empty }: { q: { isLoading: boolean; error: unknown; data?: unknown }; children: () => React.ReactNode; empty?: string }) {
  const asOf = useT((s) => s.asOf);
  if (q.isLoading) return <Skeleton />;
  if (q.error) {
    const e = q.error as ApiError;
    if (e.status === 404)
      return <div className="t-empty"><b>Not listed as of {asOf === "NOW" ? "today" : dmy(asOf)}</b><span>{e.message}</span></div>;
    if (e.status === 503) return <div className="t-empty"><b>Database busy</b><span>The pipeline is writing (refresh). Try again in a minute.</span></div>;
    return <div className="t-empty"><b>API unavailable</b><span>{e.message || "Start it: python -m uvicorn trikal_api.app:app --app-dir api"}</span></div>;
  }
  if (empty) return <div className="t-empty"><b>Nothing to show yet</b><span>{empty}</span></div>;
  if (q.data === undefined) return <Skeleton />;      // between a failed/paused fetch and the next one: never render children without data
  return <>{children()}</>;
}

export function Skeleton() {
  return (
    <div className="t-skel">
      {Array.from({ length: 7 }).map((_, i) => <i key={i} style={{ width: `${40 + ((i * 37) % 55)}%` }} />)}
    </div>
  );
}

export function Seg<T extends string>({ value, options, onChange }: { value: T; options: { v: T; l: string }[]; onChange: (v: T) => void }) {
  return (
    <div className="t-seg" role="tablist">
      {options.map((o) => (
        <button key={o.v} role="tab" aria-selected={value === o.v} className={value === o.v ? "on" : ""} onClick={() => onChange(o.v)}>{o.l}</button>
      ))}
    </div>
  );
}

export function Chip({ children, tone = "plain", title }: { children: React.ReactNode; tone?: "plain" | "gold" | "pos" | "neg" | "warn" | "mute"; title?: string }) {
  return <span className={`t-chip t-chip-${tone}`} title={title}>{children}</span>;
}
