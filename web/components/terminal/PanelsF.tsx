"use client";

/* TX — the Transmission Engine and SHOCK simulator.
   CINEMA: the 3D planes (drivers → sectors → companies). PRO: the same information as a flat matrix.
   The impact table is the answer in both; the picture is the explanation. Every number is an ESTIMATED PRICE RESPONSE from
   a historical regression, shown with its confidence: not an earnings forecast, not advice. */

import dynamic from "next/dynamic";
import { useEffect, useMemo, useState } from "react";
import { geoEquirectangular, geoPath } from "d3-geo";
import { feature } from "topojson-client";
import land110 from "world-atlas/land-110m.json";
import { ApiError, useGeo, useShock, useShockCompanies, useTransmission, type Chokepoint, type GeoData, type SensCell, type TxOverview } from "@/lib/api";
import { useT } from "@/lib/store";
import { PanelState, usePanelAsOf } from "./common";
import type { PanelProps } from "./PanelsA";

const TransmissionScene = dynamic(() => import("@/components/three/TransmissionScene"), { ssr: false });
const ExposureGlobe = dynamic(() => import("@/components/three/ExposureGlobe"), { ssr: false });

const CHIPS = ["CRUDE +20", "INR 90", "REPO +50bp", "UST +50bp", "COPPER -15", "GOLD +10", "CRUDE +20 & INR +5"];
const pct = (x: number | null | undefined, d = 1) => (x === null || x === undefined ? "n/a" : `${x >= 0 ? "+" : "−"}${Math.abs(x * 100).toFixed(d)}%`);
const cls = (x: number | null | undefined) => (x === null || x === undefined ? "" : x >= 0 ? "pos" : "neg");

function Conf({ c }: { c: "high" | "medium" | "low" }) {
  return <span className={`cf cf-${c}`} title={c === "high" ? "≥48 obs, |t|≥2.5, sector labels mostly real" : c === "medium" ? "≥36 obs, |t|≥1.65" : "weak statistics: read as a hint"}>{c === "high" ? "●●●" : c === "medium" ? "●●○" : "●○○"}</span>;
}

/* the flat twin: driver × sector, coloured by the response */
function Matrix({ ov, sh, selected, onSelect }: { ov: TxOverview; sh?: ReturnType<typeof useShock>["data"]; selected: string | null; onSelect: (s: string | null) => void }) {
  const [tip, setTip] = useState<string>("");
  const sig = new Map(ov.drivers.map((d) => [d.id, d.sigma ?? 0.03]));
  const rows = sh ? sh.rows : ov.sectors.map((s) => ({ sector: s.sector, cells: {} as Record<string, SensCell>, total: 0 }));
  const val = (sector: string, did: string): { v: number | null; c: "high" | "medium" | "low"; t: string } => {
    if (sh) {
      const cell = sh.rows.find((r) => r.sector === sector)?.cells[did];
      return { v: cell?.impact ?? null, c: cell?.confidence ?? "low", t: cell ? `β ${cell.beta?.toFixed(3)} · t ${cell.tstat?.toFixed(1)} · n ${cell.n}` : "no estimate" };
    }
    const e = ov.sectors.find((s) => s.sector === sector)?.sens[did];
    return { v: e ? e.beta * (sig.get(did) ?? 0.03) : null, c: e?.confidence ?? "low", t: e ? `β ${e.beta.toFixed(3)} · t ${e.tstat.toFixed(1)} · n ${e.n}` : "no estimate" };
  };
  const colour = (v: number | null, c: string) => {
    if (v === null) return "transparent";
    const a = Math.min(1, Math.sqrt(Math.abs(v) / (sh ? 0.12 : 0.04)));
    const base = v >= 0 ? "46,196,182" : "240,87,122";
    return `rgba(${base},${(0.12 + 0.7 * a) * (c === "low" ? 0.45 : 1)})`;
  };
  return (
    <div className="tx-mx-wrap">
      <table className="tx-mx">
        <thead>
          <tr><th className="sticky">{sh ? "Estimated price response" : "Response to a typical (1σ) monthly move"}</th>
            {ov.drivers.map((d) => <th key={d.id} className={sh?.shocks.some((s) => s.driver === d.id) ? "hot" : ""}>{d.label}</th>)}
            {sh && <th>Total</th>}</tr>
        </thead>
        <tbody>
          {sh && (
            <tr className="mkt"><td className="sticky">Market (equal weight)</td>
              {ov.drivers.map((d) => <td key={d.id}>{sh.market.cells[d.id] ? <span className={cls(sh.market.cells[d.id].impact)}>{pct(sh.market.cells[d.id].impact)}</span> : ""}</td>)}
              <td><b className={cls(sh.market.total)}>{pct(sh.market.total)}</b></td></tr>
          )}
          {rows.map((r) => (
            <tr key={r.sector} className={selected === r.sector ? "sel" : ""} onClick={() => onSelect(selected === r.sector ? null : r.sector)}>
              <td className="sticky">{r.sector}</td>
              {ov.drivers.map((d) => {
                const x = val(r.sector, d.id);
                return (
                  <td key={d.id} style={{ background: colour(x.v, x.c) }} onMouseEnter={() => setTip(`${r.sector} × ${d.label}: ${x.t} · ${x.c} confidence`)}>
                    {x.v === null ? <span className="v-muted">·</span> : <span className={`mono ${x.c === "low" ? "dim" : ""}`}>{pct(x.v, sh ? 1 : 1)}</span>}
                  </td>
                );
              })}
              {sh && <td><b className={`mono ${cls(r.total)}`}>{pct(r.total)}</b></td>}
            </tr>
          ))}
        </tbody>
      </table>
      <div className="tx-tip mono">{tip || "hover a cell for its beta, t-statistic and sample size · click a row to see its companies"}</div>
    </div>
  );
}

