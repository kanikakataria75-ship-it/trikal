"use client";

/* SCRN — screener over the KASAUTI panel: type a condition, get the companies that pass it at the scoring date on or before the as-of.
   A company with no figure for a field never matches a condition on that field. A ranking among sector peers, not a recommendation. */

import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { api, ApiError, type Envelope } from "@/lib/api";
import { dmy } from "@/lib/format";
import { useT, workspace } from "@/lib/store";
import { usePanelAsOf } from "./common";
import type { PanelProps } from "./PanelsA";

type ScreenRow = Record<string, string | number | null>;
type Screen = Envelope & { scoring_date: string; universe: number; matched: number; shown: number; columns: string[]; rows: ScreenRow[]; note: string };
type Fields = Envelope & { scoring_date: string; universe: number; text: Record<string, string>; numbers: Record<string, string>; metrics: string[]; note: string };

const PRESETS: [string, string][] = [
  ["Quality at a fair price", "quality > 70 and valuation > 50 and score > 60"],
  ["High ROCE, low debt", "roce > 20% and debt_to_equity < 0.5"],
  ["Cheap against peers", "p_pe < 30 and p_pb < 40 and p_roe > 60"],
  ["Clean ownership", "pledge_pct = 0 and promoter_change_4q >= 0 and institution_change_4q > 0"],
  ["Momentum with quality", "momentum_12_1 > 20% and quality > 60"],
  ["Banks: clean books", "playbook = 'banks' and gnpa_pct < 3% and cet1 > 12%"],
  ["Top of the ranking", "score >= 70 and confidence >= 0.8"],
];
const RATIO = new Set(["roce", "roe", "roa", "ebitda_margin", "net_margin", "revenue_growth", "profit_growth", "fcf_yield", "momentum_12_1", "momentum_6", "cost_to_income",
  "gnpa_pct", "nnpa_pct", "cet1", "credit_cost", "confidence"]);
const fmt = (k: string, v: string | number | null | undefined) => {
  if (v === null || v === undefined) return "n/a";
  if (typeof v === "string") return v;
  if (RATIO.has(k)) return k === "confidence" ? `${Math.round(v * 100)}%` : `${(v * 100).toFixed(1)}%`;
  return Math.abs(v) >= 100 ? v.toFixed(0) : v.toFixed(2);
};
const SAVED = "trikal.screens.v1";
const load = (): [string, string][] => { try { return JSON.parse(localStorage.getItem(SAVED) ?? "[]"); } catch { return []; } };

export function SCRN({ params }: PanelProps) {
  const asOf = usePanelAsOf(params.pin);
  const setCode = useT((s) => s.setCode);
  const [text, setText] = useState(PRESETS[0][1]);
  const [run, setRun] = useState(PRESETS[0][1]);
  const [saved, setSaved] = useState<[string, string][]>(load);
  const [help, setHelp] = useState(false);
  const q = useQuery({ queryKey: ["screen", run, asOf], queryFn: () => api<Screen>(`/api/screen?as_of=${encodeURIComponent(asOf)}&q=${encodeURIComponent(run)}&limit=200`), retry: false, staleTime: 300_000 });
  const f = useQuery({ queryKey: ["screen-fields", asOf], queryFn: () => api<Fields>(`/api/screen/fields?as_of=${encodeURIComponent(asOf)}`), retry: false, staleTime: Infinity, enabled: help });
  const err = q.error instanceof ApiError ? q.error.message : q.error ? "the data server did not answer" : null;
  const go = (t: string) => { setText(t); setRun(t); };
  const keep = () => {
    const name = window.prompt("Name this screen");
    if (!name) return;
    const next: [string, string][] = [...saved.filter(([n]) => n !== name), [name, text]];
    setSaved(next);
    try { localStorage.setItem(SAVED, JSON.stringify(next)); } catch { /* storage may be blocked */ }
  };
  const drop = (n: string) => { const next = saved.filter(([x]) => x !== n); setSaved(next); try { localStorage.setItem(SAVED, JSON.stringify(next)); } catch { /* ok */ } };
  const d = q.data;
  return (
    <div className="t-panel scr">
      <form className="scr-bar" onSubmit={(e) => { e.preventDefault(); setRun(text.trim()); }}>
        <input className="mono" value={text} onChange={(e) => setText(e.target.value)} spellCheck={false} placeholder="roce > 20% and pe < 25 and sector = 'Information Technology'" />
        <button type="submit">Run</button>
        <button type="button" className="ghost" onClick={keep}>Save</button>
        <button type="button" className="ghost" onClick={() => setHelp((v) => !v)}>{help ? "Hide fields" : "Fields & syntax"}</button>
      </form>
      <div className="scr-chips">
        {PRESETS.map(([n, t]) => <button key={n} onClick={() => go(t)} title={t}>{n}</button>)}
        {saved.map(([n, t]) => <span key={n} className="scr-saved"><button onClick={() => go(t)} title={t}>★ {n}</button><i onClick={() => drop(n)} title="remove">×</i></span>)}
      </div>
      {help && (
        <div className="scr-help">
          <p>Write conditions with <b>and</b>, <b>or</b>, <b>not</b> and brackets. Compare with <span className="mono">&gt; &gt;= &lt; &lt;= = !=</span>; text with <span className="mono">= in (&apos;a&apos;,&apos;b&apos;) contains</span>.
            A <b>%</b> divides by 100 (ROCE is stored as 0.2 for 20%). <span className="mono">p_roce</span> is the percentile of ROCE among sector peers (0 to 100). A company with no figure never matches.</p>
          {f.data && (
            <>
              <div><span className="t-k">Text</span> {Object.entries(f.data.text).map(([k, v]) => <code key={k} title={v}>{k}</code>)}</div>
              <div><span className="t-k">Scores</span> {Object.entries(f.data.numbers).map(([k, v]) => <code key={k} title={v}>{k}</code>)}</div>
              <div><span className="t-k">Metrics</span> {f.data.metrics.map((k) => <code key={k}>{k}</code>)}</div>
            </>
          )}
        </div>
      )}
      {err && <div className="tx-err">{err}</div>}
      {q.isLoading && <div className="t-dim">screening…</div>}
      {d && (
        <>
          <div className="scr-sum"><b>{d.matched}</b> of {d.universe} companies match · scores of {dmy(d.scoring_date)}{d.shown < d.matched ? ` · showing the top ${d.shown}` : ""}</div>
          <div className="scr-scroll">
            <table className="t-table scr-tab">
              <thead><tr><th>Company</th><th>Sector</th><th>Score</th>{d.columns.filter((c) => c !== "score").map((c) => <th key={c}>{c}</th>)}</tr></thead>
              <tbody>
                {d.rows.map((r) => (
                  <tr key={String(r.security_id)} onClick={() => { if (r.code) { setCode(String(r.code)); workspace.open("DES"); } }}>
                    <td><b className="mono">{r.code ?? "—"}</b> <span className="t-dim">{r.name}</span></td>
                    <td className="t-dim">{r.sector}</td>
                    <td className="mono"><b>{typeof r.score === "number" ? r.score.toFixed(0) : "n/a"}</b></td>
                    {d.columns.filter((c) => c !== "score").map((c) => <td key={c} className="mono">{fmt(c, r[c])}</td>)}
                  </tr>
                ))}
                {d.rows.length === 0 && <tr><td colSpan={3 + d.columns.length} className="t-dim">No company passes this condition.</td></tr>}
              </tbody>
            </table>
          </div>
          <div className="t-foot">{d.note}</div>
        </>
      )}
    </div>
  );
}
