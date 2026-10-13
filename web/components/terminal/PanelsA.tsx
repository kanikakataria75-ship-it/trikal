"use client";

/* DES · GP · EVT · HELP */

import dynamic from "next/dynamic";
import { useEffect, useMemo, useRef, useState } from "react";
import { AreaSeries, CandlestickSeries, ColorType, CrosshairMode, HistogramSeries, PriceScaleMode, createChart, createSeriesMarkers, type IChartApi, type UTCTimestamp } from "lightweight-charts";
import { useCompany, useLive, usePrices, useTimeline, type Streak } from "@/lib/api";
import { dmy, dmyTime, indianGroup, METRIC_LABEL } from "@/lib/format";
import { FUNCTIONS } from "@/lib/commands";
import { useT, workspace, type FnCode } from "@/lib/store";
import { LockIcon, Value } from "@/components/ui/Value";
import { Chip, PanelState, Seg, usePanelAsOf } from "./common";
import type { TipReadout } from "@/components/three/Touchstone";

const Touchstone = dynamic(() => import("@/components/three/Touchstone"), { ssr: false });

export type PanelProps = { params: { pin?: string } };

/* 2D twin of the touchstone (PRO mode): the same adjusted-close history as a plain log-scale line. */
function Spark({ t, c }: { t: string[]; c: number[] }) {
  const W = 300, H = 120, pad = 6;
  const lg = c.map((v) => Math.log(Math.max(v, 1e-6)));
  const lo = Math.min(...lg), hi = Math.max(...lg);
  const X = (i: number) => pad + (i / Math.max(1, c.length - 1)) * (W - 2 * pad);
  const Y = (v: number) => H - pad - ((v - lo) / Math.max(1e-9, hi - lo)) * (H - 2 * pad - 10);
  const d = lg.map((v, i) => (i ? "L" : "M") + X(i).toFixed(1) + "," + Y(v).toFixed(1)).join("");
  return (
    <svg viewBox={`0 0 ${W} ${H}`} width="100%" height="100%" preserveAspectRatio="none" className="spark">
      <path d={d} fill="none" stroke="var(--gold-1)" strokeWidth={1.2} vectorEffect="non-scaling-stroke" />
      <circle cx={X(c.length - 1)} cy={Y(lg[lg.length - 1])} r={2.5} fill="var(--gold-0)" />
      <text x={pad} y={10} fontSize={8} fill="#6B7079">{t[0].slice(0, 4)}</text>
      <text x={W - pad} y={10} fontSize={8} fill="#6B7079" textAnchor="end">{t[t.length - 1].slice(0, 4)}</text>
    </svg>
  );
}

