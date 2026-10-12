"use client";

/* The market on one day, as a city.
   Districts = sectors, plots = that day's index members sized by turnover (squarified treemap).
   Up moves rise out of a dark glass floor in teal; down moves sink beneath it in rose. Height = size of the
   move. Switching days collapses the city and raises the new one. Every tile is a real security and a real print. */

import { Canvas, useFrame, useThree, type ThreeEvent } from "@react-three/fiber";
import { Environment, Html, Lightformer, OrbitControls } from "@react-three/drei";
import type { OrbitControls as OrbitControlsImpl } from "three-stdlib";
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
const UP = new THREE.Color("#39FF88"), DN = new THREE.Color("#FF2E63"), FLAT = new THREE.Color("#2a2f37"), NA = new THREE.Color("#1a1d22");
export function moveColor(v: number | null, out = new THREE.Color()) {
  if (v === null) return out.copy(NA);
  const a = Math.min(1, Math.abs(v) / 0.05);
  out.copy(FLAT).lerp(v >= 0 ? UP : DN, Math.pow(a, 0.6));
  const glow = Math.max(0, Math.abs(v) - 0.06) * 4; // only very large moves pass 1.0 and bloom, gently
  return out.multiplyScalar(1 + glow);
}

/* Neon material: tiles glow in their own colour, and coloured faces glitter (a few cells flash each frame,
   more on bigger moves). Grey, near-flat tiles stay matte. */
function useNeonMaterial() {
  const mat = useMemo(() => {
    const m = new THREE.MeshStandardMaterial({ color: "#ffffff", roughness: 0.3, metalness: 0.35, envMapIntensity: 0.7 });
    const uTime = { value: 0 };
    m.onBeforeCompile = (sh) => {
      sh.uniforms.uTime = uTime;
      sh.vertexShader = "varying vec3 vNeonWp;\n" + sh.vertexShader.replace("#include <begin_vertex>", `#include <begin_vertex>
        vec4 neonWp = vec4(transformed, 1.0);
        #ifdef USE_INSTANCING
          neonWp = instanceMatrix * neonWp;
        #endif
        vNeonWp = (modelMatrix * neonWp).xyz;`);
      sh.fragmentShader = "uniform float uTime;\nvarying vec3 vNeonWp;\n" + sh.fragmentShader.replace("#include <emissivemap_fragment>", `#include <emissivemap_fragment>
        #if defined( USE_COLOR )
          vec3 neonC = vColor.rgb;
          float neonSat = max(max(neonC.r, neonC.g), neonC.b) - min(min(neonC.r, neonC.g), neonC.b);
          vec2 neonCell = floor(vNeonWp.xz * 46.0 + vec2(vNeonWp.y * 37.0, vNeonWp.y * 19.0));
          float neonTw = fract(sin(dot(neonCell + floor(uTime * 8.0), vec2(12.9898, 78.233))) * 43758.5453);
          float neonSpark = step(0.988 - 0.008 * clamp(neonSat, 0.0, 1.0), neonTw) * smoothstep(0.12, 0.55, neonSat);
          totalEmissiveRadiance += neonC * 0.2 * neonSat + mix(vec3(1.0), neonC, 0.5) * neonSpark * 1.3;
        #endif`);
    };
    m.userData.uTime = uTime;
    return m;
  }, []);
  useFrame((s) => { mat.userData.uTime.value = s.clock.elapsedTime; });
  return mat;
}
const heightOf = (v: number | null) => (v === null ? 0.03 : Math.sign(v || 1e-9) * Math.min(3.4, 0.05 + Math.abs(v) * 26));

/* ---------- the instanced city ---------- */
function City({ placed, mode, onHover, onPick }: { placed: Placed[]; mode: "close" | "open"; onHover: (p: Placed | null, e?: ThreeEvent<PointerEvent>) => void; onPick: (p: Placed) => void }) {
  const mesh = useRef<THREE.InstancedMesh>(null);
  const cur = useRef<Float32Array>(new Float32Array(0));
  const target = useRef<Float32Array>(new Float32Array(0));
  const dummy = useMemo(() => new THREE.Object3D(), []);
  const color = useMemo(() => new THREE.Color(), []);
  const neon = useNeonMaterial();
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
      // keep every face off the floor plane (y = 0): coplanar faces z-fight and flicker
      dummy.position.set(p.x, h >= 0 ? h / 2 + 0.006 : h / 2 - 0.018, p.z);
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
      <primitive object={neon} attach="material" />
    </instancedMesh>
  );
}

const SHORT: Record<string, string> = {
  "Automobile and Auto Components": "Auto", "Fast Moving Consumer Goods": "FMCG", "Oil Gas & Consumable Fuels": "Oil & Gas",
  "Information Technology": "IT", "Financial Services": "Financials", "Media Entertainment & Publication": "Media",
  "Construction Materials": "Cement & materials", "Metals & Mining": "Metals", "Consumer Services": "Consumer services",
  "Consumer Durables": "Durables", "Capital Goods": "Capital goods", "Telecommunication": "Telecom",
};
export const shortSector = (x: string) => SHORT[x] ?? x;

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
      <mesh rotation={[-Math.PI / 2, 0, 0]} renderOrder={1}>
        <planeGeometry args={[W + 0.6, D + 0.6]} />
        <meshPhysicalMaterial color="#0a0b0e" transparent opacity={0.6} roughness={0.35} metalness={0.12} clearcoat={0.35} depthWrite={false} polygonOffset polygonOffsetFactor={1} polygonOffsetUnits={1} />
      </mesh>
      <lineSegments geometry={lines} renderOrder={2}>
        <lineBasicMaterial color="#8C6F1E" transparent opacity={0.6} />
      </lineSegments>
    </group>
  );
}

