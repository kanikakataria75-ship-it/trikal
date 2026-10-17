"use client";

/* CAL — what is coming up: board meetings the companies announced to the exchange (results, dividends, fund raising).
   Each shows when it was announced; dates can still move. "My lists" uses your watchlist and portfolio from this browser. */

import { useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { api, type Envelope } from "@/lib/api";
import { dmy } from "@/lib/format";
import { useT, workspace } from "@/lib/store";
import { Seg, usePanelAsOf } from "./common";
import type { PanelProps } from "./PanelsA";

type Ev = { date: string; code: string; kind: "results" | "dividend" | "fundraise" | "other"; purpose: string; detail: string; announced_at: string };
type Cal = Envelope & { from: string; to: string; events: Ev[]; note: string };
const KIND: Record<string, string> = { results: "Results", dividend: "Dividend", fundraise: "Capital", other: "Other" };
const mine = (): string[] => {
  const out = new Set<string>();
  try { (JSON.parse(localStorage.getItem("trikal.watch.v1") ?? "{}").codes ?? []).forEach((c: string) => out.add(c)); } catch { /* none */ }
  try { (JSON.parse(localStorage.getItem("trikal.port.v1") ?? "[]") as { code: string }[]).forEach((p) => out.add(p.code)); } catch { /* none */ }
  return [...out];
};
const day = (iso: string) => new Date(`${iso}T00:00:00Z`).toLocaleDateString("en-IN", { weekday: "long", day: "numeric", month: "short", timeZone: "UTC" });

export function CAL({ params }: PanelProps) {
  const asOf = usePanelAsOf(params.pin);
  const setCode = useT((s) => s.setCode);
  const [scope, setScope] = useState<"nifty500" | "list" | "all">("nifty500");
  const [days, setDays] = useState("30");
  const [kinds, setKinds] = useState<Record<string, boolean>>({ results: true, dividend: true, fundraise: true, other: false });
  const [find, setFind] = useState("");
  const codes = useMemo(() => (scope === "list" ? mine().join(",") : ""), [scope]);
  const q = useQuery({
    queryKey: ["cal", asOf, scope, days, codes], retry: false, staleTime: 300_000,
    queryFn: () => api<Cal>(`/api/calendar?as_of=${encodeURIComponent(asOf)}&days=${days}&scope=${scope}&codes=${encodeURIComponent(codes)}`),
  });
  const shown = (q.data?.events ?? []).filter((e) => kinds[e.kind] && (!find || e.code.includes(find.toUpperCase())));
  const groups = useMemo(() => {
    const g = new Map<string, Ev[]>();
    shown.forEach((e) => g.set(e.date, [...(g.get(e.date) ?? []), e]));
    return [...g.entries()];
  }, [shown]);
  return (
    <div className="t-panel cal">
      <div className="t-toolbar">
        <Seg value={scope} onChange={setScope} options={[{ v: "nifty500", l: "Nifty 500" }, { v: "list", l: "My lists" }, { v: "all", l: "Every listed company" }]} />
        <Seg value={days} onChange={setDays} options={[{ v: "14", l: "2 weeks" }, { v: "30", l: "30 days" }, { v: "60", l: "60 days" }, { v: "90", l: "90 days" }]} />
        <input className="cal-find mono" value={find} onChange={(e) => setFind(e.target.value)} placeholder="find a symbol" spellCheck={false} />
        {Object.entries(KIND).map(([k, l]) => <label key={k} className="cal-k"><input type="checkbox" checked={kinds[k]} onChange={(e) => setKinds({ ...kinds, [k]: e.target.checked })} /> {l}</label>)}
      </div>
      {q.isLoading && <div className="t-dim">loading…</div>}
      {q.data && (
        <div className="t-dim">{shown.length} events from {dmy(q.data.from)} to {dmy(q.data.to)}{scope === "list" && !codes ? " · add symbols to your watchlist or portfolio first" : ""}</div>
      )}
      <div className="cal-list">
        {groups.map(([d, evs]) => (
          <div key={d} className="cal-day">
            <div className="cal-dh">{day(d)} <span className="t-dim">· {evs.length}</span></div>
            {evs.map((e, i) => (
              <div key={i} className="cal-row" onClick={() => { setCode(e.code); workspace.open("DES"); }}>
                <b className="mono">{e.code}</b>
                <span className={`cal-badge ${e.kind}`}>{KIND[e.kind]}</span>
                <span className="cal-p">{e.purpose}</span>
                <span className="t-dim cal-a">announced {dmy(e.announced_at.slice(0, 10))}</span>
              </div>
            ))}
          </div>
        ))}
        {q.data && groups.length === 0 && <div className="t-dim">Nothing announced for this selection yet.</div>}
      </div>
      <div className="t-foot">{q.data?.note}</div>
    </div>
  );
}
