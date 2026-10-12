"use client";

/* Kaal-Rekha — the Time Spine (UI_SPEC §5).
   Log-like scale: the last two years are wide, old years compress. The playhead sets the global as-of on
   release. Right of NOW is Bhavishya: hatched, data-free, scenarios only — the playhead cannot enter it. */

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import type { TimelineEvent } from "@/lib/api";
import { dmy } from "@/lib/format";
import { TipLayer, useTip } from "./Tooltip";

const DAY = 86_400_000;
const K_YEARS = 2.2;

type Props = {
  events: TimelineEvent[];
  start: string;            // earliest date on the spine
  now: string;              // today (IST)
  asOf: string;             // "NOW" or YYYY-MM-DD
  onChange?: (asOf: string) => void;
  height?: number;
  futureFrac?: number;
  showLabels?: boolean;
  scenarioNote?: string;
};

const iso = (t: number) => new Date(t).toISOString().slice(0, 10);

export default function TimeSpine({ events, start, now, asOf, onChange, height = 64, futureFrac = 0.1, showLabels = true, scenarioNote }: Props) {
  const wrap = useRef<HTMLDivElement>(null);
  const [w, setW] = useState(900);
  const [drag, setDrag] = useState<number | null>(null);
  const { tip, show, move, hide } = useTip();

  useEffect(() => {
    if (!wrap.current) return;
    const ro = new ResizeObserver((e) => setW(e[0].contentRect.width));
    ro.observe(wrap.current);
    return () => ro.disconnect();
  }, []);

  const tNow = Date.parse(now), tStart = Date.parse(start);
  const A = Math.max(0.5, (tNow - tStart) / (365.25 * DAY));
  const padL = 14, padR = 14;
  const pastW = (w - padL - padR) * (1 - futureFrac);
  const xOf = useCallback((t: number) => {
    const a = Math.max(0, (tNow - t) / (365.25 * DAY));
    const u = 1 - Math.log(1 + a / K_YEARS) / Math.log(1 + A / K_YEARS);
    return padL + u * pastW;
  }, [tNow, A, pastW]);
  const tOf = useCallback((x: number) => {
    const u = Math.min(1, Math.max(0, (x - padL) / pastW));
    const a = K_YEARS * (Math.pow(1 + A / K_YEARS, 1 - u) - 1);
    return tNow - a * 365.25 * DAY;
  }, [tNow, A, pastW]);

  const asOfT = asOf === "NOW" ? tNow : Date.parse(asOf);
  const headX = drag ?? xOf(asOfT);
  const nowX = padL + pastW;
  const mid = height / 2 + 4;

  const years = useMemo(() => {
    const out: { x: number; y: number; major: boolean }[] = [];
    const y0 = new Date(tStart).getUTCFullYear() + 1, y1 = new Date(tNow).getUTCFullYear();
    let lastX = -999;
    for (let y = y1; y >= y0; y--) {
      const x = xOf(Date.UTC(y, 0, 1));
      const major = y % 5 === 0;
      if (lastX - x > 30 || (major && lastX - x > 18) || lastX < 0) { out.push({ x, y, major }); lastX = x; }
    }
    return out;
  }, [tStart, tNow, xOf]);

  const onDown = (e: React.PointerEvent) => {
    if (!onChange) return;
    (e.target as Element).setPointerCapture?.(e.pointerId);
    const r = wrap.current!.getBoundingClientRect();
    setDrag(Math.min(nowX, Math.max(padL, e.clientX - r.left)));
  };
  const onMove = (e: React.PointerEvent) => {
    if (drag === null) return;
    const r = wrap.current!.getBoundingClientRect();
    setDrag(Math.min(nowX, Math.max(padL, e.clientX - r.left)));
  };
  const onUp = () => {
    if (drag === null || !onChange) return;
    const t = tOf(drag);
    setDrag(null);
    onChange(nowX - drag < 3 ? "NOW" : iso(t));
  };

  const onKey = (e: React.KeyboardEvent) => {
    if (!onChange) return;
    const cur = asOfT;
    const step = e.shiftKey ? 365 * DAY : (e.ctrlKey ? 91 * DAY : 30 * DAY);
    const sorted = events.map((ev) => Date.parse(ev.date)).sort((a, b) => a - b);
    let t: number | null = null;
    if (e.key === "ArrowLeft") t = cur - step;
    else if (e.key === "ArrowRight") t = cur + step;
    else if (e.key === "[") t = [...sorted].reverse().find((x) => x < cur - DAY) ?? null;
    else if (e.key === "]") t = sorted.find((x) => x > cur + DAY) ?? null;
    else if (e.key === "Home" || e.key === "Escape") { onChange("NOW"); e.preventDefault(); return; }
    if (t !== null) {
      e.preventDefault();
      onChange(t >= tNow - DAY / 2 ? "NOW" : iso(Math.max(tStart, t)));
    }
  };

  const color = (ty: TimelineEvent["type"]) =>
    ty === "corporate_action" ? "var(--gold-0)" : ty === "results" ? "var(--pos)" : ty === "index_in" ? "#9fb8ff" : "var(--neg)";

  return (
    <div ref={wrap} className="spine" style={{ position: "relative", height, userSelect: "none", touchAction: "none" }}
      tabIndex={onChange ? 0 : -1} onKeyDown={onKey} aria-label="Time spine: drag or use arrow keys to set the as-of date">
      <svg width={w} height={height} onPointerDown={onDown} onPointerMove={onMove} onPointerUp={onUp} style={{ display: "block", cursor: onChange ? "ew-resize" : "default" }}>
        <defs>
          <linearGradient id="sp-past" x1="0" x2="1">
            <stop offset="0" stopColor="#8C6F1E" stopOpacity="0.25" />
            <stop offset="0.7" stopColor="#D4AF37" stopOpacity="0.8" />
            <stop offset="1" stopColor="#F2D27A" />
          </linearGradient>
          <pattern id="sp-hatch" width="6" height="6" patternUnits="userSpaceOnUse" patternTransform="rotate(45)">
            <rect width="1.2" height="6" fill="#D4AF37" opacity="0.28" />
          </pattern>
          <filter id="sp-glow"><feGaussianBlur stdDeviation="2.4" /></filter>
        </defs>
        {/* Bhavishya: hatched future, no data */}
        <rect x={nowX + 4} y={mid - 12} width={w - nowX - padR - 4} height={24} fill="url(#sp-hatch)" rx={3} />
        {/* rewound region dims */}
        {asOf !== "NOW" && drag === null && <rect x={headX} y={mid - 14} width={nowX - headX} height={28} fill="#07080a" opacity={0.55} />}
        {/* the spine */}
        <line x1={padL} x2={nowX} y1={mid} y2={mid} stroke="url(#sp-past)" strokeWidth={1.4} />
        {years.map((y) => (
          <g key={y.y}>
            <line x1={y.x} x2={y.x} y1={mid - (y.major ? 6 : 3)} y2={mid + (y.major ? 6 : 3)} stroke="#6B7079" strokeWidth={1} />
            {showLabels && (
              <text x={y.x} y={mid + 19} fill={y.major ? "#A7A9AE" : "#6B7079"} fontSize={9.5} textAnchor="middle" className="mono">
                {y.major || years.length < 18 ? y.y : `’${String(y.y).slice(2)}`}
              </text>
            )}
          </g>
        ))}
        {/* events */}
        {events.map((ev, i) => {
          const x = xOf(Date.parse(ev.date));
          const c = color(ev.type);
          const node =
            ev.type === "corporate_action" ? <path d={`M${x} ${mid - 9} l4 4 l-4 4 l-4 -4 z`} fill={c} />
              : ev.type === "results" ? <rect x={x - 0.75} y={mid - 10} width={1.5} height={7} fill={c} opacity={0.9} />
                : ev.type === "index_in" ? <circle cx={x} cy={mid + 8} r={2.6} fill={c} />
                  : <circle cx={x} cy={mid + 8} r={2.6} fill="none" stroke={c} strokeWidth={1.2} />;
          return (
            <g key={i}
              onMouseEnter={(e) => show(e, <div><b>{ev.label}</b><div className="k">{dmy(ev.date)}</div>{ev.detail && <div>{ev.detail}</div>}<div className="k">public at {ev.known_at?.slice(0, 16).replace("T", " ")}</div></div>)}
              onMouseMove={move} onMouseLeave={hide}
              onClick={(e) => { e.stopPropagation(); onChange?.(iso(Date.parse(ev.known_at ?? ev.date) + DAY)); }}
              style={{ cursor: "pointer" }}>
              <rect x={x - 5} y={mid - 14} width={10} height={28} fill="transparent" />
              {node}
            </g>
          );
        })}
        {/* NOW */}
        <g>
          <circle cx={nowX} cy={mid} r={6} fill="#F2D27A" opacity={0.35} filter="url(#sp-glow)" className="spine-pulse" />
          <line x1={nowX} x2={nowX} y1={mid - 13} y2={mid + 13} stroke="#F2D27A" strokeWidth={2} />
          {showLabels && <text x={nowX} y={mid - 17} fill="#F2D27A" fontSize={9} textAnchor="middle" letterSpacing="0.14em">NOW</text>}
        </g>
        {showLabels && (
          <>
            <text x={padL} y={mid - 17} fill="#6B7079" fontSize={9} letterSpacing="0.18em">BHOOT · भूत</text>
            <text x={w - padR} y={mid - 17} fill="#8C6F1E" fontSize={9} textAnchor="end" letterSpacing="0.18em">BHAVISHYA · भविष्य</text>
          </>
        )}
        {scenarioNote && (
          <text x={(nowX + w - padR) / 2} y={mid + 3} fill="#A7A9AE" fontSize={8.5} textAnchor="middle" opacity={0.8}>{scenarioNote}</text>
        )}
        {/* playhead */}
        {onChange && (asOf !== "NOW" || drag !== null) && (
          <g>
            <line x1={headX} x2={headX} y1={4} y2={height - 4} stroke="#D4AF37" strokeWidth={1.5} />
            <rect x={headX - 34} y={1} width={68} height={14} rx={3} fill="#D4AF37" />
            <text x={headX} y={11} fill="#07080a" fontSize={9} textAnchor="middle" fontWeight={700} className="mono">
              {dmy(iso(drag !== null ? tOf(drag) : asOfT))}
            </text>
          </g>
        )}
      </svg>
      <TipLayer tip={tip} />
    </div>
  );
}
