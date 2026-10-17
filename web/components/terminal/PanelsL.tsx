"use client";

/* WL — a watchlist with alerts, and PORT — a portfolio view. Both lists live in this browser only (localStorage) and are sent to the data
   server with each request, which stores nothing about them. Prices are end-of-day closes (or the last close when the market is shut). */

import { useEffect, useMemo, useRef, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { api, ApiError, type Envelope } from "@/lib/api";
import { useAlertFeed, usePriceAlerts, useWatch } from "@/lib/lists";
import { dmy, indianGroup, inr, todayIST } from "@/lib/format";
import { useT, workspace } from "@/lib/store";
import { usePanelAsOf } from "./common";
import type { PanelProps } from "./PanelsA";

type Item = {
  code: string; name?: string; sector?: string | null; error?: string; price: number | null; price_date: string | null; change_1d: number | null; pos_52w: number | null; return_1y: number | null;
  score: number | null; score_prev: number | null; last_results: { period: string | null; known_at: string } | null; upcoming: { ex_date: string; kind: string; subject: string }[];
};
type Alert = { code: string; type: string; severity: "info" | "good" | "warn"; text: string };
type Watch = Envelope & { items: Item[]; alerts: Alert[]; note: string };
type Holding = Item & { qty: number; avg: number | null; value: number | null; cost: number | null; pnl: number | null; pnl_pct: number | null; day_pnl: number | null; weight: number | null };
type Port = Envelope & { holdings: Holding[]; note: string; totals: { value: number; cost: number | null; pnl: number | null; pnl_pct: number | null; day_pnl: number; day_pct: number | null;
  sectors: { sector: string; value: number; weight: number }[]; weighted_score: number | null; scored_share: number | null } };

const pc = (v: number | null | undefined, d = 1) => (v === null || v === undefined ? "n/a" : `${v >= 0 ? "+" : "−"}${Math.abs(v * 100).toFixed(d)}%`);
const tone = (v: number | null | undefined) => (v === null || v === undefined ? "" : v >= 0 ? "pos" : "neg");
const read = <T,>(k: string, d: T): T => { try { return JSON.parse(localStorage.getItem(k) ?? "") as T; } catch { return d; } };
const write = (k: string, v: unknown) => { try { localStorage.setItem(k, JSON.stringify(v)); } catch { /* blocked storage: lasts for the session */ } };
const open = (code: string, setCode: (c: string) => void) => { setCode(code); workspace.open("DES"); };

/* ───────────────────────────────────────────── WL ───────────────────────────────────────────── */
export function WL(_: PanelProps) {
  const setCode = useT((s) => s.setCode);
  const [w, setW] = useWatch();
  const [levels, setLevels] = usePriceAlerts();
  const [draft, setDraft] = useState("");
  const feed = useAlertFeed();
  const alerts = feed.all;
  const told = useRef(0);
  useEffect(() => {
    if (!w.notify || typeof Notification === "undefined" || Notification.permission !== "granted" || alerts.length <= told.current) return;
    new Notification("TRIKAL", { body: alerts.slice(told.current, told.current + 3).map((a) => a.text).join("\n") });
    told.current = alerts.length;
  }, [alerts, w.notify]);
  const enableNotify = async () => {
    if (typeof Notification === "undefined") return;
    const p = Notification.permission === "granted" ? "granted" : await Notification.requestPermission();
    setW({ notify: p === "granted" });
  };
  const add = (e: React.FormEvent) => { e.preventDefault(); const c = draft.trim().toUpperCase(); if (c && !w.codes.includes(c)) setW({ codes: [...w.codes, c] }); setDraft(""); };
  const err = feed.q.error instanceof ApiError ? feed.q.error.message : null;
  const rows = feed.items.filter((i) => w.codes.includes(i.code));
  return (
    <div className="t-panel wl">
      <form className="wl-bar" onSubmit={add}>
        <input value={draft} onChange={(e) => setDraft(e.target.value)} placeholder="add a symbol (TCS, HDFCBANK ...)" spellCheck={false} />
        <button type="submit">Add</button>
        <button type="button" className="ghost" onClick={enableNotify} title="Desktop notifications while this page is open">{w.notify ? "🔔 notifications on" : "🔔 notify me"}</button>
      </form>
      {alerts.length > 0 && (
        <div className="wl-alerts">
          <div className="wl-ah"><b>{alerts.length} alert{alerts.length > 1 ? "s" : ""}</b> since {dmy(w.seen)}<button onClick={() => { setW({ seen: todayIST() }); told.current = 0; }}>mark as read</button></div>
          {alerts.map((a, i) => <div key={i} className={`wl-a ${a.severity}`} onClick={() => open(a.code, setCode)}>{a.text}</div>)}
        </div>
      )}
      {levels.length > 0 && (
        <div className="wl-levels">
          <span className="t-k">Your price alerts</span>
          {levels.map((a) => {
            const p = feed.items.find((i) => i.code === a.code)?.price ?? null;
            const hit = p !== null && (a.op === "above" ? p >= a.price : p <= a.price);
            return <span key={a.id} className={`wl-lv ${hit ? "hit" : ""}`}><b className="mono">{a.code}</b> {a.op} ₹{indianGroup(a.price, 2)}{p !== null && <small> · now ₹{indianGroup(p, 2)}</small>}<i onClick={() => setLevels(levels.filter((x) => x.id !== a.id))} title="remove">×</i></span>;
          })}
        </div>
      )}
      {err && <div className="tx-err">{err}</div>}
      {w.codes.length === 0 && <div className="t-dim">Your watchlist is empty. Press ☆ Watch on any company, or add symbols above. Alerts appear when results come out, a score moves, or a price moves a lot.</div>}
      {w.codes.length > 0 && (
        <table className="t-table wl-tab">
          <thead><tr><th>Company</th><th>Price</th><th>1d</th><th>52-week range</th><th>1y</th><th>Score</th><th>Last results</th><th /></tr></thead>
          <tbody>
            {rows.map((it) => it.error ? (
              <tr key={it.code}><td><b className="mono">{it.code}</b></td><td colSpan={6} className="t-dim">{it.error}</td><td><i className="wl-x" onClick={() => setW({ codes: w.codes.filter((c) => c !== it.code) })}>×</i></td></tr>
            ) : (
              <tr key={it.code} onClick={() => open(it.code, setCode)}>
                <td><b className="mono">{it.code}</b> <span className="t-dim">{it.name}</span></td>
                <td className="mono">{it.price === null ? "n/a" : `₹${indianGroup(it.price, 2)}`}</td>
                <td className={`mono ${tone(it.change_1d)}`}>{pc(it.change_1d)}</td>
                <td><span className="wl-range"><i style={{ left: `${Math.round((it.pos_52w ?? 0) * 100)}%` }} /></span></td>
                <td className={`mono ${tone(it.return_1y)}`}>{pc(it.return_1y, 0)}</td>
                <td className="mono">{it.score === null ? "—" : <>{it.score.toFixed(0)}{it.score_prev !== null && Math.abs(it.score - it.score_prev) >= 0.5 && <small className={tone(it.score - it.score_prev)}> {it.score > it.score_prev ? "▲" : "▼"}{Math.abs(it.score - it.score_prev).toFixed(0)}</small>}</>}</td>
                <td className="t-dim mono">{it.last_results ? dmy(it.last_results.known_at.slice(0, 10)) : "—"}</td>
                <td><i className="wl-x" onClick={(e) => { e.stopPropagation(); setW({ codes: w.codes.filter((c) => c !== it.code) }); }}>×</i></td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
      <div className="t-foot">{feed.q.data?.note ?? "Kept in this browser only."} Scores are KASAUTI v1 rankings, not advice.</div>
    </div>
  );
}

/* ───────────────────────────────────────────── PORT ───────────────────────────────────────────── */
const PKEY = "trikal.port.v1";
type Pos = { code: string; qty: number; avg: number | null };

export function PORT({ params }: PanelProps) {
  const asOf = usePanelAsOf(params.pin);
  const setCode = useT((s) => s.setCode);
  const [pos, setPos] = useState<Pos[]>([]);
  const [f, setF] = useState({ code: "", qty: "", avg: "" });
  const [io, setIo] = useState("");
  const loaded = useRef(false);
  useEffect(() => { setPos(read<Pos[]>(PKEY, [])); loaded.current = true; }, []);
  useEffect(() => { if (loaded.current) write(PKEY, pos); }, [pos]);
  const key = useMemo(() => pos.map((p) => `${p.code}:${p.qty}${p.avg ? `:${p.avg}` : ""}`).join(","), [pos]);
  const q = useQuery({ queryKey: ["port", key, asOf], enabled: pos.length > 0, retry: false, queryFn: () => api<Port>(`/api/portfolio?as_of=${encodeURIComponent(asOf)}&holdings=${encodeURIComponent(key)}`) });
  const err = q.error instanceof ApiError ? q.error.message : null;
  const add = (e: React.FormEvent) => {
    e.preventDefault();
    const code = f.code.trim().toUpperCase(), qty = Number(f.qty), avg = f.avg ? Number(f.avg) : null;
    if (!code || !(qty > 0) || (avg !== null && !(avg > 0))) return;
    setPos([...pos.filter((p) => p.code !== code), { code, qty, avg }]);
    setF({ code: "", qty: "", avg: "" });
  };
  const exportCsv = () => setIo(pos.map((p) => `${p.code},${p.qty},${p.avg ?? ""}`).join("\n"));
  const importCsv = () => {
    const rows = io.split(/\r?\n/).map((l) => l.split(/[,\t;]/).map((x) => x.trim())).filter((r) => r[0]);
    const next: Pos[] = [];
    for (const [code, qty, avg] of rows) {
      const n = Number(qty);
      if (code && n > 0 && !/^(symbol|code|instrument)$/i.test(code)) next.push({ code: code.toUpperCase(), qty: n, avg: avg && Number(avg) > 0 ? Number(avg) : null });
    }
    if (next.length) setPos(next);
  };
  const t = q.data?.totals;
  return (
    <div className="t-panel port">
      <form className="wl-bar" onSubmit={add}>
        <input value={f.code} onChange={(e) => setF({ ...f, code: e.target.value })} placeholder="symbol" spellCheck={false} />
        <input value={f.qty} onChange={(e) => setF({ ...f, qty: e.target.value })} placeholder="quantity" inputMode="decimal" />
        <input value={f.avg} onChange={(e) => setF({ ...f, avg: e.target.value })} placeholder="average buy price (optional)" inputMode="decimal" />
        <button type="submit">Add / update</button>
      </form>
      {pos.length === 0 && <div className="t-dim">Add what you hold, or paste lines like <span className="mono">TCS,10,3200</span> below. It stays in this browser; the server only values it.</div>}
      {err && <div className="tx-err">{err}</div>}
      {t && (
        <>
          <div className="port-kpis">
            <div><span className="t-k">Value{asOf !== "NOW" ? ` on ${dmy(asOf)}` : ""}</span><b className="mono">{inr(t.value)}</b></div>
            <div><span className="t-k">Invested</span><b className="mono">{t.cost ? inr(t.cost) : "n/a"}</b></div>
            <div><span className="t-k">Profit / loss</span><b className={`mono ${tone(t.pnl)}`}>{t.pnl === null ? "n/a" : `${t.pnl >= 0 ? "+" : "−"}${inr(Math.abs(t.pnl))} (${pc(t.pnl_pct)})`}</b></div>
            <div><span className="t-k">Last session</span><b className={`mono ${tone(t.day_pnl)}`}>{t.day_pnl >= 0 ? "+" : "−"}{inr(Math.abs(t.day_pnl))} ({pc(t.day_pct, 2)})</b></div>
            <div><span className="t-k">KASAUTI score of the book</span><b className="mono">{t.weighted_score === null ? "n/a" : t.weighted_score.toFixed(0)}</b>{t.scored_share !== null && <small className="t-dim"> {Math.round(t.scored_share * 100)}% of value scored</small>}</div>
          </div>
          <div className="port-sec">{t.sectors.map((s) => <span key={s.sector} title={`${s.sector}: ${Math.round(s.weight * 100)}%`} style={{ flex: s.weight }}><i />{s.sector} <b>{Math.round(s.weight * 100)}%</b></span>)}</div>
          <table className="t-table wl-tab">
            <thead><tr><th>Holding</th><th>Qty</th><th>Avg</th><th>Price</th><th>Value</th><th>Weight</th><th>P&amp;L</th><th>1d</th><th>Score</th><th /></tr></thead>
            <tbody>
              {q.data!.holdings.map((h) => (
                <tr key={h.code} onClick={() => !h.error && open(h.code, setCode)}>
                  <td><b className="mono">{h.code}</b> <span className="t-dim">{h.name ?? h.error}</span></td>
                  <td className="mono">{indianGroup(h.qty, h.qty % 1 ? 2 : 0)}</td>
                  <td className="mono">{h.avg ? `₹${indianGroup(h.avg, 2)}` : "—"}</td>
                  <td className="mono">{h.price === null || h.price === undefined ? "n/a" : `₹${indianGroup(h.price, 2)}`}</td>
                  <td className="mono">{h.value ? inr(h.value) : "n/a"}</td>
                  <td className="mono">{h.weight ? `${(h.weight * 100).toFixed(1)}%` : "—"}</td>
                  <td className={`mono ${tone(h.pnl)}`}>{h.pnl === null || h.pnl === undefined ? "—" : `${pc(h.pnl_pct)}`}</td>
                  <td className={`mono ${tone(h.change_1d)}`}>{pc(h.change_1d)}</td>
                  <td className="mono">{h.score == null ? "—" : h.score.toFixed(0)}</td>
                  <td><i className="wl-x" onClick={(e) => { e.stopPropagation(); setPos(pos.filter((p) => p.code !== h.code)); }}>×</i></td>
                </tr>
              ))}
            </tbody>
          </table>
        </>
      )}
      <details className="port-io">
        <summary>Import / export (CSV: symbol, quantity, average price)</summary>
        <textarea value={io} onChange={(e) => setIo(e.target.value)} rows={4} placeholder={"TCS,10,3200\nHDFCBANK,25,1450"} spellCheck={false} />
        <div><button onClick={importCsv}>Replace my list with these lines</button> <button className="ghost" onClick={exportCsv}>Show my list as CSV</button></div>
      </details>
      <div className="t-foot">{q.data?.note ?? "Kept in this browser only."}</div>
    </div>
  );
}
