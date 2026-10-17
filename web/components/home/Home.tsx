"use client";

import dynamic from "next/dynamic";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { AnimatePresence, motion, useScroll, useTransform } from "framer-motion";
import { useEffect, useMemo, useRef, useState } from "react";
import { useMarket, useSearch, useShowcase, useTimeline, type MetricResult, type Mover, type Showcase } from "@/lib/api";
import { dmy, dmyTime, indianGroup, METRIC_LABEL, todayIST } from "@/lib/format";
import { parse } from "@/lib/commands";
import { Mark, Wordmark } from "@/components/ui/Logo";
import ModeSwitch from "@/components/ui/ModeSwitch";
import { storedMode, useT } from "@/lib/store";
import { LockIcon, Value } from "@/components/ui/Value";
import TimeSpine from "@/components/ui/TimeSpine";
import type { TipReadout } from "@/components/three/Touchstone";
import Survivors from "./Survivors";
import TimeMachine from "./TimeMachine";
import s from "./home.module.css";

const Touchstone = dynamic(() => import("@/components/three/Touchstone"), { ssr: false });
const ease = [0.22, 1, 0.36, 1] as const;
const pct = (x: number | null | undefined, d = 1) => (x === null || x === undefined ? "—" : `${x > 0 ? "+" : x < 0 ? "−" : ""}${Math.abs(x * 100).toFixed(d)}%`);
const WEEKDAY = ["SUNDAY", "MONDAY", "TUESDAY", "WEDNESDAY", "THURSDAY", "FRIDAY", "SATURDAY"];

/* ================================================================== tape */
function Tape() {
  const { data } = useMarket("NOW");
  const items = data?.market.most_traded ?? [];
  if (!items.length) return <div className={s.tape} />;
  return (
    <div className={s.tape} aria-label="Most traded Nifty 500 stocks, last session">
      <span className={s.tapeTag}>NSE · {dmy(data!.market.session)} · close</span>
      <div className={s.tapeView}>
        <div className={s.tapeTrack}>
          {[...items, ...items].map((m, i) => (
            <Link key={i} href={`/terminal?code=${encodeURIComponent(m.code)}`} className={s.tapeItem}>
              <b>{m.code}</b>
              <span className="mono">{m.close.toLocaleString("en-IN", { maximumFractionDigits: 2 })}</span>
              <span className={`mono ${m.change >= 0 ? "pos" : "neg"}`}>{m.change >= 0 ? "▲" : "▼"} {Math.abs(m.change * 100).toFixed(2)}%</span>
            </Link>
          ))}
        </div>
      </div>
    </div>
  );
}

function Nav() {
  const router = useRouter();
  return (
    <nav className={s.nav}>
      <Link href="/" className={s.brand}><Wordmark /></Link>
      <div className={s.links}>
        <a href="#market">Time machine</a>
        <a href="#survivors">Survivorship</a>
        <a href="#law">Sector law</a>
        <a href="#time">Time</a>
        <ModeSwitch onPick={(m) => m === "pro" && router.push("/terminal")} />
        <Link href="/terminal" className={s.navCta}>Terminal <kbd>/</kbd></Link>
      </div>
    </nav>
  );
}

