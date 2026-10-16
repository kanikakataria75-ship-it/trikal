"use client";

import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { useCallback, useEffect, useRef } from "react";
import { DockviewReact, type DockviewApi, type DockviewReadyEvent, type IDockviewHeaderActionsProps, type IDockviewPanelProps } from "dockview-react";
import "dockview-react/dist/styles/dockview.css";
import { useCompany, useContextMarkers, useLive, useMeta, useTimeline } from "@/lib/api";
import { FUNCTIONS } from "@/lib/commands";
import { dmy, dmyTime, todayIST } from "@/lib/format";
import { storedMode, useT, workspace, type FnCode, type Mode } from "@/lib/store";
import { Wordmark } from "@/components/ui/Logo";
import ModeSwitch from "@/components/ui/ModeSwitch";
import TimeSpine from "@/components/ui/TimeSpine";
import CommandPalette from "./CommandPalette";
import { DES, EVT, GP, HELP } from "./PanelsA";
import { CR, DUP, FA } from "./PanelsB";
import { DCF, OWN, RV, WC } from "./PanelsC";
import { MACRO } from "./PanelsD";
import { MAP } from "./PanelsE";
import { GEO, TX } from "./PanelsF";
import { SEG } from "./PanelsG";
import { KAS } from "./PanelsH";
import { CALL } from "./PanelsI";
import "./terminal.css";
import "./map.css";
import "./pro.css";
import "./tx.css";

type P = { pin?: string };
const wrap = (C: React.ComponentType<{ params: P }>) => function Panel(props: IDockviewPanelProps<P>) { return <C params={props.params ?? {}} />; };
const COMPONENTS = { DES: wrap(DES), GP: wrap(GP), FA: wrap(FA), DUP: wrap(DUP), CR: wrap(CR), RV: wrap(RV), WC: wrap(WC), OWN: wrap(OWN), SEG: wrap(SEG), KAS: wrap(KAS), CALL: wrap(CALL), DCF: wrap(DCF), EVT: wrap(EVT), MACRO: wrap(MACRO), MAP: wrap(MAP), TX: wrap(TX), GEO: wrap(GEO), HELP: wrap(HELP) };
const title = (fn: FnCode, pin?: string) => `${fn}  ·  ${FUNCTIONS[fn].label}${pin ? `  ·  ⌖ ${dmy(pin)}` : ""}`;
const THEME = { name: "trikal", className: "dockview-theme-trikal", gap: 6 };

function HeaderActions(props: IDockviewHeaderActionsProps) {
  const asOf = useT((s) => s.asOf);
  const p = props.activePanel;
  if (!p) return null;
  const params = (p.params ?? {}) as P;
  const pinned = !!params.pin;
  return (
    <div className="dv-acts">
      <span className="dv-link" title="Link group A: follows the active company">A</span>
      <button className={pinned ? "on" : ""} title={pinned ? `Pinned to ${dmy(params.pin!)} — click to follow the Time Spine again` : "Pin this panel to the current as-of (compare then vs now)"}
        onClick={() => {
          const pin = pinned ? undefined : asOf === "NOW" ? todayIST() : asOf;
          p.api.updateParameters({ pin });
          p.api.setTitle(title(p.id as FnCode, pin));
        }}>⌖</button>
      <button title="Maximise (Ctrl+Shift+Enter)" onClick={() => (p.api.isMaximized() ? p.api.exitMaximized() : p.api.maximize())}>⤢</button>
    </div>
  );
}

/* PRO workstation layout: everything on one screen, no scrolling between tabs for the core views.
   left: DES over RV · centre: GP over FA · right: MAP over MACRO. Other functions are tabs inside those groups. */
function proLayout(api: DockviewApi) {
  api.clear();
  const add = (id: FnCode, ref?: string, direction?: "right" | "below" | "within") =>
    api.addPanel({ id, component: id, title: title(id), params: {}, ...(ref ? { position: { referencePanel: ref, direction: direction! } } : {}) });
  add("DES");
  add("GP", "DES", "right");
  add("MAP", "GP", "right");
  add("FA", "GP", "below");
  add("RV", "DES", "below");
  add("MACRO", "MAP", "below");
  add("DUP", "RV", "within");
  add("CR", "RV", "within");
  add("DCF", "FA", "within");
  add("EVT", "FA", "within");
  add("WC", "MACRO", "within");
  add("OWN", "MACRO", "within");
  add("SEG", "FA", "within");
  add("KAS", "DES", "within");
  add("CALL", "DES", "within");
  add("TX", "MACRO", "within");
  add("GEO", "MACRO", "within");
  for (const id of ["RV", "FA", "MACRO"] as const) api.getPanel(id)?.api.setActive();
  const size = () => {
    try {
      const w = api.width, h = api.height;
      if (!w || !h) return;
      api.getPanel("DES")?.group.api.setSize({ width: Math.round(w * 0.22) });
      api.getPanel("MAP")?.group.api.setSize({ width: Math.round(w * 0.34) });
      api.getPanel("GP")?.group.api.setSize({ height: Math.round(h * 0.58) });
      api.getPanel("DES")?.group.api.setSize({ height: Math.round(h * 0.46) });
      api.getPanel("MAP")?.group.api.setSize({ height: Math.round(h * 0.5) });
    } catch { /* sizing is cosmetic */ }
  };
  size();
  setTimeout(size, 80);
  setTimeout(size, 400);
}

