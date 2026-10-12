"use client";

/* KASAUTI — the touchstone hero.
   A goldsmith tests gold by rubbing it on a black stone and reading the streak. Here the streak IS data:
   the real, split/bonus-adjusted price history of a marquee stock (served by the API from NSE bhavcopies),
   drawn onto a polished basalt slab, while the three arcs of time (past / present / future) turn around it. */

import { Canvas, useFrame, useThree } from "@react-three/fiber";
import { ContactShadows, Environment, Html, Lightformer, PerformanceMonitor, PresentationControls } from "@react-three/drei";
import { Bloom, EffectComposer, Noise, ToneMapping, Vignette } from "@react-three/postprocessing";
import { ToneMappingMode } from "postprocessing";
import { useEffect, useMemo, useRef, useState } from "react";
import * as THREE from "three";
import { RoundedBoxGeometry } from "three/addons/geometries/RoundedBoxGeometry.js";
import type { Streak } from "@/lib/api";
import { makeStoneTextures, organicSlab } from "./textures";

export type TipReadout = { code: string; name: string; date: string; price: number; progress: number; from: string; to: string; sessions: number; first: number; last: number; source: string };

const STONE = { w: 4.6, h: 0.5, d: 2.7 };
const FACE_Y = STONE.h / 2 + 0.004;
const SPAN_X = 1.95;
const SPAN_Z = 0.92;
const DRAW_SECONDS = 6.5;
const HOLD_SECONDS = 3.2;
const FADE_SECONDS = 1.1;

/* ---------- the stone ---------- */
function Stone({ intro }: { intro: React.MutableRefObject<number> }) {
  const tex = useMemo(() => makeStoneTextures(512), []);
  const geo = useMemo(() => organicSlab(new RoundedBoxGeometry(STONE.w, STONE.h, STONE.d, 10, 0.2), 0.05, 5), []);
  const mat = useRef<THREE.MeshPhysicalMaterial>(null);
  useFrame(() => {
    if (mat.current) mat.current.envMapIntensity = 0.25 + intro.current * 1.05;
  });
  return (
    <mesh geometry={geo} castShadow receiveShadow>
      <meshPhysicalMaterial
        ref={mat}
        color="#0b0b0e"
        map={tex.map}
        roughnessMap={tex.roughness}
        normalMap={tex.normal}
        normalScale={new THREE.Vector2(0.35, 0.35)}
        roughness={0.55}
        metalness={0.05}
        clearcoat={0.85}
        clearcoatRoughness={0.18}
        sheen={0.2}
        sheenColor="#2a2418"
        envMapIntensity={0.2}
      />
    </mesh>
  );
}

/* ---------- the gold streak (real prices) ---------- */
const streakVert = /* glsl */ `
  attribute float aT; attribute float aSide;
  varying float vT; varying float vSide; varying vec3 vW;
  void main(){ vT = aT; vSide = aSide; vec4 w = modelMatrix * vec4(position,1.0); vW = w.xyz; gl_Position = projectionMatrix * viewMatrix * w; }
`;
const streakFrag = /* glsl */ `
  uniform float uProgress; uniform float uTime; uniform float uFade; uniform float uDissolve;
  varying float vT; varying float vSide; varying vec3 vW;
  float hash(vec2 p){ return fract(sin(dot(p, vec2(127.1,311.7))) * 43758.5453); }
  float noise(vec2 p){ vec2 i=floor(p), f=fract(p); vec2 u=f*f*(3.0-2.0*f);
    return mix(mix(hash(i),hash(i+vec2(1,0)),u.x), mix(hash(i+vec2(0,1)),hash(i+vec2(1,1)),u.x), u.y); }
  void main(){
    if (vT > uProgress) discard;
    float s = abs(vSide);
    float edge = 1.0 - smoothstep(0.35, 1.0, s + (noise(vec2(vT*260.0, 1.7)) - 0.5) * 0.5);
    // rubbed metal: long grains along the stroke, broken by the stone's pores
    float g = noise(vec2(vT*1400.0, vSide*5.0)) * 0.55 + noise(vec2(vT*5200.0, vSide*21.0)) * 0.45;
    float pores = smoothstep(0.18, 0.45, noise(vW.xz * 140.0));
    float a = edge * smoothstep(0.22, 0.62, g * 0.85 + edge * 0.3) * mix(0.55, 1.0, pores);
    // dissolve: grains drop out at random as the stone is wiped for the next assay
    a *= step(uDissolve, hash(floor(vW.xz * 520.0)));
    vec3 deep = vec3(0.50, 0.36, 0.09), mid = vec3(0.86, 0.68, 0.24), hi = vec3(1.0, 0.9, 0.62);
    float tone = noise(vec2(vT*520.0, vSide*2.0));
    vec3 col = mix(deep, mid, smoothstep(0.1, 0.7, tone));
    col = mix(col, hi, smoothstep(0.75, 1.0, tone) * 0.8);
    // glints that shimmer with time and view
    float gl = step(0.992, hash(floor(vW.xz * 900.0) + floor(uTime * 6.0)));
    col += gl * vec3(2.4, 2.0, 1.2);
    // the hot point of contact
    float d = (uProgress - vT);
    float tip = exp(-d * d * 9000.0) * step(uProgress, 0.999);
    col += vec3(3.2, 2.4, 1.1) * tip;
    gl_FragColor = vec4(col * 1.25, a * uFade);
  }
`;