/* ================================================================== hero command */
function HeroCommand() {
  const router = useRouter();
  const [v, setV] = useState("");
  const [deb, setDeb] = useState("");
  const [sel, setSel] = useState(0);
  const [focus, setFocus] = useState(false);
  useEffect(() => { const t = setTimeout(() => setDeb(v), 160); return () => clearTimeout(t); }, [v]);
  const p = parse(v, todayIST());
  const term = p.kind === "entity" ? p.code : "";
  const { data } = useSearch(deb.trim().split(/\s+/)[0] ?? "", "NOW");
  const hits = term && data ? data.results.slice(0, 6) : [];
  const go = (code?: string) => {
    if (p.kind === "asof") return router.push(`/terminal?asof=${p.value}`);
    const fn = p.kind === "entity" ? p.fn : "DES";
    const c = code ?? hits[sel]?.code ?? (p.kind === "entity" ? p.code : "");
    if (c) router.push(`/terminal?code=${encodeURIComponent(c)}&fn=${fn}`);
  };
  return (
    <div className={s.cmdWrap}>
      <div className={`${s.cmd} ${focus ? s.cmdFocus : ""}`}>
        <span className={s.cmdPrompt}>›</span>
        <input
          value={v}
          onChange={(e) => { setV(e.target.value); setSel(0); }}
          onFocus={() => setFocus(true)}
          onBlur={() => setTimeout(() => setFocus(false), 150)}
          onKeyDown={(e) => {
            if (e.key === "ArrowDown") { setSel((x) => Math.min(x + 1, hits.length - 1)); e.preventDefault(); }
            if (e.key === "ArrowUp") { setSel((x) => Math.max(x - 1, 0)); e.preventDefault(); }
            if (e.key === "Enter") go();
          }}
          placeholder="Search 9,859 securities — or type  ASOF 2008-10-24"
          spellCheck={false}
          aria-label="Command"
        />
        <kbd>↵</kbd>
      </div>
      <AnimatePresence>
        {focus && hits.length > 0 && (
          <motion.div className={s.cmdList} initial={{ opacity: 0, y: -4 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0 }} transition={{ duration: 0.18 }}>
            {hits.map((h, i) => (
              <button key={h.security_id} className={i === sel ? s.cmdSel : ""} onMouseDown={() => go(h.code)} onMouseEnter={() => setSel(i)}>
                <b className="mono">{h.code}</b>
                <span>{h.name}</span>
                <i className="mono">{h.active ? `since ${h.listed_from.slice(0, 4)}` : `delisted · last ${dmy(h.last_trade)}`}</i>
              </button>
            ))}
          </motion.div>
        )}
      </AnimatePresence>
      <div className={s.cmdHints}>
        {["TCS", "HDFCBANK FA", "SATYAMCOMP", "ASOF 2020-03-23"].map((x) => (
          <button key={x} className="mono" onClick={() => setV(x)}>{x}</button>
        ))}
      </div>
    </div>
  );
}

