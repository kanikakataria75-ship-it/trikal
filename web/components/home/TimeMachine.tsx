"use client";

/* §1 THE TIME MACHINE — the market, exactly as it stood on one day.
   Everything on this stage is rebuilt from that day's exchange file and the index membership of that day.
   The only look forward is the "What happened next" toggle, which is labelled as hindsight and drawn apart. */

import dynamic from "next/dynamic";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { AnimatePresence, motion } from "framer-motion";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { api, type Envelope, type MarketDay, type Mover } from "@/lib/api";
import { dmy, indianGroup, todayIST } from "@/lib/format";
import type { Placed, Tile } from "@/components/three/MarketCity";
import s from "./timemachine.module.css";

const MarketCity = dynamic(() => import("@/components/three/MarketCity"), { ssr: false });

type PathPt = { d: string; r: number | null; adv: number; dec: number; n: number };
type TM = Envelope & {
  market: MarketDay;
  map: { session: string; tiles: Tile[]; universe: "nifty500" | "all_equities"; members_total: number };
  before: PathPt[];
  marquee: { code: string; close: number; today_terms: number; factor: number }[];
  hindsight: null | { after: PathPt[]; m1: number | null; m3: number | null; y1: number | null; sessions: number; still_trading_today: number; members: number; note: string };
  tape?: { kind: "corporate_action" | "results" | "index"; code: string; text: string }[];
  context?: { world: Ctx[]; india: Ctx[]; licence: string; note: string };
};

/* Built-in days. The context line is editorial (what was happening); every number on screen is data. */
const EVENTS: { d: string; t: string; c: string }[] = [
  { d: "1994-11-03", t: "Day one", c: "The first session of the National Stock Exchange’s equity market." },
  { d: "1998-05-12", t: "Pokhran-II", c: "The morning after India’s nuclear tests; sanctions were expected." },
  { d: "2000-02-29", t: "Dot-com Budget", c: "Union Budget day, at the height of the technology boom." },
  { d: "2004-05-17", t: "Black Monday ’04", c: "Days after an unexpected election result, trading was halted as prices collapsed." },
  { d: "2006-05-22", t: "May ’06 sell-off", c: "Days after record highs, a violent global sell-off reached Dalal Street." },
  { d: "2008-01-21", t: "January ’08 crash", c: "A global rout began; the bull market of the mid-2000s was ending." },
  { d: "2008-10-24", t: "Lehman autumn", c: "Weeks after Lehman Brothers failed, foreign money was fleeing." },
  { d: "2009-05-18", t: "Election euphoria", c: "Results day: the market hit its upper circuit and trading stopped." },
  { d: "2013-08-28", t: "Taper tantrum", c: "The rupee hit a record low against the dollar." },
  { d: "2014-05-16", t: "Results day ’14", c: "The general-election count, live." },
  { d: "2016-06-24", t: "Brexit", c: "The morning after Britain voted to leave the European Union." },
  { d: "2016-11-09", t: "Demonetisation", c: "The morning after ₹500 and ₹1,000 notes were withdrawn." },
  { d: "2019-09-20", t: "Tax-cut rally", c: "A surprise corporate tax cut was announced that morning." },
  { d: "2020-03-23", t: "COVID crash", c: "Pandemic panic swept every market in the world." },
  { d: "2021-02-01", t: "Budget ’21", c: "A spending-led Budget the market loved." },
  { d: "2023-01-27", t: "Adani rout", c: "Adani group stocks fell after a short-seller’s report." },
  { d: "2024-06-04", t: "Results day ’24", c: "The general-election count surprised the market." },
  { d: "NOW", t: "Today", c: "The last session in the archive." },
];

const WEEKDAY = ["SUNDAY", "MONDAY", "TUESDAY", "WEDNESDAY", "THURSDAY", "FRIDAY", "SATURDAY"];
const MONTH = ["JANUARY", "FEBRUARY", "MARCH", "APRIL", "MAY", "JUNE", "JULY", "AUGUST", "SEPTEMBER", "OCTOBER", "NOVEMBER", "DECEMBER"];
const pct = (x: number | null | undefined, d = 1) => (x === null || x === undefined ? "—" : `${x > 0 ? "+" : x < 0 ? "−" : ""}${Math.abs(x * 100).toFixed(d)}%`);