function defaultLayout(api: DockviewApi, mode: Mode = "cinema") {
  if (mode === "pro") return proLayout(api);
  api.clear();
  api.addPanel({ id: "DES", component: "DES", title: title("DES"), params: {} });
  api.addPanel({ id: "GP", component: "GP", title: title("GP"), params: {}, position: { referencePanel: "DES", direction: "right" } });
  api.addPanel({ id: "DUP", component: "DUP", title: title("DUP"), params: {}, position: { referencePanel: "GP", direction: "right" } });
  api.addPanel({ id: "CR", component: "CR", title: title("CR"), params: {}, position: { referencePanel: "DUP", direction: "within" } });
  api.addPanel({ id: "DCF", component: "DCF", title: title("DCF"), params: {}, position: { referencePanel: "DUP", direction: "within" } });
  api.addPanel({ id: "FA", component: "FA", title: title("FA"), params: {}, position: { referencePanel: "GP", direction: "below" } });
  api.addPanel({ id: "EVT", component: "EVT", title: title("EVT"), params: {}, position: { referencePanel: "FA", direction: "within" } });
  api.addPanel({ id: "RV", component: "RV", title: title("RV"), params: {}, position: { referencePanel: "DUP", direction: "below" } });
  api.addPanel({ id: "WC", component: "WC", title: title("WC"), params: {}, position: { referencePanel: "RV", direction: "within" } });
  api.addPanel({ id: "OWN", component: "OWN", title: title("OWN"), params: {}, position: { referencePanel: "RV", direction: "within" } });
  api.addPanel({ id: "SEG", component: "SEG", title: title("SEG"), params: {}, position: { referencePanel: "FA", direction: "within" } });
  api.addPanel({ id: "KAS", component: "KAS", title: title("KAS"), params: {}, position: { referencePanel: "RV", direction: "within" } });
  api.addPanel({ id: "CALL", component: "CALL", title: title("CALL"), params: {}, position: { referencePanel: "RV", direction: "within" } });
  api.addPanel({ id: "MACRO", component: "MACRO", title: title("MACRO"), params: {}, position: { referencePanel: "RV", direction: "within" } });
  api.addPanel({ id: "TX", component: "TX", title: title("TX"), params: {}, position: { referencePanel: "RV", direction: "within" } });
  api.addPanel({ id: "GEO", component: "GEO", title: title("GEO"), params: {}, position: { referencePanel: "RV", direction: "within" } });
  api.getPanel("DUP")?.api.setActive();
  api.getPanel("FA")?.api.setActive();
  api.getPanel("RV")?.api.setActive();
  // the price chart is the centre of the desk: about half the width and two thirds of the height
  const size = () => {
    try {
      const w = api.width, h = api.height;
      if (!w || !h) return false;
      api.getPanel("DES")?.group.api.setSize({ width: Math.round(w * 0.24) });
      api.getPanel("DUP")?.group.api.setSize({ width: Math.round(w * 0.26) });
      api.getPanel("GP")?.group.api.setSize({ height: Math.round(h * 0.66) });
      api.getPanel("DUP")?.group.api.setSize({ height: Math.round(h * 0.55) });
      return true;
    } catch { return true; /* sizing is cosmetic */ }
  };
  size();
  // dockview finishes measuring after the first frames: apply again once the grid has settled
  setTimeout(size, 80);
  setTimeout(size, 400);
}

/* Function-key bar (PRO): the core views one keystroke away. F5/F11/F12 stay with the browser. */
const FKEYS: [string, FnCode][] = [["F1", "HELP"], ["F2", "DES"], ["F3", "GP"], ["F4", "FA"], ["F6", "RV"], ["F7", "MAP"], ["F8", "MACRO"], ["F9", "TX"], ["F10", "OWN"]];
const FKEY_MAP = Object.fromEntries(FKEYS) as Record<string, FnCode>;

