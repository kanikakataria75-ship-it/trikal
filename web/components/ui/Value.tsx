"use client";

import type { MetricResult } from "@/lib/api";
import { byUnit, dmyTime, LINE_LABEL, METRIC_LABEL } from "@/lib/format";
import { Tip } from "./Tooltip";

export function LockIcon({ size = 11 }: { size?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 16 16" aria-hidden>
      <rect x="3" y="7" width="10" height="7.5" rx="1.6" fill="none" stroke="currentColor" strokeWidth="1.4" />
      <path d="M5.2 7V5.2a2.8 2.8 0 0 1 5.6 0V7" fill="none" stroke="currentColor" strokeWidth="1.4" />
    </svg>
  );
}

function shortDoc(url: string) {
  const s = url.split("/").pop() ?? url;
  return s.length > 42 ? s.slice(0, 20) + "…" + s.slice(-18) : s;
}

export function Lineage({ r }: { r: MetricResult }) {
  if (r.state === "value") {
    return (
      <div>
        <b>{METRIC_LABEL[r.metric] ?? r.metric}</b>
        <div className="k" style={{ margin: "4px 0 6px" }}>{r.formula}</div>
        {r.inputs.slice(0, 6).map((i, k) => (
          <div key={k} style={{ display: "flex", justifyContent: "space-between", gap: 12 }}>
            <span>{LINE_LABEL(i.name)} <span className="k">{i.period_end ?? ""}</span></span>
            <span className="mono k">{shortDoc(i.filing_id)}</span>
          </div>
        ))}
        {r.inputs[0] && <div className="k" style={{ marginTop: 6 }}>known at {dmyTime(r.inputs[0].known_at)}</div>}
        {r.warnings.length > 0 && <div style={{ marginTop: 6, color: "var(--warn)" }}>{r.warnings.join(" · ")}</div>}
      </div>
    );
  }
  if (r.state === "forbidden")
    return (
      <div>
        <b>Forbidden for this sector</b>
        <div className="k" style={{ margin: "4px 0" }}>playbook <span className="mono">{r.playbook}</span> · {r.rule}</div>
        <div>{r.reason}</div>
      </div>
    );
  if (r.state === "undefined") return <div><b>n.m. — not meaningful</b><div>{r.reason}</div></div>;
  return (
    <div>
      <b>n/a — not available</b>
      {r.missing.length > 0 && <div>missing: <span className="mono">{r.missing.join(", ")}</span></div>}
      {r.reason && <div className="k">{r.reason}</div>}
    </div>
  );
}

/* A metric in one of the four honest states. Never zero-filled, never blank without a reason. */
export function Value({ r, className }: { r: MetricResult | undefined; className?: string }) {
  if (!r) return <span className="v v-muted">…</span>;
  let body: React.ReactNode;
  if (r.state === "value" && r.value !== null) {
    body = (
      <span className={`v ${className ?? ""}`}>
        {byUnit(r.value, r.unit)}
        {r.low_confidence && <span className="v-dot" />}
      </span>
    );
  } else if (r.state === "forbidden") {
    body = <span className="v v-lock"><LockIcon /> —</span>;
  } else if (r.state === "undefined") {
    body = <span className="v v-muted">n.m.</span>;
  } else {
    body = <span className="v v-muted">n/a</span>;
  }
  return <Tip content={<Lineage r={r} />}>{body}</Tip>;
}
