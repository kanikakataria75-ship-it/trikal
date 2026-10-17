"use client";

/* Compare 2-3 companies on one clean screen: rebased price chart, headline numbers, KASAUTI, ownership and the statements side by side.
   Nothing else on the page. All numbers are the same point-in-time numbers the terminal shows; the as-of date applies to all of them. */

import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { useEffect, useMemo, useRef, useState } from "react";
import { ColorType, CrosshairMode, LineSeries, PriceScaleMode, createChart, type UTCTimestamp } from "lightweight-charts";
import { useCompanies, useFinancialsMany, useKasautiMany, useOwnershipMany, usePricesMany, type Financials } from "@/lib/api";
import { byUnit, dmy, LINE_LABEL, METRIC_LABEL, todayIST } from "@/lib/format";
import "@/components/terminal/terminal.css";
import "./compare.css";

const COLORS = ["#D4AF37", "#2EC4B6", "#B48EF0"];
const ROWS = ["market_cap", "revenue_ttm", "pat_ttm", "ebitda_margin", "net_margin", "roe", "roce", "pe", "pb", "ev_ebitda", "debt_to_equity", "interest_coverage", "revenue_growth", "profit_growth", "fcf_yield"];
const LOWER_BETTER = new Set(["pe", "pb", "ev_ebitda", "debt_to_equity"]);
const STATEMENTS: [string, string][] = [["income", "Income statement"], ["balance", "Balance sheet"], ["cashflow", "Cash flow"]];
const YEARS = 4;

function Chart({ series, log, from }: { series: { code: string; t: string[]; c: number[] }[]; log: boolean; from: string | null }) {
  const el = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (!el.current || !series.length) return;
    const chart = createChart(el.current, {
      autoSize: true,
      layout: { background: { type: ColorType.Solid, color: "transparent" }, textColor: "#8A8D93", fontFamily: "JetBrains Mono, monospace", fontSize: 11, attributionLogo: false },
      grid: { vertLines: { color: "rgba(38,43,51,0.35)" }, horzLines: { color: "rgba(38,43,51,0.35)" } },
      rightPriceScale: { borderColor: "#262B33", mode: log ? PriceScaleMode.Logarithmic : PriceScaleMode.Normal },
      timeScale: { borderColor: "#262B33" },
      crosshair: { mode: CrosshairMode.Normal },
    });
    const starts = series.map((s) => s.t.findIndex((d) => !from || d >= from)).map((i, k) => (i < 0 ? series[k].t.length : i));
    const common = series.map((s, k) => s.t[starts[k]] ?? "0000").sort().at(-1) ?? "0000";          // the first day every company has a price
    series.forEach((s, k) => {
      const i0 = s.t.findIndex((d) => d >= common);
      if (i0 < 0) return;
      const base = s.c[i0];
      const line = chart.addSeries(LineSeries, { color: COLORS[k], lineWidth: 2, priceLineVisible: false, title: s.code });
      line.setData(s.t.slice(i0).map((d, i) => ({ time: (Date.parse(`${d}T00:00:00Z`) / 1000) as UTCTimestamp, value: (s.c[i0 + i] / base) * 100 })));
    });
    chart.timeScale().fitContent();
    return () => chart.remove();
  }, [series, log, from]);
  return <div ref={el} className="cmp-chart" />;
}

const years = (n: number) => { const d = new Date(`${todayIST()}T00:00:00Z`); d.setUTCFullYear(d.getUTCFullYear() - n); return d.toISOString().slice(0, 10); };