function FKeyBar() {
  const { asOf, say } = useT();
  return (
    <div className="t-fkeys">
      {FKEYS.map(([k, fn]) => (
        <button key={k} onClick={() => workspace.open(fn)} title={FUNCTIONS[fn].desc}><b>{k}</b>{fn}</button>
      ))}
      <i />
      {(["DUP", "CR", "DCF", "EVT", "WC"] as FnCode[]).map((fn) => (
        <button key={fn} className="plain" onClick={() => workspace.open(fn)} title={FUNCTIONS[fn].desc}>{fn}</button>
      ))}
      <span className="t-fk-sp" />
      <button className="plain" onClick={() => say("SCRN, SHOCK, PORT arrive with M5–M9", "warn")}>SCRN · SHOCK · PORT <em>soon</em></button>
      <span className="t-fk-asof mono">{asOf === "NOW" ? "LIVE" : `AS OF ${dmy(asOf)}`}</span>
    </div>
  );
}

function Header() {
  const { asOf, setAsOf, code, setPalette, mode } = useT();
  const meta = useMeta(asOf);
  const co = useCompany(code, asOf);
  const live = useLive(code, asOf).data;
  const wm = meta.data?.watermark;
  return (
    <header className="t-head">
      <Link href="/?stay=1" className="t-brand">{mode === "pro" ? <span className="t-pro-brand">TRIKAL<b>PRO</b></span> : <Wordmark deva={false} />}</Link>
      <button className="t-cmd" onClick={() => setPalette(true)}>
        <span className="t-cmd-p">›</span>
        <span className="t-cmd-ph">Command · company, function or ASOF date</span>
        <kbd>/</kbd>
      </button>
      <div className="t-active">
        <span className="t-active-link">A</span>
        <b className="mono">{code}</b>
        <span className="t-active-name">{co.data?.name ?? (co.isError ? "not listed at this as-of" : "…")}</span>
        {live?.state === "value" && live.quote.change_pct !== null && (
          <span className={`t-live mono ${live.quote.change_pct >= 0 ? "pos" : "neg"}`}>{live.quote.ltp.toLocaleString("en-IN", { maximumFractionDigits: 2 })} {live.quote.change_pct >= 0 ? "▲" : "▼"}{Math.abs(live.quote.change_pct * 100).toFixed(2)}%{live.market_open ? <i className="live-dot" /> : null}</span>
        )}
      </div>
      <div className="t-head-right">
        <ModeSwitch />
        {asOf !== "NOW" ? (
          <button className="t-asof" onClick={() => setAsOf("NOW")} title="Return to NOW (Esc Esc)">AS OF {dmy(asOf)} <span>×</span></button>
        ) : (
          <span className="t-now">LIVE · NOW</span>
        )}
        <span className="t-wm" title="Newest data that any panel can be showing at this as-of">
          data to <b className="mono">{wm?.prices_known_at ? dmyTime(wm.prices_known_at) : "—"}</b>
        </span>
      </div>
    </header>
  );
}

function SpineBar() {
  const { asOf, setAsOf, code, mode } = useT();
  const tl = useTimeline(code, asOf);
  const cm = useContextMarkers(asOf);
  const co = useCompany(code, "NOW");
  const start = co.data?.listings.reduce((m, l) => (l.valid_from < m ? l.valid_from : m), "9999") ?? "1994-11-03";
  return (
    <div className="t-spine">
      <TimeSpine events={tl.data?.events ?? []} markers={cm.data?.markers} start={start === "9999" ? "1994-11-03" : start} now={todayIST()} asOf={asOf} onChange={setAsOf} height={mode === "pro" ? 44 : 58} futureFrac={0.08} />
    </div>
  );
}

function StatusBar() {
  const { asOf, lineage, dense, colorBlind, toggle, toast } = useT();
  const meta = useMeta(asOf);
  const st = meta.data?.stats;
  return (
    <footer className="t-status">
      <span className={`t-dot ${meta.isError ? "bad" : "ok"}`} />
      <span>{meta.isError ? "API offline" : st ? `${(st.price_rows / 1e6).toFixed(1)}M price rows · ${st.securities.toLocaleString("en-IN")} securities · ${st.filings} result filings (download in progress)` : "connecting…"}</span>
      {toast && <span className={`t-toast ${toast.tone}`}>{toast.text}</span>}
      <span className="t-sp" />
      <button className={lineage ? "on" : ""} onClick={() => toggle("lineage")} title="L">Lineage</button>
      <button className={dense ? "on" : ""} onClick={() => toggle("dense")} title="D">Dense</button>
      <button className={colorBlind ? "on" : ""} onClick={() => toggle("colorBlind")}>CB colours</button>
      {meta.data?.demo && <span className="t-demo">DEMO DATA</span>}
      <span className="t-disc">{meta.data?.disclaimer ?? "Research tool. Not investment advice."}</span>
    </footer>
  );
}