function buildStreak(st: Streak) {
  const n = st.c.length;
  const t0 = Date.parse(st.t[0]), t1 = Date.parse(st.t[n - 1]);
  const logs = st.c.map((c) => Math.log(Math.max(c, 1e-6)));
  const lo = Math.min(...logs), hi = Math.max(...logs);
  // light smoothing so the stroke reads like a hand stroke but keeps every turn of the chart
  const sm = logs.map((_, i) => {
    let s = 0, k = 0;
    for (let j = Math.max(0, i - 1); j <= Math.min(n - 1, i + 1); j++) { s += logs[j]; k++; }
    return s / k;
  });
  const pts = sm.map((v, i) => {
    const x = -SPAN_X + ((Date.parse(st.t[i]) - t0) / Math.max(1, t1 - t0)) * SPAN_X * 2;
    const z = SPAN_Z - ((v - lo) / Math.max(1e-6, hi - lo)) * SPAN_Z * 2;
    return new THREE.Vector3(x, FACE_Y, z);
  });
  const curve = new THREE.CatmullRomCurve3(pts, false, "centripetal", 0.3);
  const N = 1400;
  const P = curve.getSpacedPoints(N);
  const pos: number[] = [], aT: number[] = [], aSide: number[] = [], idx: number[] = [];
  for (let i = 0; i <= N; i++) {
    const a = P[Math.max(0, i - 1)], b = P[Math.min(N, i + 1)];
    const tx = b.x - a.x, tz = b.z - a.z;
    const l = Math.hypot(tx, tz) || 1;
    const nx = -tz / l, nz = tx / l;
    // pressure varies along a real stroke
    const w = 0.034 + 0.016 * Math.sin(i * 0.021) + 0.01 * Math.sin(i * 0.137 + 1.3);
    for (const side of [-1, 1]) {
      pos.push(P[i].x + nx * w * side, FACE_Y, P[i].z + nz * w * side);
      aT.push(i / N);
      aSide.push(side);
    }
    if (i < N) { const k = i * 2; idx.push(k, k + 1, k + 2, k + 1, k + 3, k + 2); }
  }
  const g = new THREE.BufferGeometry();
  g.setAttribute("position", new THREE.Float32BufferAttribute(pos, 3));
  g.setAttribute("aT", new THREE.Float32BufferAttribute(aT, 1));
  g.setAttribute("aSide", new THREE.Float32BufferAttribute(aSide, 1));
  g.setIndex(idx);
  // map spline progress back to a data index, for the live readout
  const tAt = (p: number) => {
    const pt = curve.getPointAt(Math.min(1, Math.max(0, p)));
    const frac = (pt.x + SPAN_X) / (SPAN_X * 2);
    const target = t0 + frac * (t1 - t0);
    let best = 0;
    for (let i = 0; i < n; i++) if (Date.parse(st.t[i]) <= target) best = i;
    return { i: best, point: pt };
  };
  return { geo: g, curve, tAt };
}