export default function Compare() {
  const sp = useSearchParams();
  const router = useRouter();
  const asOf = sp.get("asof") || "NOW";
  const codes = useMemo(() => (sp.get("codes") ?? "").split(",").map((c) => c.trim().toUpperCase()).filter(Boolean).slice(0, 3), [sp]);
  const [draft, setDraft] = useState("");
  const [range, setRange] = useState<number | null>(5);
  const [log, setLog] = useState(false);
  const [st, setSt] = useState("income");
  const cos = useCompanies(codes, asOf);
  const px = usePricesMany(codes, asOf);
  const fin = useFinancialsMany(codes, asOf);
  const kas = useKasautiMany(codes, asOf);
  const own = useOwnershipMany(codes, asOf);
  const go = (next: string[]) => router.replace(`/compare?codes=${next.join(",")}${asOf !== "NOW" ? `&asof=${asOf}` : ""}`);
  const series = codes.flatMap((c, i) => (px[i].data?.bars.t.length ? [{ code: c, t: px[i].data!.bars.t, c: px[i].data!.bars.c }] : []));

  const best = (m: string): number | null => {
    const vals = cos.map((q) => { const r = q.data?.metrics[m]; return r && r.state === "value" ? r.value : null; });
    const v = vals.filter((x): x is number => x !== null && (!LOWER_BETTER.has(m) || x > 0));
    if (v.length < 2) return null;
    return LOWER_BETTER.has(m) ? Math.min(...v) : Math.max(...v);
  };
  const lines = useMemo(() => {
    const set = new Map<string, number>();
    fin.forEach((q, ci) => (q.data as Financials | undefined)?.rows.filter((r) => r.statement === st).forEach((r) => { if (!set.has(r.line_item)) set.set(r.line_item, ci * 1000 + set.size); }));
    return [...set.keys()];
  }, [fin, st]);

  return (
    <div className="cmp">
      <header className="cmp-head">
        <Link href={`/terminal${codes[0] ? `?code=${codes[0]}` : ""}`} className="cmp-back">← Terminal</Link>
        <h1>Compare</h1>
        <div className="cmp-chips">
          {codes.map((c, i) => <span key={c} className="cmp-chip" style={{ borderColor: COLORS[i], color: COLORS[i] }}>{c}<button onClick={() => go(codes.filter((x) => x !== c))} aria-label={`remove ${c}`}>×</button></span>)}
          {codes.length < 3 && (
            <form onSubmit={(e) => { e.preventDefault(); const c = draft.trim().toUpperCase(); if (c && !codes.includes(c)) go([...codes, c]); setDraft(""); }}>
              <input value={draft} onChange={(e) => setDraft(e.target.value)} placeholder="+ add symbol" spellCheck={false} />
            </form>
          )}
        </div>
        <span className="cmp-asof">{asOf === "NOW" ? "as of today" : `as it was on ${dmy(asOf)}`}</span>
      </header>
      {codes.length < 2 && <p className="cmp-empty">Add at least two symbols, for example <b>TCS</b>, <b>INFY</b>, <b>WIPRO</b>.</p>}
      {codes.length >= 2 && (
        <>
          <section>
            <div className="cmp-bar">
              <b>Price, rebased to 100 at the first day all have a price</b>
              <div className="cmp-btns">
                {[["1Y", 1], ["3Y", 3], ["5Y", 5], ["10Y", 10], ["MAX", null]].map(([l, y]) => <button key={l as string} className={range === y ? "on" : ""} onClick={() => setRange(y as number | null)}>{l}</button>)}
                <button className={log ? "on" : ""} onClick={() => setLog((v) => !v)}>Log</button>
              </div>
            </div>
            <Chart series={series} log={log} from={range === null ? null : years(range)} />
            <div className="cmp-legend">{codes.map((c, i) => <span key={c}><i style={{ background: COLORS[i] }} />{cos[i].data?.name ?? c}</span>)}</div>
          </section>
          <section>
            <table className="cmp-table">
              <thead><tr><th />{codes.map((c, i) => <th key={c} style={{ color: COLORS[i] }}>{c}<small>{cos[i].data?.name}</small></th>)}</tr></thead>
              <tbody>
                <tr><td>Sector · playbook</td>{codes.map((c, i) => <td key={c}>{cos[i].data?.sector ?? "n/a"} <small>{cos[i].data?.playbook?.label}</small></td>)}</tr>
                <tr><td>Last price</td>{codes.map((c, i) => <td key={c} className="mono">{cos[i].data?.last_price ? `₹${cos[i].data!.last_price!.close.toLocaleString("en-IN")}` : "n/a"}</td>)}</tr>
                {ROWS.map((m) => {
                  const b = best(m);
                  return (
                    <tr key={m}><td>{METRIC_LABEL[m] ?? m}</td>
                      {codes.map((c, i) => {
                        const r = cos[i].data?.metrics[m];
                        const ok = !!r && r.state === "value";
                        const rv = r as { value: number; unit: string };
                        return <td key={c} className={`mono ${ok && b !== null && rv.value === b ? "cmp-best" : ""}`}>{ok ? byUnit(rv.value, rv.unit) : <span className="v-muted" title={r ? ("reason" in r ? String(r.reason) : r.state) : ""}>n/a</span>}</td>;
                      })}
                    </tr>
                  );
                })}
                <tr className="cmp-sec"><td colSpan={codes.length + 1}>KASAUTI (sector-relative ranking, not advice)</td></tr>
                <tr><td>Score · confidence</td>{codes.map((c, i) => { const k = kas[i].data; return <td key={c} className="mono">{k?.available && k.score != null ? <><b>{k.score.toFixed(0)}</b> <small>{k.confidence != null ? `${Math.round(k.confidence * 100)}%` : ""} · {k.kind}</small></> : <span className="v-muted">not scored</span>}</td>; })}</tr>
                {["quality", "growth", "valuation", "balance", "ownership", "momentum"].map((p) => (
                  <tr key={p}><td className="cmp-sub">{p === "balance" ? "Balance sheet" : p[0].toUpperCase() + p.slice(1)} (percentile)</td>
                    {codes.map((c, i) => { const v = kas[i].data?.detail?.pillars[p]?.score; return <td key={c} className="mono">{v === undefined || v === null ? <span className="v-muted">n/a</span> : Math.round(v * 100)}</td>; })}
                  </tr>
                ))}
                <tr className="cmp-sec"><td colSpan={codes.length + 1}>Ownership (latest quarter)</td></tr>
                {[["promoter", "Promoter"], ["mutual_funds", "Mutual funds"], ["fpi", "Foreign portfolio"], ["insurance", "Insurance"], ["retail", "Retail"]].map(([k, l]) => (
                  <tr key={k}><td>{l}</td>{codes.map((c, i) => { const v = own[i].data?.quarters[0]?.[k]; return <td key={c} className="mono">{typeof v === "number" ? `${v.toFixed(2)}%` : <span className="v-muted">n/a</span>}</td>; })}</tr>
                ))}
              </tbody>
            </table>
          </section>
          <section>
            <div className="cmp-bar">
              <b>Statements, last {YEARS} financial years (₹ crore)</b>
              <div className="cmp-btns">{STATEMENTS.map(([k, l]) => <button key={k} className={st === k ? "on" : ""} onClick={() => setSt(k)}>{l}</button>)}</div>
            </div>
            <div className="cmp-scroll">
              <table className="cmp-table cmp-fin">
                <thead>
                  <tr><th rowSpan={2}>Line item</th>{codes.map((c, i) => <th key={c} colSpan={YEARS} style={{ color: COLORS[i] }}>{c}</th>)}</tr>
                  <tr>{codes.map((c) => ((fin[codes.indexOf(c)].data?.periods ?? []).slice(0, YEARS).reverse()).map((p) => <th key={c + p}>FY{p.slice(2, 4)}</th>))}</tr>
                </thead>
                <tbody>
                  {lines.map((li) => (
                    <tr key={li}><td>{LINE_LABEL(li)}</td>
                      {codes.map((c, i) => {
                        const d = fin[i].data;
                        const row = d?.rows.find((r) => r.line_item === li);
                        return (d?.periods ?? []).slice(0, YEARS).reverse().map((p) => {
                          const v = row?.cells[p]?.value;
                          return <td key={c + p} className="mono">{v === undefined ? <span className="v-muted">·</span> : li.startsWith("eps") || li === "face_value" ? v.toFixed(2) : (v / 1e7).toLocaleString("en-IN", { maximumFractionDigits: 0 })}</td>;
                        });
                      })}
                    </tr>
                  ))}
                  {!lines.length && <tr><td colSpan={1 + codes.length * YEARS} className="v-muted">No statements known for these companies at this date.</td></tr>}
                </tbody>
              </table>
            </div>
          </section>
          <p className="cmp-foot">Point-in-time data from exchange filings and prices; a research view, not advice. Sectors differ: compare like with like (a bank has no EBITDA).</p>
        </>
      )}
    </div>
  );
}
