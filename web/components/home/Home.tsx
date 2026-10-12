"use client";

import dynamic from "next/dynamic";
import Link from "next/link";
import { motion, useInView, useScroll, useTransform, animate } from "framer-motion";
import { useEffect, useMemo, useRef, useState } from "react";
import { useShowcase, useTimeline, type MetricResult, type Showcase } from "@/lib/api";
import { dmy, dmyTime, indianGroup, METRIC_LABEL, todayIST } from "@/lib/format";
import { Mark, Wordmark } from "@/components/ui/Logo";
import { LockIcon, Value } from "@/components/ui/Value";
import TimeSpine from "@/components/ui/TimeSpine";
import type { TipReadout } from "@/components/three/Touchstone";
import s from "./home.module.css";

const Touchstone = dynamic(() => import("@/components/three/Touchstone"), { ssr: false });
const Strata = dynamic(() => import("@/components/three/Strata"), { ssr: false });

const ease = [0.22, 1, 0.36, 1] as const;

/* ------------------------------------------------------------------ hero */
function Hero({ data, offline }: { data?: Showcase; offline: boolean }) {
  const [tip, setTip] = useState<TipReadout | null>(null);
  const ref = useRef<HTMLElement>(null);
  const { scrollYProgress } = useScroll({ target: ref, offset: ["start start", "end start"] });
  const fade = useTransform(scrollYProgress, [0, 0.7], [1, 0]);
  const lift = useTransform(scrollYProgress, [0, 1], [0, -120]);
  const mult = tip ? tip.last / tip.first : null;

  return (
    <section ref={ref} className={s.hero}>
      <div className={s.canvas}>
        <Touchstone streaks={data?.streaks ?? []} onTip={setTip} />
      </div>
      <div className={s.heroShade} />
      <motion.div className={s.deva} initial={{ opacity: 0 }} animate={{ opacity: 1 }} transition={{ duration: 3, delay: 0.6 }}>त्रिकाल</motion.div>

      <motion.div style={{ opacity: fade, y: lift }} className={s.heroCopy}>
        <motion.div className={s.eyebrow} initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 1, delay: 0.9, ease }}>
          <span className={s.dot} /> Indian equity research · point-in-time · since 1994
        </motion.div>
        <h1 className={`display ${s.h1}`}>
          {["Every", "number,"].map((w, i) => (
            <motion.span key={w} className={s.word} initial={{ opacity: 0, y: 40, filter: "blur(12px)" }} animate={{ opacity: 1, y: 0, filter: "blur(0px)" }} transition={{ duration: 1.3, delay: 1.1 + i * 0.12, ease }}>{w}&nbsp;</motion.span>
          ))}
          <br />
          <motion.em className={`gold-text ${s.em}`} initial={{ opacity: 0, y: 40, filter: "blur(14px)" }} animate={{ opacity: 1, y: 0, filter: "blur(0px)" }} transition={{ duration: 1.6, delay: 1.5, ease }}>
            as it was known.
          </motion.em>
        </h1>
        <motion.p className={s.lede} initial={{ opacity: 0, y: 16 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 1.2, delay: 2.0, ease }}>
          TRIKAL rebuilds the Indian market exactly as it stood on any day — every delisted company, every split and bonus,
          every filing stamped with the minute it became public. Then it judges each company by the law of its own sector.
        </motion.p>
        <motion.div className={s.ctas} initial={{ opacity: 0, y: 16 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 1, delay: 2.3, ease }}>
          <Link href="/terminal" className={s.primary}>
            <span>Enter the terminal</span>
            <kbd className={s.kbd}>Ctrl K</kbd>
          </Link>
          <a href="#bhoot" className={s.ghost}>See the method <span aria-hidden>↓</span></a>
        </motion.div>
      </motion.div>

      {/* the assay readout: what the gold on the stone is, in real numbers */}
      <motion.aside className={s.assay} initial={{ opacity: 0, x: 30 }} animate={{ opacity: 1, x: 0 }} transition={{ duration: 1.2, delay: 2.6, ease }} style={{ opacity: fade }}>
        <div className={s.assayHead}>
          <span>ON THE TOUCHSTONE</span>
          <span className={s.live}><i />live data</span>
        </div>
        {tip ? (
          <>
            <div className={s.assayCode}>{tip.code}</div>
            <div className={s.assayName}>{tip.name}</div>
            <div className={s.assayPrice}>
              <span className="mono">₹{tip.price.toLocaleString("en-IN", { maximumFractionDigits: tip.price < 100 ? 2 : 0 })}</span>
              <span className={`mono ${s.assayDate}`}>{dmy(tip.date)}</span>
            </div>
            <div className={s.bar}><i style={{ width: `${tip.progress * 100}%` }} /></div>
            <div className={s.assayGrid}>
              <span>sessions</span><b className="mono">{indianGroup(tip.sessions)}</b>
              <span>span</span><b className="mono">{tip.from.slice(0, 4)} → {tip.to.slice(0, 4)}</b>
              <span>multiple</span><b className="mono">{mult ? `${mult.toFixed(1)}×` : "—"}</b>
            </div>
            <div className={s.assaySrc}>Split &amp; bonus adjusted · {tip.source.split(",")[0]}</div>
          </>
        ) : (
          <div className={s.assayWait}>{offline ? "API offline — start it to read live data" : "Preparing the stone…"}</div>
        )}
      </motion.aside>

      <div className={s.asOfChip}>
        <span>AS OF</span>
        <b className="mono">{dmy(todayIST())}</b>
        <span className={s.sep} />
        <span>data to</span>
        <b className="mono">{data?.watermark?.prices_known_at ? dmyTime(data.watermark.prices_known_at) : "—"}</b>
      </div>
      <motion.div className={s.scrollCue} animate={{ y: [0, 8, 0] }} transition={{ duration: 2.4, repeat: Infinity }}>
        <span>descend through time</span>
        <i />
      </motion.div>
    </section>
  );
}