function GoldDust({ tip, active }: { tip: React.MutableRefObject<THREE.Vector3>; active: React.MutableRefObject<boolean> }) {
  const COUNT = 220;
  const ref = useRef<THREE.Points>(null);
  const state = useMemo(() => ({
    p: new Float32Array(COUNT * 3), v: new Float32Array(COUNT * 3), life: new Float32Array(COUNT), next: 0,
  }), []);
  const geo = useMemo(() => {
    const g = new THREE.BufferGeometry();
    g.setAttribute("position", new THREE.BufferAttribute(state.p, 3));
    g.setAttribute("aLife", new THREE.BufferAttribute(state.life, 1));
    return g;
  }, [state]);
  const mat = useMemo(() => new THREE.ShaderMaterial({
    transparent: true, depthWrite: false, blending: THREE.AdditiveBlending,
    vertexShader: `attribute float aLife; varying float vL; void main(){ vL = aLife; vec4 mv = modelViewMatrix * vec4(position,1.0); gl_PointSize = (2.0 + 5.0*aLife) * (6.0 / -mv.z); gl_Position = projectionMatrix * mv; }`,
    fragmentShader: `varying float vL; void main(){ vec2 c = gl_PointCoord - 0.5; float d = length(c); if (d > 0.5) discard; float a = smoothstep(0.5, 0.0, d) * vL; gl_FragColor = vec4(vec3(1.0,0.82,0.45) * 2.2, a); }`,
  }), []);
  useFrame((_, dt) => {
    const s = state;
    const spawn = active.current ? 3 : 0;
    for (let k = 0; k < spawn; k++) {
      const i = s.next; s.next = (s.next + 1) % COUNT;
      s.p[i * 3] = tip.current.x; s.p[i * 3 + 1] = tip.current.y + 0.01; s.p[i * 3 + 2] = tip.current.z;
      s.v[i * 3] = (Math.random() - 0.5) * 0.5; s.v[i * 3 + 1] = 0.25 + Math.random() * 0.55; s.v[i * 3 + 2] = (Math.random() - 0.5) * 0.5;
      s.life[i] = 1;
    }
    for (let i = 0; i < COUNT; i++) {
      if (s.life[i] <= 0) continue;
      s.v[i * 3 + 1] -= 1.6 * dt;
      s.p[i * 3] += s.v[i * 3] * dt; s.p[i * 3 + 1] += s.v[i * 3 + 1] * dt; s.p[i * 3 + 2] += s.v[i * 3 + 2] * dt;
      if (s.p[i * 3 + 1] < FACE_Y) { s.p[i * 3 + 1] = FACE_Y; s.v[i * 3] *= 0.3; s.v[i * 3 + 2] *= 0.3; s.v[i * 3 + 1] *= -0.2; }
      s.life[i] -= dt * 0.9;
    }
    geo.attributes.position.needsUpdate = true;
    geo.attributes.aLife.needsUpdate = true;
  });
  return <points ref={ref} geometry={geo} material={mat} frustumCulled={false} />;
}