function useTM(date: string, hindsight: boolean) {
  return useQuery({
    queryKey: ["tm", date, hindsight],
    queryFn: () => api<TM>(`/api/timemachine?as_of=${date}&hindsight=${hindsight}`),
    staleTime: Infinity,
    placeholderData: (p) => p,
  });
}

function era(year: number) {
  if (year < 2000) return { name: "THE NINETIES", cls: s.era90 };
  if (year < 2008) return { name: "THE BOOM YEARS", cls: s.era00 };
  if (year < 2014) return { name: "AFTER THE CRASH", cls: s.era08 };
  if (year < 2020) return { name: "THE LONG BULL", cls: s.era14 };
  return { name: "THE 2020s", cls: s.era20 };
}

/* ------------------------------------------------------------------ odometer date */
function Roll({ text }: { text: string }) {
  return (
    <span className={s.roll}>
      {text.split("").map((ch, i) => (
        <span key={i} className={s.rollCell}>
          <AnimatePresence mode="popLayout" initial={false}>
            <motion.span key={ch + i} initial={{ y: "-100%", opacity: 0, filter: "blur(6px)" }} animate={{ y: 0, opacity: 1, filter: "blur(0px)" }}
              exit={{ y: "100%", opacity: 0, filter: "blur(6px)" }} transition={{ duration: 0.55, delay: i * 0.035, ease: [0.22, 1, 0.36, 1] }}>
              {ch === " " ? " " : ch}
            </motion.span>
          </AnimatePresence>
        </span>
      ))}
    </span>
  );
}

/* ------------------------------------------------------------------ breadth gauge */
function Gauge({ adv, dec, unch }: { adv: number; dec: number; unch: number }) {
  const total = Math.max(1, adv + dec + unch);
  const share = adv / Math.max(1, adv + dec);          // 0 = all fell, 1 = all rose
  const ang = -90 + share * 180;
  const L = "M16,92 A74,74 0 0 1 164,92", Rv = "M164,92 A74,74 0 0 0 16,92";
  return (
    <div className={s.gauge}>
      <svg viewBox="0 0 180 104" width="100%">
        <path d={L} stroke="rgba(38,43,51,0.9)" strokeWidth={9} fill="none" />
        <motion.path d={L} stroke="#39FF88" strokeWidth={9} fill="none" initial={false} animate={{ pathLength: share }} transition={{ duration: 1.1, ease: [0.22, 1, 0.36, 1] }} />
        <motion.path d={Rv} stroke="#FF2E63" strokeWidth={9} fill="none" initial={false} animate={{ pathLength: 1 - share }} transition={{ duration: 1.1, ease: [0.22, 1, 0.36, 1] }} />
        {Array.from({ length: 11 }).map((_, i) => {
          const a = (i / 10) * Math.PI;
          return <line key={i} x1={90 - Math.cos(a) * 60} y1={92 - Math.sin(a) * 60} x2={90 - Math.cos(a) * 55} y2={92 - Math.sin(a) * 55} stroke="#3A414C" strokeWidth={1} />;
        })}
        <motion.g initial={false} animate={{ rotate: ang }} transition={{ type: "spring", stiffness: 60, damping: 11 }} style={{ originX: "90px", originY: "92px" }}>
          <line x1={90} y1={92} x2={90} y2={30} stroke="#F2D27A" strokeWidth={2} strokeLinecap="round" />
        </motion.g>
        <circle cx={90} cy={92} r={5} fill="#0d0f12" stroke="#F2D27A" strokeWidth={1.5} />
      </svg>
      <div className={s.gaugeRow}>
        <span className="neg mono">{indianGroup(dec)}<i>fell</i></span>
        <span className="mono">{indianGroup(unch)}<i>flat</i></span>
        <span className="pos mono">{indianGroup(adv)}<i>rose</i></span>
      </div>
      <div className={s.gaugeCap}>{indianGroup(total)} stocks traded</div>
    </div>
  );
}