export function TX({ params }: PanelProps) {
  const asOf = usePanelAsOf(params.pin);
  const mode = useT((s) => s.mode);
  const text = useT((s) => s.shock);
  const setShock = useT((s) => s.setShock);
  const [draft, setDraft] = useState(text);
  const [sel, setSel] = useState<string | null>(null);
  useEffect(() => setDraft(text), [text]);
  const ov = useTransmission(asOf);
  const sh = useShock(text, asOf);
  const co = useShockCompanies(text, sel, asOf);
  const err = sh.error instanceof ApiError ? sh.error.message : null;
  const rows = sh.data?.rows ?? [];
  const maxAbs = useMemo(() => Math.max(1e-6, ...rows.map((r) => Math.abs(r.total))), [rows]);
  return (
    <div className="t-panel tx">
      <form className="tx-bar" onSubmit={(e) => { e.preventDefault(); setShock(draft.trim()); }}>
        <span className="tx-sh">SHOCK</span>
        <input className="mono" value={draft} onChange={(e) => setDraft(e.target.value)} placeholder="CRUDE +20 · INR 90 · REPO +50bp · combine with &" spellCheck={false} />
        <button type="submit">Run</button>
        {text && <button type="button" className="ghost" onClick={() => { setShock(""); setSel(null); }}>Clear</button>}
        <div className="tx-chips">{CHIPS.map((c) => <button type="button" key={c} onClick={() => { setDraft(c); setShock(c); }}>{c}</button>)}</div>
      </form>
      {err && <div className="tx-err">{err}</div>}
      <PanelState q={ov}>
        {() => (
          <div className="tx-main">
            <div className="tx-left">
              {mode === "cinema" ? (
                <div className="tx-scene">
                  <TransmissionScene overview={ov.data!} shock={sh.data} selected={sel} onSelect={setSel} companies={co.data} />
                  <div className="tx-scene-cap">{sh.data ? `Shock: ${sh.data.shocks.map((s) => `${s.label} ${s.text}`).join(" & ")}` : "Links shown are statistically meaningful (|t| ≥ 1.65): brighter = stronger. Run a shock to send it down the planes. Click a sector."}</div>
                </div>
              ) : (
                <Matrix ov={ov.data!} sh={sh.data} selected={sel} onSelect={setSel} />
              )}
            </div>
            <div className="tx-right">
              {!sh.data ? (
                <div className="tx-help">
                  <b>The answer appears here.</b> Type a shock above (or press a chip). Each sector shows its estimated price response
                  relative to the market, the market’s own response, and their total, with the confidence of the statistics behind it.
                  <div className="t-foot">{ov.data!.estimates.toLocaleString("en-IN")} point-in-time estimates available at this as-of.</div>
                </div>
              ) : (
                <>
                  <table className="t-table tx-tab">
                    <thead><tr><th>Sector</th><th>Relative</th><th>Market</th><th>Total</th><th /><th>Conf.</th></tr></thead>
                    <tbody>
                      {rows.map((r) => (
                        <tr key={r.sector} className={sel === r.sector ? "sel" : ""} onClick={() => setSel(sel === r.sector ? null : r.sector)}>
                          <td>{r.sector}{r.missing.length > 0 && <span className="v-dot" title={`no estimate for ${r.missing.join(", ")}`} />}</td>
                          <td className={`mono ${cls(r.relative)}`}>{pct(r.relative)}</td>
                          <td className={`mono ${cls(r.market)}`}>{pct(r.market)}</td>
                          <td className={`mono ${cls(r.total)}`}><b>{pct(r.total)}</b></td>
                          <td className="tx-bar-cell"><i className={r.total >= 0 ? "up" : "dn"} style={{ width: `${(Math.abs(r.total) / maxAbs) * 100}%` }} /></td>
                          <td><Conf c={r.confidence} /></td>
                        </tr>
                      ))}
                      {rows.length === 0 && <tr><td colSpan={6} className="t-dim">No estimates yet at this as-of (needs 36 months of history for the driver).</td></tr>}
                    </tbody>
                  </table>
                  <ul className="tx-notes">{sh.data.notes.map((n, i) => <li key={i}>{n}</li>)}</ul>
                </>
              )}
              {sel && sh.data && (
                <div className="tx-co">
                  <div className="t-k">{sel} · largest members</div>
                  {co.isLoading ? <div className="t-dim">estimating…</div> : (
                    <table className="t-table tx-tab">
                      <thead><tr><th>Company</th><th>Total</th><th>Conf.</th></tr></thead>
                      <tbody>
                        {(co.data?.rows ?? []).map((c) => (
                          <tr key={c.security_id}><td><b className="mono">{c.code}</b> <span className="t-dim">{c.name}</span></td>
                            <td className={`mono ${cls(c.total)}`}>{c.relative === 0 && Object.values(c.cells).every((x) => x.impact === null) ? <span className="v-muted">n/a</span> : pct(c.total)}</td>
                            <td><Conf c={c.confidence} /></td></tr>
                        ))}
                      </tbody>
                    </table>
                  )}
                </div>
              )}
            </div>
          </div>
        )}
      </PanelState>
    </div>
  );
}

