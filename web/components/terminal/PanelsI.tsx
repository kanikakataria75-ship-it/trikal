"use client";

/* CALL — what management said on earnings calls, and whether it held.
   Statements are read by rules from the transcripts the company filed with the exchange (no model); each shows its sentence, call and page.
   A verdict compares the statement with the company's own later results and uses only what was public at the as-of date. */

import * as echarts from "echarts/core";
import { LineChart } from "echarts/charts";
import { GridComponent, LegendComponent, TooltipComponent } from "echarts/components";
import { CanvasRenderer } from "echarts/renderers";
import { useEffect, useRef, useState } from "react";
import { useConcalls, type CallPromise } from "@/lib/api";
import { dmy } from "@/lib/format";
import { useT } from "@/lib/store";
import { PanelState, usePanelAsOf } from "./common";
import type { PanelProps } from "./PanelsA";

echarts.use([LineChart, GridComponent, LegendComponent, TooltipComponent, CanvasRenderer]);

const METRIC: Record<string, string> = { revenue_growth: "Revenue growth", ebitda_margin: "EBITDA margin", ebit_margin: "EBIT / operating margin", margin_generic: "Margin (unspecified)", revenue_growth_cc: "Revenue growth (constant currency / business)", profit_growth: "Profit growth", capex: "Capex / investment",
  volume_growth: "Volume", return_ratio: "Return ratio", debt: "Debt" };
const VERDICT: Record<string, string> = { delivered: "kept", partially: "partly", missed: "missed", pending: "pending", "not judged": "not judged", "no data": "no data" };
const cls = (v: string) => (v === "delivered" ? "pos" : v === "missed" ? "neg" : v === "partially" ? "warn" : "t-dim");
const target = (p: CallPromise) =>
  p.op === "range" ? `${p.low}–${p.high}%` : p.op === "at_least" ? `≥ ${p.low}%` : p.op === "at_most" ? `≤ ${p.high}%` : `≈ ${p.low}%`;