/* ================================================================== hero */
function Hero({ data, offline }: { data?: Showcase; offline: boolean }) {
  const [tip, setTip] = useState<TipReadout | null>(null);
  const ref = useRef<HTMLElement>(null);
  const { scrollYProgress } = useScroll({ target: ref, offset: ["start start", "end start"] });
  const fade = useTransform(scrollYProgress, [0, 0.6], [1, 0]);
  const mult = tip ? tip.last / tip.first : null;
  return (
    <section ref={ref} className={s.hero}>
      <div className={s.canvas}><Touchstone streaks={data?.streaks ?? []} onTip={setTip} /></div>
      <div className={s.heroShade} />

      <motion.div style={{ opacity: fade }} className={s.heroCopy}>
        <motion.div className={s.eyebrow} initial={{ opacity: 0 }} animate={{ opacity: 1 }} transition={{ duration: 1.2, delay: 0.8 }}>
          <span className="deva">त्रिकाल</span><i /> Indian equity research terminal
        </motion.div>
        <motion.h1 className={`display ${s.h1}`} initial={{ opacity: 0, y: 26, filter: "blur(10px)" }} animate={{ opacity: 1, y: 0, filter: "blur(0px)" }} transition={{ duration: 1.4, delay: 1.0, ease }}>
          Every number,<br /><em>as it was known.</em>
        </motion.h1>
        <motion.p className={s.lede} initial={{ opacity: 0 }} animate={{ opacity: 1 }} transition={{ duration: 1.2, delay: 1.6 }}>
          The Indian market rebuilt exactly as it stood on any day since 1994 — delisted companies included, every split
          and bonus confirmed, every filing stamped with the minute it became public.
        </motion.p>
        <motion.div initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 1, delay: 1.9, ease }}>
          <HeroCommand />
        </motion.div>
      </motion.div>

      <motion.aside className={s.plate} style={{ opacity: fade }} initial={{ opacity: 0 }} animate={{ opacity: 1 }} transition={{ duration: 1.4, delay: 2.2 }}>
        <div className={s.plateHead}>
          <span>ASSAY</span>
          <span className={s.plateNo}>{tip ? `№ ${tip.code}-${tip.from.slice(0, 4)}-${tip.to.slice(0, 4)}` : "№ —"}</span>
        </div>
        {tip ? (
          <>
            <div className={s.plateName}>{tip.name}</div>
            <div className={s.plateRow}><span>Session</span><b className="mono">{dmy(tip.date)}</b></div>
            <div className={s.plateRow}><span>Adjusted close</span><b className="mono">₹{tip.price.toLocaleString("en-IN", { maximumFractionDigits: tip.price < 100 ? 2 : 0 })}</b></div>
            <div className={s.plateRow}><span>Sessions on stone</span><b className="mono">{indianGroup(tip.sessions)}</b></div>
            <div className={s.plateRow}><span>First → last</span><b className="mono">{mult ? `${mult >= 10 ? mult.toFixed(0) : mult.toFixed(1)}×` : "—"}</b></div>
            <div className={s.plateBar}><i style={{ transform: `scaleX(${tip.progress})` }} /></div>
            <div className={s.plateFoot}>NSE bhavcopy · split &amp; bonus adjusted, confirmed events only</div>
          </>
        ) : (
          <div className={s.plateWait}>{offline ? "API offline — start trikal-api to assay live data." : "Preparing the stone…"}</div>
        )}
      </motion.aside>

      <div className={s.heroFoot}>
        <span>AS OF <b className="mono">{dmy(todayIST())}</b></span>
        <span>DATA TO <b className="mono">{data?.watermark?.prices_known_at ? dmyTime(data.watermark.prices_known_at) : "—"}</b></span>
        <span className={s.heroScroll}>SCROLL</span>
      </div>
    </section>
  );
}

/* ================================================================== section head */
function Head({ n, kicker, title, children }: { n: string; kicker: string; title: React.ReactNode; children?: React.ReactNode }) {
  return (
    <motion.header className={s.head} initial={{ opacity: 0, y: 24 }} whileInView={{ opacity: 1, y: 0 }} viewport={{ once: true, margin: "-10%" }} transition={{ duration: 1, ease }}>
      <div className={s.headLeft}><span className="mono">{n}</span><span>{kicker}</span></div>
      <div className={s.headRight}>
        <h2 className={`display ${s.h2}`}>{title}</h2>
        {children && <div className={s.headLede}>{children}</div>}
      </div>
    </motion.header>
  );
}

/* ================================================================== sector law */
const LAW = ["ev_ebitda", "ebitda_margin", "debt_to_equity", "pe", "pb", "roe"];

function Law({ data }: { data?: Showcase }) {
  const rules = data?.rules ?? [];
  const forb = rules.flatMap((r) => Object.values(r.metrics).filter((m): m is Extract<MetricResult, { state: "forbidden" }> => m.state === "forbidden").map((m) => ({ ...m, code: r.code })));
  return (
    <section id="law" className={s.section}>
      <Head n="§3" kicker="Sector law" title={<>A bank has no EBITDA.<br /><em>So TRIKAL refuses to compute one.</em></>}>
        Thirty sector playbooks live inside the engine, not the screen. Ask for EV/EBITDA on a lender and the request fails
        before a single input is read, with the rule and its source. Every value states what it is: a number with lineage,
        not meaningful, not available, or forbidden. Hover any cell.
      </Head>
      <div className={s.lawTable}>
        <div className={s.lawRow + " " + s.lawHeadRow}>
          <span />
          {rules.map((r) => (
            <div key={r.code}>
              <Link href={`/terminal?code=${r.code}`} className="mono">{r.code}</Link>
              <b>{r.name}</b>
              <i>{r.label} playbook</i>
            </div>
          ))}
        </div>
        {LAW.map((m) => (
          <div key={m} className={s.lawRow}>
            <span>{METRIC_LABEL[m]}</span>
            {rules.map((r) => (
              <div key={r.code} className={r.metrics[m]?.state === "forbidden" ? s.lawLocked : ""}><Value r={r.metrics[m]} /></div>
            ))}
          </div>
        ))}
      </div>
      {forb[0] && (
        <blockquote className={s.quote}>
          <LockIcon size={13} />
          <p>“{forb[0].reason}”</p>
          <cite className="mono">rule · {forb[0].playbook} · {forb[0].rule}</cite>
        </blockquote>
      )}
      <div className={s.legend}>
        <span><b className="mono">₹1,234 Cr</b> value with lineage</span>
        <span><b className="mono v-muted">n.m.</b> not meaningful</span>
        <span><b className="mono v-muted">n/a</b> input missing, named</span>
        <span><b className="v-lock"><LockIcon /> —</b> forbidden by sector rule</span>
      </div>
    </section>
  );
}

