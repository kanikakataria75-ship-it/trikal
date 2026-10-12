"use client";

/* The market on one day, as a city.
   Districts = sectors, plots = that day's index members sized by turnover (squarified treemap).
   Up moves rise out of a dark glass floor in teal; down moves sink beneath it in rose. Height = size of the
   move. Switching days collapses the city and raises the new one. Every tile is a real security and a real print. */

import { Canvas, useFrame, useThree, type ThreeEvent } from "@react-three/fiber";
import { Environment, Html, Lightformer } from "@react-three/drei";
import { Bloom, EffectComposer, ToneMapping, Vignette } from "@react-three/postprocessing";
import { ToneMappingMode } from "postprocessing";
import { useEffect, useLayoutEffect, useMemo, useRef } from "react";
import * as THREE from "three";

export type Tile = { security_id: string; code: string; name: string; open: number | null; close: number; prev_close: number | null; turnover: number; sector: string | null; change: number | null; gap: number | null; comparable: boolean };

const W = 15, D = 9;

/* ---------- squarified treemap ---------- */
type R = { x: number; y: number; w: number; h: number };
function squarify<T>(items: { v: number; d: T }[], rect: R): { r: R; d: T }[] {
  const out: { r: R; d: T }[] = [];
  const total = items.reduce((a, b) => a + b.v, 0) || 1;
  const scale = (rect.w * rect.h) / total;
  const list = items.map((x) => ({ a: x.v * scale, d: x.d })).sort((a, b) => b.a - a.a);
  let { x, y, w, h } = rect;
  let row: typeof list = [];
  const worst = (rw: typeof list, side: number) => {
    const s = rw.reduce((a, b) => a + b.a, 0);
    const mx = Math.max(...rw.map((r) => r.a)), mn = Math.min(...rw.map((r) => r.a));
    return Math.max((side * side * mx) / (s * s), (s * s) / (side * side * mn));
  };
  const flush = () => {
    const s = row.reduce((a, b) => a + b.a, 0);
    if (w >= h) {
      const cw = s / h;
      let cy = y;
      for (const r of row) { const ch = r.a / cw; out.push({ r: { x, y: cy, w: cw, h: ch }, d: r.d }); cy += ch; }
      x += cw; w -= cw;
    } else {
      const chh = s / w;
      let cx = x;
      for (const r of row) { const cw = r.a / chh; out.push({ r: { x: cx, y, w: cw, h: chh }, d: r.d }); cx += cw; }
      y += chh; h -= chh;
    }
    row = [];
  };
  for (const it of list) {
    const side = Math.min(w, h);
    if (!row.length || worst([...row, it], side) <= worst(row, side)) row.push(it);
    else { flush(); row.push(it); }
  }
  if (row.length) flush();
  return out;
}

export type Placed = { t: Tile; x: number; z: number; w: number; d: number };
export type District = { name: string; x: number; z: number; w: number; d: number; n: number; avg: number | null };

export function layoutCity(tiles: Tile[]): { placed: Placed[]; districts: District[] } {
  const groups = new Map<string, Tile[]>();
  for (const t of tiles) {
    const k = t.sector ?? "Unclassified";
    groups.set(k, [...(groups.get(k) ?? []), t]);
  }
  const weight = (t: Tile) => Math.pow(Math.max(t.turnover, 1e5), 0.55);
  const sec = squarify([...groups.entries()].map(([k, ts]) => ({ v: ts.reduce((a, t) => a + weight(t), 0), d: k })), { x: -W / 2, y: -D / 2, w: W, h: D });
  const placed: Placed[] = [];
  const districts: District[] = [];
  for (const s of sec) {
    const pad = 0.09;
    const inner = { x: s.r.x + pad, y: s.r.y + pad, w: Math.max(0.01, s.r.w - 2 * pad), h: Math.max(0.01, s.r.h - 2 * pad) };
    const ts = groups.get(s.d)!;
    const ch = ts.filter((t) => t.change !== null).map((t) => t.change!);
    districts.push({ name: s.d, x: s.r.x, z: s.r.y, w: s.r.w, d: s.r.h, n: ts.length, avg: ch.length ? ch.reduce((a, b) => a + b, 0) / ch.length : null });
    for (const c of squarify(ts.map((t) => ({ v: weight(t), d: t })), inner)) {
      const g = Math.min(0.03, c.r.w * 0.12, c.r.h * 0.12);
      placed.push({ t: c.d, x: c.r.x + c.r.w / 2, z: c.r.y + c.r.h / 2, w: Math.max(0.01, c.r.w - 2 * g), d: Math.max(0.01, c.r.h - 2 * g) });
    }
  }
  return { placed, districts };
}