/* ------------------------------------------------------------------ context path (+ hindsight) */
function Path({ before, after, session, y1 }: { before: PathPt[]; after: PathPt[] | null; session: string; y1: number | null }) {
  const ref = useRef<HTMLDivElement>(null);
  const [w, setW] = useState(0);
  useEffect(() => {
    if (!ref.current) return;
    const ro = new ResizeObserver((e) => setW(e[0].contentRect.width));
    ro.observe(ref.current);
    return () => ro.disconnect();
  }, []);
  const H = 96;
  const pts = useMemo(() => {
    const out: { d: string; v: number; f: boolean; b: number }[] = [];
    let v = 100;
    for (const p of before) { v *= 1 + (p.r ?? 0); out.push({ d: p.d, v, f: false, b: p.n ? (p.adv - p.dec) / p.n : 0 }); }
    const base = out.length ? out[0].v / (1 + (before[0].r ?? 0)) : 100;
    for (const p of after ?? []) { v *= 1 + (p.r ?? 0); out.push({ d: p.d, v, f: true, b: p.n ? (p.adv - p.dec) / p.n : 0 }); }
    return out.map((x) => ({ ...x, v: (x.v / base) * 100 }));
  }, [before, after]);
  if (!pts.length) return <div ref={ref} className={s.path} />;
  const vs = pts.map((p) => p.v);
  const lo = Math.min(...vs), hi = Math.max(...vs);
  const X = (i: number) => 8 + (i / Math.max(1, pts.length - 1)) * (w - 16);
  const Y = (v: number) => 10 + (1 - (v - lo) / Math.max(1e-9, hi - lo)) * (H - 26);
  const k = pts.findIndex((p) => p.f) - 1;
  const today = k >= 0 ? k : pts.length - 1;
  const d1 = pts.slice(0, today + 1).map((p, i) => `${i ? "L" : "M"}${X(i).toFixed(1)},${Y(p.v).toFixed(1)}`).join("");
  const d2 = pts.slice(today).map((p, i) => `${i ? "L" : "M"}${X(today + i).toFixed(1)},${Y(p.v).toFixed(1)}`).join("");
  const area = `${d1}L${X(today)},${H - 14}L${X(0)},${H - 14}Z`;
  return (
    <div ref={ref} className={s.path}>
      {w > 0 && (
        <svg width={w} height={H}>
          <defs>
            <linearGradient id="tm-a" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stopColor="rgba(212,175,55,0.28)" /><stop offset="1" stopColor="rgba(212,175,55,0)" /></linearGradient>
          </defs>
          {pts.map((p, i) => (
            <rect key={i} x={X(i) - 0.6} width={1.2} y={p.b >= 0 ? H - 14 - p.b * 10 : H - 14} height={Math.abs(p.b) * 10} fill={p.b >= 0 ? "rgba(57,255,136,0.55)" : "rgba(255,46,99,0.55)"} opacity={p.f ? 0.35 : 0.8} />
          ))}
          <path d={area} fill="url(#tm-a)" />
          <motion.path key={session} d={d1} fill="none" stroke="#D4AF37" strokeWidth={1.6} initial={{ pathLength: 0 }} animate={{ pathLength: 1 }} transition={{ duration: 1.2 }} />
          {after && after.length > 0 && <motion.path d={d2} fill="none" stroke={(y1 ?? 0) >= 0 ? "#39FF88" : "#FF2E63"} strokeWidth={1.4} strokeDasharray="4 3" initial={{ pathLength: 0 }} animate={{ pathLength: 1 }} transition={{ duration: 1.6, delay: 0.3 }} />}
          <line x1={X(today)} x2={X(today)} y1={4} y2={H - 14} stroke="#F2D27A" strokeWidth={1} strokeDasharray="2 2" />
          <circle cx={X(today)} cy={Y(pts[today].v)} r={4} fill="#F2D27A" className={s.here} />
          <text x={X(today) + (today > pts.length * 0.8 ? -8 : 8)} y={14} fill="#F2D27A" fontSize={9.5} letterSpacing="0.16em" textAnchor={today > pts.length * 0.8 ? "end" : "start"}>THIS DAY</text>
          {after && after.length > 0 && (
            <text x={w - 10} y={Y(pts[pts.length - 1].v) - 8} textAnchor="end" fontSize={10.5} fill={(y1 ?? 0) >= 0 ? "#39FF88" : "#FF2E63"} className="mono">
              {pct(y1, 0)} a year later · hindsight
            </text>
          )}
          <text x={8} y={H - 2} fontSize={9} fill="#6B7079" className="mono">{dmy(pts[0].d)}</text>
          {after && after.length > 0 && <text x={w - 8} y={H - 2} fontSize={9} fill="#6B7079" textAnchor="end" className="mono">{dmy(pts[pts.length - 1].d)}</text>}
        </svg>
      )}
    </div>
  );
}

