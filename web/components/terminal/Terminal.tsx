"use client";

import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { useCallback, useEffect, useRef } from "react";
import { DockviewReact, type DockviewApi, type DockviewReadyEvent, type IDockviewHeaderActionsProps, type IDockviewPanelProps } from "dockview-react";
import "dockview-react/dist/styles/dockview.css";
import { useCompany, useMeta, useTimeline } from "@/lib/api";
import { FUNCTIONS } from "@/lib/commands";
import { dmy, dmyTime, todayIST } from "@/lib/format";
import { useT, workspace, type FnCode } from "@/lib/store";
import { Wordmark } from "@/components/ui/Logo";
import TimeSpine from "@/components/ui/TimeSpine";
import CommandPalette from "./CommandPalette";
import { DES, EVT, GP, HELP } from "./PanelsA";
import { CR, DUP, FA } from "./PanelsB";
import { DCF, OWN, RV, WC } from "./PanelsC";
import "./terminal.css";

type P = { pin?: string };
const wrap = (C: React.ComponentType<{ params: P }>) => function Panel(props: IDockviewPanelProps<P>) { return <C params={props.params ?? {}} />; };
const COMPONENTS = { DES: wrap(DES), GP: wrap(GP), FA: wrap(FA), DUP: wrap(DUP), CR: wrap(CR), RV: wrap(RV), WC: wrap(WC), OWN: wrap(OWN), DCF: wrap(DCF), EVT: wrap(EVT), HELP: wrap(HELP) };
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

function defaultLayout(api: DockviewApi) {
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
  api.getPanel("DUP")?.api.setActive();
  api.getPanel("FA")?.api.setActive();
  api.getPanel("RV")?.api.setActive();
  try {
    const w = api.width;
    api.getPanel("DES")?.group.api.setSize({ width: Math.round(w * 0.3) });
    api.getPanel("DUP")?.group.api.setSize({ width: Math.round(w * 0.3) });
  } catch { /* sizing is cosmetic */ }
}

function Header() {
  const { asOf, setAsOf, code, setPalette } = useT();
  const meta = useMeta(asOf);
  const co = useCompany(code, asOf);
  const wm = meta.data?.watermark;
  return (
    <header className="t-head">
      <Link href="/" className="t-brand"><Wordmark deva={false} /></Link>
      <button className="t-cmd" onClick={() => setPalette(true)}>
        <span className="t-cmd-p">›</span>
        <span className="t-cmd-ph">Command · company, function or ASOF date</span>
        <kbd>/</kbd>
      </button>
      <div className="t-active">
        <span className="t-active-link">A</span>
        <b className="mono">{code}</b>
        <span className="t-active-name">{co.data?.name ?? (co.isError ? "not listed at this as-of" : "…")}</span>
      </div>
      <div className="t-head-right">
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
  const { asOf, setAsOf, code } = useT();
  const tl = useTimeline(code, asOf);
  const co = useCompany(code, "NOW");
  const start = co.data?.listings.reduce((m, l) => (l.valid_from < m ? l.valid_from : m), "9999") ?? "1994-11-03";
  return (
    <div className="t-spine">
      <TimeSpine events={tl.data?.events ?? []} start={start === "9999" ? "1994-11-03" : start} now={todayIST()} asOf={asOf} onChange={setAsOf} height={58} futureFrac={0.08} />
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
  const { asOf, setAsOf, setCode, setPalette, toggle, dense, colorBlind } = useT();
  const lastEsc = useRef(0);

  const open = useCallback((fn: FnCode, opts?: { pin?: string }) => {
    const api = apiRef.current;
    if (!api) return;
    const ex = api.getPanel(fn);
    if (ex) { ex.api.setActive(); return; }
    const ref = api.activePanel;
    api.addPanel({ id: fn, component: fn, title: title(fn, opts?.pin), params: { pin: opts?.pin }, ...(ref ? { position: { referencePanel: ref.id, direction: "within" as const } } : {}) });
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
    defaultLayout(e.api);
    const f = sp.get("fn") as FnCode | null;
    if (f && f in FUNCTIONS) open(f);
  };

  return (
    <div className={`term ${dense ? "dense" : ""} ${asOf !== "NOW" ? "rewound" : ""}`} data-cb={colorBlind ? "1" : "0"}>
      <Header />
      <div className="t-work">
        <DockviewReact components={COMPONENTS} onReady={onReady} theme={THEME} rightHeaderActionsComponent={HeaderActions} />
      </div>
      <SpineBar />
      <StatusBar />
      <CommandPalette />
    </div>
  );
}