/* ------------------------------------------------------------------ helpers */
function Counter({ to, duration = 2.2, format = (n: number) => indianGroup(Math.round(n)) }: { to: number; duration?: number; format?: (n: number) => string }) {
  const ref = useRef<HTMLSpanElement>(null);
  const inView = useInView(ref, { once: true, margin: "-10%" });
  useEffect(() => {
    if (!inView || !ref.current) return;
    const c = animate(0, to, { duration, ease: [0.16, 1, 0.3, 1], onUpdate: (v) => { if (ref.current) ref.current.textContent = format(v); } });
    return () => c.stop();
  }, [inView, to, duration, format]);
  return <span ref={ref} className="mono">0</span>;
}

function Reveal({ children, delay = 0, className }: { children: React.ReactNode; delay?: number; className?: string }) {
  return (
    <motion.div className={className} initial={{ opacity: 0, y: 36 }} whileInView={{ opacity: 1, y: 0 }} viewport={{ once: true, margin: "-12%" }} transition={{ duration: 1.1, delay, ease }}>
      {children}
    </motion.div>
  );
}

function SectionMark({ deva, roman, n }: { deva: string; roman: string; n: string }) {
  return (
    <div className={s.mark}>
      <span className="mono">{n}</span>
      <span className={s.markLine} />
      <span className="deva">{deva}</span>
      <span>{roman}</span>
    </div>
  );
}