type Ctx = { day: string; scope: "world" | "india"; category: string | null; story: string | null; text: string; source_name: string | null; source_url: string | null; page: string };

const wikiUrl = (page: string) => `https://en.wikipedia.org/wiki/${encodeURI(page)}`;
const shortDate = (iso: string) => dmy(iso).slice(0, 6);

/* ------------------------------------------------------------------ the news lower-third (our own design) */
function Ticker({ data, session, headline, live }: { data: TM; session: string; headline: string; live: boolean }) {
  const m = data.market;
  const isNow = live;
  const items = useMemo(() => {
    const out: { tag: string; text: string; tone?: "up" | "down" | "news" | "world" | "india"; src?: string }[] = [];
    if (m.securities) {
      out.push({ tag: "BREADTH", text: `${indianGroup(m.advances)} up · ${indianGroup(m.declines)} down · median ${pct(m.median_change, 2)}` });
      if (m.members_eqw_change !== null) out.push({ tag: "NIFTY 500 EW", text: pct(m.members_eqw_change, 2), tone: m.members_eqw_change >= 0 ? "up" : "down" });
      for (const x of m.losers.slice(0, 4)) out.push({ tag: x.code, text: `${pct(x.change)} at ₹${x.close.toLocaleString("en-IN")}`, tone: "down" });
      for (const x of m.gainers.slice(0, 4)) out.push({ tag: x.code, text: `${pct(x.change)} at ₹${x.close.toLocaleString("en-IN")}`, tone: "up" });
    }
    for (const x of data.marquee.slice(0, 5)) out.push({ tag: x.code, text: `closes ₹${x.close.toLocaleString("en-IN", { maximumFractionDigits: 2 })}` });
    for (const t of (data.tape ?? []).slice(0, 10)) out.push({ tag: t.kind === "index" ? "INDEX" : t.kind === "results" ? "RESULTS" : "CORP ACTION", text: t.text, tone: "news" });
    const exact = (c: Ctx[]) => [...c.filter((x) => x.day === session), ...c.filter((x) => x.day !== session)];
    const biz = (c: Ctx[]) => [...c.filter((x) => (x.category ?? "").startsWith("Business")), ...c.filter((x) => !(x.category ?? "").startsWith("Business"))];
    for (const x of exact(data.context?.india ?? []).slice(0, 4)) out.push({ tag: x.day === session ? "INDIA" : `INDIA · ${shortDate(x.day)}`, text: x.text, tone: "india", src: x.source_name ?? "Wikipedia" });
    for (const x of biz(exact(data.context?.world ?? [])).slice(0, 6)) out.push({ tag: x.day === session ? "WORLD" : `WORLD · ${shortDate(x.day)}`, text: x.text, tone: "world", src: x.source_name ?? "Wikipedia" });
    return out;
  }, [data, m, session]);
  const dur = Math.max(40, items.reduce((a, x) => a + x.text.length + x.tag.length, 0) / 9);  // constant reading speed
  return (
    <div className={s.ticker}>
      <div className={s.tkTop}>
        <span className={s.tkBug}><i />{isNow ? "LIVE" : "ARCHIVE"}</span>
        <span className={s.tkDate}>{dmy(session)}</span>
        <AnimatePresence mode="wait">
          <motion.b key={headline} initial={{ y: 14, opacity: 0 }} animate={{ y: 0, opacity: 1 }} exit={{ y: -14, opacity: 0 }} transition={{ duration: 0.4 }}>{headline}</motion.b>
        </AnimatePresence>
        <span className={s.tkBrand}>TRIKAL</span>
      </div>
      <div className={s.tkCrawl}>
        <div key={session} className={s.tkTrack} style={{ animationDuration: `${dur}s` }}>
          {[...items, ...items].map((x, i) => (
            <span key={i} className={`${s.tkItem} ${x.tone ? s["tk_" + x.tone] : ""}`}>
              <em>{x.tag}</em>{x.text}{x.src && <small>· {x.src}</small>}
            </span>
          ))}
        </div>
      </div>
    </div>
  );
}

