"use client";

/* RES  — the latest results against the quarter before and the year before, with what moved alongside them.
   HEAT — a sector's companies as a grid of KASAUTI pillar scores.
   NOTE — your own words about a company, kept in this browser.
   ScoreHistory — the KASAUTI score over time next to the price (used inside KAS).
   Everything is descriptive: a ranking among peers and a comparison of filed numbers, never a recommendation. */

import * as echarts from "echarts/core";
import { LineChart } from "echarts/charts";
import { GridComponent, LegendComponent, TooltipComponent } from "echarts/components";
import { CanvasRenderer } from "echarts/renderers";
import { useEffect, useMemo, useRef, useState } from "react";
import { useCompany, useHeatmap, useKasHistory, useResultsCard, type CardRow } from "@/lib/api";
import { dmy, dmyTime, indianGroup, inr } from "@/lib/format";
import { useNotes } from "@/lib/lists";
import { useT } from "@/lib/store";
import { PanelState, Seg, usePanelAsOf } from "./common";
import type { PanelProps } from "./PanelsA";

echarts.use([LineChart, GridComponent, TooltipComponent, LegendComponent, CanvasRenderer]);

const PILLARS = ["quality", "valuation", "growth", "balance", "momentum", "ownership", "earnings_quality", "credibility"] as const;
const PNAME: Record<string, string> = { quality: "Quality", valuation: "Valuation", growth: "Growth", balance: "Balance", momentum: "Momentum", ownership: "Ownership", earnings_quality: "Earnings quality", credibility: "Credibility" };
const signed = (x: number, d = 1) => `${x >= 0 ? "+" : "−"}${Math.abs(x).toFixed(d)}`;
const pctS = (x: number | null | undefined, d = 1) => (x === null || x === undefined ? "—" : `${signed(x * 100, d)}%`);
const tone = (x: number | null | undefined) => (x === null || x === undefined || Math.abs(x) < 1e-9 ? "" : x > 0 ? "pos" : "neg");

/* ───────────────────────────────────────────── score history (inside KAS) ───────────────────────────────────────────── */
export function ScoreHistory({ code, asOf, version = 1 }: { code: string; asOf: string; version?: number }) {
  const q = useKasHistory(code, asOf, { version });
  const el = useRef<HTMLDivElement>(null);
  const pts = q.data?.available ? q.data.points : [];
  useEffect(() => {
    if (!el.current || pts.length < 2) return;
    const ch = echarts.init(el.current);
    ch.setOption({
      animationDuration: 400, grid: { left: 36, right: 52, top: 24, bottom: 22 },
      legend: { top: 0, right: 0, textStyle: { color: "#9AA0A9", fontSize: 10 }, itemHeight: 7, itemWidth: 14 },
      tooltip: {
        trigger: "axis", backgroundColor: "rgba(13,15,18,0.96)", borderColor: "#3A414C", textStyle: { color: "#E8E6E1", fontSize: 12 },
        formatter: (ps: { dataIndex: number }[]) => {
          const p = pts[ps[0].dataIndex];
          const pil = Object.entries(p.pillars).map(([k, v]) => `${PNAME[k] ?? k} ${v === null ? "n/a" : Math.round(v * 100)}`).join(" · ");
          return `<b>${dmy(p.date)}</b> — score ${p.score.toFixed(0)}${p.reconstructed ? " (reconstructed)" : " (live)"}<br/>price ${p.price ? "₹" + indianGroup(p.price, 2) : "n/a"}<br/><span style="color:#9AA0A9">${pil}</span>`;
        },
      },
      xAxis: { type: "category", data: pts.map((p) => p.date.slice(0, 7)), axisLabel: { color: "#6B7079", fontSize: 10 }, axisLine: { lineStyle: { color: "#262B33" } } },
      yAxis: [
        { type: "value", min: 0, max: 100, splitLine: { lineStyle: { color: "rgba(38,43,51,0.4)" } }, axisLabel: { color: "#D4AF37", fontSize: 10 } },
        { type: "value", scale: true, splitLine: { show: false }, axisLabel: { color: "#6B7079", fontSize: 10, formatter: (v: number) => indianGroup(v) } },
      ],
      series: [
        { name: "KASAUTI score", type: "line", data: pts.map((p) => p.score), symbol: "circle", symbolSize: 7, lineStyle: { color: "#D4AF37", width: 2 }, itemStyle: { color: "#D4AF37" } },
        { name: "Price (adjusted)", type: "line", yAxisIndex: 1, data: pts.map((p) => p.price), symbol: "none", lineStyle: { color: "#6B7079", width: 1.5 } },
      ],
    });
    const ro = new ResizeObserver(() => ch.resize());
    ro.observe(el.current);
    return () => { ro.disconnect(); ch.dispose(); };
  }, [pts]);
  if (q.isLoading) return null;
  if (!q.data?.available || pts.length < 2) return <div className="t-dim kas-hist-none">Score history: {q.data?.reason ?? "fewer than two scoring dates for this company"}.</div>;
  const f = pts[0], l = pts[pts.length - 1];
  const pr = f.price && l.price ? l.price / f.price - 1 : null;
  return (
    <div className="kas-hist">
      <div className="t-k">Score history · quarterly</div>
      <div ref={el} className="kas-hist-chart" />
      <div className="t-foot">
        {dmy(f.date)} → {dmy(l.date)}: score {f.score.toFixed(0)} → {l.score.toFixed(0)} ({signed(Math.round(l.score) - Math.round(f.score), 0)}); price {pctS(pr, 0)} over the same dates.
        This lines up what the ranking said with what the price did; it describes the past and does not say what comes next.
      </div>
    </div>
  );
}