/* ------------------------------------------------------------------ bhoot: strata */
function Bhoot({ data }: { data?: Showcase }) {
  const ref = useRef<HTMLDivElement>(null);
  const inView = useInView(ref, { margin: "200px" });
  const strata = data?.strata ?? [];
  const y2006 = strata.find((x) => x.date.startsWith("2006"));
  const y2011 = strata.find((x) => x.date.startsWith("2011"));
  const ghosts = data?.ghosts.members ?? [];
  return (
    <section id="bhoot" className={s.section}>
      <SectionMark n="01" deva="भूत" roman="BHOOT — the past, uncorrupted" />
      <div className={s.split}>
        <div ref={ref} className={s.strataStage}>
          {inView && strata.length > 0 && <Strata strata={strata} />}
          <div className={s.strataLegend}>
            <span><i className={s.lgSolid} /> still trading today</span>
            <span><i className={s.lgGhost} /> vanished since — delisted, merged, failed</span>
            <span className={s.lgHint}>hover a layer · oldest at the bottom</span>
          </div>
        </div>
        <div className={s.copy}>
          <Reveal>
            <h2 className={`display ${s.h2}`}>History is written by the <em className="gold-text">survivors.</em><br />Ours isn’t.</h2>
          </Reveal>
          <Reveal delay={0.1}>
            <p className={s.p}>
              Most datasets quietly start from today’s winners and walk backwards. Every backtest built on them is flattered by the
              companies that died along the way and were never in the data.
            </p>
          </Reveal>
          {y2006 && y2011 && (
            <Reveal delay={0.2}>
              <div className={s.bigStats}>
                <div><b className="display"><Counter to={y2006.gone} /></b><span>of the <span className="mono">{y2006.members}</span> Nifty 500 members of June 2006 no longer trade</span></div>
                <div><b className="display"><Counter to={y2011.gone} /></b><span>of June 2011’s <span className="mono">{y2011.members}</span> are gone too</span></div>
              </div>
            </Reveal>
          )}
          <Reveal delay={0.3}>
            <p className={s.pSmall}>
              Reconstructed from <b className="mono">{data ? indianGroup(data.stats.index_press_releases) : "—"}</b> NSE index press releases,
              exact to 500 names on every rebalance since Dec-2011. Each of these companies keeps its full price history.
            </p>
          </Reveal>
        </div>
      </div>
      {ghosts.length > 0 && (
        <div className={s.ghostRail} aria-label="Nifty 500 members of January 2008 that no longer trade">
          <div className={s.ghostLabel}>In the Nifty 500 on {dmy(data!.ghosts.on)} — gone since</div>
          <div className={s.marquee}>
            <div className={s.marqueeTrack}>
              {[...ghosts, ...ghosts].map((g, i) => (
                <span key={i} className={s.ghost}>
                  {g.name}<i className="mono">last traded {dmy(g.last_trade)}</i>
                </span>
              ))}
            </div>
          </div>
        </div>
      )}
    </section>
  );
}

/* ------------------------------------------------------------------ the ledger */
function Ledger({ data }: { data?: Showcase }) {
  const st = data?.stats;
  const items = st
    ? [
        { v: st.price_rows, l: "daily price rows", sub: `every NSE session since ${dmy(st.first_session)}, BSE since 2007` },
        { v: st.securities, l: "securities, dead or alive", sub: `${indianGroup(st.securities_inactive)} of them no longer trade` },
        { v: st.adjustments_applied, l: "confirmed splits & bonuses", sub: "applied only when the announcement and the price move agree" },
        { v: st.corporate_announcements, l: "corporate announcements", sub: "read and classified, back to 1995" },
        { v: st.nifty500_ever_members, l: "companies ever in the Nifty 500", sub: "the survivorship-free research universe" },
        { v: st.shareholding_filings, l: "shareholding filings", sub: "promoter, institutions, public — quarter by quarter" },
      ]
    : [];
  return (
    <section className={`${s.section} ${s.ledger}`}>
      <Reveal><h3 className={s.kicker}>The ledger, as of today</h3></Reveal>
      <div className={s.ledgerGrid}>
        {items.map((it, i) => (
          <Reveal key={it.l} delay={i * 0.06} className={s.ledgerCell}>
            <div className={`display ${s.ledgerNum}`}><Counter to={it.v} /></div>
            <div className={s.ledgerLabel}>{it.l}</div>
            <div className={s.ledgerSub}>{it.sub}</div>
          </Reveal>
        ))}
      </div>
      <Reveal delay={0.2}>
        <p className={s.ledgerNote}>
          Every value carries its lineage: source document, broadcast minute, and the time we recorded it. Fundamentals are
          still streaming in from the exchange archives
          {st ? <> — <span className="mono">{indianGroup(st.companies_with_filings)}</span> companies parsed so far</> : null}; until a
          number is there, the terminal says <span className="mono">n/a</span> and names what is missing. It never guesses.
        </p>
      </Reveal>
    </section>
  );
}

