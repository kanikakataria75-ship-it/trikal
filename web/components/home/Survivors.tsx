"use client";

/* §2 Survivorship.
   Left: every Nifty 500 cohort (30 June of each year) as a stacked area — still trading today, vanished since,
   and old index names never matched to a security (fate unknown, shown as its own band, never guessed).
   Right: the selected cohort as one cell per real company. The vanished fade to ghosts in the order they
   died, while a counter runs through the years. Hover any cell for the company. */

import { motion, useInView } from "framer-motion";
import { useEffect, useMemo, useRef, useState } from "react";
import { useSurvivors, type Fate, type Showcase } from "@/lib/api";
import { dmy, indianGroup } from "@/lib/format";
import s from "./survivors.module.css";

type Row = Showcase["strata"][number];

function useWidth<T extends HTMLElement>() {
  const ref = useRef<T>(null);
  const [w, setW] = useState(0);
  useEffect(() => {
    if (!ref.current) return;
    const ro = new ResizeObserver((e) => setW(e[0].contentRect.width));
    ro.observe(ref.current);
    return () => ro.disconnect();
  }, []);
  return [ref, w] as const;
}

/* ------------------------------------------------------------------ cohort area chart */
function Cohorts({ rows, selected, onSelect }: { rows: Row[]; selected: string; onSelect: (year: string) => void }) {
  const [ref, w] = useWidth<HTMLDivElement>();
  const inView = useInView(ref, { once: true, margin: "-15%" });
  const [hover, setHover] = useState<number | null>(null);
  const H = 380, padL = 40, padR = 14, padT = 18, padB = 30;
  const n = rows.length;
  const max = Math.max(540, ...rows.map((r) => r.members));
  const X = (i: number) => padL + (i / Math.max(1, n - 1)) * (w - padL - padR);
  const Y = (v: number) => padT + (1 - v / max) * (H - padT - padB);
  const band = (lo: (r: Row) => number, hi: (r: Row) => number) =>
    rows.map((r, i) => `${i ? "L" : "M"}${X(i).toFixed(1)},${Y(hi(r)).toFixed(1)}`).join("") +
    rows.map((_, k) => { const i = n - 1 - k; return `L${X(i).toFixed(1)},${Y(lo(rows[i])).toFixed(1)}`; }).join("") + "Z";
  const line = (f: (r: Row) => number) => rows.map((r, i) => `${i ? "L" : "M"}${X(i).toFixed(1)},${Y(f(r)).toFixed(1)}`).join("");
  const alive = (r: Row) => r.still_trading;
  const goneTop = (r: Row) => r.still_trading + r.gone;
  const all = (r: Row) => r.members;
  const sel = rows.findIndex((r) => r.date.slice(0, 4) === selected);
  const focus = hover ?? sel;
  const fr = focus >= 0 ? rows[focus] : null;
  const pick = (clientX: number) => {
    const b = ref.current!.getBoundingClientRect();
    const i = Math.round(((clientX - b.left - padL) / (w - padL - padR)) * (n - 1));
    return Math.max(0, Math.min(n - 1, i));
  };
  // a label position inside the vanished band where it is thickest
  const thick = rows.reduce((b, r, i) => (r.gone > rows[b].gone ? i : b), 0);

  return (
    <div ref={ref} className={s.cohorts}>
      {w > 0 && rows.length > 1 && (
        <svg width={w} height={H} onMouseMove={(e) => setHover(pick(e.clientX))} onMouseLeave={() => setHover(null)}
          onClick={(e) => onSelect(rows[pick(e.clientX)].date.slice(0, 4))} style={{ cursor: "crosshair", display: "block" }}>
          <defs>
            <linearGradient id="sv-alive" x1="0" y1="0" x2="0" y2="1">
              <stop offset="0" stopColor="#2a3039" />
              <stop offset="1" stopColor="#111419" />
            </linearGradient>
            <pattern id="sv-gone" width="5" height="5" patternUnits="userSpaceOnUse" patternTransform="rotate(45)">
              <rect width="5" height="5" fill="rgba(240,87,122,0.10)" />
              <rect width="1.4" height="5" fill="rgba(240,87,122,0.75)" />
            </pattern>
            <pattern id="sv-unres" width="5" height="5" patternUnits="userSpaceOnUse">
              <circle cx="2.5" cy="2.5" r="0.8" fill="#6B7079" />
            </pattern>
            <clipPath id="sv-reveal">
              <motion.rect x={0} y={0} height={H} initial={{ width: 0 }} animate={{ width: inView ? w : 0 }} transition={{ duration: 1.8, ease: [0.22, 1, 0.36, 1] }} />
            </clipPath>
          </defs>
          {[100, 200, 300, 400, 500].map((v) => (
            <g key={v}>
              <line x1={padL} x2={w - padR} y1={Y(v)} y2={Y(v)} stroke="rgba(38,43,51,0.7)" strokeDasharray={v === 500 ? "0" : "2 4"} />
              <text x={padL - 8} y={Y(v) + 3} textAnchor="end" fontSize={9.5} fill="#6B7079" className="mono">{v}</text>
            </g>
          ))}
          <g clipPath="url(#sv-reveal)">
            <path d={band(() => 0, alive)} fill="url(#sv-alive)" />
            <path d={band(alive, goneTop)} fill="url(#sv-gone)" />
            <path d={band(goneTop, all)} fill="url(#sv-unres)" opacity={0.9} />
            <path d={line(alive)} fill="none" stroke="#D4AF37" strokeWidth={1.6} />
            <path d={line(goneTop)} fill="none" stroke="#F0577A" strokeWidth={1} opacity={0.8} />
            <path d={line(all)} fill="none" stroke="#6B7079" strokeWidth={1} strokeDasharray="2 3" />
            <text x={X(Math.floor(n * 0.62))} y={Y(rows[Math.floor(n * 0.62)].still_trading * 0.45)} className={s.areaLbl} textAnchor="middle">STILL TRADING TODAY</text>
            {rows[thick].gone > 40 && (
              <text x={X(thick) + 10} y={(Y(alive(rows[thick])) + Y(goneTop(rows[thick]))) / 2 + 3} className={`${s.areaLbl} ${s.areaGone}`}>VANISHED SINCE</text>
            )}
          </g>
          {rows.map((r, i) => (i % 3 === 0 || i === n - 1) && (
            <text key={r.date} x={X(i)} y={H - 10} textAnchor="middle" fontSize={9.5} fill={i === sel ? "#F2D27A" : "#6B7079"} className="mono">{r.date.slice(0, 4)}</text>
          ))}
          {sel >= 0 && (
            <g>
              <line x1={X(sel)} x2={X(sel)} y1={padT - 6} y2={H - padB} stroke="#D4AF37" strokeWidth={1.2} />
              <circle cx={X(sel)} cy={Y(alive(rows[sel]))} r={3.5} fill="#F2D27A" />
              <circle cx={X(sel)} cy={Y(goneTop(rows[sel]))} r={3} fill="#F0577A" />
            </g>
          )}
          {hover !== null && hover !== sel && (
            <line x1={X(hover)} x2={X(hover)} y1={padT} y2={H - padB} stroke="#A7A9AE" strokeWidth={0.8} strokeDasharray="3 3" />
          )}
        </svg>
      )}
      {fr && (
        <div className={s.readout}>
          <b className="mono">30-JUN-{fr.date.slice(0, 4)}</b>
          <span><i className={s.kAlive} />{fr.still_trading} still trade</span>
          <span><i className={s.kGone} />{fr.gone} vanished · {Math.round((fr.gone / fr.members) * 100)}%</span>
          {fr.unresolved > 0 && <span><i className={s.kUnres} />{fr.unresolved} unidentified</span>}
          <em>{hover !== null && hover !== sel ? "click to open this cohort →" : "selected cohort"}</em>
        </div>
      )}
    </div>
  );
}