function StreakAssay({ streaks, onTip, reduced }: { streaks: Streak[]; onTip: (t: TipReadout) => void; reduced: boolean }) {
  const [k, setK] = useState(0);
  const st = streaks[k % streaks.length];
  const built = useMemo(() => buildStreak(st), [st]);
  const mat = useMemo(() => new THREE.ShaderMaterial({
    vertexShader: streakVert, fragmentShader: streakFrag, transparent: true, depthWrite: false,
    polygonOffset: true, polygonOffsetFactor: -2,
    uniforms: { uProgress: { value: 0 }, uTime: { value: 0 }, uFade: { value: 1 }, uDissolve: { value: 0 } },
  }), []);
  const clock = useRef(0);
  const tip = useRef(new THREE.Vector3());
  const drawing = useRef(false);
  const light = useRef<THREE.PointLight>(null);
  const lastEmit = useRef(0);

  useEffect(() => { clock.current = reduced ? DRAW_SECONDS : -0.6; }, [k, reduced, st]);

  useFrame((s, dt) => {
    clock.current += dt;
    const c = clock.current;
    const u = mat.uniforms;
    u.uTime.value = s.clock.elapsedTime;
    const raw = Math.min(1, Math.max(0, c / DRAW_SECONDS));
    const p = raw < 0.5 ? 4 * raw ** 3 : 1 - Math.pow(-2 * raw + 2, 3) / 2; // ease in-out, like a hand
    u.uProgress.value = p;
    const fadeStart = DRAW_SECONDS + HOLD_SECONDS;
    u.uDissolve.value = reduced || streaks.length < 2 ? 0 : Math.min(1, Math.max(0, (c - fadeStart) / FADE_SECONDS));
    drawing.current = c > 0 && c < DRAW_SECONDS;
    const { i, point } = built.tAt(p);
    tip.current.copy(point);
    if (light.current) {
      light.current.position.set(point.x, FACE_Y + 0.25, point.z);
      light.current.intensity = drawing.current ? 1.6 + Math.sin(s.clock.elapsedTime * 40) * 0.25 : THREE.MathUtils.lerp(light.current.intensity, 0, 0.06);
    }
    if (s.clock.elapsedTime - lastEmit.current > 0.07) {
      lastEmit.current = s.clock.elapsedTime;
      onTip({ code: st.code, name: st.name, date: st.t[i], price: st.c[i], progress: p, from: st.from, to: st.to, sessions: st.sessions, first: st.first, last: st.last, source: st.source });
    }
    if (!reduced && c > fadeStart + FADE_SECONDS + 0.2 && streaks.length > 1) setK((x) => x + 1);
  });

  return (
    <group>
      <mesh geometry={built.geo} material={mat} renderOrder={2} />
      <pointLight ref={light} color="#ffcf7a" distance={1.6} decay={2} intensity={0} />
      {!reduced && <GoldDust tip={tip} active={drawing} />}
    </group>
  );
}

/* ---------- the three arcs of time ---------- */
function TimeArcs({ reduced }: { reduced: boolean }) {
  const g = useRef<THREE.Group>(null);
  const bead = useRef<THREE.Mesh>(null);
  const R = 3.45;
  const past = 1.18 * Math.PI;   // Bhoot: the long engraved arc
  const gap = 0.07 * Math.PI;
  const futureN = 22;            // Bhavishya: dashed, never solid
  useFrame((s, dt) => {
    if (g.current && !reduced) g.current.rotation.y += dt * 0.035;
    if (bead.current) {
      const k = 1 + Math.sin(s.clock.elapsedTime * 2.2) * 0.18;
      bead.current.scale.setScalar(k);
    }
  });
  const ticks = useMemo(() => {
    const arr: number[] = [];
    for (let i = 0; i <= 32; i++) arr.push((i / 32) * past);
    return arr;
  }, [past]);
  const presentAngle = past + gap / 2;
  return (
    <group rotation={[0.16, 0, -0.05]} position={[0, -0.05, 0]}>
      <group ref={g}>
        {/* Bhoot */}
        <mesh rotation={[Math.PI / 2, 0, 0]}>
          <torusGeometry args={[R, 0.0065, 8, 360, past]} />
          <meshStandardMaterial color="#d4af37" emissive="#8c6f1e" emissiveIntensity={0.9} metalness={1} roughness={0.25} />
        </mesh>
        {ticks.map((a, i) => (
          <mesh key={i} position={[Math.cos(a) * R, 0, -Math.sin(a) * R]} rotation={[0, a, 0]}>
            <boxGeometry args={[i % 4 === 0 ? 0.11 : 0.05, 0.004, 0.004]} />
            <meshStandardMaterial color="#f2d27a" emissive="#d4af37" emissiveIntensity={i % 4 === 0 ? 1.2 : 0.5} />
          </mesh>
        ))}
        {/* Vartaman: the present, a single bright bead */}
        <mesh ref={bead} position={[Math.cos(presentAngle) * R, 0, -Math.sin(presentAngle) * R]}>
          <sphereGeometry args={[0.045, 24, 24]} />
          <meshBasicMaterial color={new THREE.Color(4, 3.1, 1.4)} toneMapped={false} />
        </mesh>
        {/* Bhavishya: dashed and faint, because the future is scenarios, not data */}
        {Array.from({ length: futureN }).map((_, i) => {
          const a0 = past + gap + (i / futureN) * (2 * Math.PI - past - 2 * gap);
          const len = ((2 * Math.PI - past - 2 * gap) / futureN) * 0.45;
          return (
            <mesh key={i} rotation={[Math.PI / 2, 0, a0]}>
              <torusGeometry args={[R, 0.004, 6, 12, len]} />
              <meshBasicMaterial color="#f2d27a" transparent opacity={0.28 * (1 - i / futureN) + 0.06} />
            </mesh>
          );
        })}
        <Html position={[Math.cos(0.55 * past) * R, 0.16, -Math.sin(0.55 * past) * R]} center className="arc-label">
          <span className="deva">भूत</span> BHOOT
        </Html>
        <Html position={[Math.cos(presentAngle) * R, 0.2, -Math.sin(presentAngle) * R]} center className="arc-label arc-now">
          <span className="deva">वर्तमान</span> NOW
        </Html>
        <Html position={[Math.cos(past + 0.45 * (2 * Math.PI - past)) * R, 0.16, -Math.sin(past + 0.45 * (2 * Math.PI - past)) * R]} center className="arc-label arc-future">
          <span className="deva">भविष्य</span> BHAVISHYA
        </Html>
      </group>
    </group>
  );
}