/* ───────────────────────── GEO — the Exposure Theatre ───────────────────────── */

const MON = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
const heat = (x: number) => (x >= 0.85 ? "very high" : x >= 0.65 ? "high" : x >= 0.35 ? "usual" : "quiet");

/* the flat twin: an equirectangular map with the same arteries and rings */
function FlatMap({ geo, selected, onSelect }: { geo: GeoData; selected: string | null; onSelect: (id: string | null) => void }) {
  const W = 760, H = 330;
  const { d, proj } = useMemo(() => {
    const proj = geoEquirectangular().scale(118).translate([W / 2 - 40, H / 2 + 20]).rotate([-40, 0]);
    const land = feature(land110 as never, (land110 as never as { objects: { land: never } }).objects.land) as never;
    return { d: geoPath(proj)(land) ?? "", proj };
  }, []);
  const pt = (lat: number, lon: number) => proj([lon, lat]) ?? [0, 0];
  const byId = new Map(geo.chokepoints.map((c) => [c.id, c]));
  return (
    <svg viewBox={`0 0 ${W} ${H}`} className="geo-flat" preserveAspectRatio="xMidYMid meet" onClick={() => onSelect(null)}>
      <path d={d} className="geo-land" />
      {geo.corridors.map((c) => {
        const pts = c.path.map(([la, lo]) => pt(la, lo));
        const hot = Math.max(0, ...c.via.map((v) => byId.get(v)?.intensity ?? 0));
        return <polyline key={c.id} points={pts.map((p) => p.join(",")).join(" ")} className={`geo-cor ${c.dashed ? "dash" : ""} ${hot > 0.75 ? "hot" : ""}`} />;
      })}
      {geo.chokepoints.map((c) => {
        const [x, y] = pt(c.lat, c.lon);
        const r = 5 + 9 * c.intensity;
        return (
          <g key={c.id} onClick={(e) => { e.stopPropagation(); onSelect(c.id === selected ? null : c.id); }} style={{ cursor: "pointer" }}>
            <circle cx={x} cy={y} r={r} className={`geo-ring ${c.intensity > 0.75 ? "hot" : ""} ${selected === c.id ? "sel" : ""}`} />
            <circle cx={x} cy={y} r={2} className="geo-core" />
            <text x={x} y={y - r - 4} textAnchor="middle" className="geo-t">{c.label}</text>
          </g>
        );
      })}
      {(() => { const [x, y] = pt(21, 79); return <g><circle cx={x} cy={y} r={3.5} className="geo-in" /><text x={x + 7} y={y + 3} className="geo-t">India</text></g>; })()}
    </svg>
  );
}

function Spark({ data }: { data: { month: string; n: number }[] }) {
  if (data.length < 2) return <div className="t-dim">not enough history</div>;
  const W = 300, H = 46, mx = Math.max(1, ...data.map((x) => x.n));
  const pts = data.map((x, i) => `${(i / (data.length - 1)) * W},${H - 12 - (x.n / mx) * (H - 18)}`).join(" ");
  return (
    <svg viewBox={`0 0 ${W} ${H}`} className="geo-spark" preserveAspectRatio="none">
      <polyline points={pts} fill="none" stroke="var(--gold-1)" strokeWidth="1.3" vectorEffect="non-scaling-stroke" />
      <text x="0" y={H - 1} className="geo-t2">{data[0].month}</text><text x={W} y={H - 1} textAnchor="end" className="geo-t2">{data[data.length - 1].month}</text>
    </svg>
  );
}

