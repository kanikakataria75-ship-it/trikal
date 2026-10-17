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

import { D, W, layoutCity, type District, type Placed, type Tile } from "@/lib/treemap";

export { layoutCity };
export type { District, Placed, Tile };

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
    <OrbitControls ref={ctl} makeDefault target={[0, -0.2, -1.0]} enableDamping dampingFactor={0.08} autoRotate autoRotateSpeed={0.25}
      minPolarAngle={0.35} maxPolarAngle={1.18} minDistance={7} maxDistance={24} enablePan={false}
      onStart={() => { touched.current = true; }} />
  );
}

/* ---------- the land around the city ---------- */
/* Mood of the day: wine on a fall, teal on a rise, ink when flat. Used for ground tint, sky and fog. */
function moodColors(mood: number) {
  const a = Math.min(1, Math.abs(mood) / 0.04);
  const base = new THREE.Color("#0b1018");
  const tint = new THREE.Color(mood < 0 ? "#3d0716" : "#063326");
  return { horizon: base.clone().lerp(tint, a), ground: new THREE.Color("#07080b").lerp(tint, a * 0.35) };
}

/* A survey map under the city: gold contour lines of a slow, drifting relief. Purely decorative (no data),
   masked under the city floor and fading into the distance. */
function TopoGround({ mood }: { mood: number }) {
  const mat = useMemo(() => new THREE.ShaderMaterial({
    transparent: true, depthWrite: false,
    uniforms: { uTime: { value: 0 }, uTint: { value: new THREE.Color() }, uHalf: { value: new THREE.Vector2(W / 2 + 0.45, D / 2 + 0.45) } },
    vertexShader: `varying vec2 vP; void main(){ vec4 w = modelMatrix * vec4(position,1.0); vP = w.xz; gl_Position = projectionMatrix * viewMatrix * w; }`,
    fragmentShader: `
      uniform float uTime; uniform vec3 uTint; uniform vec2 uHalf; varying vec2 vP;
      float h2(vec2 p){ return fract(sin(dot(p, vec2(127.1, 311.7))) * 43758.5453); }
      float n2(vec2 p){ vec2 i = floor(p), f = fract(p); vec2 u = f*f*(3.0-2.0*f);
        return mix(mix(h2(i), h2(i+vec2(1,0)), u.x), mix(h2(i+vec2(0,1)), h2(i+vec2(1,1)), u.x), u.y); }
      float fbm(vec2 p){ float s = 0.0, a = 0.5; for (int i = 0; i < 5; i++){ s += a * n2(p); p *= 2.03; a *= 0.5; } return s; }
      void main(){
        vec2 q = vP * 0.075 + vec2(uTime * 0.006, -uTime * 0.004);
        float h = fbm(q + fbm(q * 0.7) * 0.6);
        float k = h * 14.0;
        float w = fwidth(k);
        float line = 1.0 - smoothstep(w * 0.6, w * 1.6, min(fract(k), 1.0 - fract(k)));
        float major = 1.0 - smoothstep(w * 0.6, w * 1.8, min(fract(k / 5.0), 1.0 - fract(k / 5.0)) * 5.0);
        vec2 d = abs(vP) - uHalf;
        float outside = smoothstep(0.0, 1.2, max(d.x, d.y));            // nothing under the city floor
        float r = length(vP);
        float fade = 1.0 - smoothstep(16.0, 34.0, r);
        vec3 gold = vec3(0.83, 0.68, 0.22);
        vec3 col = uTint + gold * (line * 0.22 + major * 0.45);
        float alpha = (0.85 + line * 0.1) * outside * fade;
        gl_FragColor = vec4(col, alpha);
      }`,
  }), []);
  useEffect(() => { mat.uniforms.uTint.value.copy(moodColors(mood).ground); }, [mood, mat]);
  useFrame((s) => { mat.uniforms.uTime.value = s.clock.elapsedTime; });
  return (
    <mesh rotation={[-Math.PI / 2, 0, 0]} position={[0, -0.04, 0]} material={mat} renderOrder={0}>
      <planeGeometry args={[90, 90, 1, 1]} />
    </mesh>
  );
}

/* The months before, as a mountain range behind the city: the equal-weight path of that day's members
   (real data), with a gold rim and a beam of light standing on "this day". */
export type BeaconFn = (x: number, y: number, visible: boolean) => void;