/* ------------------------------------------------------------------ DES */
export function DES({ params }: PanelProps) {
  const code = useT((s) => s.code);
  const asOf = usePanelAsOf(params.pin);
  const q = useCompany(code, asOf);
  const px = usePrices(code, asOf);
  const live = useLive(code, asOf).data;
  const [tip, setTip] = useState<TipReadout | null>(null);
  const mode = useT((s) => s.mode);
  const streak: Streak | null = useMemo(() => {
    const b = px.data?.bars;
    if (!b || b.t.length < 40 || !q.data) return null;
    const step = Math.max(1, Math.floor(b.t.length / 300));
    const idx = b.t.map((_, i) => i).filter((i) => i % step === 0 || i === b.t.length - 1);
    return {
      code: q.data.code, name: q.data.name, security_id: q.data.security_id, from: b.t[0], to: b.t[b.t.length - 1],
      sessions: b.t.length, first: b.c[0], last: b.c[b.c.length - 1], t: idx.map((i) => b.t[i]), c: idx.map((i) => b.c[i]), source: px.data!.source,
    };
  }, [px.data, q.data]);

  return (
    <div className="t-panel">
      <PanelState q={q}>
        {() => {
          const d = q.data!;
          const pb = d.playbook;
          const firstListing = d.listings.reduce((m, l) => (l.valid_from < m ? l.valid_from : m), d.listings[0]?.valid_from ?? "");
          return (
            <div className="des">
              <div className="des-hero">
                <div className="des-id">
                  <div className="des-code mono">{d.code}<span className="des-ex">{d.listings.map((l) => l.exchange).filter((v, i, a) => a.indexOf(v) === i).join(" · ")}</span></div>
                  <h2 className="des-name">{d.name}</h2>
                  <div className="des-chips">
                    {d.active ? <Chip tone="pos">trading</Chip> : <Chip tone="neg">not trading as of {asOf === "NOW" ? "today" : dmy(asOf)}</Chip>}
                    {d.nifty500_member && <Chip tone="gold">Nifty 500</Chip>}
                    {d.sector && <Chip title={`${d.sector_method} · confidence ${d.sector_confidence}`}>{d.sector}{d.sector_confidence !== null && d.sector_confidence < 1 && <span className="v-dot" />}</Chip>}
                    {d.family && <Chip tone="mute">files {d.family}</Chip>}
                  </div>
                  <div className="des-price">
                    {live?.state === "value" ? (
                      <>
                        <span className="mono des-px">₹{live.quote.ltp.toLocaleString("en-IN", { maximumFractionDigits: 2 })}</span>
                        {live.quote.change_pct !== null && <span className={`mono ${live.quote.change_pct >= 0 ? "pos" : "neg"}`}>{live.quote.change_pct >= 0 ? "▲" : "▼"} {Math.abs(live.quote.change_pct * 100).toFixed(2)}%</span>}
                        <span className="des-pxd"><span className={live.market_open ? "live-dot" : "live-dot off"} />{live.market_open ? "LIVE" : "market closed"} · {live.quote.exchange_time ?? ""} · Angel One</span>
                      </>
                    ) : d.last_price ? (
                      <>
                        <span className="mono des-px">₹{d.last_price.close.toLocaleString("en-IN", { maximumFractionDigits: 2 })}</span>
                        <span className="des-pxd">end-of-day close {dmy(d.last_price.date)} · unadjusted{asOf === "NOW" && live?.state === "na" ? ` · live price: ${live.configured ? live.reason : "not set up"}` : ""}</span>
                      </>
                    ) : <span className="v-muted">no price known</span>}
                  </div>
                  <div className="des-listed">listed since <b className="mono">{dmy(firstListing)}</b> · id <span className="mono">{d.security_id}</span></div>
                </div>
                <div className={"des-stone" + (mode === "pro" ? " flat" : "")}>
                  {mode === "pro" ? (streak && <Spark t={streak.t} c={streak.c} />) : streak && <Touchstone variant="panel" streaks={[streak]} onTip={setTip} />}
                  {tip && (
                    <div className="des-stone-read mono">
                      <span>{dmy(tip.date)}</span><b>₹{tip.price.toLocaleString("en-IN", { maximumFractionDigits: 0 })}</b>
                    </div>
                  )}
                  <div className="des-stone-cap">{mode === "pro" ? "adjusted close since listing (log scale)" : "adjusted close since listing, assayed on the touchstone"}</div>
                </div>
              </div>

              <div className="des-grid">
                {["market_cap", "revenue_ttm", "pat_ttm", "pe", "pb", "ev_ebitda", "roe", "roce", "ebitda_margin", "net_margin", "debt_to_equity", "revenue_growth"].map((m) => (
                  <div key={m} className="des-m">
                    <span>{METRIC_LABEL[m]}</span>
                    <Value r={d.metrics[m]} />
                  </div>
                ))}
              </div>

              <div className="pb-card">
                <div className="pb-head">
                  <span className="pb-k">SECTOR PLAYBOOK</span>
                  <b>{pb.label}</b>
                  <span className="mono pb-id">{pb.id}{pb.overlays.length ? ` + ${pb.overlays.join(", ")}` : ""}</span>
                  <Chip tone={pb.confidence >= 0.8 ? "pos" : pb.confidence >= 0.6 ? "warn" : "neg"} title={pb.why}>{pb.how.replace("_", " ")} · {pb.confidence}</Chip>
                </div>
                <div className="pb-cols">
                  <div>
                    <div className="pb-k">Valuation — primary</div>
                    <div className="pb-list">{pb.primary.map((x) => <Chip key={x} tone="gold">{x}</Chip>)}</div>
                    <div className="pb-k">secondary</div>
                    <div className="pb-list">{pb.secondary.map((x) => <Chip key={x}>{x}</Chip>)}{!pb.secondary.length && <span className="v-muted">—</span>}</div>
                    <div className="pb-k">key metrics</div>
                    <div className="pb-list">{pb.key_metrics.slice(0, 10).map((x) => <Chip key={x} tone="mute">{x}</Chip>)}</div>
                  </div>
                  <div>
                    <div className="pb-k"><LockIcon /> forbidden for this sector</div>
                    <div className="pb-list">
                      {[...pb.forbidden_metrics, ...pb.forbidden_methods].slice(0, 16).map((x) => <span key={x} className="pb-forb mono">{x}</span>)}
                      {!pb.forbidden_metrics.length && !pb.forbidden_methods.length && <span className="v-muted">nothing beyond the global rules</span>}
                    </div>
                    {pb.forbidden_reason && <p className="pb-why">{pb.forbidden_reason}</p>}
                    {pb.cautions.slice(0, 2).map((c) => <p key={c.metric} className="pb-caution"><b className="mono">{c.metric}</b> {c.reason}</p>)}
                  </div>
                </div>
              </div>
            </div>
          );
        }}
      </PanelState>
    </div>
  );
}