/* ------------------------------------------------------------------ the world that day */
function WorldDrawer({ data, session, onClose }: { data: TM; session: string; onClose: () => void }) {
  const c = data.context;
  const group = (xs: Ctx[]) => {
    const byDay = new Map<string, Ctx[]>();
    for (const x of xs) byDay.set(x.day, [...(byDay.get(x.day) ?? []), x]);
    return [...byDay.entries()].sort((a, b) => b[0].localeCompare(a[0]));
  };
  const Section = ({ title, xs }: { title: string; xs: Ctx[] }) => (
    <div className={s.wdSec}>
      <div className={s.wdHead}>{title}</div>
      {xs.length === 0 && <div className={s.wdNone}>Nothing recorded for these days.</div>}
      {group(xs).map(([day, list]) => (
        <div key={day} className={s.wdDay}>
          <div className={s.wdDate}>{day === session ? "THAT DAY" : dmy(day)}</div>
          {list.slice(0, 14).map((x, i) => (
            <div key={i} className={s.wdItem}>
              {x.category && <span className={s.wdCat}>{x.category}</span>}
              <p>{x.text}</p>
              <div className={s.wdSrc}>
                {x.source_url && <a href={x.source_url} target="_blank" rel="noreferrer noopener">{x.source_name ?? "source"} ↗</a>}
                <a href={wikiUrl(x.page)} target="_blank" rel="noreferrer noopener">Wikipedia ↗</a>
              </div>
            </div>
          ))}
        </div>
      ))}
    </div>
  );
  return (
    <motion.aside className={s.drawer} initial={{ x: "100%" }} animate={{ x: 0 }} exit={{ x: "100%" }} transition={{ type: "spring", stiffness: 260, damping: 32 }}>
      <div className={s.wdTop}>
        <div>
          <span>MEANWHILE</span>
          <b className="display">The world around {dmy(session)}</b>
        </div>
        <button onClick={onClose} aria-label="Close">✕</button>
      </div>
      <div className={s.wdScroll}>
        <Section title="India" xs={c?.india ?? []} />
        <Section title="World" xs={c?.world ?? []} />
      </div>
      <div className={s.wdFoot}>
        Summaries by {c?.licence ?? "Wikipedia contributors · CC BY-SA 4.0"}. Written after the fact by editors — context, never data:
        nothing here feeds a number in TRIKAL. Only items dated on or before the session are shown.
      </div>
    </motion.aside>
  );
}

function MoverList({ title, rows }: { title: string; rows: Mover[] }) {
  return (
    <div className={s.mlist}>
      <div className={s.mhead}>{title}</div>
      {rows.slice(0, 5).map((r) => (
        <div key={r.code} className={s.mrow}>
          <b className="mono">{r.code}{r.trades_today === false && <sup>†</sup>}</b>
          <span className={`mono ${r.change >= 0 ? "pos" : "neg"}`}>{pct(r.change)}</span>
        </div>
      ))}
    </div>
  );
}