export function CALL({ params }: PanelProps) {
  const code = useT((s) => s.code);
  const asOf = usePanelAsOf(params.pin);
  const q = useConcalls(code, asOf);
  const el = useRef<HTMLDivElement>(null);
  const [all, setAll] = useState(false);
  const tone = q.data?.tone ?? [];
  useEffect(() => {
    if (!el.current || tone.length < 2) return;
    const ch = echarts.init(el.current);
    ch.setOption({
      animationDuration: 500, grid: { left: 40, right: 44, top: 28, bottom: 24 },
      legend: { top: 0, left: 0, textStyle: { color: "#A7A9AE", fontSize: 11 }, itemWidth: 12, itemHeight: 3 },
      tooltip: { trigger: "axis", backgroundColor: "rgba(13,15,18,0.96)", borderColor: "#3A414C", textStyle: { color: "#E8E6E1", fontSize: 12 } },
      xAxis: { type: "category", data: tone.map((t) => String(t.period_end).slice(0, 7)), axisLabel: { color: "#6B7079", fontSize: 10 }, axisLine: { lineStyle: { color: "#262B33" } } },
      yAxis: [
        { type: "value", name: "net tone", nameTextStyle: { color: "#6B7079", fontSize: 9 }, splitLine: { lineStyle: { color: "rgba(38,43,51,0.4)" } }, axisLabel: { color: "#6B7079", fontSize: 10 } },
        { type: "value", name: "hedging /1000 words", nameTextStyle: { color: "#6B7079", fontSize: 9 }, splitLine: { show: false }, axisLabel: { color: "#6B7079", fontSize: 10 } },
      ],
      series: [
        { name: "Net tone (positive − negative)", type: "line", smooth: true, data: tone.map((t) => t.net_tone), itemStyle: { color: "#D4AF37" }, lineStyle: { width: 2 } },
        { name: "Hedging", type: "line", yAxisIndex: 1, smooth: true, data: tone.map((t) => t.hedge_rate), itemStyle: { color: "#B48EF0" }, lineStyle: { width: 1.5, type: "dashed" } },
      ],
    });
    const ro = new ResizeObserver(() => ch.resize());
    ro.observe(el.current);
    return () => { ro.disconnect(); ch.dispose(); };
  }, [tone]);

  const d = q.data;
  const shown = (d?.promises ?? []).filter((p) => all || ["delivered", "partially", "missed", "pending"].includes(p.verdict));
  const last = tone[tone.length - 1];
  return (
    <div className="t-panel call">
      <PanelState q={q} empty={d && d.calls === 0 ? "No earnings-call transcript known at this as-of (transcripts are filed with the exchange; the download covers the last few years of Nifty 500 companies)." : undefined}>
        {() => (
          <>
            <div className="call-head">
              <div>
                <div className="t-k">Management credibility</div>
                <b className="mono call-score">{d!.credibility.score === null ? "n/a" : `${Math.round(d!.credibility.score * 100)}%`}</b>
              </div>
              <div className="call-meta">
                {d!.credibility.judged} statements judged ({d!.credibility.delivered} kept · {d!.credibility.partially} partly · {d!.credibility.missed} missed), {d!.credibility.pending} pending.
                {d!.credibility.score === null && ` A score needs ${d!.credibility.needs} judged statements.`}
                <div className="t-dim">{d!.calls} calls read. Only statements with a number, a metric and a year are scored.</div>
              </div>
            </div>
            <div className="t-toolbar"><label className="t-dim"><input type="checkbox" checked={all} onChange={(e) => setAll(e.target.checked)} /> also show statements that are not judged</label></div>
            <table className="t-table call-tab">
              <thead><tr><th>Call</th><th>Statement</th><th>Said</th><th>Year</th><th>Result</th><th /></tr></thead>
              <tbody>
                {shown.slice(0, 60).map((p, i) => (
                  <tr key={i} title={p.why ?? ""}>
                    <td className="mono">{String(p.call_period_end).slice(0, 7)}</td>
                    <td><div className="call-q">{p.quote.length > 210 ? `${p.quote.slice(0, 210)}…` : p.quote}</div><div className="t-dim">{METRIC[p.metric] ?? p.metric} · page {p.page}</div></td>
                    <td className="mono">{target(p)}</td>
                    <td className="mono">{p.horizon_end ? `FY${String(p.horizon_end).slice(2, 4)}` : "—"}</td>
                    <td className={`mono ${cls(p.verdict)}`}>{p.actual === null ? "—" : `${p.actual.toFixed(1)}%`}</td>
                    <td className={cls(p.verdict)}><b>{VERDICT[p.verdict] ?? p.verdict}</b></td>
                  </tr>
                ))}
                {shown.length === 0 && <tr><td colSpan={6} className="t-dim">No numeric statement found in the calls read so far (many companies give no numeric guidance).</td></tr>}
              </tbody>
            </table>
            {tone.length >= 2 && <div ref={el} className="call-chart" />}
            {last && (
              <div className="t-foot">
                Latest call ({dmy(String(last.announced_at).slice(0, 10))}): net tone {last.net_tone === null ? "n/a" : last.net_tone.toFixed(2)}
                {last.net_tone_vs_avg4 !== null && ` (${last.net_tone_vs_avg4 >= 0 ? "+" : "−"}${Math.abs(last.net_tone_vs_avg4).toFixed(2)} vs its previous four calls)`}, hedging {last.hedge_rate === null ? "n/a" : last.hedge_rate.toFixed(1)} per 1,000 words
                {last.hedge_rate_vs_avg4 !== null && ` (${last.hedge_rate_vs_avg4 >= 0 ? "+" : "−"}${Math.abs(last.hedge_rate_vs_avg4).toFixed(1)})`}, {last.evasive_count} answers deflected.
              </div>
            )}
            {d!.examples?.evasive && d!.examples.evasive.length > 0 && (
              <ul className="kas-drop">{d!.examples.evasive.map((x, i) => <li key={i}>“{x}”</li>)}</ul>
            )}
            <div className="t-foot">{d!.note}</div>
          </>
        )}
      </PanelState>
    </div>
  );
}