/* ---------- camera, light sweep, pool of light ---------- */
function Rig({ intro, reduced }: { intro: React.MutableRefObject<number>; reduced: boolean }) {
  const { camera, pointer } = useThree();
  const key = useRef<THREE.SpotLight>(null);
  const t = useRef(0);
  useFrame((_, dt) => {
    t.current += dt;
    intro.current = reduced ? 1 : Math.min(1, t.current / 2.4);
    const e = 1 - Math.pow(1 - intro.current, 3);
    const tx = pointer.x * 0.45, ty = 3.05 + pointer.y * 0.25;
    camera.position.x = THREE.MathUtils.lerp(camera.position.x, tx, 0.03);
    camera.position.y = THREE.MathUtils.lerp(camera.position.y, ty - (1 - e) * 0.6, 0.04);
    camera.position.z = THREE.MathUtils.lerp(camera.position.z, 6.4 + (1 - e) * 1.6, 0.04);
    camera.lookAt(0, -0.15, 0);
    if (key.current) {
      key.current.intensity = 26 * e;
      key.current.position.x = -4 + Math.sin(t.current * 0.15) * 0.8;
    }
  });
  return (
    <>
      <spotLight ref={key} position={[-4, 5.5, 3]} angle={0.42} penumbra={0.85} color="#ffe2a8" castShadow intensity={0} shadow-mapSize={[1024, 1024]} />
      <spotLight position={[4.5, 2.5, -4]} angle={0.5} penumbra={1} color="#8fb4ff" intensity={9} />
      <ambientLight intensity={0.04} />
    </>
  );
}

function LightPool() {
  const mat = useMemo(() => new THREE.ShaderMaterial({
    transparent: true, depthWrite: false,
    vertexShader: `varying vec2 vUv; void main(){ vUv = uv; gl_Position = projectionMatrix * modelViewMatrix * vec4(position,1.0); }`,
    fragmentShader: `varying vec2 vUv; void main(){ float d = distance(vUv, vec2(0.5)); float a = smoothstep(0.5, 0.0, d); gl_FragColor = vec4(vec3(0.42,0.32,0.14) * a * 0.55, a * 0.9); }`,
  }), []);
  return (
    <mesh rotation={[-Math.PI / 2, 0, 0]} position={[0, -STONE.h / 2 - 0.02, 0]} material={mat}>
      <planeGeometry args={[11, 8]} />
    </mesh>
  );
}

function PanelRig() {
  const { camera, pointer } = useThree();
  useFrame(() => {
    camera.position.x = THREE.MathUtils.lerp(camera.position.x, pointer.x * 0.3, 0.05);
    camera.position.y = THREE.MathUtils.lerp(camera.position.y, 3.6 + pointer.y * 0.2, 0.05);
    camera.lookAt(0, 0, 0.1);
  });
  return (
    <>
      <spotLight position={[-4, 5.5, 3]} angle={0.5} penumbra={0.85} color="#ffe2a8" intensity={22} />
      <spotLight position={[4.5, 2.5, -4]} angle={0.5} penumbra={1} color="#8fb4ff" intensity={8} />
    </>
  );
}

