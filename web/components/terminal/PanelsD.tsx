"use client";

/* MACRO — the macro desk. Every tile is the last value KNOWN at the as-of (not the last value that exists),
   with its year-ago value and how its release time is known (source vintage, or ≈ an imputed rule). */

import { useEffect, useMemo, useRef, useState } from "react";
import * as echarts from "echarts/core";
import { LineChart } from "echarts/charts";
import { DataZoomComponent, GridComponent, TooltipComponent } from "echarts/components";
import { CanvasRenderer } from "echarts/renderers";
import { useMacro, useMacroSeries, type MacroSeries } from "@/lib/api";
import { dmy, dmyTime } from "@/lib/format";
import { PanelState, usePanelAsOf } from "./common";
import type { PanelProps } from "./PanelsA";

echarts.use([LineChart, GridComponent, TooltipComponent, DataZoomComponent, CanvasRenderer]);

const CATEGORY: [string, string][] = [
  ["fx", "Currency"], ["india_rates", "India rates"], ["inflation", "Inflation"], ["commodities", "Commodities"],
  ["global_rates", "Global rates"], ["global_markets", "Global risk"],
];

const fmt = (v: number, unit: string) => {
  const d = Math.abs(v) >= 1000 ? 0 : Math.abs(v) >= 100 ? 1 : 2;
  return `${v.toLocaleString("en-IN", { maximumFractionDigits: d, minimumFractionDigits: d })}${unit === "percent" ? "%" : ""}`;
};

function change(s: MacroSeries) {
  const l = s.latest;
  if (!l || l.year_ago === null || l.year_ago === undefined) return null;
  if (s.unit === "percent") return { txt: `${l.value - l.year_ago >= 0 ? "+" : "−"}${Math.abs((l.value - l.year_ago) * 100).toFixed(0)} bp y/y`, up: l.value >= l.year_ago };
  const c = l.value / l.year_ago - 1;
  return { txt: `${c >= 0 ? "+" : "−"}${Math.abs(c * 100).toFixed(1)}% y/y`, up: c >= 0 };
}

function SeriesChart({ id, asOf }: { id: string; asOf: string }) {
  const q = useMacroSeries(id, asOf);
  const el = useRef<HTMLDivElement>(null);
  useEffect(() => {
    const d = q.data;
    if (!el.current || !d || !d.obs.length) return;
    const ch = echarts.init(el.current);
    const imputed = d.obs.some((o) => o.precision === "imputed");
    ch.setOption({
      animationDuration: 600,
      grid: { left: 56, right: 18, top: 16, bottom: 52 },
      tooltip: {
        trigger: "axis", backgroundColor: "rgba(13,15,18,0.96)", borderColor: "#3A414C", textStyle: { color: "#E8E6E1", fontSize: 12 },
        formatter: (ps: { dataIndex: number }[]) => {
          const o = d.obs[ps[0].dataIndex];
          return `${dmy(o.period_end)}<br/><b>${fmt(o.value, d.series.unit)}</b> ${d.series.unit === "percent" ? "" : d.series.unit}<br/><span style="color:#6B7079">known ${o.precision === "imputed" ? "≈ " : ""}${dmyTime(o.known_at)}</span>`;
        },
      },
      xAxis: { type: "category", data: d.obs.map((o) => o.period_end), axisLine: { lineStyle: { color: "#262B33" } }, axisLabel: { color: "#6B7079", fontSize: 10, fontFamily: "JetBrains Mono" } },
      yAxis: { type: "value", scale: true, splitLine: { lineStyle: { color: "rgba(38,43,51,0.45)" } }, axisLabel: { color: "#6B7079", fontSize: 10 } },
      dataZoom: [{ type: "inside", start: 70, end: 100 }, { type: "slider", start: 70, end: 100, height: 18, bottom: 10, borderColor: "#262B33", fillerColor: "rgba(212,175,55,0.12)", handleStyle: { color: "#D4AF37" }, textStyle: { color: "#6B7079" } }],
      series: [{ type: "line", data: d.obs.map((o) => o.value), showSymbol: false, lineStyle: { color: "#D4AF37", width: 1.6 },
        areaStyle: { color: new echarts.graphic.LinearGradient(0, 0, 0, 1, [{ offset: 0, color: "rgba(212,175,55,0.22)" }, { offset: 1, color: "rgba(212,175,55,0)" }]) } }],
    });
    const ro = new ResizeObserver(() => ch.resize());
    ro.observe(el.current);
    return () => { ro.disconnect(); ch.dispose(); };
  }, [q.data]);
  const s = q.data?.series;
  return (
    <div className="mc-chart">
      {s && (
        <div className="mc-head">
          <b>{s.name}</b>
          <span>{s.unit} · {s.freq === "D" ? "daily" : "monthly"} · {JSON.parse(s.source).kind === "fred" ? `FRED ${JSON.parse(s.source).id}` : JSON.parse(s.source).kind === "pinksheet" ? "World Bank Pink Sheet" : "MOSPI"}</span>
          <i>{(() => { const k = JSON.parse(s.known_rule); return k.lag_days ? `release ≈ period end + ${k.lag_days} days` : k.release_day ? `release ≈ ${k.release_day}th of next month` : "source vintages"; })()}</i>
        </div>
      )}
      <div ref={el} className="mc-canvas" />
      {s?.note && <div className="t-foot">{s.note}</div>}
    </div>
  );
}

export function MACRO({ params }: PanelProps) {
  const asOf = usePanelAsOf(params.pin);
  const q = useMacro(asOf);
  const [sel, setSel] = useState("usdinr");
  const groups = useMemo(() => CATEGORY.map(([k, l]) => [l, (q.data?.series ?? []).filter((s) => s.category === k)] as const), [q.data]);
  return (
    <div className="t-panel macro">
      <PanelState q={q}>
        {() => (
          <div className="mc">
            <div className="mc-tiles">
              {groups.map(([label, list]) => list.length > 0 && (
                <div key={label} className="mc-group">
                  <div className="t-k">{label}</div>
                  <div className="mc-grid">
                    {list.map((s) => {
                      const c = change(s);
                      const l = s.latest;
                      return (
                        <button key={s.series_id} className={`mc-tile ${sel === s.series_id ? "on" : ""}`} onClick={() => setSel(s.series_id)}>
                          <span className="mc-name">{s.name}</span>
                          {l ? (
                            <>
                              <b className="mono">{fmt(l.value, s.unit)}</b>
                              <span className={`mc-chg mono ${c ? (c.up ? "pos" : "neg") : ""}`}>{c?.txt ?? ""}</span>
                              <i className="mono">{s.freq === "M" ? dmy(l.period_end).slice(3) : dmy(l.period_end)}{l.precision === "imputed" ? " ≈" : ""}</i>
                            </>
                          ) : <span className="v v-muted">n/a — nothing published yet</span>}
                        </button>
                      );
                    })}
                  </div>
                </div>
              ))}
            </div>
            <SeriesChart id={sel} asOf={asOf} />
          </div>
        )}
      </PanelState>
    </div>
  );
}