/* ---------- colour and height of a move ---------- */
const TEAL = new THREE.Color("#2EC4B6"), ROSE = new THREE.Color("#F0577A"), FLAT = new THREE.Color("#2a2f37"), NA = new THREE.Color("#1a1d22");
export function moveColor(v: number | null, out = new THREE.Color()) {
  if (v === null) return out.copy(NA);
  const a = Math.min(1, Math.abs(v) / 0.06);
  out.copy(FLAT).lerp(v >= 0 ? TEAL : ROSE, Math.pow(a, 0.7));
  const glow = Math.max(0, Math.abs(v) - 0.05) * 14; // big moves exceed 1.0 and bloom
  return out.multiplyScalar(1 + glow);
}
const heightOf = (v: number | null) => (v === null ? 0.03 : Math.sign(v || 1e-9) * Math.min(3.4, 0.05 + Math.abs(v) * 26));

/* ---------- the instanced city ---------- */
function City({ placed, mode, onHover, onPick }: { placed: Placed[]; mode: "close" | "open"; onHover: (p: Placed | null, e?: ThreeEvent<PointerEvent>) => void; onPick: (p: Placed) => void }) {
  const mesh = useRef<THREE.InstancedMesh>(null);
  const cur = useRef<Float32Array>(new Float32Array(0));
  const target = useRef<Float32Array>(new Float32Array(0));
  const dummy = useMemo(() => new THREE.Object3D(), []);
  const color = useMemo(() => new THREE.Color(), []);
  const n = placed.length;

  useLayoutEffect(() => {
    cur.current = new Float32Array(n);           // a new day rises from flat ground
    target.current = new Float32Array(n);
  }, [placed, n]);

  useEffect(() => {
    if (!mesh.current) return;
    placed.forEach((p, i) => {
      const v = mode === "open" ? p.t.gap : p.t.change;
      target.current[i] = heightOf(v);
      mesh.current!.setColorAt(i, moveColor(v, color));
    });
    if (mesh.current.instanceColor) mesh.current.instanceColor.needsUpdate = true;
  }, [placed, mode, color]);

  useFrame((_, dt) => {
    const m = mesh.current;
    if (!m || !n) return;
    const k = 1 - Math.pow(0.0025, dt);       // frame-rate independent ease
    for (let i = 0; i < n; i++) {
      // stagger: tiles further back rise a beat later, like a wave rolling across the city
      const delay = (placed[i].z + D / 2) / D;
      const kk = cur.current[i] === 0 && delay > 0 ? k * (1 - delay * 0.55) : k;
      cur.current[i] += (target.current[i] - cur.current[i]) * kk;
      const h = cur.current[i];
      const p = placed[i];
      dummy.position.set(p.x, h / 2, p.z);
      dummy.scale.set(p.w, Math.max(0.004, Math.abs(h)), p.d);
      dummy.updateMatrix();
      m.setMatrixAt(i, dummy.matrix);
    }
    m.instanceMatrix.needsUpdate = true;
  });

  return (
    <instancedMesh
      key={n}
      ref={mesh}
      args={[undefined, undefined, Math.max(1, n)]}
      onPointerMove={(e) => { e.stopPropagation(); if (e.instanceId !== undefined) onHover(placed[e.instanceId], e); }}
      onPointerOut={() => onHover(null)}
      onClick={(e) => { e.stopPropagation(); if (e.instanceId !== undefined) onPick(placed[e.instanceId]); }}
    >
      <boxGeometry args={[1, 1, 1]} />
      <meshStandardMaterial color="#ffffff" roughness={0.35} metalness={0.25} envMapIntensity={0.6} />
    </instancedMesh>
  );
}