function ChokeDetail({ c, asOf }: { c: Chokepoint; asOf: string }) {
  const shock = c.driver === "brent" ? "CRUDE +20" : null;
  const sh = useShock(shock ?? "", asOf);
  const top = (sh.data?.rows ?? []).slice().sort((a, b) => Math.abs(b.total) - Math.abs(a.total)).slice(0, 5);
  return (
    <div className="geo-detail">
      <div className="geo-h">{c.label}</div>
      <div className="t-kv"><span className="t-k">Carries</span><span>{c.carries}</span></div>
      <div className="t-kv"><span className="t-k">Channel</span><span>{c.channel}</span></div>
      <div className="t-kv"><span className="t-k">Intensity</span><span><b className="mono">{c.last_90d}</b> dated items in the last 3 months · {heat(c.intensity)} for this area ({Math.round(c.intensity * 100)}th percentile of its own history)</span></div>
      <Spark data={c.monthly} />
      <div className="t-k" style={{ marginTop: 8 }}>Sectors linked (qualitative)</div>
      <div className="geo-sec">{c.sectors.map((s) => <span key={s}>{s}</span>)}</div>
      {shock && top.length > 0 && (
        <>
          <div className="t-k" style={{ marginTop: 8 }}>Measured: a +20% crude move, estimated price response</div>
          <table className="t-table"><tbody>{top.map((r) => <tr key={r.sector}><td>{r.sector}</td><td className={`mono ${cls(r.total)}`}>{pct(r.total)}</td><td><Conf c={r.confidence} /></td></tr>)}</tbody></table>
        </>
      )}
      {!shock && <div className="t-foot">No measured driver for this area yet: the link to sectors is qualitative. Company-level exposure needs export/import splits from annual reports (M6).</div>}
      <div className="t-k" style={{ marginTop: 8 }}>Latest dated items</div>
      <ul className="geo-items">
        {c.recent.length === 0 && <li className="t-dim">none at this as-of</li>}
        {c.recent.map((x, i) => (
          <li key={i}><span className="mono">{x.day.slice(8, 10)} {MON[+x.day.slice(5, 7) - 1]} {x.day.slice(0, 4)}</span> {x.text.length > 200 ? `${x.text.slice(0, 200)}…` : x.text}{" "}
            <a href={x.source_url} target="_blank" rel="noreferrer">{x.source_name || "source"}</a></li>
        ))}
      </ul>
      <div className="t-foot">Source for the link: {c.source}. News items: Wikipedia current events (CC BY-SA). Context, not an input to any number.</div>
    </div>
  );
}

export function GEO({ params }: PanelProps) {
  const asOf = usePanelAsOf(params.pin);
  const mode = useT((s) => s.mode);
  const g = useGeo(asOf);
  const [sel, setSel] = useState<string | null>(null);
  const chosen = g.data?.chokepoints.find((c) => c.id === sel) ?? null;
  return (
    <div className="t-panel geo">
      <PanelState q={g}>
        {() => {
          const geo = g.data!;
          const ranked = geo.chokepoints.slice().sort((a, b) => b.intensity - a.intensity);
          return (
            <div className="tx-main">
              <div className="tx-left">
                {mode === "cinema" ? (
                  <div className="tx-scene">
                    <ExposureGlobe chokes={geo.chokepoints} corridors={geo.corridors} selected={sel} onSelect={setSel} />
                    <div className="tx-scene-cap">Rings grow and redden with the number of dated news items in the last three months, against the area’s own history. Lines are India’s trade arteries. Click a ring.</div>
                  </div>
                ) : (
                  <FlatMap geo={geo} selected={sel} onSelect={setSel} />
                )}
              </div>
              <div className="tx-right">
                <table className="t-table tx-tab">
                  <thead><tr><th>Chokepoint</th><th>3-mo items</th><th>Intensity</th></tr></thead>
                  <tbody>
                    {ranked.map((c) => (
                      <tr key={c.id} className={sel === c.id ? "sel" : ""} onClick={() => setSel(sel === c.id ? null : c.id)}>
                        <td>{c.label}</td><td className="mono">{c.last_90d}</td>
                        <td className="tx-bar-cell"><i className={c.intensity > 0.75 ? "dn" : "up"} style={{ width: `${Math.max(4, c.intensity * 100)}%` }} /></td>
                      </tr>
                    ))}
                  </tbody>
                </table>
                {chosen ? <ChokeDetail c={chosen} asOf={asOf} /> : <div className="tx-help">Pick a chokepoint to see what it carries, how it reaches Indian sectors, and the latest dated items. {geo.note}</div>}
              </div>
            </div>
          );
        }}
      </PanelState>
    </div>
  );
}