/* ------------------------------------------------------------------ vartaman: sector law */
const SHOW = ["ev_ebitda", "ebitda_margin", "debt_to_equity", "pe", "pb", "roe"];

function LawCard({ r, i }: { r: Showcase["rules"][number]; i: number }) {
  const ref = useRef<HTMLDivElement>(null);
  const [t, setT] = useState({ x: 0, y: 0 });
  const forb = Object.values(r.metrics).filter((m) => m.state === "forbidden") as Extract<MetricResult, { state: "forbidden" }>[];
  return (
    <motion.div
      ref={ref}
      className={s.card}
      initial={{ opacity: 0, y: 60, rotateX: 18 }}
      whileInView={{ opacity: 1, y: 0, rotateX: 0 }}
      viewport={{ once: true, margin: "-10%" }}
      transition={{ duration: 1.2, delay: i * 0.14, ease }}
      onMouseMove={(e) => {
        const b = ref.current!.getBoundingClientRect();
        setT({ x: ((e.clientY - b.top) / b.height - 0.5) * -10, y: ((e.clientX - b.left) / b.width - 0.5) * 12 });
      }}
      onMouseLeave={() => setT({ x: 0, y: 0 })}
      style={{ transform: `perspective(1100px) rotateX(${t.x}deg) rotateY(${t.y}deg)` }}
    >
      <div className={s.cardShine} style={{ background: `radial-gradient(600px circle at ${50 + t.y * 4}% ${50 - t.x * 5}%, rgba(242,210,122,0.10), transparent 40%)` }} />
      <div className={s.cardTop}>
        <span className="mono">{r.code}</span>
        <span className={s.pb}>{r.label}</span>
      </div>
      <div className={s.cardName}>{r.name}</div>
      <div className={s.cardRows}>
        {SHOW.map((m) => (
          <div key={m} className={`${s.cardRow} ${r.metrics[m]?.state === "forbidden" ? s.rowLocked : ""}`}>
            <span>{METRIC_LABEL[m]}</span>
            <Value r={r.metrics[m]} />
          </div>
        ))}
      </div>
      {forb.length > 0 ? (
        <div className={s.cardLaw}>
          <LockIcon size={12} />
          <span>{forb[0].reason}</span>
        </div>
      ) : (
        <div className={s.cardLawOk}>All six are meaningful for this sector.</div>
      )}
    </motion.div>
  );
}

function Vartaman({ data }: { data?: Showcase }) {
  return (
    <section className={s.section}>
      <SectionMark n="02" deva="वर्तमान" roman="VARTAMAN — the law of each sector" />
      <div className={s.center}>
        <Reveal><h2 className={`display ${s.h2} ${s.h2c}`}>A bank has no EBITDA.<br /><em className="gold-text">So TRIKAL refuses to compute one.</em></h2></Reveal>
        <Reveal delay={0.1}>
          <p className={`${s.p} ${s.pc}`}>
            Thirty sector playbooks are enforced inside the engine, not hidden by the screen. Ask for EV/EBITDA on a lender and the
            request fails before a single input is read — with the rule and its source. Hover any value to see where it came from.
          </p>
        </Reveal>
      </div>
      <div className={s.cards}>{(data?.rules ?? []).map((r, i) => <LawCard key={r.code} r={r} i={i} />)}</div>
      <Reveal delay={0.2}>
        <div className={s.states}>
          <span><b className="mono">₹1,234 Cr</b> value, with lineage</span>
          <span><b className="mono v-muted">n.m.</b> not meaningful (P/E of a loss)</span>
          <span><b className="mono v-muted">n/a</b> input missing — named</span>
          <span><b className="v-lock"><LockIcon /> —</b> forbidden by the sector rule</span>
        </div>
      </Reveal>
    </section>
  );
}