/* ───────────────────────────────────────────── RES ───────────────────────────────────────────── */
function cell(r: CardRow, v: number | null) {
  if (v === null) return "—";
  if (r.kind === "ratio") return `${(v * 100).toFixed(1)}%`;
  return r.label.startsWith("EPS") ? `₹${v.toFixed(2)}` : inr(v);
}
function delta(r: CardRow, v: number | null) {
  if (v === null) return <span className="t-dim">—</span>;
  const t = r.kind === "ratio" ? `${signed(v * 100)} pp` : pctS(v);
  return <span className={`mono ${tone(v)}`}>{t}</span>;
}
const qlab = (d: string | null) => (d ? dmy(d).replace(/^\d+ /, "") : "—");

export function RES({ params }: PanelProps) {
  const code = useT((s) => s.code);
  const asOf = usePanelAsOf(params.pin);
  const q = useResultsCard(code, asOf);
  const d = q.data;
  return (
    <div className="t-panel res">
      <PanelState q={q}>
        {() => !d!.available ? <div className="t-empty"><b>No results card</b><span>{d!.reason}</span></div> : (
          <>
            <div className="res-head">
              <b>Quarter ended {dmy(d!.period_end)}</b>
              <span className="t-dim">public {dmyTime(d!.known_at)}</span>
            </div>
            {d!.reaction && (
              <div className="res-react">
                Price after the numbers came out, against the close of {dmy(d!.reaction.base_date)}:
                <span className={`mono ${tone(d!.reaction.day1)}`}> first session {pctS(d!.reaction.day1)}</span>
                {d!.reaction.day5 !== null && <span className={`mono ${tone(d!.reaction.day5)}`}> · after five sessions {pctS(d!.reaction.day5)}</span>}
                <span className="t-dim"> (adjusted prices; the market also moved for other reasons)</span>
              </div>
            )}
            <table className="t-table res-tab">
              <thead><tr><th /><th>{qlab(d!.period_end)}</th><th>{qlab(d!.prev_end)}</th><th>vs quarter</th><th>{qlab(d!.yago_end)}</th><th>vs year</th></tr></thead>
              <tbody>
                {d!.rows.map((r) => (
                  <tr key={r.label}><td>{r.label}</td><td className="mono"><b>{cell(r, r.now)}</b></td><td className="mono t-dim">{cell(r, r.prev)}</td><td>{delta(r, r.qoq)}</td>
                    <td className="mono t-dim">{cell(r, r.yago)}</td><td>{delta(r, r.yoy)}</td></tr>
                ))}
              </tbody>
            </table>
            <div className="res-cols">
              <div>
                <div className="t-k">Who holds it{d!.holding_periods ? ` · ${qlab(d!.holding_periods[0])} vs ${qlab(d!.holding_periods[1])}` : ""}</div>
                {d!.holding.length === 0 ? <div className="t-dim">Shareholding for two quarters is not in the database.</div> : (
                  <table className="t-table"><tbody>
                    {d!.holding.map((h) => (
                      <tr key={h.label}><td>{h.label}</td><td className="mono">{h.now.toFixed(2)}%</td><td className={`mono ${tone(h.delta)}`}>{Math.abs(h.delta) < 0.005 ? "no change" : `${signed(h.delta, 2)} pp`}</td></tr>
                    ))}
                  </tbody></table>
                )}
              </div>
              <div>
                <div className="t-k">KASAUTI since the last scoring date</div>
                {d!.score.length === 2 && d!.score[0].score !== null && d!.score[1].score !== null ? (
                  <>
                    <div className="mono">{d!.score[0].score!.toFixed(0)} → <b>{d!.score[1].score!.toFixed(0)}</b> <span className={tone(Math.round(d!.score[1].score!) - Math.round(d!.score[0].score!))}>({signed(Math.round(d!.score[1].score!) - Math.round(d!.score[0].score!), 0)})</span>
                      <span className="t-dim"> · {dmy(d!.score[0].date)} → {dmy(d!.score[1].date)}</span></div>
                    <table className="t-table"><tbody>
                      {d!.pillar_moves.map((m) => (
                        <tr key={m.pillar}><td>{PNAME[m.pillar] ?? m.pillar}</td><td className="mono">{Math.round(m.prev)} → {Math.round(m.now)}</td><td className={`mono ${tone(m.delta)}`}>{signed(Math.round(m.now) - Math.round(m.prev), 0)}</td></tr>
                      ))}
                    </tbody></table>
                  </>
                ) : <div className="t-dim">Fewer than two scoring dates.</div>}
              </div>
            </div>
            <div className="t-k" style={{ marginTop: 10 }}>What management said about {d!.said_fy ? `the year to ${dmy(d!.said_fy)}` : "the latest year"}, and what happened</div>
            {d!.said.length === 0 ? <div className="t-dim">No judged statements about that year (the calls are read by rules; many guide in words, not numbers).</div> : (
              <table className="t-table res-said"><tbody>
                {d!.said.map((s, i) => (
                  <tr key={i}><td className="t-dim mono">{qlab(s.call_period_end)}</td><td>“{s.quote.length > 160 ? s.quote.slice(0, 160) + "…" : s.quote}”</td>
                    <td><span className={`res-v ${s.verdict}`}>{s.verdict}</span>{s.actual !== null && <span className="mono t-dim"> {s.actual.toFixed(1)}%</span>}</td></tr>
                ))}
              </tbody></table>
            )}
            <div className="t-foot">{d!.note}. Nothing here is a recommendation.</div>
          </>
        )}
      </PanelState>
    </div>
  );
}

