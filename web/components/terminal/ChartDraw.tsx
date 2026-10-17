"use client";

/* Drawing tools for the price chart, like a trading platform: trend lines and rays, horizontal / vertical lines, support-resistance
   zones (blocks), Fibonacci retracement, text notes and a measure tool. Everything is anchored to (bar index, price), so it stays put
   when the chart is panned, zoomed or switched between log and linear. Drawings are the viewer's own notes: they live in this browser
   (localStorage, per stock) and never touch any data or any number TRIKAL computes. */

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import type { IChartApi, ISeriesApi, SeriesType } from "lightweight-charts";

type Pt = { l: number; p: number };
type Kind = "trend" | "hline" | "vline" | "zone" | "fib" | "text";
type Drawing = { id: string; kind: Kind; pts: Pt[]; color: string; width: number; text?: string; ray?: boolean };
type Tool = "select" | Kind | "measure";

const COLORS = ["#F2D27A", "#2EC4B6", "#F0577A", "#7AA2F7", "#B48EF0", "#E8E6E1"];
const FIB = [0, 0.236, 0.382, 0.5, 0.618, 0.786, 1];
const TOOLS: { id: Tool; label: string; title: string; pts: number }[] = [
  { id: "select", label: "⌖", title: "Select, move and edit (Esc)", pts: 0 },
  { id: "trend", label: "／", title: "Trend line (two clicks). Double-click it to turn it into a ray", pts: 2 },
  { id: "hline", label: "─", title: "Horizontal line / price level (one click)", pts: 1 },
  { id: "vline", label: "│", title: "Vertical line (one click)", pts: 1 },
  { id: "zone", label: "▭", title: "Support / resistance zone (two clicks: opposite corners; it extends to the right)", pts: 2 },
  { id: "fib", label: "≡", title: "Fibonacci retracement (two clicks: swing start, swing end)", pts: 2 },
  { id: "text", label: "T", title: "Text note (one click)", pts: 1 },
  { id: "measure", label: "⇔", title: "Measure: change in price and bars between two clicks (not saved)", pts: 2 },
];
const key = (code: string) => `trikal.draw.v1.${code}`;
const uid = () => Math.random().toString(36).slice(2, 9);

function load(code: string | null): Drawing[] {
  if (!code) return [];
  try { return JSON.parse(localStorage.getItem(key(code)) ?? "[]") as Drawing[]; } catch { return []; }
}
function save(code: string | null, d: Drawing[]) {
  if (!code) return;
  try { localStorage.setItem(key(code), JSON.stringify(d)); } catch { /* storage can be blocked: drawings just last for the session */ }
}