/* ------------------------------------------------------------------ bhavishya: the time spine */
function Bhavishya({ data }: { data?: Showcase }) {
  const { data: tl } = useTimeline("TCS", "NOW");
  const [asOf, setAsOf] = useState("NOW");
  const tcs = data?.streaks.find((x) => x.code === "TCS");
  const priceAt = useMemo(() => {
    if (!tcs) return null;
    const target = asOf === "NOW" ? tcs.t[tcs.t.length - 1] : asOf;
    let k = -1;
    for (let i = 0; i < tcs.t.length; i++) if (tcs.t[i] <= target) k = i;
    return k >= 0 ? { d: tcs.t[k], c: tcs.c[k] } : null;
  }, [tcs, asOf]);
  const visible = (tl?.events ?? []).filter((e) => asOf === "NOW" || e.date <= asOf);
  return (
    <section className={s.section}>
      <SectionMark n="03" deva="भविष्य" roman="BHAVISHYA — scenarios, never prophecies" />
      <div className={s.center}>
        <Reveal><h2 className={`display ${s.h2} ${s.h2c}`}>Drag time. <em className="gold-text">Nothing from the future leaks back.</em></h2></Reveal>
        <Reveal delay={0.1}>
          <p className={`${s.p} ${s.pc}`}>
            This is the Kaal-Rekha — the time spine under every screen. Pull the gold playhead into the past and the whole terminal
            forgets everything published after that minute. To the right of NOW there is no data at all: only scenario ranges you
            build yourself. No ratings. No target prices.
          </p>
        </Reveal>
      </div>
      <Reveal delay={0.15}>
        <div className={s.spineStage}>
          <div className={s.spineHead}>
            <div>
              <span className={s.spineCode}>TCS</span>
              <span className={s.spineName}>Tata Consultancy Services · real events: bonuses, results, index entries</span>
            </div>
            <div className={s.spineRead}>
              <span>AS OF</span><b className="mono">{asOf === "NOW" ? "NOW" : dmy(asOf)}</b>
              <span>adj. close</span><b className="mono">{priceAt ? `₹${priceAt.c.toLocaleString("en-IN", { maximumFractionDigits: 0 })}` : "—"}</b>
              <span>events known</span><b className="mono">{visible.length}</b>
            </div>
          </div>
          {tl && tcs && (
            <TimeSpine events={tl.events} start={tcs.from} now={todayIST()} asOf={asOf} onChange={setAsOf} height={96}
              futureFrac={0.14} scenarioNote="scenarios only · no data" />
          )}
          <div className={s.spineKeys}>
            <span><i style={{ background: "var(--gold-0)" }} className={s.dia} /> split / bonus</span>
            <span><i style={{ background: "var(--pos)" }} /> results published</span>
            <span><i style={{ background: "#9fb8ff", borderRadius: 9 }} /> joins index</span>
            <span className={s.lgHint}>drag · ← → months · Shift = years · [ ] events · Esc = now</span>
          </div>
        </div>
      </Reveal>
    </section>
  );
}

/* ------------------------------------------------------------------ the terminal teaser */
const COMMANDS = [
  { c: "TCS DES", r: "Tata Consultancy Services · IT services playbook · every panel follows the link group" },
  { c: "HDFCBANK DCF", r: "🔒 FCFF DCF is forbidden for banks — debt is a lender’s raw material" },
  { c: "ASOF 2008-01-04", r: "Rewound. Satyam still trades; nothing published after that day exists on any screen" },
  { c: "INFY GP", r: "Every NSE session since listing, adjusted only for confirmed splits and bonuses — toggle to see the raw prints" },
];