/* ------------------------------------------------------------------ GP */
/* "Bonus 1:1" / "Split 1:5" from the applied factor (prices before the ex-date are multiplied by it). */
function ratio(r: number): string {
  for (let b = 1; b <= 20; b++) { const a = r * b; if (Math.abs(a - Math.round(a)) < 0.02 && Math.round(a) > 0) return `${Math.round(a)}:${b}`; }
  return `×${r.toFixed(2)}`;
}
export function adjLabel(kind: string | null, f: number): { short: string; long: string } {
  const k = (kind ?? "").toLowerCase();
  const mult = 1 / f;
  if (k.startsWith("split") && !k.includes("bonus")) return { short: `SPLIT 1:${Math.round(mult)}`, long: `Split 1:${Math.round(mult)}` };
  if (k.startsWith("bonus") && !k.includes("split")) return { short: `BONUS ${ratio(mult - 1)}`, long: `Bonus ${ratio(mult - 1)}` };
  if (k.includes("split") && k.includes("bonus")) return { short: `SPLIT+BONUS ×${mult.toFixed(1)}`, long: `Split + bonus (×${mult.toFixed(1)} shares)` };
  if (k.startsWith("rights")) return { short: "RIGHTS", long: `Rights issue (price adj ×${f.toFixed(3)})` };
  return { short: k.toUpperCase() || "ADJ", long: `${k || "adjustment"} ×${f.toFixed(3)}` };
}