/* ------------------------------------------------------------------ the stage */
export default function TimeMachine() {
  const router = useRouter();
  const qc = useQueryClient();
  const [date, setDate] = useState("2008-10-24");
  const [mode, setMode] = useState<"close" | "open">("close");
  const [hind, setHind] = useState(false);
  const [tour, setTour] = useState(false);
  const [custom, setCustom] = useState("");
  const [hover, setHover] = useState<{ p: Placed; x: number; y: number } | null>(null);
  const [world, setWorld] = useState(false);
  const stage = useRef<HTMLDivElement>(null);
  const [full, setFull] = useState(false);
  useEffect(() => {
    const onFs = () => { if (!document.fullscreenElement) setFull(false); };
    const onKey = (e: KeyboardEvent) => { if (e.key === "Escape") setFull(false); };
    document.addEventListener("fullscreenchange", onFs);
    window.addEventListener("keydown", onKey);
    return () => { document.removeEventListener("fullscreenchange", onFs); window.removeEventListener("keydown", onKey); };
  }, []);
  useEffect(() => { document.body.style.overflow = full ? "hidden" : ""; }, [full]);
  const toggleFull = async () => {
    if (full) {
      if (document.fullscreenElement) await document.exitFullscreen().catch(() => {});
      setFull(false);
      return;
    }
    setFull(true); // covers the window even where the Fullscreen API is blocked (embedded browsers, iframes)
    try { await stage.current?.requestFullscreen?.(); } catch { /* the CSS fallback stays on */ }
  };
  const { data, isFetching, error } = useTM(date, hind);
  const m = data?.market;
  const sess = m?.session ?? (date === "NOW" ? todayIST() : date);
  const year = +sess.slice(0, 4);
  const er = era(year);
  const ev = EVENTS.find((e) => e.d === date);

  const prefetch = useCallback((d: string) => qc.prefetchQuery({ queryKey: ["tm", d, hind], queryFn: () => api<TM>(`/api/timemachine?as_of=${d}&hindsight=${hind}`), staleTime: Infinity }), [qc, hind]);

  // tour mode for recording: walk through history, eight seconds a day
  useEffect(() => {
    if (!tour) return;
    setHind(true);
    const days = EVENTS.filter((e) => e.d !== "NOW").map((e) => e.d);
    let i = Math.max(0, days.indexOf(date));
    const t = setInterval(() => { i = (i + 1) % days.length; setDate(days[i]); prefetch(days[(i + 1) % days.length]); }, 8000);
    return () => clearInterval(t);
  }, [tour]); // eslint-disable-line react-hooks/exhaustive-deps

  const step = (dir: 1 | -1) => {
    const base = new Date((m?.session ?? todayIST()) + "T00:00:00Z");
    base.setUTCDate(base.getUTCDate() + (dir === 1 ? 4 : -1));      // the API returns the last session on or before the date
    const iso = base.toISOString().slice(0, 10);
    if (iso > todayIST()) return setDate("NOW");
    setDate(iso);
  };

  const headline = useMemo(() => {
    if (!m) return { h: "", sub: "" };
    if (!m.securities) return { h: `${indianGroup(data!.map.tiles.length)} companies traded. There was no yesterday.`, sub: "Without a previous close there is no change to report — only first prints." };
    const big = [...m.gainers, ...m.losers].sort((a, b) => Math.abs(b.change) - Math.abs(a.change))[0];
    const h = m.declines > m.advances * 1.6 ? `${indianGroup(m.declines)} stocks fell. ${indianGroup(m.advances)} rose.`
      : m.advances > m.declines * 1.6 ? `${indianGroup(m.advances)} stocks rose. ${indianGroup(m.declines)} fell.`
        : `A divided market: ${indianGroup(m.advances)} up, ${indianGroup(m.declines)} down.`;
    const idx = data!.map.universe === "nifty500" ? `Nifty 500 members, equal weight ${pct(m.members_eqw_change, 2)}` : "Before the Nifty 500 existed: the day’s 500 most-traded stocks";
    return { h, sub: `${idx}${big ? ` · biggest move ${big.code} ${pct(big.change)}` : ""}` };
  }, [m, data]);

  const d = new Date(sess + "T00:00:00Z");
  const dateText = `${String(d.getUTCDate()).padStart(2, "0")} ${MONTH[d.getUTCMonth()].slice(0, 3)} ${d.getUTCFullYear()}`;

  return (
    <section id="market" className={s.section}>
      <div ref={stage} className={`${s.stage} ${er.cls} ${full ? s.full : ""}`}>
        <div className={s.grade} />
        <div className={s.grain} />

        {/* masthead: its own band, never drawn over the city */}
        <header className={s.mast}>
          <div className={s.mastTop}>
            <span>§1 · THE TIME MACHINE</span>
            <span className={s.mastEra}>{er.name}</span>
            <span>{m ? `${indianGroup(m.securities || data!.map.tiles.length)} SECURITIES ON THE TAPE` : "…"}</span>
          </div>
          <div className={s.mastBody}>
            <div className={s.mastDate}>
              <span className={s.weekday}>{WEEKDAY[d.getUTCDay()]}</span>
              <Roll text={dateText} />
            </div>
            <AnimatePresence mode="wait">
              <motion.div key={sess + headline.h} className={s.headline} initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: -6 }} transition={{ duration: 0.5, delay: 0.2 }}>
                <h2 className="display">{headline.h}</h2>
                <p>{headline.sub}</p>
                {ev && <p className={s.context}>{ev.c}</p>}
                {date !== "NOW" && m && m.session !== date && <p className={s.holiday}>No session on {dmy(date)} — showing the last one before it.</p>}
              </motion.div>
            </AnimatePresence>
          </div>
        </header>

        {/* event rail */}
        <nav className={s.rail} aria-label="Historic days">
          {EVENTS.map((e) => (
            <button key={e.d} className={date === e.d ? s.on : ""} onClick={() => { setTour(false); setDate(e.d); }} onMouseEnter={() => prefetch(e.d)}>
              <span className="mono">{e.d === "NOW" ? "NOW" : e.d.slice(0, 4)}</span>
              <b>{e.t}</b>
            </button>
          ))}
          <form onSubmit={(e) => { e.preventDefault(); if (/^\d{4}-\d{2}-\d{2}$/.test(custom)) { setTour(false); setDate(custom); } }}>
            <input type="date" min="1994-11-03" max={todayIST()} value={custom} onChange={(e) => setCustom(e.target.value)} aria-label="Any date" />
            <button type="submit">Go</button>
          </form>
        </nav>

        {/* the city gets its own clear window */}
        <div className={`${s.city} ${year < 2000 ? s.tv90 : year < 2008 ? s.tv00 : year < 2014 ? s.tv08 : ""}`}>
          {year < 2008 && <div className={s.scan} />}
          {data && <MarketCity tiles={data.map.tiles} mode={mode} arrive={Date.parse(sess)} onPick={(p) => router.push(`/terminal?code=${encodeURIComponent(p.t.code)}&asof=${sess}`)}
            onHover={(p, x, y) => setHover(p && x !== undefined && y !== undefined ? { p, x, y } : null)} />}
          <AnimatePresence>
            <motion.div key={sess} className={s.flash} initial={{ opacity: 0.9 }} animate={{ opacity: 0 }} transition={{ duration: 1.1, ease: "easeOut" }} />
          </AnimatePresence>
          {data && <Ticker data={data} session={sess} headline={headline.h} live={date === "NOW"} />}
          <AnimatePresence>{world && data && <WorldDrawer data={data} session={sess} onClose={() => setWorld(false)} />}</AnimatePresence>
          <div className={s.cityKey}>
            <span><i className={s.kUp} />rose · height = size of move</span>
            <span><i className={s.kDown} />fell · sinks below the floor</span>
            <span>area = turnover · drag to orbit · scroll to zoom · click a tile</span>
          </div>
          {(isFetching || (!data && !error)) && <div className={s.loading}><i />rebuilding {date === "NOW" ? "today" : dmy(date)}…</div>}
          {error && !data && <div className={s.loading}>Time machine offline — is the API running?</div>}
        </div>

        {/* instrument cluster */}
        <aside className={s.cluster}>
          {m && <Gauge adv={m.advances} dec={m.declines} unch={m.unchanged} />}
          {m && (
            <div className={s.kpis}>
              <div><span>Median stock</span><b className={`mono ${(m.median_change ?? 0) >= 0 ? "pos" : "neg"}`}>{pct(m.median_change, 2)}</b></div>
              <div><span>Turnover</span><b className="mono">₹{indianGroup(m.turnover / 1e7)} Cr</b></div>
            </div>
          )}
          {data && data.marquee.length > 0 && (
            <div className={s.prices}>
              <div className={s.pricesHead}><span>Close that day</span><span>in today’s shares</span></div>
              {data.marquee.map((x) => (
                <div key={x.code} className={s.priceRow} title={x.factor !== 1 ? `Splits & bonuses since: one share then = ${(1 / x.factor).toFixed(x.factor < 0.1 ? 0 : 2)} shares today` : "No split or bonus since"}>
                  <b className="mono">{x.code}</b>
                  <span className="mono">₹{x.close.toLocaleString("en-IN", { maximumFractionDigits: 2 })}</span>
                  <em className="mono">{x.factor !== 1 ? `≈ ₹${x.today_terms.toLocaleString("en-IN", { maximumFractionDigits: x.today_terms < 100 ? 2 : 0 })}` : "same"}</em>
                </div>
              ))}
              <i>Left: the price printed that day. Right: the same money in today’s shares, after every split and bonus since.</i>
            </div>
          )}
          {m && m.gainers.length > 0 && (
            <div className={s.movers}>
              <MoverList title="Led" rows={m.gainers} />
              <MoverList title="Lagged" rows={m.losers} />
            </div>
          )}
        </aside>

        {/* bottom deck */}
        <div className={s.deck}>
          <div className={s.controls}>
            <button onClick={() => step(-1)} title="Previous session">◀ prev day</button>
            <button onClick={() => step(1)} title="Next session">next day ▶</button>
            <div className={s.seg}>
              <button className={mode === "open" ? s.segOn : ""} onClick={() => setMode("open")}>09:15 · at the open</button>
              <button className={mode === "close" ? s.segOn : ""} onClick={() => setMode("close")}>15:30 · at the close</button>
            </div>
            <button className={`${s.hind} ${hind ? s.hindOn : ""}`} onClick={() => setHind((x) => !x)}>
              {hind ? "◉" : "○"} What happened next <i>hindsight</i>
            </button>
            <span className={s.sp} />
            <button className={tour ? s.hindOn : ""} onClick={() => setTour((x) => !x)}>{tour ? "■ Stop tour" : "▶ Tour history"}</button>
            <button className={world ? s.hindOn : ""} onClick={() => setWorld((x) => !x)}>☰ The world that day{data?.context ? ` · ${data.context.india.length + data.context.world.length}` : ""}</button>
            <button onClick={toggleFull}>{full ? "✕ Exit full screen" : "⤢ Full screen"}</button>
          </div>
          <div className={s.deckRow}>
            <div className={s.deckPath}>
              <div className={s.deckLbl}>
                {data?.map.universe === "nifty500" ? "That day’s Nifty 500 members, equal weight — the four months before" : "The day’s most-traded stocks — the months before"}
              </div>
              {data && <Path before={data.before} after={hind ? data.hindsight?.after ?? null : null} session={sess} y1={data.hindsight?.y1 ?? null} />}
            </div>
            {hind && data?.hindsight && (
              <div className={s.after}>
                <div className={s.deckLbl}>Hindsight · same {data.hindsight.members} companies</div>
                <div><span>1 month</span><b className={`mono ${(data.hindsight.m1 ?? 0) >= 0 ? "pos" : "neg"}`}>{pct(data.hindsight.m1)}</b></div>
                <div><span>3 months</span><b className={`mono ${(data.hindsight.m3 ?? 0) >= 0 ? "pos" : "neg"}`}>{pct(data.hindsight.m3)}</b></div>
                <div><span>1 year</span><b className={`mono ${(data.hindsight.y1 ?? 0) >= 0 ? "pos" : "neg"}`}>{pct(data.hindsight.y1)}</b></div>
                <div><span>Still trade today</span><b className="mono">{data.hindsight.still_trading_today}/{data.hindsight.members}</b></div>
              </div>
            )}
          </div>
        </div>

        {hover && (
          <div className={s.tip} style={{ left: Math.min(hover.x + 16, (typeof window !== "undefined" ? window.innerWidth : 1600) - 280), top: Math.min(hover.y + 14, (typeof window !== "undefined" ? window.innerHeight : 900) - 210) }}>
            <div className={s.tipCode}>{hover.p.t.code}<span>{hover.p.t.sector ?? "unclassified"}</span></div>
            <div className={s.tipName}>{hover.p.t.name}</div>
            <div className={s.tipGrid}>
              <span>Open</span><b className="mono">{hover.p.t.open?.toLocaleString("en-IN") ?? "—"}</b>
              <span>Close</span><b className="mono">{hover.p.t.close.toLocaleString("en-IN")}</b>
              <span>Gap at open</span><b className={`mono ${(hover.p.t.gap ?? 0) >= 0 ? "pos" : "neg"}`}>{pct(hover.p.t.gap)}</b>
              <span>Day change</span><b className={`mono ${(hover.p.t.change ?? 0) >= 0 ? "pos" : "neg"}`}>{hover.p.t.comparable ? pct(hover.p.t.change) : "n/a · ex-date"}</b>
              <span>Turnover</span><b className="mono">₹{indianGroup(hover.p.t.turnover / 1e7)} Cr</b>
            </div>
            <div className={s.tipFoot}>click to open {hover.p.t.code} in the terminal, as of this day</div>
          </div>
        )}
      </div>
      <p className={s.foot}>
        Rebuilt from that day’s NSE bhavcopy and the Nifty 500 membership known on that day. Tile area = turnover, height = the day’s move
        (rising above the floor, sinking below it). Sector labels before 2011 are partly reconstructed. <b>†</b> no longer trades today.
        “What happened next” and “in today’s shares” use today’s data on purpose and are labelled. <Link href="/terminal">Open the terminal →</Link>
      </p>
    </section>
  );
}