function Ridge({ levels, mood, onBeacon }: { levels: number[]; mood: number; onBeacon?: BeaconFn }) {
  const { camera, size } = useThree();
  const proj = useMemo(() => new THREE.Vector3(), []);
  const built = useMemo(() => {
    if (levels.length < 5) return null;
    const lo = Math.min(...levels), hi = Math.max(...levels);
    const n = levels.length;
    // just behind the city, low enough to stay in frame from the default camera: four months back on the left,
    // this day on the right
    const z0 = -(D / 2 + 1.6);
    const pts = levels.map((v, i) => {
      const u = i / (n - 1);
      const x = -W / 2 + 0.3 + u * (W - 0.6);
      const bend = Math.pow(Math.abs(u - 0.5) * 2, 2) * 0.9;
      const y = 0.3 + ((v - lo) / Math.max(1e-9, hi - lo)) * 2.3;
      return new THREE.Vector3(x, y, z0 + bend);
    });
    const pos: number[] = [], al: number[] = [], idx: number[] = [];
    pts.forEach((p, i) => {
      pos.push(p.x, p.y, p.z, p.x, -0.05, p.z);
      al.push(1, 0);
      if (i < n - 1) { const k = i * 2; idx.push(k, k + 1, k + 2, k + 1, k + 3, k + 2); }
    });
    const g = new THREE.BufferGeometry();
    g.setAttribute("position", new THREE.Float32BufferAttribute(pos, 3));
    g.setAttribute("aTop", new THREE.Float32BufferAttribute(al, 1));
    g.setIndex(idx);
    const rim = new THREE.BufferGeometry().setFromPoints(pts);
    const rimLine = new THREE.Line(rim, new THREE.LineBasicMaterial({ color: new THREE.Color(2.4, 1.9, 0.7), toneMapped: false }));
    return { g, rimLine, end: pts[n - 1], start: pts[0], lo, hi, first: levels[0], last: levels[n - 1] };
  }, [levels]);
  const fill = useMemo(() => new THREE.ShaderMaterial({
    transparent: true, depthWrite: false, side: THREE.DoubleSide,
    uniforms: { uTint: { value: new THREE.Color() } },
    vertexShader: `attribute float aTop; varying float vTop; void main(){ vTop = aTop; gl_Position = projectionMatrix * modelViewMatrix * vec4(position,1.0); }`,
    fragmentShader: `uniform vec3 uTint; varying float vTop; void main(){ vec3 c = mix(uTint * 0.6, uTint * 2.4 + vec3(0.16,0.12,0.04), pow(vTop, 1.5)); gl_FragColor = vec4(c, 0.35 + vTop * 0.55); }`,
  }), []);
  useEffect(() => { fill.uniforms.uTint.value.copy(moodColors(mood).horizon); }, [mood, fill]);
  const beam = useRef<THREE.Mesh>(null);
  useFrame((s) => {
    if (beam.current) (beam.current.material as THREE.MeshBasicMaterial).opacity = 0.22 + Math.sin(s.clock.elapsedTime * 2) * 0.06;
    // project the beacon to the canvas so a plain DOM label can follow it (no per-frame React renders)
    if (onBeacon && built) {
      proj.copy(built.end); proj.y += 0.35; proj.project(camera);
      onBeacon((proj.x * 0.5 + 0.5) * size.width, (-proj.y * 0.5 + 0.5) * size.height, proj.z < 1 && Math.abs(proj.x) < 1.05 && Math.abs(proj.y) < 1.05);
    }
  });
  if (!built) return null;
  return (
    <group>
      <mesh geometry={built.g} material={fill} />
      <primitive object={built.rimLine} />
      <mesh ref={beam} position={[built.end.x, built.end.y + 1.6, built.end.z]}>
        <cylinderGeometry args={[0.04, 0.14, 3.2, 16, 1, true]} />
        <meshBasicMaterial color={new THREE.Color(2.2, 1.8, 0.7)} transparent opacity={0.25} toneMapped={false} depthWrite={false} side={THREE.DoubleSide} />
      </mesh>
      <mesh position={built.end}>
        <sphereGeometry args={[0.11, 20, 20]} />
        <meshBasicMaterial color={new THREE.Color(3, 2.4, 1)} toneMapped={false} />
      </mesh>
    </group>
  );
}

/* For low orbits: a sky that carries the day's mood down to the horizon. */
function Sky({ mood }: { mood: number }) {
  const mat = useMemo(() => new THREE.ShaderMaterial({
    side: THREE.BackSide, depthWrite: false, fog: false,
    uniforms: { uH: { value: new THREE.Color() }, uZ: { value: new THREE.Color("#040507") } },
    vertexShader: `varying vec3 vD; void main(){ vD = normalize(position); gl_Position = projectionMatrix * modelViewMatrix * vec4(position,1.0); }`,
    fragmentShader: `uniform vec3 uH; uniform vec3 uZ; varying vec3 vD; void main(){ float t = smoothstep(-0.05, 0.55, vD.y); vec3 c = mix(uH * 1.3, uZ, t); c += uH * exp(-pow((vD.y - 0.03) * 14.0, 2.0)) * 0.6; gl_FragColor = vec4(c, 1.0); }`,
  }), []);
  useEffect(() => { mat.uniforms.uH.value.copy(moodColors(mood).horizon); }, [mood, mat]);
  return <mesh material={mat}><sphereGeometry args={[70, 32, 16]} /></mesh>;
}

function MoodFog({ mood }: { mood: number }) {
  const { scene } = useThree();
  useEffect(() => {
    const c = moodColors(mood).horizon.clone().multiplyScalar(0.55);
    scene.fog = new THREE.Fog(c, 22, 48);
    scene.background = c;
  }, [mood, scene]);
  return null;
}

export default function MarketCity({ tiles, mode, arrive, onHover, onPick, ridge = [], mood = 0, onBeacon }: {
  tiles: Tile[]; mode: "close" | "open"; arrive: number;
  onHover: (p: Placed | null, x?: number, y?: number) => void; onPick: (p: Placed) => void;
  ridge?: number[]; mood?: number; onBeacon?: BeaconFn;
}) {
  const { placed, districts } = useMemo(() => layoutCity(tiles), [tiles]);
  return (
    <Canvas dpr={[1, 1.5]} flat camera={{ position: [0, 11.2, 12.8], fov: 38, near: 0.1, far: 160 }} gl={{ antialias: true, powerPreference: "high-performance" }}>
      <MoodFog mood={mood} />
      <Sky mood={mood} />
      <TopoGround mood={mood} />
      <Ridge levels={ridge} mood={mood} onBeacon={onBeacon} />
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