export function GP({ params }: PanelProps) {
  const code = useT((s) => s.code);
  const asOf = usePanelAsOf(params.pin);
  const [adjusted, setAdjusted] = useState<"adj" | "raw">("adj");
  const [style, setStyle] = useState<"area" | "candle">("area");
  const [log, setLog] = useState<"log" | "lin">("log");
  const q = usePrices(code, asOf, { adjusted: adjusted === "adj" });
  const el = useRef<HTMLDivElement>(null);
  const chartRef = useRef<IChartApi | null>(null);
  const [hover, setHover] = useState<{ t: string; c: number; f: number } | null>(null);
  const [lines, setLines] = useState<{ x: number; date: string; short: string; long: string }[]>([]);
  const zoomTo = (date: string) => {
    const c = chartRef.current;
    if (!c) return;
    const t = Date.parse(date);
    c.timeScale().setVisibleRange({ from: ((t - 400 * 864e5) / 1000) as UTCTimestamp, to: ((t + 400 * 864e5) / 1000) as UTCTimestamp });
  };

  useEffect(() => {
    const d = q.data;
    if (!el.current || !d || !d.bars.t.length) return;
    const chart = createChart(el.current, {
      autoSize: true,
      layout: { background: { type: ColorType.Solid, color: "transparent" }, textColor: "#6B7079", fontFamily: "JetBrains Mono, monospace", fontSize: 10, attributionLogo: false },
      grid: { vertLines: { color: "rgba(38,43,51,0.35)" }, horzLines: { color: "rgba(38,43,51,0.35)" } },
      rightPriceScale: { borderColor: "#262B33", mode: log === "log" ? PriceScaleMode.Logarithmic : PriceScaleMode.Normal },
      timeScale: { borderColor: "#262B33", rightOffset: 4, minBarSpacing: 0.02 }, // fit 30 years of daily bars
      crosshair: { mode: CrosshairMode.Normal, vertLine: { color: "#8C6F1E", labelBackgroundColor: "#8C6F1E" }, horzLine: { color: "#8C6F1E", labelBackgroundColor: "#8C6F1E" } },
    });
    chartRef.current = chart;
    const b = d.bars;
    const time = (s: string) => (Date.parse(s + "T00:00:00Z") / 1000) as UTCTimestamp;
    const main = style === "area"
      ? chart.addSeries(AreaSeries, { lineColor: "#D4AF37", topColor: "rgba(212,175,55,0.30)", bottomColor: "rgba(212,175,55,0.0)", lineWidth: 2, priceLineColor: "#F2D27A" })
      : chart.addSeries(CandlestickSeries, { upColor: "#2EC4B6", downColor: "#F0577A", borderVisible: false, wickUpColor: "#2EC4B6", wickDownColor: "#F0577A" });
    if (style === "area") main.setData(b.t.map((t, i) => ({ time: time(t), value: b.c[i] })));
    else main.setData(b.t.map((t, i) => ({ time: time(t), open: b.o[i] ?? b.c[i], high: b.h[i] ?? b.c[i], low: b.l[i] ?? b.c[i], close: b.c[i] })));
    const vol = chart.addSeries(HistogramSeries, { priceScaleId: "", priceFormat: { type: "volume" }, color: "rgba(167,169,174,0.18)" });
    vol.priceScale().applyOptions({ scaleMargins: { top: 0.84, bottom: 0 } });
    vol.setData(b.t.map((t, i) => ({ time: time(t), value: b.v[i] ?? 0 })));
    const days = new Set(b.t);
    const applied = d.adjustments.filter((a) => a.applied && days.has(a.ex_date));
    createSeriesMarkers(main, applied.map((a) => ({
      time: time(a.ex_date), position: "aboveBar" as const, shape: "arrowDown" as const, color: "#F2D27A", text: adjLabel(a.kind, a.factor).short,
    })));
    chart.timeScale().fitContent();
    // gold verticals through every applied split/bonus, re-placed whenever the visible range or size changes
    const place = () => {
      const ts = chart.timeScale();
      const out: { x: number; date: string; short: string; long: string }[] = [];
      for (const a of applied) {
        const x = ts.timeToCoordinate(time(a.ex_date));
        if (x !== null) out.push({ x: x as number, date: a.ex_date, ...adjLabel(a.kind, a.factor) });
      }
      setLines(out);
    };
    chart.timeScale().subscribeVisibleTimeRangeChange(place);
    let fitted = false; // autoSize gives the chart its width a frame late: fit once the real width is known
    chart.timeScale().subscribeSizeChange((w) => {
      if (!fitted && w > 0) { fitted = true; chart.timeScale().fitContent(); }
      place();
    });
    requestAnimationFrame(place);
    chart.subscribeCrosshairMove((p) => {
      if (!p.time) { setHover(null); return; }
      const iso = new Date((p.time as number) * 1000).toISOString().slice(0, 10);
      const i = b.t.indexOf(iso);
      if (i >= 0) setHover({ t: iso, c: b.c[i], f: b.f[i] });
    });
    return () => { chart.remove(); chartRef.current = null; };
  }, [q.data, style, log]);

  const range = (years: number | null) => {
    const c = chartRef.current, b = q.data?.bars;
    if (!c || !b?.t.length) return;
    if (years === null) { c.timeScale().fitContent(); return; }
    const end = Date.parse(b.t[b.t.length - 1]);
    c.timeScale().setVisibleRange({ from: ((end - years * 365.25 * 864e5) / 1000) as UTCTimestamp, to: (end / 1000) as UTCTimestamp });
  };
  const last = q.data?.bars.c.at(-1);
  return (
    <div className="t-panel gp">
      <div className="t-toolbar">
        <Seg value={adjusted} onChange={setAdjusted} options={[{ v: "adj", l: "Adjusted" }, { v: "raw", l: "Raw prints" }]} />
        <Seg value={style} onChange={setStyle} options={[{ v: "area", l: "Line" }, { v: "candle", l: "Candles" }]} />
        <Seg value={log} onChange={setLog} options={[{ v: "log", l: "Log" }, { v: "lin", l: "Linear" }]} />
        <div className="t-ranges">{[["1Y", 1], ["5Y", 5], ["10Y", 10], ["MAX", null]].map(([l, y]) => <button key={l as string} onClick={() => range(y as number | null)}>{l}</button>)}</div>
        <div className="gp-read mono">
          {hover ? <>{dmy(hover.t)} <b>₹{hover.c.toLocaleString("en-IN", { maximumFractionDigits: 2 })}</b>{hover.f !== 1 && <span className="gp-f"> ×{hover.f.toFixed(4)} adj</span>}</>
            : last !== undefined ? <>last <b>₹{last.toLocaleString("en-IN", { maximumFractionDigits: 2 })}</b></> : null}
        </div>
      </div>
      <PanelState q={q} empty={q.data && !q.data.bars.t.length ? "No price prints known for this as-of." : undefined}>
        {() => (
          <>
            {q.data!.adjustments.some((a) => a.applied) && (
              <div className="gp-events">
                <span className="t-k">Splits &amp; bonuses</span>
                {q.data!.adjustments.filter((a) => a.applied).map((a) => (
                  <button key={a.ex_date} onClick={() => zoomTo(a.ex_date)} title={`${a.subject ?? ""} · price before this date ×${a.factor.toFixed(4)} in the adjusted series`}>
                    <i />{dmy(a.ex_date)} <b>{adjLabel(a.kind, a.factor).long}</b>
                  </button>
                ))}
              </div>
            )}
            <div className="gp-wrap">
              <div ref={el} className="gp-chart" />
              <div className="gp-lines" aria-hidden>
                {lines.map((l) => (
                  <div key={l.date} className="gp-line" style={{ left: l.x }}>
                    <span>{l.short}<em>{l.date.slice(0, 4)}</em></span>
                  </div>
                ))}
              </div>
            </div>
          </>
        )}
      </PanelState>
      {q.data && <div className="t-foot">{q.data.source} · {indianGroup(q.data.bars.t.length)} sessions · {q.data.adjustments.filter((a) => a.applied).length} adjustments applied</div>}
    </div>
  );
}

