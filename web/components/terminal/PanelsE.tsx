"use client";

/* MAP — the day's market as a flat heatmap. Same data and same treemap as the 3D Time Machine:
   sector → stock, area = turnover, colour = the session's move. Follows the global as-of. */

import { useEffect, useMemo, useRef, useState } from "react";
import { useTimeMachine } from "@/lib/api";
import { dmy, indianGroup } from "@/lib/format";
import { D, W, layoutCity, type Placed } from "@/lib/treemap";
import { useT, workspace } from "@/lib/store";
import { PanelState, usePanelAsOf } from "./common";
import type { PanelProps } from "./PanelsA";

const hex = (c: string) => [1, 3, 5].map((i) => parseInt(c.slice(i, i + 2), 16));
const mix = (a: string, b: string, t: number) => {
  const x = hex(a), y = hex(b);
  return `rgb(${x.map((v, i) => Math.round(v + (y[i] - v) * t)).join(",")})`;
};
const pct = (x: number | null) => (x === null ? "n/a" : `${x >= 0 ? "+" : "−"}${Math.abs(x * 100).toFixed(2)}%`);

export function MAP({ params }: PanelProps) {
  const asOf = usePanelAsOf(params.pin);
  const cb = useT((s) => s.colorBlind);
  const setCode = useT((s) => s.setCode);
  const q = useTimeMachine(asOf);
  const box = useRef<HTMLDivElement>(null);
  const [size, setSize] = useState({ w: 0, h: 0 });
  const [hover, setHover] = useState<Placed | null>(null);
  useEffect(() => {
    if (!box.current) return;
    const ro = new ResizeObserver((e) => setSize({ w: e[0].contentRect.width, h: e[0].contentRect.height }));
    ro.observe(box.current);
    return () => ro.disconnect();
  }, [q.data]);
  const up = cb ? "#4ea1ff" : "#2EC4B6", down = cb ? "#ff9f1c" : "#F0577A";
  const layout = useMemo(() => (q.data ? layoutCity(q.data.map.tiles) : null), [q.data]);
  const sx = size.w / W, sz = size.h / D;
  const colour = (v: number | null) => (v === null ? "#14171c" : mix("#1c2027", v >= 0 ? up : down, Math.pow(Math.min(1, Math.abs(v) / 0.05), 0.65)));
  const m = q.data?.market;
  return (
    <div className="t-panel map">
      <PanelState q={q}>
        {() => (
          <div className="mp">
            <div className="mp-bar">
              <b className="mono">{dmy(q.data!.map.session)}</b>
              {m && m.securities > 0 && (
                <>
                  <span><i className="pos">▲ {indianGroup(m.advances)}</i> <i className="neg">▼ {indianGroup(m.declines)}</i></span>
                  <span>median <b className={`mono ${(m.median_change ?? 0) >= 0 ? "pos" : "neg"}`}>{pct(m.median_change)}</b></span>
                </>
              )}
              <span className="t-dim">{q.data!.map.universe === "nifty500" ? "that day’s Nifty 500 members" : "the day’s 500 most-traded stocks (before the index existed)"} · area = turnover</span>
              <span className="mp-scale"><i style={{ background: down }} />−5%<i style={{ background: "#1c2027" }} />0<i style={{ background: up }} />+5%</span>
            </div>
            <div ref={box} className="mp-box" onMouseLeave={() => setHover(null)}>
              {layout && size.w > 0 && (
                <svg width={size.w} height={size.h}>
                  {layout.placed.map((p) => {
                    const x = (p.x - p.w / 2 + W / 2) * sx, y = (p.z - p.d / 2 + D / 2) * sz, w = p.w * sx, h = p.d * sz;
                    return (
                      <g key={p.t.security_id} onMouseEnter={() => setHover(p)} onClick={() => { setCode(p.t.code); workspace.open("DES"); }} style={{ cursor: "pointer" }}>
                        <rect x={x} y={y} width={Math.max(0, w)} height={Math.max(0, h)} fill={colour(p.t.change)} stroke={hover?.t.security_id === p.t.security_id ? "#F2D27A" : "none"} strokeWidth={1.5} />
                        {w > 38 && h > 22 && (
                          <text x={x + 4} y={y + 12} className="mp-code">
                            {p.t.code.slice(0, Math.floor(w / 6.4))}
                            {h > 34 && p.t.change !== null && <tspan x={x + 4} dy={11} className="mp-chg">{pct(p.t.change)}</tspan>}
                          </text>
                        )}
                      </g>
                    );
                  })}
                  {layout.districts.map((d) => (
                    <g key={d.name} pointerEvents="none">
                      <rect x={(d.x + W / 2) * sx} y={(d.z + D / 2) * sz} width={d.w * sx} height={d.d * sz} fill="none" stroke="#000" strokeWidth={2} />
                      {d.w * sx > 80 && d.d * sz > 40 && (
                        <text x={(d.x + W / 2) * sx + 4} y={(d.z + D / 2) * sz + d.d * sz - 5} className="mp-sec">
                          {d.name.toUpperCase().slice(0, Math.floor((d.w * sx) / 6.5))}{d.avg !== null && ` ${pct(d.avg)}`}
                        </text>
                      )}
                    </g>
                  ))}
                </svg>
              )}
            </div>
            <div className="mp-info mono">
              {hover ? (
                <>
                  <b>{hover.t.code}</b> {hover.t.name} · {hover.t.sector ?? "unclassified"} · close {hover.t.close.toLocaleString("en-IN")} ·{" "}
                  <span className={(hover.t.change ?? 0) >= 0 ? "pos" : "neg"}>{hover.t.comparable ? pct(hover.t.change) : "n/a · ex-date"}</span>
                  {" "}· turnover ₹{indianGroup(hover.t.turnover / 1e7)} Cr · click = open
                </>
              ) : <span className="t-dim">hover a stock · click opens it · the as-of follows the Time Spine</span>}
            </div>
          </div>
        )}
      </PanelState>
    </div>
  );
}