export default function Terminal() {
  const apiRef = useRef<DockviewApi | null>(null);
  const sp = useSearchParams();
  const { asOf, setAsOf, setCode, setPalette, toggle, dense, colorBlind, mode, setMode } = useT();
  const lastEsc = useRef(0);
  const layoutMode = useRef<Mode>("cinema");

  // the saved choice (localStorage) can only be read in the browser, after hydration
  useEffect(() => { setMode(storedMode()); }, [setMode]);
  // switching modes re-lays the workspace out: the same panels, arranged for the mode
  useEffect(() => {
    const api = apiRef.current;
    if (!api || layoutMode.current === mode) return;
    layoutMode.current = mode;
    defaultLayout(api, mode);
    const f = sp.get("fn") as FnCode | null;
    if (f && f in FUNCTIONS) setTimeout(() => open(f), 120);
  }, [mode]); // eslint-disable-line react-hooks/exhaustive-deps

  const open = useCallback((fn: FnCode, opts?: { pin?: string }) => {
    const api = apiRef.current;
    if (!api) return;
    if (api.hasMaximizedGroup()) api.exitMaximizedGroup();
    const ex = api.getPanel(fn);
    const ref = api.activePanel;
    const panel = ex ?? api.addPanel({ id: fn, component: fn, title: title(fn, opts?.pin), params: { pin: opts?.pin }, ...(ref ? { position: { referencePanel: ref.id, direction: "within" as const } } : {}) });
    panel.api.setActive();
    // the transmission and exposure desks need room: they open full-window (Esc, or open any other function, to go back)
    if (fn === "TX" || fn === "GEO") setTimeout(() => { try { api.maximizeGroup(panel); } catch { /* sizing only */ } }, 60);
  }, []);

  useEffect(() => {
    workspace.open = open;
    workspace.reset = () => apiRef.current && defaultLayout(apiRef.current);
  }, [open]);

  // deep links from the home page: /terminal?code=TCS&fn=FA&asof=2008-10-24
  useEffect(() => {
    const c = sp.get("code"), f = sp.get("fn") as FnCode | null, a = sp.get("asof");
    if (c) setCode(c);
    if (a) setAsOf(a);
    if (f && f in FUNCTIONS) setTimeout(() => open(f), 50);
  }, [sp, setCode, setAsOf, open]);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const typing = e.target instanceof HTMLElement && (e.target.tagName === "INPUT" || e.target.tagName === "TEXTAREA" || e.target.isContentEditable);
      if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "k") { e.preventDefault(); setPalette(true); return; }
      if (e.ctrlKey && e.shiftKey && e.key === "Enter") {
        const p = apiRef.current?.activePanel;
        if (p) (p.api.isMaximized() ? p.api.exitMaximized() : p.api.maximize());
        e.preventDefault();
        return;
      }
      if (e.key === "Escape" && apiRef.current?.hasMaximizedGroup()) { apiRef.current.exitMaximizedGroup(); return; }
      if (FKEY_MAP[e.key] && !e.ctrlKey && !e.altKey && !e.shiftKey) { e.preventDefault(); workspace.open(FKEY_MAP[e.key]); return; }
      if (typing) return;
      if (e.key === "/") { e.preventDefault(); setPalette(true); }
      else if (e.key === "Escape") {
        const now = Date.now();
        if (now - lastEsc.current < 600) setAsOf("NOW");
        lastEsc.current = now;
      }
      else if (e.key === "l" || e.key === "L") toggle("lineage");
      else if (e.key === "d" || e.key === "D") toggle("dense");
      else if (e.key === "[" || e.key === "]") {
        (document.querySelector(".t-spine .spine") as HTMLElement | null)?.dispatchEvent(new KeyboardEvent("keydown", { key: e.key, bubbles: true }));
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [setPalette, setAsOf, toggle]);

  const onReady = (e: DockviewReadyEvent) => {
    apiRef.current = e.api;
    layoutMode.current = useT.getState().mode;
    defaultLayout(e.api, layoutMode.current);
    const f = sp.get("fn") as FnCode | null;
    if (f && f in FUNCTIONS) open(f);
  };

  return (
    <div className={`term ${mode === "pro" ? "pro" : ""} ${dense ? "dense" : ""} ${asOf !== "NOW" ? "rewound" : ""}`} data-cb={colorBlind ? "1" : "0"}>
      <Header />
      <div className="t-work">
        <DockviewReact components={COMPONENTS} onReady={onReady} theme={THEME} rightHeaderActionsComponent={HeaderActions} />
      </div>
      <SpineBar />
      {mode === "pro" && <FKeyBar />}
      <StatusBar />
      <CommandPalette />
    </div>
  );
}