export default function ChartDraw({ chart, series, code, bars }: { chart: IChartApi | null; series: ISeriesApi<SeriesType> | null; code: string | null; bars: number }) {
  const [open, setOpen] = useState(false);
  const [tool, setTool] = useState<Tool>("select");
  const [color, setColor] = useState(COLORS[0]);
  const [items, setItems] = useState<Drawing[]>([]);
  const [sel, setSel] = useState<string | null>(null);
  const [pending, setPending] = useState<Pt[]>([]);
  const [cursor, setCursor] = useState<Pt | null>(null);
  const [measure, setMeasure] = useState<[Pt, Pt] | null>(null);
  const [, setTick] = useState(0);
  const undo = useRef<Drawing[][]>([]);
  const box = useRef<HTMLDivElement>(null);
  const drag = useRef<{ id: string; handle: number | null; x: number; y: number; orig: Pt[] } | null>(null);

  useEffect(() => { setItems(load(code)); setSel(null); setPending([]); undo.current = []; }, [code]);

  const commit = useCallback((next: Drawing[], remember = true) => {
    if (remember) undo.current = [...undo.current.slice(-30), items];
    setItems(next);
    save(code, next);
  }, [items, code]);

  // re-place the drawings when the chart moves: time range, size, or a change of the price scale
  const sig = useRef("");
  useEffect(() => {
    if (!chart || !series) return;
    const iv = setInterval(() => {
      const ts = chart.timeScale();
      const r = ts.getVisibleLogicalRange();
      const s = `${r?.from}|${r?.to}|${series.priceToCoordinate(1)}|${series.priceToCoordinate(1000)}|${box.current?.clientWidth}|${box.current?.clientHeight}`;
      if (s !== sig.current) { sig.current = s; setTick((n) => n + 1); }
    }, 90);
    return () => clearInterval(iv);
  }, [chart, series]);

  const dims = () => {
    const w = box.current?.clientWidth ?? 0, h = box.current?.clientHeight ?? 0;
    let pw = 56, th = 26;
    try { pw = chart!.priceScale("right").width(); th = chart!.timeScale().height(); } catch { /* defaults */ }
    return { w, h, pw, th, pr: Math.max(10, w - pw), pb: Math.max(10, h - th) };
  };
  const toXY = (p: Pt): { x: number; y: number } | null => {
    if (!chart || !series) return null;
    const x = chart.timeScale().logicalToCoordinate(p.l as never), y = series.priceToCoordinate(p.p);
    return x === null || y === null ? null : { x: x as number, y: y as number };
  };
  const toPt = (x: number, y: number): Pt | null => {
    if (!chart || !series) return null;
    const l = chart.timeScale().coordinateToLogical(x), p = series.coordinateToPrice(y);
    return l === null || p === null ? null : { l: Math.round((l as number) * 100) / 100, p: p as number };
  };
  const local = (e: React.PointerEvent | PointerEvent) => {
    const r = box.current!.getBoundingClientRect();
    return { x: e.clientX - r.left, y: e.clientY - r.top };
  };

  const need = TOOLS.find((t) => t.id === tool)?.pts ?? 0;
  const onDown = (e: React.PointerEvent) => {
    if (tool === "select") return;
    const { x, y } = local(e);
    const pt = toPt(x, y);
    if (!pt) return;
    e.stopPropagation();
    if (tool === "measure") {
      if (pending.length === 0) { setPending([pt]); setMeasure(null); } else { setMeasure([pending[0], pt]); setPending([]); }
      return;
    }
    if (need === 1) {
      let text: string | undefined;
      if (tool === "text") { text = window.prompt("Note") ?? ""; if (!text) return; }
      const d: Drawing = { id: uid(), kind: tool as Kind, pts: [pt], color, width: 1.5, text };
      commit([...items, d]);
      setSel(d.id);
      setTool("select");
      return;
    }
    if (pending.length === 0) { setPending([pt]); return; }
    const d: Drawing = { id: uid(), kind: tool as Kind, pts: [pending[0], pt], color, width: 1.5 };
    commit([...items, d]);
    setPending([]);
    setSel(d.id);
    setTool("select");
  };
  const onMove = (e: React.PointerEvent) => {
    const { x, y } = local(e);
    if (drag.current) {
      const dr = drag.current;
      const dx = x - dr.x, dy = y - dr.y;
      const next = items.map((d) => {
        if (d.id !== dr.id) return d;
        const pts = dr.orig.map((o, i) => {
          if (dr.handle !== null && dr.handle !== i) return o;
          const o2 = toXY(o);
          return o2 ? (toPt(o2.x + dx, o2.y + dy) ?? o) : o;
        });
        return { ...d, pts };
      });
      setItems(next);
      return;
    }
    if (tool !== "select" && pending.length) setCursor(toPt(x, y));
  };
  const onUp = () => {
    if (drag.current) { save(code, items); drag.current = null; }
  };
  const startDrag = (e: React.PointerEvent, d: Drawing, handle: number | null) => {
    if (tool !== "select") return;
    e.stopPropagation();
    (e.currentTarget as Element).setPointerCapture?.(e.pointerId);
    const { x, y } = local(e);
    undo.current = [...undo.current.slice(-30), items];
    drag.current = { id: d.id, handle, x, y, orig: d.pts };
    setSel(d.id);
  };

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const t = e.target as HTMLElement | null;
      if (t && (t.tagName === "INPUT" || t.tagName === "TEXTAREA")) return;
      if (e.key === "Escape") { setPending([]); setTool("select"); setMeasure(null); setSel(null); }
      if ((e.key === "Delete" || e.key === "Backspace") && sel && open) { commit(items.filter((d) => d.id !== sel)); setSel(null); }
      if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "z" && open && undo.current.length) {
        e.preventDefault();
        const prev = undo.current[undo.current.length - 1];
        undo.current = undo.current.slice(0, -1);
        setItems(prev);
        save(code, prev);
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [sel, items, open, commit, code]);

  const D = dims();
  const fmt = (p: number) => p.toLocaleString("en-IN", { maximumFractionDigits: p >= 100 ? 1 : 2 });
  const selected = items.find((d) => d.id === sel);

  const shapes = useMemo(() => items, [items]);
  const rightEdge = D.pr;

  function renderShape(d: Drawing) {
    const a = toXY(d.pts[0]);
    const b = d.pts[1] ? toXY(d.pts[1]) : null;
    if (!a) return null;
    const isSel = d.id === sel;
    const hit = { stroke: "transparent", strokeWidth: 12, fill: "none", pointerEvents: tool === "select" ? ("stroke" as const) : ("none" as const), cursor: "move" };
    const handle = (p: { x: number; y: number }, i: number) => isSel && (
      <circle key={i} cx={p.x} cy={p.y} r={5} fill="#0B0D10" stroke={d.color} strokeWidth={2} style={{ cursor: "grab", pointerEvents: "all" }} onPointerDown={(e) => startDrag(e, d, i)} />
    );
    const grab = (e: React.PointerEvent) => startDrag(e, d, null);
    if (d.kind === "hline") {
      return (
        <g key={d.id}>
          <line x1={0} x2={rightEdge} y1={a.y} y2={a.y} stroke={d.color} strokeWidth={d.width} strokeDasharray="6 4" />
          <line x1={0} x2={rightEdge} y1={a.y} y2={a.y} {...hit} onPointerDown={grab} />
          <text x={rightEdge - 6} y={a.y - 4} textAnchor="end" className="cd-t" fill={d.color}>{fmt(d.pts[0].p)}</text>
          {handle({ x: 24, y: a.y }, 0)}
        </g>
      );
    }
    if (d.kind === "vline") {
      return (
        <g key={d.id}>
          <line x1={a.x} x2={a.x} y1={0} y2={D.pb} stroke={d.color} strokeWidth={d.width} strokeDasharray="6 4" />
          <line x1={a.x} x2={a.x} y1={0} y2={D.pb} {...hit} onPointerDown={grab} />
          {handle({ x: a.x, y: 24 }, 0)}
        </g>
      );
    }
    if (d.kind === "text") {
      return (
        <g key={d.id} onPointerDown={grab} style={{ cursor: tool === "select" ? "move" : "default", pointerEvents: tool === "select" ? "all" : "none" }}>
          <rect x={a.x - 3} y={a.y - 14} width={Math.max(20, (d.text?.length ?? 1) * 6.4 + 8)} height={18} fill="rgba(11,13,16,0.82)" stroke={isSel ? d.color : "transparent"} />
          <text x={a.x + 1} y={a.y - 1} className="cd-t" fill={d.color}>{d.text}</text>
        </g>
      );
    }
    if (!b) return null;
    if (d.kind === "trend") {
      let x2 = b.x, y2 = b.y;
      if (d.ray && b.x !== a.x) { const k = (b.y - a.y) / (b.x - a.x); x2 = rightEdge; y2 = a.y + k * (x2 - a.x); if (b.x < a.x) { x2 = 0; y2 = a.y + k * (x2 - a.x); } }
      const chg = (d.pts[1].p / d.pts[0].p - 1) * 100;
      return (
        <g key={d.id} onDoubleClick={() => tool === "select" && commit(items.map((x) => (x.id === d.id ? { ...x, ray: !x.ray } : x)))}>
          <line x1={a.x} y1={a.y} x2={x2} y2={y2} stroke={d.color} strokeWidth={d.width} />
          <line x1={a.x} y1={a.y} x2={x2} y2={y2} {...hit} onPointerDown={grab} />
          {isSel && <text x={(a.x + b.x) / 2 + 6} y={(a.y + b.y) / 2 - 6} className="cd-t" fill={d.color}>{chg >= 0 ? "+" : "−"}{Math.abs(chg).toFixed(1)}% · {Math.abs(Math.round(d.pts[1].l - d.pts[0].l))} bars{d.ray ? " · ray" : ""}</text>}
          {handle(a, 0)}{handle(b, 1)}
        </g>
      );
    }
    if (d.kind === "zone") {
      const x1 = Math.min(a.x, b.x), y1 = Math.min(a.y, b.y), h = Math.abs(b.y - a.y);
      const hi = Math.max(d.pts[0].p, d.pts[1].p), lo = Math.min(d.pts[0].p, d.pts[1].p);
      return (
        <g key={d.id}>
          <rect x={x1} y={y1} width={Math.max(2, rightEdge - x1)} height={Math.max(2, h)} fill={d.color} fillOpacity={0.14} stroke={d.color} strokeOpacity={0.7} strokeWidth={1} />
          <rect x={x1} y={y1} width={Math.max(2, rightEdge - x1)} height={Math.max(2, h)} {...hit} onPointerDown={grab} />
          <text x={x1 + 6} y={y1 + 12} className="cd-t" fill={d.color}>{fmt(hi)} – {fmt(lo)}</text>
          {handle(a, 0)}{handle(b, 1)}
        </g>
      );
    }
    // fib
    const p0 = d.pts[0].p, p1 = d.pts[1].p;
    const x1 = Math.min(a.x, b.x);
    return (
      <g key={d.id}>
        {FIB.map((f, i) => {
          const price = p1 + (p0 - p1) * f;
          const y = series!.priceToCoordinate(price);
          if (y === null) return null;
          return (
            <g key={f}>
              <line x1={x1} x2={rightEdge} y1={y as number} y2={y as number} stroke={d.color} strokeOpacity={f === 0 || f === 1 ? 0.9 : 0.55} strokeWidth={1} strokeDasharray={f === 0 || f === 1 ? undefined : "4 4"} />
              <text x={x1 + 4} y={(y as number) - 3} className="cd-t" fill={d.color}>{(f * 100).toFixed(1)}% · {fmt(price)}</text>
            </g>
          );
        })}
        <line x1={a.x} y1={a.y} x2={b.x} y2={b.y} stroke={d.color} strokeOpacity={0.5} strokeDasharray="2 3" />
        <line x1={a.x} y1={a.y} x2={b.x} y2={b.y} {...hit} onPointerDown={grab} />
        {handle(a, 0)}{handle(b, 1)}
      </g>
    );
  }

  // the preview while a two-click tool waits for its second point
  function preview() {
    if (!pending.length || !cursor) return null;
    const a = toXY(pending[0]), b = toXY(cursor);
    if (!a || !b) return null;
    if (tool === "zone") return <rect x={Math.min(a.x, b.x)} y={Math.min(a.y, b.y)} width={Math.max(2, rightEdge - Math.min(a.x, b.x))} height={Math.abs(b.y - a.y)} fill={color} fillOpacity={0.1} stroke={color} strokeDasharray="4 3" />;
    return <line x1={a.x} y1={a.y} x2={b.x} y2={b.y} stroke={color} strokeDasharray="4 3" strokeWidth={1.5} />;
  }
  function measureShape() {
    if (!measure) return null;
    const a = toXY(measure[0]), b = toXY(measure[1]);
    if (!a || !b) return null;
    const chg = (measure[1].p / measure[0].p - 1) * 100;
    const up = chg >= 0;
    return (
      <g>
        <rect x={Math.min(a.x, b.x)} y={Math.min(a.y, b.y)} width={Math.abs(b.x - a.x)} height={Math.abs(b.y - a.y)} fill={up ? "#2EC4B6" : "#F0577A"} fillOpacity={0.12} stroke={up ? "#2EC4B6" : "#F0577A"} strokeDasharray="3 3" />
        <text x={(a.x + b.x) / 2} y={Math.min(a.y, b.y) - 6} textAnchor="middle" className="cd-t" fill={up ? "#2EC4B6" : "#F0577A"}>
          {up ? "+" : "−"}{Math.abs(chg).toFixed(2)}% · {fmt(measure[1].p - measure[0].p)} · {Math.abs(Math.round(measure[1].l - measure[0].l))} bars
        </text>
      </g>
    );
  }

  return (
    <>
      <div className="cd-bar">
        <button className={`cd-toggle ${open ? "on" : ""}`} onClick={() => { setOpen((o) => !o); setTool("select"); setPending([]); }} title="Drawing tools: trend lines, support / resistance zones, Fibonacci, notes">✎ Draw{items.length ? ` (${items.length})` : ""}</button>
        {open && (
          <>
            {TOOLS.map((t) => (
              <button key={t.id} className={`cd-tool ${tool === t.id ? "on" : ""}`} title={t.title} onClick={() => { setTool(t.id); setPending([]); setMeasure(null); }}>{t.label}</button>
            ))}
            <span className="cd-sep" />
            {COLORS.map((c) => (
              <button key={c} className={`cd-sw ${(selected?.color ?? color) === c ? "on" : ""}`} style={{ background: c }} title="Colour"
                onClick={() => { setColor(c); if (selected) commit(items.map((d) => (d.id === selected.id ? { ...d, color: c } : d))); }} />
            ))}
            <span className="cd-sep" />
            <button className="cd-tool" title="Delete the selected drawing (Delete)" disabled={!sel} onClick={() => { if (sel) { commit(items.filter((d) => d.id !== sel)); setSel(null); } }}>⌫</button>
            <button className="cd-tool" title="Undo (Ctrl+Z)" disabled={!undo.current.length} onClick={() => { const prev = undo.current.pop(); if (prev) { setItems(prev); save(code, prev); } }}>↶</button>
            <button className="cd-tool" title="Remove every drawing on this stock" disabled={!items.length} onClick={() => { if (window.confirm("Remove all drawings on this stock?")) { commit([]); setSel(null); } }}>✕</button>
            <span className="cd-hint">{pending.length ? "click the second point (Esc cancels)" : tool === "select" ? "drag a drawing or its handles · Delete removes" : need === 2 ? "click two points" : "click to place"}</span>
          </>
        )}
      </div>
      <div ref={box} className="cd-layer" style={{ pointerEvents: "none" }}>
        {chart && series && bars > 0 && (
          <svg width="100%" height="100%" onPointerMove={onMove} onPointerUp={onUp}
            style={{ position: "absolute", inset: 0, pointerEvents: drag.current ? "all" : "none", overflow: "hidden" }}>
            <defs><clipPath id="cd-clip"><rect x={0} y={0} width={D.pr} height={D.pb} /></clipPath></defs>
            <g clipPath="url(#cd-clip)">
              {tool !== "select" && <rect x={0} y={0} width={D.pr} height={D.pb} fill="transparent" style={{ pointerEvents: "all", cursor: "crosshair" }} onPointerDown={onDown} onPointerMove={onMove} />}
              {shapes.map(renderShape)}
              {preview()}
              {measureShape()}
            </g>
          </svg>
        )}
      </div>
    </>
  );
}
