"use client";

/* SEG — reportable segments as the company files them (exchange XBRL, Ind AS results). Labels are the company's own words;
   revenue is external revenue, result is profit before tax and finance cost. Nothing is estimated or allocated by us. */

import * as echarts from "echarts/core";
import { BarChart } from "echarts/charts";
import { GridComponent, LegendComponent, TooltipComponent } from "echarts/components";
import { CanvasRenderer } from "echarts/renderers";
import { useEffect, useMemo, useRef, useState } from "react";
import { useSegments } from "@/lib/api";
import { crore, dmy } from "@/lib/format";
import { useT } from "@/lib/store";
import { PanelState, Seg, usePanelAsOf } from "./common";
import type { PanelProps } from "./PanelsA";

echarts.use([BarChart, GridComponent, LegendComponent, TooltipComponent, CanvasRenderer]);

const PALETTE = ["#D4AF37", "#2EC4B6", "#7AA2F7", "#B48EF0", "#F0577A", "#E9A23B", "#8FB996", "#A7A9AE"];
const pct = (x: number | null | undefined) => (x === null || x === undefined ? "n/a" : `${(x * 100).toFixed(1)}%`);

export function SEG({ params }: PanelProps) {
  const code = useT((s) => s.code);
  const asOf = usePanelAsOf(params.pin);
  const [period, setPeriod] = useState<"FY" | "Q">("FY");
  const q = useSegments(code, asOf, { period });
  const el = useRef<HTMLDivElement>(null);
  const periods = useMemo(() => [...(q.data?.periods ?? [])].reverse(), [q.data]);
  const labels = useMemo(() => {
    const tot = new Map<string, number>();
    for (const p of periods) for (const s of p.segments) tot.set(s.label, (tot.get(s.label) ?? 0) + (s.revenue ?? 0));
    return [...tot.entries()].sort((a, b) => b[1] - a[1]).map(([l]) => l);
  }, [periods]);

  useEffect(() => {
    if (!el.current || !periods.length) return;
    const ch = echarts.init(el.current);
    ch.setOption({
      animationDuration: 600,
      grid: { left: 54, right: 10, top: 34, bottom: 24 },
      legend: { top: 0, left: 0, type: "scroll", textStyle: { color: "#A7A9AE", fontSize: 11 }, itemWidth: 10, itemHeight: 8 },
      tooltip: { trigger: "axis", backgroundColor: "rgba(13,15,18,0.96)", borderColor: "#3A414C", textStyle: { color: "#E8E6E1", fontSize: 12 },
        valueFormatter: (v: number | null) => (v === null || v === undefined ? "n/a" : crore(v)) },
      xAxis: { type: "category", data: periods.map((p) => p.period_end.slice(0, 7)), axisLine: { lineStyle: { color: "#262B33" } },
        axisLabel: { color: "#6B7079", fontSize: 10, fontFamily: "JetBrains Mono" } },
      yAxis: { type: "value", splitLine: { lineStyle: { color: "rgba(38,43,51,0.4)" } },
        axisLabel: { color: "#6B7079", fontSize: 10, formatter: (v: number) => `${Math.round(v / 1e7).toLocaleString("en-IN")}` } },
      series: labels.map((l, i) => ({
        name: l, type: "bar" as const, stack: "rev", barWidth: "56%", itemStyle: { color: PALETTE[i % PALETTE.length] },
        data: periods.map((p) => p.segments.find((s) => s.label === l)?.revenue ?? null),
      })),
    });
    const ro = new ResizeObserver(() => ch.resize());
    ro.observe(el.current);
    return () => { ro.disconnect(); ch.dispose(); };
  }, [periods, labels]);

  const latest = q.data?.periods[0];
  return (
    <div className="t-panel seg">
      <div className="t-toolbar">
        <Seg value={period} onChange={setPeriod} options={[{ v: "FY", l: "Annual" }, { v: "Q", l: "Quarterly" }]} />
        {latest && <span className="t-dim">{latest.basis} · period ending {dmy(latest.period_end)} · public {dmy(latest.known_at)}</span>}
      </div>
      <PanelState q={q} empty={q.data && !q.data.periods.length ? "No segment disclosure known at this as-of (single-segment company, a bank/insurer, or a filing before Ind AS XBRL, about FY2019)." : undefined}>
        {() => (
          <>
            <div ref={el} className="seg-chart" />
            <table className="t-table seg-tab">
              <thead><tr><th>Segment</th><th>Revenue</th><th>Share</th><th>Result</th><th>Margin</th><th>Assets</th></tr></thead>
              <tbody>
                {latest!.segments.map((s) => (
                  <tr key={s.label}>
                    <td>{s.label}</td>
                    <td className="mono">{s.revenue === undefined ? "n/a" : crore(s.revenue)}</td>
                    <td className="mono">{pct(s.share)}</td>
                    <td className={`mono ${s.result === undefined ? "" : s.result >= 0 ? "pos" : "neg"}`}>{s.result === undefined ? "n/a" : crore(s.result)}</td>
                    <td className={`mono ${s.margin === null || s.margin === undefined ? "" : s.margin >= 0 ? "pos" : "neg"}`}>{pct(s.margin)}</td>
                    <td className="mono">{s.assets === undefined ? "n/a" : crore(s.assets)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
            <div className="t-foot">{q.data!.note}</div>
          </>
        )}
      </PanelState>
    </div>
  );
}
