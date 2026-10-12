"use client";

/* RV · WC · OWN · DCF */

import { useEffect, useMemo, useRef, useState } from "react";
import * as echarts from "echarts/core";
import { BarChart } from "echarts/charts";
import { GridComponent, LegendComponent, TooltipComponent } from "echarts/components";
import { CanvasRenderer } from "echarts/renderers";
import { runValuation, useChanges, useOwnership, usePeers, useValuationMethods, type MetricResult } from "@/lib/api";
import { byUnit, dmy, dmyTime, inr, METRIC_LABEL } from "@/lib/format";
import { useT } from "@/lib/store";
import { LockIcon, Value } from "@/components/ui/Value";
import { Chip, PanelState, usePanelAsOf } from "./common";
import type { PanelProps } from "./PanelsA";

echarts.use([BarChart, GridComponent, LegendComponent, TooltipComponent, CanvasRenderer]);

/* ------------------------------------------------------------------ RV */
export function RV({ params }: PanelProps) {
  const code = useT((s) => s.code);
  const setCode = useT((s) => s.setCode);
  const asOf = usePanelAsOf(params.pin);
  const q = usePeers(code, asOf);
  const [sort, setSort] = useState<string>("market_cap");
  const rows = useMemo(() => {
    const r = [...(q.data?.rows ?? [])];
    const key = (x: (typeof r)[number]) => { const m = x.metrics[sort]; return m?.state === "value" && m.value !== null ? m.value : -Infinity; };
    return r.sort((a, b) => key(b) - key(a));
  }, [q.data, sort]);
  return (
    <div className="t-panel">
      <PanelState q={q}>
        {() => (
          <>
            <div className="t-toolbar"><span className="t-dim">{q.data!.sector ?? "no sector label"} · playbook <span className="mono">{q.data!.playbook}</span> · {rows.length} with data</span></div>
            <div className="fa-scroll">
              <table className="t-table">
                <thead><tr><th className="sticky">Company</th>{q.data!.columns.map((c) => <th key={c} className={`sortable ${sort === c ? "on" : ""}`} onClick={() => setSort(c)}>{METRIC_LABEL[c] ?? c}{sort === c ? " ↓" : ""}</th>)}</tr></thead>
                <tbody>
                  {rows.map((r) => (
                    <tr key={r.security_id} className={r.self ? "self" : ""}>
                      <td className="sticky"><button className="t-link" onClick={() => !r.self && setCode(r.security_id)}>{r.name}</button></td>
                      {q.data!.columns.map((c) => <td key={c}><Value r={r.metrics[c]} /></td>)}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <div className="t-foot">{q.data!.note}. Peers without any computable metric are hidden until their filings arrive.</div>
          </>
        )}
      </PanelState>
    </div>
  );
}

/* ------------------------------------------------------------------ WC */
function delta(m: MetricResult, d: number | null) {
  if (d === null || m.state !== "value") return <span className="v v-muted">—</span>;
  const s = m.unit === "INR" ? inr(d) : m.unit === "ratio" ? `${(d * 100).toFixed(1)} pp` : byUnit(d, m.unit);
  return <span className={`v ${d > 0 ? "pos" : d < 0 ? "neg" : ""}`}>{d > 0 ? "▲ " : d < 0 ? "▼ " : ""}{s.replace("−", "")}</span>;
}

export function WC({ params }: PanelProps) {
  const code = useT((s) => s.code);
  const asOf = usePanelAsOf(params.pin);
  const q = useChanges(code, asOf);
  return (
    <div className="t-panel">
      <PanelState q={q}>
        {() => (
          <>
            <div className="t-toolbar"><span className="t-dim">since {dmyTime(q.data!.since)} → {asOf === "NOW" ? "now" : dmy(asOf)}</span></div>
            <div className="wc-grid">
              <table className="t-table">
                <thead><tr><th>Metric</th><th>Then</th><th>Now</th><th>Change</th></tr></thead>
                <tbody>
                  {q.data!.metrics.map((m) => (
                    <tr key={m.metric}>
                      <td>{METRIC_LABEL[m.metric] ?? m.metric}</td>
                      <td><Value r={m.then} /></td>
                      <td><Value r={m.now} /></td>
                      <td>{delta(m.now, m.delta)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
              <div className="wc-events">
                <div className="t-k">Became public in the window</div>
                {q.data!.events.length === 0 && <div className="t-dim">No filings, corporate actions or index changes.</div>}
                {q.data!.events.map((e, i) => (
                  <div key={i} className="wc-ev"><span className={`evt evt-${e.type}`} /><b>{e.label}</b><span className="mono t-dim">{dmyTime(e.known_at)}</span></div>
                ))}
              </div>
            </div>
          </>
        )}
      </PanelState>
    </div>
  );
}

/* ------------------------------------------------------------------ OWN */
const GROUPS: [string, string, string][] = [
  ["promoter", "Promoter", "#D4AF37"], ["mutual_funds", "Mutual funds", "#2EC4B6"], ["insurance", "Insurance", "#7AA2F7"],
  ["fpi", "Foreign portfolio", "#B48EF0"], ["retail", "Retail", "#A7A9AE"],
];

export function OWN({ params }: PanelProps) {
  const code = useT((s) => s.code);
  const asOf = usePanelAsOf(params.pin);
  const q = useOwnership(code, asOf);
  const el = useRef<HTMLDivElement>(null);
  const quarters = useMemo(() => [...(q.data?.quarters ?? [])].reverse(), [q.data]);
  useEffect(() => {
    if (!el.current || !quarters.length) return;
    const ch = echarts.init(el.current);
    const x = quarters.map((r) => String(r.period_end).slice(0, 7));
    const series = GROUPS.map(([k, name, color]) => ({
      name, type: "bar" as const, stack: "own", barWidth: "58%", itemStyle: { color, borderRadius: 0 },
      data: quarters.map((r) => (typeof r[k] === "number" ? (r[k] as number) : null)),
    }));
    const known = quarters.map((r) => GROUPS.reduce((a, [k]) => a + (typeof r[k] === "number" ? (r[k] as number) : 0), 0));
    series.push({ name: "Other / not broken out", type: "bar", stack: "own", barWidth: "58%", itemStyle: { color: "#262B33", borderRadius: 0 },
      data: known.map((k) => Math.max(0, 100 - k)) });
    ch.setOption({
      animationDuration: 700,
      grid: { left: 36, right: 10, top: 34, bottom: 26 },
      legend: { top: 0, left: 0, textStyle: { color: "#A7A9AE", fontSize: 11 }, itemWidth: 10, itemHeight: 8 },
      tooltip: { trigger: "axis", backgroundColor: "rgba(13,15,18,0.96)", borderColor: "#3A414C", textStyle: { color: "#E8E6E1", fontSize: 12 },
        valueFormatter: (v: number | null) => (v === null || v === undefined ? "n/a" : `${v.toFixed(2)}%`) },
      xAxis: { type: "category", data: x, axisLine: { lineStyle: { color: "#262B33" } }, axisLabel: { color: "#6B7079", fontSize: 10, fontFamily: "JetBrains Mono" } },
      yAxis: { type: "value", max: 100, splitLine: { lineStyle: { color: "rgba(38,43,51,0.4)" } }, axisLabel: { color: "#6B7079", fontSize: 10, formatter: "{value}%" } },
      series,
    });
    const ro = new ResizeObserver(() => ch.resize());
    ro.observe(el.current);
    return () => { ro.disconnect(); ch.dispose(); };
  }, [quarters]);
  const latest = q.data?.quarters[0];
  return (
    <div className="t-panel own">
      <PanelState q={q} empty={q.data && !q.data.quarters.length ? "No shareholding filings known at this as-of." : undefined}>
        {() => (
          <>
            {latest && (
              <div className="own-kpis">
                {GROUPS.map(([k, n, c]) => (
                  <div key={k}><i style={{ background: c }} /><span>{n}</span><b className="mono">{typeof latest[k] === "number" ? `${(latest[k] as number).toFixed(2)}%` : <span className="v-muted">n/a</span>}</b></div>
                ))}
                <div><span>Quarter</span><b className="mono">{dmy(String(latest.period_end))}</b></div>
              </div>
            )}
            <div ref={el} className="own-chart" />
            {q.data!.pledge.length > 0 && (
              <div className="own-pledge">
                <span className="t-k">Promoter pledge</span>
                {q.data!.pledge.slice(0, 4).map((p, i) => (
                  <span key={i} className="mono">{dmy(String(p.as_on))}: {typeof p.pledged_pct_of_promoter === "number" ? `${(p.pledged_pct_of_promoter as number).toFixed(2)}% of promoter holding` : "n/a"}</span>
                ))}
              </div>
            )}
            <div className="t-foot">{q.data!.note}. Missing categories are n/a, never zero.</div>
          </>
        )}
      </PanelState>
    </div>
  );
}

/* ------------------------------------------------------------------ DCF: Valuation Lab */
const METHOD_LABEL: Record<string, string> = {
  dcf_fcff: "DCF · free cash flow to firm", dcf_fcfe: "DCF · free cash flow to equity", reverse_dcf_fcff: "Reverse DCF · growth priced in",
  ddm: "Dividend discount", justified_pb: "Justified P/B", residual_income: "Residual income", sotp: "Sum of the parts", nav: "Net asset value",
  ev_per_tonne: "EV per tonne", ev_per_mw: "EV per MW", multiples: "Multiples vs history & peers", p_abv: "P / adjusted book", pe: "P/E",
};
const PCT_KEYS = new Set(["wacc", "g_start", "g_terminal", "cost_of_equity", "roe", "payout", "persistence"]);

type RunOut = Awaited<ReturnType<typeof runValuation>>;

export function DCF({ params }: PanelProps) {
  const code = useT((s) => s.code);
  const asOf = usePanelAsOf(params.pin);
  const q = useValuationMethods(code, asOf);
  const [method, setMethod] = useState<string | null>(null);
  const [vals, setVals] = useState<Record<string, string>>({});
  const [edited, setEdited] = useState<Set<string>>(new Set());
  const [out, setOut] = useState<RunOut | null>(null);
  const [busy, setBusy] = useState(false);
  const d = q.data;
  const all = useMemo(() => (d ? [...new Set([...d.primary, ...d.secondary, ...Object.keys(d.required), ...d.forbidden])] : []), [d]);
  const runnable = (m: string) => !!d && m in d.required;

  useEffect(() => {
    if (!d) return;
    const first = [...d.primary, ...d.secondary].find((m) => m in d.required && !d.forbidden.includes(m)) ?? Object.keys(d.templates)[0] ?? null;
    setMethod(first);
    setOut(null);
  }, [d]);
  useEffect(() => {
    if (!d || !method) return;
    const t = d.templates[method] ?? {};
    const v: Record<string, string> = {};
    for (const k of d.required[method] ?? []) {
      const x = t[k];
      v[k] = x === undefined ? "" : PCT_KEYS.has(k) ? String(+(Number(x) * 100).toFixed(2)) : String(x);
    }
    setVals(v);
    setEdited(new Set());
    setOut(null);
  }, [d, method]);

  const run = async () => {
    if (!method) return;
    setBusy(true);
    const a: Record<string, unknown> = {};
    for (const [k, s] of Object.entries(vals)) {
      if (s === "") continue;
      const n = Number(s);
      a[k] = PCT_KEYS.has(k) ? n / 100 : n;
    }
    try { setOut(await runValuation(code, asOf, method, a)); } catch (e) { setOut({ as_of: "", demo: false, state: "na", reason: String(e) }); }
    setBusy(false);
  };

  const v = out?.valuation as Record<string, unknown> | undefined;
  const fmt = (x: unknown, unit: "inr" | "ps" | "x" | "pct") => {
    if (typeof x !== "number") return <span className="v v-muted">n/a</span>;
    if (unit === "inr") return <span className="v">{inr(x)}</span>;
    if (unit === "ps") return <span className="v">₹{x.toLocaleString("en-IN", { maximumFractionDigits: 2 })}</span>;
    if (unit === "pct") return <span className="v">{(x * 100).toFixed(1)}%</span>;
    return <span className="v">{x.toFixed(2)}×</span>;
  };

  return (
    <div className="t-panel dcf">
      <PanelState q={q}>
        {() => (
          <div className="lab">
            <div className="lab-methods">
              <div className="t-k">Methods · {d!.playbook} playbook</div>
              {all.map((m) => {
                const forb = d!.forbidden.includes(m);
                const tag = d!.primary.includes(m) ? "primary" : d!.secondary.includes(m) ? "secondary" : d!.not_primary.includes(m) ? "not primary" : "";
                return (
                  <button key={m} disabled={forb || !runnable(m)} className={`lab-m ${method === m ? "on" : ""} ${forb ? "forb" : ""}`} onClick={() => setMethod(m)}
                    title={forb ? d!.reason : !runnable(m) ? "Computed in the Relative panel / needs data from a later milestone" : ""}>
                    {forb && <LockIcon />}
                    <span>{METHOD_LABEL[m] ?? m}</span>
                    {tag && <i>{tag}</i>}
                  </button>
                );
              })}
              {d!.forbidden.length > 0 && <p className="lab-why"><LockIcon /> {d!.reason}</p>}
            </div>
            <div className="lab-main">
              {method && (
                <>
                  <div className="lab-title">{METHOD_LABEL[method] ?? method}</div>
                  <div className="lab-form">
                    {(d!.required[method] ?? []).map((k) => {
                      const tmpl = k in (d!.templates[method] ?? {});
                      return (
                        <label key={k}>
                          <span>{k.replace(/_/g, " ")}{PCT_KEYS.has(k) ? " %" : ""}</span>
                          <input className="mono" value={vals[k] ?? ""} placeholder="required"
                            onChange={(e) => { setVals({ ...vals, [k]: e.target.value }); setEdited(new Set(edited).add(k)); }} />
                          <i className={edited.has(k) ? "user" : tmpl ? "tmpl" : "need"}>{edited.has(k) ? "user" : tmpl ? "template" : "you must set"}</i>
                        </label>
                      );
                    })}
                  </div>
                  <div className="lab-actions">
                    <button className="lab-run" onClick={run} disabled={busy}>{busy ? "Running…" : "Run"}</button>
                    <span className="t-dim">Template values are conventional starting points, not recommendations. Inputs from filings are labelled <b>pit</b>.</span>
                  </div>
                </>
              )}
              {out && out.state === "forbidden" && (
                <div className="lab-out forb"><LockIcon size={14} /><div><b>Forbidden for {out.playbook}</b><p>{out.reason}</p></div></div>
              )}
              {out && out.state === "na" && (
                <div className="lab-out na"><b>Cannot compute yet</b><p>{out.reason}</p></div>
              )}
              {out && out.state === "value" && v && (
                <div className="lab-out ok">
                  <div className="lab-res">
                    <div><span>Equity value</span>{fmt(v.equity_value, "inr")}</div>
                    <div><span>Per share</span>{fmt(v.per_share, "ps")}</div>
                    <div><span>Last price</span>{fmt(v.price, "ps")}</div>
                    <div><span>Value / price</span>{fmt(v.value_to_price, "x")}</div>
                    {typeof v.terminal_share === "number" && <div><span>Terminal share</span>{fmt(v.terminal_share, "pct")}</div>}
                    {Object.entries((v.implied as Record<string, number>) ?? {}).map(([k, x]) => <div key={k}><span>{k.replace(/_/g, " ")}</span>{fmt(x, k.includes("growth") ? "pct" : "x")}</div>)}
                  </div>
                  <div className="lab-ass">
                    {((v.assumptions as { name: string; value: unknown; source: string }[]) ?? []).map((a) => (
                      <Chip key={a.name} tone={a.source.startsWith("pit") ? "pos" : a.source === "template" ? "warn" : "gold"} title={a.source}>
                        {a.name} = {typeof a.value === "number" ? (PCT_KEYS.has(a.name) ? `${(a.value * 100).toFixed(1)}%` : Math.abs(a.value) > 1e6 ? inr(a.value) : a.value.toLocaleString("en-IN")) : "…"} · {a.source.split(":")[0]}
                      </Chip>
                    ))}
                  </div>
                  {((v.warnings as string[]) ?? []).length > 0 && <div className="lab-warn">{(v.warnings as string[]).join(" · ")}</div>}
                  <div className="t-foot">A value under stated assumptions — not a target price, not a rating.</div>
                </div>
              )}
            </div>
          </div>
        )}
      </PanelState>
    </div>
  );
}