/* ------------------------------------------------------------------ one cell per company */
function Cohort({ year }: { year: string }) {
  const on = `${year}-06-30`;
  const { data, isFetching } = useSurvivors(on);
  const box = useRef<HTMLDivElement>(null);
  const inView = useInView(box, { margin: "-10%" });
  const [shown, setShown] = useState(0);       // how many of the vanished have faded so far (death order)
  const [hover, setHover] = useState<Fate | null>(null);
  const [run, setRun] = useState(0);

  const { cells, order } = useMemo(() => {
    const m = data?.on === on ? data.members : [];
    const cells = [...m].sort((a, b) => a.name.localeCompare(b.name));            // the index as a register, A→Z
    const order = new Map(m.filter((x) => x.fate === "gone").sort((a, b) => (a.last_trade ?? "").localeCompare(b.last_trade ?? ""))
      .map((x, i) => [x.security_id, i]));                                        // when each one died
    return { cells, order };
  }, [data, on]);
  const deathOrder = useMemo(() => [...order.entries()].sort((a, b) => a[1] - b[1]).map(([id]) => cells.find((c) => c.security_id === id)!), [order, cells]);

  useEffect(() => {
    if (!inView || !order.size) return;
    setShown(0);
    const total = order.size, dur = 3600;
    let raf = 0;
    const t0 = performance.now() + 500;
    const tick = (t: number) => {
      const p = Math.min(1, Math.max(0, (t - t0) / dur));
      setShown(Math.round((1 - Math.pow(1 - p, 1.6)) * total));
      if (p < 1) raf = requestAnimationFrame(tick);
    };
    raf = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(raf);
  }, [inView, order, run]);

  const last = shown > 0 ? deathOrder[shown - 1] : null;
  const ok = data && data.on === on;
  return (
    <div className={s.cohort}>
      <div className={s.cohortHead}>
        <span>NIFTY 500 · 30 JUNE {year}</span>
        <button onClick={() => setRun((x) => x + 1)} title="Replay">↺ replay</button>
      </div>
      <div className={s.big}>
        <div>
          <b className={`display ${s.bigGone}`}>{ok ? shown : "—"}</b>
          <span>vanished{ok && shown < data!.gone ? "…" : ""}</span>
        </div>
        <div className={s.bigOf}>
          <span>of <b className="mono">{ok ? data!.members.length : "—"}</b> members</span>
          <span className={s.clock}>{last ? <>through <b className="mono">{last.last_trade?.slice(0, 4)}</b></> : <>&nbsp;</>}</span>
        </div>
      </div>
      <div ref={box} className={`${s.grid} ${isFetching && !ok ? s.wait : ""}`} onMouseLeave={() => setHover(null)}>
        {cells.map((c) => {
          const k = order.get(c.security_id);
          const cls = c.fate === "unresolved" ? s.unres : k !== undefined && k < shown ? s.ghost : s.alive;
          return <i key={c.security_id} className={`${s.cell} ${cls} ${hover?.security_id === c.security_id ? s.hot : ""}`} onMouseEnter={() => setHover(c)} />;
        })}
      </div>
      <div className={s.info}>
        {hover ? (
          <>
            <b>{hover.name}</b>
            <span className={hover.fate === "alive" ? "pos" : hover.fate === "gone" ? "neg" : ""}>
              {hover.fate === "alive" ? "still trades today" : hover.fate === "gone" ? `last traded ${dmy(hover.last_trade)}` : "pre-2011 name never matched to a security — fate unknown, not guessed"}
            </span>
          </>
        ) : (
          <span className={s.hint}>Each cell is a real company, A→Z. Hover one.</span>
        )}
      </div>
      {ok && (
        <div className={s.legend}>
          <span><i className={s.lgAlive} /> {data!.alive} still trade</span>
          <span><i className={s.lgGhost} /> {data!.gone} vanished</span>
          {data!.unresolved > 0 && <span><i className={s.lgUnres} /> {data!.unresolved} unidentified</span>}
        </div>
      )}
    </div>
  );
}