function TerminalTeaser() {
  const [k, setK] = useState(0);
  const [typed, setTyped] = useState("");
  useEffect(() => {
    const cmd = COMMANDS[k % COMMANDS.length].c;
    let i = 0;
    const t = setInterval(() => {
      i++;
      setTyped(cmd.slice(0, i));
      if (i >= cmd.length) {
        clearInterval(t);
        setTimeout(() => setK((x) => x + 1), 2600);
      }
    }, 85);
    return () => clearInterval(t);
  }, [k]);
  const cur = COMMANDS[k % COMMANDS.length];
  const done = typed === cur.c;
  return (
    <section className={`${s.section} ${s.teaser}`}>
      <div className={s.center}>
        <Reveal><h2 className={`display ${s.h2} ${s.h2c}`}>A terminal that <em className="gold-text">types back.</em></h2></Reveal>
        <Reveal delay={0.1}><p className={`${s.p} ${s.pc}`}>Bloomberg-style function codes, a tiling workspace, link groups, and a command bar that understands time.</p></Reveal>
      </div>
      <Reveal delay={0.15}>
        <div className={s.screen}>
          <div className={s.screenGlow} />
          <div className={s.screenBar}>
            <Mark size={14} />
            <div className={s.cmd}>
              <span className={s.prompt}>›</span>
              <span className="mono">{typed}</span>
              <span className={s.caret} />
            </div>
            <span className={s.badge}>{cur.c.startsWith("ASOF") && done ? `AS OF ${dmy(cur.c.slice(5))}` : "NOW"}</span>
          </div>
          <motion.div key={k} className={s.screenOut} initial={{ opacity: 0 }} animate={{ opacity: done ? 1 : 0 }} transition={{ duration: 0.5 }}>
            {cur.r}
          </motion.div>
          <div className={s.screenPanels}>
            {["DES", "GP", "FA", "DUP", "CR", "RV", "WC", "OWN", "DCF"].map((p, i) => (
              <motion.div key={p} className={s.panel} initial={{ opacity: 0, y: 14 }} whileInView={{ opacity: 1, y: 0 }} viewport={{ once: true }} transition={{ delay: 0.3 + i * 0.05, duration: 0.7, ease }}>
                <span className="mono">{p}</span>
                <i style={{ width: `${30 + ((i * 37) % 60)}%` }} />
                <i style={{ width: `${20 + ((i * 53) % 70)}%` }} />
              </motion.div>
            ))}
          </div>
        </div>
      </Reveal>
      <Reveal delay={0.2} className={s.center}>
        <Link href="/terminal" className={`${s.primary} ${s.big}`}><span>Open TRIKAL</span><kbd className={s.kbd}>/</kbd></Link>
      </Reveal>
    </section>
  );
}

/* ------------------------------------------------------------------ roadmap + footer */
const ROAD = [
  ["M0", "Plan & sources", "done"], ["M1", "Prices · identity · index history", "done"], ["M2", "Fundamentals & ownership", "download running"],
  ["M3", "Terminal shell & this page", "now"], ["M4", "Sector playbooks · Valuation Lab", "done"], ["M5", "Macro · policy · geo", "next"],
  ["M6", "Concalls & annual reports", "next"], ["M7", "KASAUTI score & backtests", "next"], ["M8", "Research bot & reports", "next"], ["M9", "Forensics · screener · calendar", "next"],
];

function Footer({ data }: { data?: Showcase }) {
  return (
    <footer className={s.footer}>
      <div className={s.road}>
        {ROAD.map(([m, l, st]) => (
          <div key={m} className={`${s.roadItem} ${s["st_" + st.split(" ")[0]]}`}>
            <span className="mono">{m}</span><b>{l}</b><i>{st}</i>
          </div>
        ))}
      </div>
      <div className={s.footBottom}>
        <Wordmark />
        <p>{data?.disclaimer ?? "Research tool. Not investment advice. No ratings or target prices."} Personal research use; data from public NSE/BSE archives, not redistributed.</p>
      </div>
    </footer>
  );
}

function Nav({ data }: { data?: Showcase }) {
  return (
    <nav className={s.nav}>
      <Link href="/" className={s.brand}><Wordmark /></Link>
      <div className={s.links}>
        <a href="#bhoot">Method</a>
        <Link href="/terminal">Terminal</Link>
        <span className={s.navStat}>{data ? <><b className="mono">{(data.stats.price_rows / 1e6).toFixed(1)}M</b> rows · <b className="mono">{indianGroup(data.stats.securities)}</b> securities</> : "connecting…"}</span>
      </div>
    </nav>
  );
}

export default function Home() {
  const { data, isError } = useShowcase();
  return (
    <main className={`${s.main} grain`}>
      <Nav data={data} />
      <Hero data={data} offline={isError} />
      <Bhoot data={data} />
      <Ledger data={data} />
      <Vartaman data={data} />
      <Bhavishya data={data} />
      <TerminalTeaser />
      <Footer data={data} />
      {data?.demo && <div className="demo-watermark">DEMO DATA</div>}
    </main>
  );
}