/* ───────────────────────────────────────────── HEAT ───────────────────────────────────────────── */
const shade = (v: number | null) => {
  if (v === null || v === undefined) return undefined;
  const a = (Math.abs(v - 50) / 50) * 0.6 + 0.04;
  return v >= 50 ? `rgba(46,196,182,${a})` : `rgba(240,87,122,${a})`;
};

export function HEAT({ params }: PanelProps) {
  const code = useT((s) => s.code);
  const setCode = useT((s) => s.setCode);
  const asOf = usePanelAsOf(params.pin);
  const [ver, setVer] = useState(1);
  const q = useHeatmap(asOf, ver);
  const [pick, setPick] = useState<string | null>(null);
  const [key, setKey] = useState<string>("score");
  const rows = q.data?.rows ?? [];
  const groups = useMemo(() => {
    const m = new Map<string, number>();
    rows.forEach((r) => m.set(r.playbook, (m.get(r.playbook) ?? 0) + 1));
    return [...m.entries()].sort((a, b) => b[1] - a[1]);
  }, [rows]);
  const mine = rows.find((r) => r.code === code)?.playbook;
  const group = pick ?? mine ?? groups[0]?.[0] ?? "";
  const cols = PILLARS.filter((k) => rows.some((r) => r.playbook === group && typeof r[k] === "number"));
  const list = rows.filter((r) => r.playbook === group).sort((a, b) => ((b[key] as number | null) ?? -1) - ((a[key] as number | null) ?? -1));
  const med = (k: string) => {
    const v = list.map((r) => r[k] as number | null).filter((x): x is number => typeof x === "number").sort((a, b) => a - b);
    return v.length ? v[Math.floor(v.length / 2)] : null;
  };
  return (
    <div className="t-panel heat">
      <PanelState q={q}>
        {() => (
          <>
            <div className="heat-bar">
              <select value={group} onChange={(e) => setPick(e.target.value)}>
                {groups.map(([g, n]) => <option key={g} value={g}>{g.replace(/_/g, " ")} ({n}){g === mine ? " · " + code : ""}</option>)}
              </select>
              <Seg value={String(ver)} onChange={(v) => setVer(Number(v))} options={[{ v: "1", l: "v1" }, { v: "2", l: "v2 draft" }]} />
              <span className="t-dim">scored {dmy(q.data!.scoring_date)} · {list.length} companies · click a header to sort, a row to open</span>
              <i className="heat-key"><b style={{ background: shade(10) }}>weak</b><b style={{ background: shade(50) }}>middle</b><b style={{ background: shade(90) }}>strong</b></i>
            </div>
            <table className="t-table heat-tab">
              <thead><tr><th>Company</th>
                {["score", ...cols].map((k) => <th key={k} className={key === k ? "on" : ""} onClick={() => setKey(k)}>{k === "score" ? "Score" : PNAME[k]}</th>)}</tr></thead>
              <tbody>
                {list.map((r) => (
                  <tr key={r.code} className={r.code === code ? "me" : ""} onClick={() => setCode(r.code)}>
                    <td><b className="mono">{r.code}</b> <span className="t-dim">{r.name}</span></td>
                    {["score", ...cols].map((k) => {
                      const v = r[k] as number | null;
                      return <td key={k} className="mono heat-c" style={{ background: shade(v) }}>{v === null || v === undefined ? "·" : Math.round(v)}</td>;
                    })}
                  </tr>
                ))}
                <tr className="heat-med"><td>Median of this group</td>{["score", ...cols].map((k) => <td key={k} className="mono">{med(k) === null ? "·" : Math.round(med(k)!)}</td>)}</tr>
              </tbody>
            </table>
            <div className="t-foot">{q.data!.note} A dot means the pillar was left out for this company. KASAUTI v1 is a ranking among peers, not a rating.</div>
          </>
        )}
      </PanelState>
    </div>
  );
}