/* ================================================================== time spine */
function Time({ data }: { data?: Showcase }) {
  const { data: tl } = useTimeline("TCS", "NOW");
  const [asOf, setAsOf] = useState("NOW");
  const tcs = data?.streaks.find((x) => x.code === "TCS");
  const priceAt = useMemo(() => {
    if (!tcs) return null;
    const target = asOf === "NOW" ? tcs.t[tcs.t.length - 1] : asOf;
    let k = -1;
    for (let i = 0; i < tcs.t.length; i++) if (tcs.t[i] <= target) k = i;
    return k >= 0 ? tcs.c[k] : null;
  }, [tcs, asOf]);
  const known = (tl?.events ?? []).filter((e) => asOf === "NOW" || e.date <= asOf).length;
  return (
    <section id="time" className={s.section}>
      <Head n="§4" kicker="Kaal-Rekha · the time spine" title={<>Drag time.<br /><em>The future stays empty.</em></>}>
        The spine under every screen. Pull the playhead into the past and the terminal forgets everything published after
        that minute. Right of NOW there is no data at all — only scenario ranges you build in the Valuation Lab. No ratings,
        no target prices.
      </Head>
      <div className={s.spineBox}>
        <div className={s.spineTop}>
          <div><span className="mono">TCS</span> Tata Consultancy Services · bonuses, results, index entries — each at the minute it became public</div>
          <div className={s.spineRead}>
            <span>AS OF <b className="mono">{asOf === "NOW" ? "NOW" : dmy(asOf)}</b></span>
            <span>ADJ. CLOSE <b className="mono">{priceAt ? `₹${priceAt.toLocaleString("en-IN", { maximumFractionDigits: 0 })}` : "—"}</b></span>
            <span>EVENTS KNOWN <b className="mono">{known}</b></span>
          </div>
        </div>
        {tl && tcs && <TimeSpine events={tl.events} start={tcs.from} now={todayIST()} asOf={asOf} onChange={setAsOf} height={96} futureFrac={0.14} scenarioNote="scenarios only · no data" />}
        <div className={s.spineKeys}>
          <span><i className={s.kDia} /> split / bonus</span><span><i className={s.kRes} /> results published</span><span><i className={s.kIdx} /> joins index</span>
          <span className={s.dim}>drag · ← → months · Shift years · [ ] events · Esc now</span>
        </div>
      </div>
    </section>
  );
}

