"use client";

/* KAS — KASAUTI: a sector-relative ranking and the report card that audits it.
   The number is a percentile blend among the company's own playbook peers, never an absolute grade. What was left out is shown as
   prominently as what was used, and the report card is labelled in-sample until a frozen version has a live record. */

import * as echarts from "echarts/core";
import { BarChart } from "echarts/charts";
import { GridComponent, TooltipComponent } from "echarts/components";
import { CanvasRenderer } from "echarts/renderers";
import { useEffect, useRef, useState } from "react";
import { useKasauti, useKasautiReport, type KasHorizon } from "@/lib/api";
import { dmy } from "@/lib/format";
import { useT } from "@/lib/store";
import { PanelState, Seg, usePanelAsOf } from "./common";
import type { PanelProps } from "./PanelsA";
import { ScoreHistory } from "./PanelsN";

echarts.use([BarChart, GridComponent, TooltipComponent, CanvasRenderer]);

const PILLAR = { quality: "Quality", growth: "Growth", valuation: "Valuation", balance: "Balance sheet", ownership: "Ownership flow", momentum: "Momentum", earnings_quality: "Earnings quality", credibility: "Mgmt credibility" } as Record<string, string>;
const METRIC = { roce: "ROCE", roe: "ROE", roa: "ROA", ebitda_margin: "EBITDA margin", net_margin: "Net margin", revenue_growth: "Revenue growth", profit_growth: "Profit growth",
  ev_ebitda: "EV/EBITDA", pe: "P/E", pb: "P/B", fcf_yield: "FCF yield", net_debt_ebitda: "Net debt/EBITDA", debt_to_equity: "Debt/equity", interest_coverage: "Interest cover",
  altman_z: "Altman Z", promoter_change_4q: "Promoter Δ 1y", institution_change_4q: "Institutions Δ 1y", pledge_pct: "Pledge %", momentum_12_1: "Momentum 12-1m", momentum_6: "Momentum 6m",
  cost_to_income: "Cost/income", cfo_to_profit: "Cash flow / profit", accruals_ratio: "Accruals / assets", other_income_share: "Other income / PBT", promise_kept: "Promises kept", gnpa_pct: "Gross NPA", nnpa_pct: "Net NPA", cet1: "CET1", credit_cost: "Credit cost", leverage_assets_to_equity: "Assets/equity" } as Record<string, string>;
const pctFmt = (x: number | null | undefined, d = 1) => (x === null || x === undefined ? "n/a" : `${x >= 0 ? "+" : "−"}${Math.abs(x * 100).toFixed(d)}%`);
const num = (x: number | null | undefined) => (x === null || x === undefined ? "n/a" : Math.abs(x) >= 100 ? x.toFixed(0) : Math.abs(x) >= 10 ? x.toFixed(1) : x.toFixed(2));
const tone = (p: number | null | undefined) => (p === null || p === undefined ? "" : p >= 0.66 ? "pos" : p <= 0.33 ? "neg" : "");

function Bar({ v }: { v: number | null | undefined }) {
  return <span className="kas-bar"><i style={{ width: `${Math.round((v ?? 0) * 100)}%` }} className={tone(v)} /></span>;
}

function Deciles({ h }: { h: KasHorizon }) {
  const el = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (!el.current || !h.decile_mean_return) return;
    const ch = echarts.init(el.current);
    const ks = Array.from({ length: 10 }, (_, i) => String(i + 1));
    ch.setOption({
      animationDuration: 500, grid: { left: 40, right: 8, top: 14, bottom: 22 },
      tooltip: { trigger: "axis", backgroundColor: "rgba(13,15,18,0.96)", borderColor: "#3A414C", textStyle: { color: "#E8E6E1", fontSize: 12 }, valueFormatter: (v: number) => pctFmt(v) },
      xAxis: { type: "category", data: ks, axisLabel: { color: "#6B7079", fontSize: 10 }, axisLine: { lineStyle: { color: "#262B33" } } },
      yAxis: { type: "value", splitLine: { lineStyle: { color: "rgba(38,43,51,0.4)" } }, axisLabel: { color: "#6B7079", fontSize: 10, formatter: (v: number) => `${(v * 100).toFixed(0)}%` } },
      series: [{ type: "bar", barWidth: "60%", data: ks.map((k) => ({ value: h.decile_mean_return![k], itemStyle: { color: (h.decile_mean_return![k] ?? 0) >= 0 ? "#2EC4B6" : "#F0577A" } })) }],
    });
    const ro = new ResizeObserver(() => ch.resize());
    ro.observe(el.current);
    return () => { ro.disconnect(); ch.dispose(); };
  }, [h]);
  return <div ref={el} className="kas-dec" />;
}