function Floor({ districts }: { districts: District[] }) {
  const lines = useMemo(() => {
    const pts: number[] = [];
    for (const s of districts) {
      const x0 = s.x + 0.04, x1 = s.x + s.w - 0.04, z0 = s.z + 0.04, z1 = s.z + s.d - 0.04;
      pts.push(x0, 0.002, z0, x1, 0.002, z0, x1, 0.002, z0, x1, 0.002, z1, x1, 0.002, z1, x0, 0.002, z1, x0, 0.002, z1, x0, 0.002, z0);
    }
    const g = new THREE.BufferGeometry();
    g.setAttribute("position", new THREE.Float32BufferAttribute(pts, 3));
    return g;
  }, [districts]);
  return (
    <group>
      {/* dark glass: what sank is still visible beneath it */}
      <mesh rotation={[-Math.PI / 2, 0, 0]} position={[0, 0, 0]} renderOrder={1}>
        <planeGeometry args={[W + 0.6, D + 0.6]} />
        <meshPhysicalMaterial color="#0a0b0e" transparent opacity={0.62} roughness={0.15} metalness={0.4} clearcoat={1} depthWrite={false} />
      </mesh>
      <lineSegments geometry={lines} renderOrder={2}>
        <lineBasicMaterial color="#8C6F1E" transparent opacity={0.55} />
      </lineSegments>
      {districts.filter((s) => s.w * s.d > 2.2).map((s) => (
        <Html key={s.name} position={[s.x + 0.14, 0.02, s.z + 0.2]} className="city-district" zIndexRange={[5, 0]} style={{ pointerEvents: "none" }}>
          <span>{s.name}</span>
          {s.avg !== null && <b className={s.avg >= 0 ? "pos" : "neg"}>{s.avg >= 0 ? "+" : "−"}{Math.abs(s.avg * 100).toFixed(1)}%</b>}
        </Html>
      ))}
    </group>
  );
}

function Rig({ arrive }: { arrive: number }) {
  const { camera, pointer } = useThree();
  const t = useRef(0);
  const a0 = useRef(arrive);
  const since = useRef(0);
  useFrame((_, dt) => {
    t.current += dt;
    if (a0.current !== arrive) { a0.current = arrive; since.current = 0; }
    since.current += dt;
    const e = 1 - Math.pow(1 - Math.min(1, since.current / 1.8), 3);   // arrival dolly on every new day
    const ang = Math.sin(t.current * 0.07) * 0.22 + pointer.x * 0.18;
    const r = 15.5 - e * 2.2;
    const y = 10.5 - e * 2.6 + pointer.y * 0.8;
    camera.position.set(Math.sin(ang) * r, y, Math.cos(ang) * r);
    camera.lookAt(0, -0.4, 0.4);
  });
  return null;
}

export default function MarketCity({ tiles, mode, arrive, onHover, onPick }: {
  tiles: Tile[]; mode: "close" | "open"; arrive: number;
  onHover: (p: Placed | null, x?: number, y?: number) => void; onPick: (p: Placed) => void;
}) {
  const { placed, districts } = useMemo(() => layoutCity(tiles), [tiles]);
  return (
    <Canvas dpr={[1, 1.5]} flat camera={{ position: [0, 9, 13], fov: 38, near: 0.1, far: 80 }} gl={{ antialias: true, powerPreference: "high-performance" }}>
      <color attach="background" args={["#060709"]} />
      <fog attach="fog" args={["#060709", 16, 34]} />
      <Environment resolution={128} frames={1}>
        <Lightformer form="rect" intensity={2.4} color="#fff1d2" position={[0, 8, 0]} rotation={[Math.PI / 2, 0, 0]} scale={[16, 6, 1]} />
        <Lightformer form="rect" intensity={1.0} color="#d4af37" position={[-10, 2, 4]} rotation={[0, Math.PI / 2, 0]} scale={[10, 2, 1]} />
        <Lightformer form="rect" intensity={0.9} color="#8fb4ff" position={[10, 1, -4]} rotation={[0, -Math.PI / 2, 0]} scale={[10, 2, 1]} />
      </Environment>
      <ambientLight intensity={0.25} />
      <directionalLight position={[-6, 12, 8]} intensity={1.6} color="#ffe6b8" />
      <directionalLight position={[8, -6, -6]} intensity={0.8} color="#ff8fa8" />
      <Rig arrive={arrive} />
      <City placed={placed} mode={mode} onHover={(p, e) => onHover(p, e?.nativeEvent.clientX, e?.nativeEvent.clientY)} onPick={onPick} />
      <Floor districts={districts} />
      <EffectComposer multisampling={0}>
        <Bloom mipmapBlur intensity={0.85} luminanceThreshold={0.9} luminanceSmoothing={0.25} radius={0.7} />
        <Vignette offset={0.2} darkness={0.9} />
        <ToneMapping mode={ToneMappingMode.ACES_FILMIC} />
      </EffectComposer>
    </Canvas>
  );
}