/* ================================================================== provenance */
function Provenance({ data }: { data?: Showcase }) {
  const st = data?.stats;
  const rows: [string, string, string, string][] = st ? [
    ["Daily prices", `NSE ${dmy(st.first_session)} → today · BSE 2007 → today`, `${(st.price_rows / 1e6).toFixed(1)}M rows`, "Raw bhavcopies, five file formats, stored unadjusted"],
    ["Security master", "Every listed security, alive or dead", `${indianGroup(st.securities)}`, `ISIN, code continuity, symbol chains, cross-exchange match; ${indianGroup(st.securities_inactive)} inactive`],
    ["Corporate actions", "Announcements from 1995", `${indianGroup(st.corporate_announcements)}`, `${indianGroup(st.adjustments_applied)} applied — only when announcement and price move agree`],
    ["Index membership", "Nifty 500, rebuilt from press releases", `${indianGroup(st.nifty500_ever_members)} ever-members`, "Exact to 500 from Dec-2011; earlier rows carry confidence"],
    ["Shareholding", "Quarterly pattern filings", `${indianGroup(st.shareholding_filings)} filings`, "Promoter, institutions, public; category detail from Sep-2021"],
    ["Results", "XBRL from 2017, results pages 2008–17", `${indianGroup(st.filings)} filings · ${indianGroup(st.companies_with_filings)} cos`, "Download in progress — numbers appear as documents arrive"],
  ] : [];
  return (
    <section className={s.section}>
      <Head n="§5" kicker="Provenance" title={<>Where every number comes from.</>}>
        Public exchange archives, read in full, with the source document and broadcast minute kept beside each value.
      </Head>
      <div className={s.prov}>
        <div className={`${s.provRow} ${s.provHead}`}><span>Dataset</span><span>Coverage</span><span>Size</span><span>Method</span></div>
        {rows.map((r) => (
          <motion.div key={r[0]} className={s.provRow} initial={{ opacity: 0 }} whileInView={{ opacity: 1 }} viewport={{ once: true }} transition={{ duration: 0.8 }}>
            <b>{r[0]}</b><span>{r[1]}</span><span className="mono">{r[2]}</span><span>{r[3]}</span>
          </motion.div>
        ))}
      </div>
    </section>
  );
}

/* ================================================================== close */
const ROAD = [
  ["M1", "Prices · identity · index", "done"], ["M2", "Fundamentals & ownership", "downloading"], ["M3", "Terminal & home", "building"],
  ["M4", "Playbooks · Valuation Lab", "done"], ["M5", "Macro · policy · geo", "next"], ["M6", "Concalls & reports", "next"],
  ["M7", "KASAUTI score", "next"], ["M8", "Research bot", "next"], ["M9", "Forensics · screener", "next"],
];

function Close({ data }: { data?: Showcase }) {
  return (
    <section className={s.close}>
      <div className={s.closeInner}>
        <Mark size={34} />
        <h2 className="display">Open the terminal.</h2>
        <p>Press <kbd>/</kbd> anywhere to command it.</p>
        <Link href="/terminal" className={s.enter}>Enter TRIKAL <span aria-hidden>→</span></Link>
      </div>
      <div className={s.road}>
        {ROAD.map(([m, l, st]) => <div key={m} className={s["r_" + st]}><span className="mono">{m}</span><b>{l}</b><i>{st}</i></div>)}
      </div>
      <footer className={s.foot}>
        <Wordmark />
        <p>{data?.disclaimer ?? "Research tool. Not investment advice. No ratings or target prices."} Personal research use · public NSE/BSE archives, not redistributed.</p>
      </footer>
    </section>
  );
}

export default function Home() {
  const { data, isError } = useShowcase();
  const router = useRouter();
  const setMode = useT((s) => s.setMode);
  // PRO users skip the home page and land in the workstation (the logo link adds ?stay=1 to come back here)
  useEffect(() => {
    const m = storedMode();
    setMode(m);
    if (m === "pro" && !new URLSearchParams(window.location.search).has("stay")) router.replace("/terminal");
  }, [router, setMode]);
  return (
    <main className={s.main}>
      <Nav />
      <Tape />
      <Hero data={data} offline={isError} />
      <TimeMachine />
      <Survivors data={data} Head={Head} />
      <Law data={data} />
      <Time data={data} />
      <Provenance data={data} />
      <Close data={data} />
      {data?.demo && <div className="demo-watermark">DEMO DATA</div>}
    </main>
  );
}
