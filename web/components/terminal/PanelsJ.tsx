"use client";

/* CALC — "if I had put money in on that date": value today (or on any later date), with splits and bonuses counted as extra shares and
   dividends ignored, kept as cash, or reinvested. History only: it uses what was known on the end date. No tax, brokerage or charges. */

import * as echarts from "echarts/core";
import { LineChart } from "echarts/charts";
import { GridComponent, LegendComponent, TooltipComponent } from "echarts/components";
import { CanvasRenderer } from "echarts/renderers";
import { useEffect, useMemo, useRef, useState } from "react";
import { useReturns } from "@/lib/api";
import { dmy, indianGroup, todayIST } from "@/lib/format";
import { useT } from "@/lib/store";
import { PanelState, Seg } from "./common";
import type { PanelProps } from "./PanelsA";

echarts.use([LineChart, GridComponent, LegendComponent, TooltipComponent, CanvasRenderer]);

const rs = (v: number) => `₹${indianGroup(v, v < 1000 ? 2 : 0)}`;
const pc = (v: number | null | undefined, d = 1) => (v === null || v === undefined ? "n/a" : `${v >= 0 ? "+" : "−"}${Math.abs(v * 100).toFixed(d)}%`);
const back = (years: number) => { const d = new Date(`${todayIST()}T00:00:00Z`); d.setUTCFullYear(d.getUTCFullYear() - years); return d.toISOString().slice(0, 10); };