export default function Survivors({ data, Head }: { data?: Showcase; Head: React.ComponentType<{ n: string; kicker: string; title: React.ReactNode; children?: React.ReactNode }> }) {
  const rows = (data?.strata ?? []).filter((x) => x.members > 0);
  const [year, setYear] = useState("2006");
  return (
    <section id="survivors" className={s.section}>
      <Head n="§2" kicker="Survivorship" title={<>History is written by the survivors.<br /><em>Ours isn’t.</em></>}>
        Most datasets start from today’s winners and walk backwards, so every backtest built on them is flattered by the
        companies that died on the way. TRIKAL rebuilt Nifty 500 membership from {data ? indianGroup(data.stats.index_press_releases) : "—"} NSE
        press releases and kept every member’s full price history. Pick any year.
      </Head>
      <div className={s.layout}>
        <figure className={s.fig}>
          <figcaption>
            <b>Every Nifty 500 cohort, 1999 → today</b>
            <span>members on 30 June of each year, by what became of them</span>
          </figcaption>
          {rows.length > 0 && <Cohorts rows={rows} selected={year} onSelect={setYear} />}
          <p className={s.note}>
            Older cohorts have lost more of their members: that is time, not luck. Names from pre-2011 press releases that could
            not be matched to a security are shown as their own dotted band — their fate is unknown and is not guessed.
          </p>
        </figure>
        <Cohort year={year} />
      </div>
    </section>
  );
}