/* Screen-space labels: always upright and readable, whatever the camera angle. */
function Labels({ districts, placed, mode }: { districts: District[]; placed: Placed[]; mode: "close" | "open" }) {
  const top = useMemo(() => {
    const v = (p: Placed) => (mode === "open" ? p.t.gap : p.t.change);
    const byArea = [...placed].sort((a, b) => b.w * b.d - a.w * a.d).slice(0, 10);
    const byMove = [...placed].filter((p) => v(p) !== null).sort((a, b) => Math.abs(v(b)!) - Math.abs(v(a)!)).slice(0, 6);
    const seen = new Set<string>();
    return [...byMove, ...byArea].filter((p) => (seen.has(p.t.security_id) ? false : (seen.add(p.t.security_id), true)));
  }, [placed, mode]);
  return (
    <>
      {districts.filter((s) => s.w * s.d > 3).map((s) => (
        <Html key={"d" + s.name} position={[s.x + 0.12, 0.02, s.z + s.d - 0.12]} zIndexRange={[4, 0]} style={{ pointerEvents: "none" }}>
          <div className="city-district">
            <span>{shortSector(s.name)}</span>
            {s.avg !== null && <b className={s.avg >= 0 ? "pos" : "neg"}>{s.avg >= 0 ? "+" : "−"}{Math.abs(s.avg * 100).toFixed(1)}%</b>}
          </div>
        </Html>
      ))}
      {top.map((p) => {
        const v = mode === "open" ? p.t.gap : p.t.change;
        const h = heightOf(v);
        return (
          <Html key={"t" + p.t.security_id} position={[p.x, Math.max(0, h) + 0.15, p.z]} center zIndexRange={[6, 5]} style={{ pointerEvents: "none" }}>
            <div className={`city-tag ${(v ?? 0) >= 0 ? "up" : "down"}`}>
              <b>{p.t.code}</b>{v !== null && <span>{v >= 0 ? "+" : "−"}{Math.abs(v * 100).toFixed(1)}%</span>}
            </div>
          </Html>
        );
      })}
    </>
  );
}

/* Orbit/zoom for the viewer; a slow drift and an arrival dolly on every new day. */
function Rig({ arrive }: { arrive: number }) {
  const { camera } = useThree();
  const ctl = useRef<OrbitControlsImpl>(null);
  const since = useRef(0);
  const last = useRef(arrive);
  const touched = useRef(false);
  useFrame((_, dt) => {
    if (last.current !== arrive) { last.current = arrive; since.current = 0; }
    since.current += dt;
    const c = ctl.current;
    if (!c) return;
    if (since.current < 1.8) {
      const e = 1 - Math.pow(1 - since.current / 1.8, 3);
      const dir = camera.position.clone().sub(c.target).normalize();
      const dist = 21 - e * (21 - (touched.current ? camera.position.distanceTo(c.target) : 14.5));
      camera.position.copy(c.target.clone().add(dir.multiplyScalar(dist)));
    }
    c.update();
  });
  return (
    <OrbitControls ref={ctl} makeDefault target={[0, -0.3, 0.6]} enableDamping dampingFactor={0.08} autoRotate autoRotateSpeed={0.25}
      minPolarAngle={0.35} maxPolarAngle={1.18} minDistance={7} maxDistance={24} enablePan={false}
      onStart={() => { touched.current = true; }} />
  );
}

export default function MarketCity({ tiles, mode, arrive, onHover, onPick }: {
  tiles: Tile[]; mode: "close" | "open"; arrive: number;
  onHover: (p: Placed | null, x?: number, y?: number) => void; onPick: (p: Placed) => void;
}) {
  const { placed, districts } = useMemo(() => layoutCity(tiles), [tiles]);
  return (
    <Canvas dpr={[1, 1.5]} flat camera={{ position: [0, 13.5, 9.5], fov: 36, near: 0.1, far: 80 }} gl={{ antialias: true, powerPreference: "high-performance" }}>
      <color attach="background" args={["#060709"]} />
      <fog attach="fog" args={["#060709", 20, 40]} />
      <Environment resolution={128} frames={1}>
        <Lightformer form="rect" intensity={2.4} color="#fff1d2" position={[0, 8, 0]} rotation={[Math.PI / 2, 0, 0]} scale={[16, 6, 1]} />
        <Lightformer form="rect" intensity={1.0} color="#d4af37" position={[-10, 2, 4]} rotation={[0, Math.PI / 2, 0]} scale={[10, 2, 1]} />
        <Lightformer form="rect" intensity={0.9} color="#8fb4ff" position={[10, 1, -4]} rotation={[0, -Math.PI / 2, 0]} scale={[10, 2, 1]} />
      </Environment>
      <ambientLight intensity={0.3} />
      <directionalLight position={[-6, 12, 8]} intensity={1.6} color="#ffe6b8" />
      <directionalLight position={[8, -6, -6]} intensity={0.8} color="#ff8fa8" />
      <Rig arrive={arrive} />
      <City placed={placed} mode={mode} onHover={(p, e) => onHover(p, e?.nativeEvent.clientX, e?.nativeEvent.clientY)} onPick={onPick} />
      <Floor districts={districts} />
      <Labels districts={districts} placed={placed} mode={mode} />
      <EffectComposer multisampling={0}>
        <Bloom mipmapBlur intensity={0.4} luminanceThreshold={1.05} luminanceSmoothing={0.2} radius={0.55} />
        <Vignette offset={0.25} darkness={0.75} />
        <ToneMapping mode={ToneMappingMode.ACES_FILMIC} />
      </EffectComposer>
    </Canvas>
  );
}