export function CALC(_: PanelProps) {
  const code = useT((s) => s.code);
  const today = todayIST();
  const [start, setStart] = useState(back(5));
  const [end, setEnd] = useState("");
  const [amount, setAmount] = useState("100000");
  const [mode, setMode] = useState<"ignore" | "cash" | "reinvest">("cash");
  const [showDiv, setShowDiv] = useState(false);
  const amt = Math.max(1, Number(amount.replace(/,/g, "")) || 0);
  const q = useReturns(code, end || "NOW", { start, amount: amt, dividends: mode });
  const el = useRef<HTMLDivElement>(null);
  const d = q.data;
  const curve = useMemo(() => d?.curve ?? [], [d]);

  useEffect(() => {
    if (!el.current || curve.length < 2) return;
    const ch = echarts.init(el.current);
    ch.setOption({
      animationDuration: 500, grid: { left: 62, right: 14, top: 26, bottom: 24 },
      legend: { top: 0, left: 0, textStyle: { color: "#A7A9AE", fontSize: 11 }, itemWidth: 12, itemHeight: 3 },
      tooltip: { trigger: "axis", backgroundColor: "rgba(13,15,18,0.96)", borderColor: "#3A414C", textStyle: { color: "#E8E6E1", fontSize: 12 }, valueFormatter: (v: number) => rs(v) },
      xAxis: { type: "category", data: curve.map((p) => p.date), axisLabel: { color: "#6B7079", fontSize: 10 }, axisLine: { lineStyle: { color: "#262B33" } } },
      yAxis: { type: "value", scale: true, splitLine: { lineStyle: { color: "rgba(38,43,51,0.4)" } }, axisLabel: { color: "#6B7079", fontSize: 10, formatter: (v: number) => (v >= 1e5 ? `${(v / 1e5).toFixed(1)}L` : indianGroup(v)) } },
      series: [
        { name: "Value", type: "line", showSymbol: false, data: curve.map((p) => p.value), lineStyle: { color: "#D4AF37", width: 2 }, areaStyle: { color: "rgba(212,175,55,0.10)" } },
        { name: "Invested", type: "line", showSymbol: false, data: curve.map(() => d!.amount), lineStyle: { color: "#6B7079", width: 1, type: "dashed" } },
      ],
    });
    const ro = new ResizeObserver(() => ch.resize());
    ro.observe(el.current);
    return () => { ro.disconnect(); ch.dispose(); };
  }, [curve, d]);

  const up = (d?.return ?? 0) >= 0;
  return (
    <div className="t-panel calc">
      <div className="calc-form">
        <label>Invested on<input type="date" value={start} max={today} onChange={(e) => setStart(e.target.value)} /></label>
        <label>Amount (₹)<input inputMode="numeric" value={amount} onChange={(e) => setAmount(e.target.value)} /></label>
        <label>Until<input type="date" value={end} max={today} onChange={(e) => setEnd(e.target.value)} placeholder="today" /></label>
        <div className="calc-quick">{[["1Y", 1], ["3Y", 3], ["5Y", 5], ["10Y", 10], ["15Y", 15]].map(([l, y]) => <button key={l as string} onClick={() => setStart(back(y as number))}>{l}</button>)}{end && <button onClick={() => setEnd("")}>till today</button>}</div>
        <Seg value={mode} onChange={setMode} options={[{ v: "ignore", l: "Ignore dividends" }, { v: "cash", l: "Dividends as cash" }, { v: "reinvest", l: "Reinvest dividends" }]} />
      </div>
      <PanelState q={q}>
        {() => (
          <>
            <div className="calc-hero">
              <div>
                <div className="t-k">{rs(d!.amount)} on {dmy(d!.buy_date)} became</div>
                <b className={`mono calc-val ${up ? "pos" : "neg"}`}>{rs(d!.total_value)}</b>
                <div className="t-dim">on {dmy(d!.end_date)}</div>
              </div>
              <div className="calc-kpis">
                <div><span className="t-k">Total return</span><b className={`mono ${up ? "pos" : "neg"}`}>{pc(d!.return)}</b></div>
                <div><span className="t-k">Per year (CAGR)</span><b className={`mono ${up ? "pos" : "neg"}`}>{pc(d!.cagr)}</b></div>
                <div><span className="t-k">Gain</span><b className={`mono ${up ? "pos" : "neg"}`}>{up ? "+" : "−"}{rs(Math.abs(d!.gain))}</b></div>
                <div><span className="t-k">Worst fall on the way</span><b className="mono neg">{pc(d!.max_drawdown)}</b></div>
              </div>
            </div>
            <table className="t-table calc-tab">
              <tbody>
                <tr><td>Bought</td><td className="mono">{indianGroup(d!.shares_bought, 2)} shares at {rs(d!.buy_price_traded)} (the price that day)</td></tr>
                <tr><td>Now hold</td><td className="mono"><b>{indianGroup(d!.shares_at_end, 2)}</b> shares {d!.shares_at_end > d!.shares_bought * 1.0001 ? <span className="t-dim">· extra shares from splits, bonuses{mode === "reinvest" ? " and reinvested dividends" : ""}</span> : null} at {rs(d!.end_price_traded)}</td></tr>
                <tr><td>Value of the shares</td><td className="mono">{rs(d!.value_shares)}</td></tr>
                {mode === "cash" && <tr><td>Dividends kept as cash</td><td className="mono">{rs(d!.dividend_cash_kept)} <span className="t-dim">· {d!.dividends_received.length} payments, no interest</span></td></tr>}
                {mode === "reinvest" && <tr><td>Dividends reinvested</td><td className="mono">{rs(d!.dividends_total)} <span className="t-dim">· {d!.dividends_received.length} payments, bought back at that day&apos;s price</span></td></tr>}
                {mode === "ignore" && <tr><td>Dividends</td><td className="t-dim">ignored ({d!.dividends_ignored} would have been paid)</td></tr>}
                <tr><td>Price-only return</td><td className="mono">{pc(d!.return_price_only)} ({pc(d!.cagr_price_only)} a year): what the chart alone shows</td></tr>
              </tbody>
            </table>
            <div ref={el} className="calc-chart" />
            {d!.events.length > 0 && (
              <div className="calc-ev">
                <span className="t-k">Splits and bonuses on the way</span>
                {d!.events.map((e) => <span key={e.date} className="calc-chip">{dmy(e.date)} · shares ×{e.share_multiplier.toFixed(2)}{e.kind ? ` (${e.kind.replace("_", " ")})` : ""}</span>)}
              </div>
            )}
            {d!.dividends_received.length > 0 && (
              <div>
                <button className="t-link" onClick={() => setShowDiv((v) => !v)}>{showDiv ? "hide" : "show"} the {d!.dividends_received.length} dividends</button>
                {showDiv && (
                  <table className="t-table calc-tab">
                    <thead><tr><th>Ex-date</th><th>Per share</th><th>Shares held</th><th>Received</th></tr></thead>
                    <tbody>{d!.dividends_received.map((x) => <tr key={x.date + x.per_share}><td className="mono">{dmy(x.date)}</td><td className="mono">{rs(x.per_share)}</td><td className="mono">{indianGroup(x.shares, 2)}</td><td className="mono">{rs(x.cash)}</td></tr>)}</tbody>
                  </table>
                )}
              </div>
            )}
            <div className="t-foot">{d!.notes.join(" · ")}</div>
          </>
        )}
      </PanelState>
    </div>
  );
}