export default function Touchstone({ streaks, onTip, onReady, variant = "hero" }: { streaks: Streak[]; onTip: (t: TipReadout) => void; onReady?: () => void; variant?: "hero" | "panel" }) {
  const intro = useRef(variant === "panel" ? 1 : 0);
  const [dpr, setDpr] = useState(variant === "panel" ? 1.25 : 1.5);
  const [fx, setFx] = useState(true);
  const reduced = typeof window !== "undefined" && window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  if (variant === "panel") {
    return (
      <Canvas dpr={dpr} flat camera={{ position: [0, 3.6, 4.6], fov: 34 }} gl={{ antialias: true }}>
        <PerformanceMonitor onDecline={() => setDpr(1)} />
        <color attach="background" args={["#0d0f12"]} />
        <Environment resolution={128} frames={1}>
          <Lightformer form="rect" intensity={3} color="#fff1d2" position={[0, 5, 0]} rotation={[Math.PI / 2, 0, 0]} scale={[9, 2.2, 1]} />
          <Lightformer form="rect" intensity={1.2} color="#d4af37" position={[-6, 1.5, 2]} rotation={[0, Math.PI / 2, 0]} scale={[8, 0.6, 1]} />
        </Environment>
        <PanelRig />
        <Stone intro={intro} />
        {streaks.length > 0 && <StreakAssay streaks={streaks} onTip={onTip} reduced={reduced} />}
        <EffectComposer multisampling={0}>
          <Bloom mipmapBlur intensity={0.8} luminanceThreshold={0.85} radius={0.6} />
          <Vignette offset={0.3} darkness={0.7} />
          <ToneMapping mode={ToneMappingMode.ACES_FILMIC} />
        </EffectComposer>
      </Canvas>
    );
  }
  return (
    <Canvas
      shadows
      dpr={dpr}
      flat
      camera={{ position: [0, 2.6, 8.2], fov: 30, near: 0.1, far: 60 }}
      gl={{ antialias: true, powerPreference: "high-performance" }}
      onCreated={() => onReady?.()}
    >
      <PerformanceMonitor onDecline={() => { setDpr(1); setFx(false); }} onIncline={() => setDpr(1.5)} />
      <color attach="background" args={["#07080a"]} />
      <fog attach="fog" args={["#07080a", 9, 18]} />
      <Environment resolution={256} frames={1}>
        <Lightformer form="rect" intensity={3} color="#fff1d2" position={[0, 5, 0]} rotation={[Math.PI / 2, 0, 0]} scale={[9, 2.2, 1]} />
        <Lightformer form="rect" intensity={1.4} color="#d4af37" position={[-6, 1.5, 2]} rotation={[0, Math.PI / 2, 0]} scale={[8, 0.6, 1]} />
        <Lightformer form="rect" intensity={1.1} color="#9fb8ff" position={[6, 1, -2]} rotation={[0, -Math.PI / 2, 0]} scale={[8, 0.4, 1]} />
        <Lightformer form="ring" intensity={2} color="#ffffff" position={[2, 3, 6]} scale={1.6} />
      </Environment>
      <Rig intro={intro} reduced={reduced} />
      <PresentationControls global={false} cursor snap polar={[-0.08, 0.14]} azimuth={[-0.45, 0.45]} speed={1.2} zoom={1}>
        <group rotation={[0.02, -0.12, 0]}>
          <Stone intro={intro} />
          {streaks.length > 0 && <StreakAssay streaks={streaks} onTip={onTip} reduced={reduced} />}
        </group>
      </PresentationControls>
      <TimeArcs reduced={reduced} />
      <LightPool />
      <ContactShadows position={[0, -STONE.h / 2 - 0.01, 0]} opacity={0.85} scale={12} blur={2.6} far={2} color="#000000" />
      {fx && (
        <EffectComposer multisampling={0}>
          <Bloom mipmapBlur intensity={0.9} luminanceThreshold={0.85} luminanceSmoothing={0.2} radius={0.75} />
          <Noise opacity={0.045} premultiply />
          <Vignette eskil={false} offset={0.22} darkness={0.85} />
          <ToneMapping mode={ToneMappingMode.ACES_FILMIC} />
        </EffectComposer>
      )}
    </Canvas>
  );
}