export function KAS({ params }: PanelProps) {
  const code = useT((s) => s.code);
  const asOf = usePanelAsOf(params.pin);
  const [ver, setVer] = useState(1);
  const q = useKasauti(code, asOf, { version: ver });
  const rep = useKasautiReport(asOf, ver);
  const [hz, setHz] = useState("3");
  const d = q.data;
  const det = d?.detail;
  const horizons = rep.data?.report?.horizons ?? {};
  const h = horizons[hz];
  return (
    <div className="t-panel kas">
      <div className="kas-ver"><Seg value={String(ver)} onChange={(v) => setVer(Number(v))} options={[{ v: "1", l: "v1 · frozen" }, { v: "2", l: "v2 · draft" }]} />
        {ver === 2 && <span className="t-dim">adds earnings quality and management credibility; v1 stays the frozen reference</span>}</div>
      <PanelState q={q}>
        {() => (
          !d!.available ? <div className="t-empty"><b>Not scored</b><span>{d!.reason}</span></div> : (
            <>
              <div className="kas-head">
                <div className="kas-score">
                  <b className="mono">{d!.score === null || d!.score === undefined ? "n/a" : d!.score.toFixed(0)}</b><span>/ 100</span>
                </div>
                <div className="kas-meta">
                  <div><span className={`kas-kind ${d!.kind === "live record" ? "live" : ""}`}>{d!.kind}</span> scored {dmy(d!.scoring_date)} · v{d!.version}{d!.frozen ? " · frozen" : " · draft"}</div>
                  <div className="t-dim">peers: {d!.peer_group}{det?.peer_fallback ? " (parent group: too few direct peers)" : ""} · {d!.n_peers} companies · confidence {d!.confidence === null || d!.confidence === undefined ? "n/a" : `${Math.round(d!.confidence * 100)}%`}</div>
                  <div className="t-dim">{d!.kind_note}</div>
                  {d!.status !== "ok" && <div className="neg">{d!.status}</div>}
                </div>
              </div>
              <ScoreHistory code={code} asOf={asOf} version={ver} />
              {det && (
                <div className="kas-grid">
                  <div>
                    <div className="t-k">Pillars (percentile among peers)</div>
                    {Object.entries(det.pillars).map(([k, p]) => (
                      <div key={k} className="kas-row" title={`data coverage ${Math.round(p.coverage * 100)}%`}>
                        <span>{PILLAR[k] ?? k}</span><Bar v={p.score} /><b className={`mono ${tone(p.score)}`}>{p.score === null ? "n/a" : Math.round(p.score * 100)}</b>
                        <i className="t-dim mono">{Math.round(p.coverage * 100)}%</i>
                      </div>
                    ))}
                    <div className="t-k" style={{ marginTop: 10 }}>Left out, and why</div>
                    <ul className="kas-drop">
                      {Object.entries(det.dropped).map(([k, why]) => <li key={k}><b>{PILLAR[k] ?? k}</b> {why}</li>)}
                      {Object.entries(det.skipped).map(([k, why]) => <li key={k}><b>{METRIC[k] ?? k}</b> {why}</li>)}
                    </ul>
                  </div>
                  <div>
                    <div className="t-k">What moved it most</div>
                    <table className="t-table">
                      <tbody>
                        {det.drivers.map((x) => (
                          <tr key={x.metric}><td>{METRIC[x.metric] ?? x.metric} <span className="t-dim">· {PILLAR[x.pillar] ?? x.pillar}</span></td>
                            <td className="mono">{num(x.value)}</td><td className="mono">p{Math.round(x.percentile * 100)}</td>
                            <td className={`mono ${x.points >= 0 ? "pos" : "neg"}`}>{x.points >= 0 ? "+" : "−"}{Math.abs(x.points).toFixed(1)}</td></tr>
                        ))}
                      </tbody>
                    </table>
                    <div className="t-k" style={{ marginTop: 10 }}>All inputs</div>
                    <table className="t-table kas-all">
                      <tbody>
                        {Object.entries(det.pillars).flatMap(([k, p]) => Object.entries(p.metrics).map(([m, x]) => (
                          <tr key={`${k}.${m}`} className={x.percentile === null ? "dim" : ""}>
                            <td>{METRIC[m] ?? m}</td><td className="mono">{num(x.value)}</td>
                            <td className={`mono ${tone(x.percentile)}`}>{x.percentile === null ? "n/a" : `p${Math.round(x.percentile * 100)}`}</td></tr>
                        )))}
                      </tbody>
                    </table>
                  </div>
                </div>
              )}
              <div className="t-foot">{d!.note}</div>
            </>
          )
        )}
      </PanelState>
      <div className="kas-card">
        <div className="t-k">Report card · does the ranking predict returns?</div>
        {!rep.data?.available ? <div className="t-dim">{rep.data?.reason ?? "…"}</div> : (
          <>
            <div className="kas-warn">
              In-sample backtest: {rep.data.report!.label}.{" "}
              {rep.data.frozen ? `Version ${rep.data.frozen.version} was frozen on ${dmy(rep.data.frozen.frozen_at.slice(0, 10))}: scores computed after that date form the live record (none long enough yet to judge).` : "Not frozen yet."}
            </div>
            <Seg value={hz} onChange={setHz} options={Object.keys(horizons).map((k) => ({ v: k, l: `${k}m` }))} />
            {h && h.dates > 0 ? (
              <div className="kas-rc">
                <div>
                  <table className="t-table">
                    <tbody>
                      <tr><td>Scoring dates</td><td className="mono">{h.dates}</td></tr>
                      <tr><td>Rank IC (mean)</td><td className="mono">{h.ic_mean === null || h.ic_mean === undefined ? "n/a" : h.ic_mean.toFixed(3)}</td></tr>
                      <tr><td>IC t-stat (Newey-West)</td><td className="mono">{h.ic_t_newey_west === null || h.ic_t_newey_west === undefined ? "n/a" : h.ic_t_newey_west.toFixed(2)}</td></tr>
                      <tr><td>IC positive on</td><td className="mono">{h.ic_positive_share === null || h.ic_positive_share === undefined ? "n/a" : `${Math.round(h.ic_positive_share * 100)}% of dates`}</td></tr>
                      <tr><td>Top decile − universe</td><td className={`mono ${(h.top_minus_universe ?? 0) >= 0 ? "pos" : "neg"}`}>{pctFmt(h.top_minus_universe)}</td></tr>
                      <tr><td>Decile 10 − decile 1</td><td className={`mono ${(h.d10_minus_d1 ?? 0) >= 0 ? "pos" : "neg"}`}>{pctFmt(h.d10_minus_d1)}</td></tr>
                      <tr><td>Top decile beat the universe</td><td className="mono">{h.hit_rate_top_beats_universe === undefined ? "n/a" : `${Math.round(h.hit_rate_top_beats_universe * 100)}% of dates`}</td></tr>
                    </tbody>
                  </table>
                </div>
                <Deciles h={h} />
              </div>
            ) : <div className="t-dim">Not enough dates for this horizon.</div>}
            {rep.data.report!.portfolio.periods > 0 && (() => {
              const p = rep.data.report!.portfolio;
              return (
                <div className="t-foot mono">
                  Top-decile portfolio, quarterly, costs {((p.cost_per_side ?? 0) * 100).toFixed(2)}%/side: {pctFmt(p.cagr_net)} a year vs {pctFmt(p.cagr_benchmark)} for the equal-weight universe ·
                  max drawdown {pctFmt(p.max_drawdown)} vs {pctFmt(p.max_drawdown_benchmark)} · turnover {pctFmt(p.avg_turnover, 0)} a quarter · {p.periods} periods
                </div>
              );
            })()}
            <div className="t-foot">Price returns on split/bonus-adjusted prices (dividends excluded); entry at the next session&apos;s open; benchmark = equal-weight Nifty 500 members. A null result is a valid result.</div>
          </>
        )}
      </div>
    </div>
  );
}