/* ------------------------------------------------------------------ EVT */
export function EVT({ params }: PanelProps) {
  const code = useT((s) => s.code);
  const asOf = usePanelAsOf(params.pin);
  const setAsOf = useT((s) => s.setAsOf);
  const q = useTimeline(code, asOf);
  return (
    <div className="t-panel">
      <PanelState q={q} empty={q.data && !q.data.events.length ? "No events known at this as-of." : undefined}>
        {() => (
          <table className="t-table">
            <thead><tr><th>Date</th><th>Event</th><th>Detail</th><th>Public at</th><th /></tr></thead>
            <tbody>
              {[...q.data!.events].reverse().map((e, i) => (
                <tr key={i}>
                  <td className="mono">{dmy(e.date)}</td>
                  <td><span className={`evt evt-${e.type}`} />{e.label}</td>
                  <td className="t-dim">{e.detail}</td>
                  <td className="mono t-dim">{dmyTime(e.known_at)}</td>
                  <td><button className="t-link" onClick={() => setAsOf(new Date(Date.parse(e.known_at) + 864e5).toISOString().slice(0, 10))}>rewind here</button></td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </PanelState>
    </div>
  );
}

/* ------------------------------------------------------------------ HELP */
export function HELP() {
  return (
    <div className="t-panel help">
      <h3>Function codes</h3>
      <div className="help-grid">
        {(Object.keys(FUNCTIONS) as FnCode[]).map((f) => (
          <button key={f} className="help-fn" onClick={() => workspace.open(f)}>
            <b className="mono">{f}</b><span>{FUNCTIONS[f].label}</span><i>{FUNCTIONS[f].desc}</i>
          </button>
        ))}
      </div>
      <h3>Grammar</h3>
      <div className="help-cmds mono">
        <span>TCS</span><i>open the company (DES)</i>
        <span>TCS FA</span><i>company + function</i>
        <span>FA</span><i>function for the active company</i>
        <span>ASOF 2008-01-04</span><i>rewind everything to that day</i>
        <span>ASOF -5Y</span><i>relative rewind (Y / M / D)</i>
        <span>ASOF NOW</span><i>return to the present</i>
      </div>
      <h3>Keys</h3>
      <div className="help-cmds mono">
        <span>/ · Ctrl K</span><i>command bar</i>
        <span>MODE PRO · MODE CINEMA</span><i>flat dense workstation / 3D experience</i>
        <span>F1–F4 · F6–F10</span><i>PRO: help, DES, GP, FA, RV, MAP, MACRO, WC, OWN</i>
        <span>[ · ]</span><i>previous / next event on the Time Spine</i>
        <span>Esc Esc</span><i>return to NOW</i>
        <span>L</span><i>lineage mode — source chips on every value</i>
        <span>D</span><i>dense / comfort</i>
        <span>Ctrl Shift Enter</span><i>maximise panel</i>
      </div>
    </div>
  );
}