/* ───────────────────────────────────────────── NOTE ───────────────────────────────────────────── */
const SUGGEST = ["why I looked", "to research", "waiting for results", "bought", "avoid", "good business, expensive"];

export function NOTE(_: PanelProps) {
  const code = useT((s) => s.code);
  const setCode = useT((s) => s.setCode);
  const [notes, setNote] = useNotes();
  const co = useCompany(code, "NOW");
  const [tag, setTag] = useState("");
  const [find, setFind] = useState("");
  const mine = notes[code];
  const price = co.data?.last_price ?? null;
  const write = (patch: Partial<NonNullable<typeof mine>>) =>
    setNote(code, { ...(mine ? {} : { price: price?.close ?? null, price_date: price?.date ?? null }), ...patch });
  const addTag = (t: string) => { const x = t.trim().toLowerCase(); if (x && !(mine?.tags ?? []).includes(x)) write({ tags: [...(mine?.tags ?? []), x] }); setTag(""); };
  const all = Object.entries(notes).filter(([c, n]) => !find || (c + " " + n.text + " " + n.tags.join(" ")).toLowerCase().includes(find.toLowerCase())).sort((a, b) => b[1].updated.localeCompare(a[1].updated));
  const download = () => {
    const text = Object.entries(notes).sort().map(([c, n]) => `## ${c}${n.tags.length ? "  [" + n.tags.join(", ") + "]" : ""}\n${n.price ? `(first noted ${n.created.slice(0, 10)} at ₹${n.price})\n` : ""}${n.text}\n`).join("\n");
    const a = document.createElement("a");
    a.href = URL.createObjectURL(new Blob([text], { type: "text/markdown" }));
    a.download = "trikal-notes.md";
    a.click();
    URL.revokeObjectURL(a.href);
  };
  return (
    <div className="t-panel note">
      <div className="note-h"><b className="mono">{code}</b> <span className="t-dim">{co.data?.name}</span>
        {mine && <span className="t-dim"> · first noted {dmy(mine.created.slice(0, 10))}{mine.price ? ` at ₹${indianGroup(mine.price, 2)}` : ""}{price && mine.price ? <> · price since <b className={tone(price.close / mine.price - 1)}>{pctS(price.close / mine.price - 1, 0)}</b></> : null}</span>}
      </div>
      <textarea value={mine?.text ?? ""} placeholder={`Your notes on ${code}: why you are looking at it, what you want to check, what would change your mind…`} spellCheck={false}
        onChange={(e) => write({ text: e.target.value })} />
      <div className="note-tags">
        {(mine?.tags ?? []).map((t) => <span key={t} className="note-tag">{t}<i onClick={() => write({ tags: mine!.tags.filter((x) => x !== t) })}>×</i></span>)}
        <input value={tag} placeholder="add a tag…" onChange={(e) => setTag(e.target.value)} onKeyDown={(e) => { if (e.key === "Enter") { e.preventDefault(); addTag(tag); } }} />
      </div>
      <div className="note-sug">{SUGGEST.filter((s) => !(mine?.tags ?? []).includes(s)).map((s) => <button key={s} onClick={() => addTag(s)}>+ {s}</button>)}
        {mine && <button className="danger" onClick={() => { if (confirm(`Delete your note on ${code}?`)) setNote(code, null); }}>delete this note</button>}</div>
      <div className="note-all">
        <div className="note-bar"><span className="t-k">All notes ({Object.keys(notes).length})</span>
          <input value={find} onChange={(e) => setFind(e.target.value)} placeholder="search notes and tags" />
          <button onClick={download} disabled={Object.keys(notes).length === 0}>Download .md</button></div>
        {all.length === 0 && <div className="t-dim">Nothing yet. Notes stay in this browser; download them to keep a copy.</div>}
        {all.map(([c, n]) => (
          <div key={c} className={`note-item ${c === code ? "me" : ""}`} onClick={() => setCode(c)}>
            <b className="mono">{c}</b> {n.tags.map((t) => <span key={t} className="note-tag small">{t}</span>)}
            <div className="t-dim">{n.text.slice(0, 160) || "(no text)"}{n.text.length > 160 ? "…" : ""}</div>
          </div>
        ))}
      </div>
    </div>
  );
}
