"use client";

/* The Transmission Engine: three stacked glass planes — macro drivers (top), sectors (middle), companies of the selected
   sector (bottom). Edges carry the estimated sensitivity (width of light = strength, colour = sign). A SHOCK sends pulses
   down the edges of the shocked drivers and the sector nodes glow by their estimated total price response.
   The impact table next to it is the answer; this scene is the explanation. */

import { Canvas, useFrame, useThree } from "@react-three/fiber";
import { Environment, Lightformer, OrbitControls } from "@react-three/drei";
import { Bloom, EffectComposer, ToneMapping, Vignette } from "@react-three/postprocessing";
import { ToneMappingMode } from "postprocessing";
import { useEffect, useMemo, useRef } from "react";
import * as THREE from "three";
import { Label } from "./Label";
import type { ShockCompanies, ShockResult, TxOverview } from "@/lib/api";

const Y = { driver: 4.4, sector: 0, company: -4.4 };
const UP = new THREE.Color("#39ff88"), DN = new THREE.Color("#ff2e63"), NEUTRAL = new THREE.Color("#8c7a45");

type Edge = { a: THREE.Vector3; b: THREE.Vector3; val: number; on: boolean };

function spread(n: number, width: number, stagger: number): THREE.Vector3[] {
  return Array.from({ length: n }, (_, i) => new THREE.Vector3(n === 1 ? 0 : -width / 2 + (i / (n - 1)) * width, 0, (i % 2 ? 1 : -1) * stagger));
}

/* ------------------------------------------------------------------ edges with travelling pulses */
const SEG = 28;
function Edges({ edges, active }: { edges: Edge[]; active: boolean }) {
  const mat = useMemo(() => new THREE.ShaderMaterial({
    transparent: true, depthWrite: false, blending: THREE.AdditiveBlending,
    uniforms: { uTime: { value: 0 }, uUp: { value: UP }, uDn: { value: DN } },
    vertexShader: `attribute float aT; attribute float aVal; attribute float aOn; attribute float aSeed; varying float vT, vVal, vOn, vSeed;
      void main(){ vT = aT; vVal = aVal; vOn = aOn; vSeed = aSeed; gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.0); }`,
    fragmentShader: `uniform float uTime; uniform vec3 uUp; uniform vec3 uDn; varying float vT, vVal, vOn, vSeed;
      void main(){
        float s = abs(vVal);
        vec3 col = vVal >= 0.0 ? uUp : uDn;
        float p = fract(uTime * 0.28 - vT + vSeed);
        float pulse = vOn * smoothstep(0.0, 0.03, p) * (1.0 - smoothstep(0.03, 0.2, p));
        float a = 0.05 + 0.45 * s + pulse * (0.4 + 1.6 * s);
        gl_FragColor = vec4(col * (0.6 + pulse * 2.2), a);
      }`,
  }), []);
  const geo = useMemo(() => {
    const pos: number[] = [], t: number[] = [], v: number[] = [], on: number[] = [], seed: number[] = [];
    edges.forEach((e, k) => {
      const mid = e.a.clone().lerp(e.b, 0.5);
      const ctrl = new THREE.Vector3(mid.x, mid.y, mid.z + (e.b.x - e.a.x) * 0.0);
      const curve = new THREE.QuadraticBezierCurve3(e.a, ctrl, e.b);
      const P = curve.getPoints(SEG);
      for (let i = 0; i < SEG; i++) {
        pos.push(P[i].x, P[i].y, P[i].z, P[i + 1].x, P[i + 1].y, P[i + 1].z);
        t.push(i / SEG, (i + 1) / SEG);
        v.push(e.val, e.val); on.push(e.on ? 1 : 0, e.on ? 1 : 0);
        const sd = (k * 0.37) % 1;
        seed.push(sd, sd);
      }
    });
    const g = new THREE.BufferGeometry();
    g.setAttribute("position", new THREE.Float32BufferAttribute(pos, 3));
    g.setAttribute("aT", new THREE.Float32BufferAttribute(t, 1));
    g.setAttribute("aVal", new THREE.Float32BufferAttribute(v, 1));
    g.setAttribute("aOn", new THREE.Float32BufferAttribute(on, 1));
    g.setAttribute("aSeed", new THREE.Float32BufferAttribute(seed, 1));
    return g;
  }, [edges]);
  useFrame((s) => { mat.uniforms.uTime.value = active ? s.clock.elapsedTime : 0; });
  return <lineSegments geometry={geo} material={mat} frustumCulled={false} />;
}

/* ------------------------------------------------------------------ nodes */
function Nodes({ pts, colors, scales, onClick, hoverTitle }: { pts: THREE.Vector3[]; colors: THREE.Color[]; scales: number[]; onClick?: (i: number) => void; hoverTitle?: (i: number) => string }) {
  const ref = useRef<THREE.InstancedMesh>(null);
  useEffect(() => {
    const m = ref.current;
    if (!m) return;
    const o = new THREE.Object3D();
    pts.forEach((p, i) => {
      o.position.copy(p); o.scale.setScalar(scales[i]); o.updateMatrix();
      m.setMatrixAt(i, o.matrix); m.setColorAt(i, colors[i]);
    });
    m.instanceMatrix.needsUpdate = true;
    if (m.instanceColor) m.instanceColor.needsUpdate = true;
  }, [pts, colors, scales]);
  return (
    <instancedMesh key={pts.length} ref={ref} args={[undefined, undefined, Math.max(1, pts.length)]}
      onClick={(e) => { e.stopPropagation(); if (e.instanceId !== undefined) onClick?.(e.instanceId); }}
      onPointerOver={() => { document.body.style.cursor = onClick ? "pointer" : "default"; }}
      onPointerOut={() => { document.body.style.cursor = "default"; }}>
      <sphereGeometry args={[0.16, 20, 20]} />
      <meshBasicMaterial toneMapped={false} />
    </instancedMesh>
  );
}

function Plane({ y, label }: { y: number; label: string }) {
  const edge = useMemo(() => {
    const g = new THREE.BufferGeometry().setFromPoints([[-10.5, -2.6], [10.5, -2.6], [10.5, 2.6], [-10.5, 2.6], [-10.5, -2.6]].map(([x, z]) => new THREE.Vector3(x, 0, z)));
    return g;
  }, []);
  return (
    <group position={[0, y, 0]}>
      <mesh rotation={[-Math.PI / 2, 0, 0]}>
        <planeGeometry args={[21, 5.2]} />
        <meshBasicMaterial color="#9aa5bd" transparent opacity={0.045} depthWrite={false} side={THREE.DoubleSide} />
      </mesh>
      <line>
        <primitive object={edge} attach="geometry" />
        <lineBasicMaterial color="#8c6f1e" transparent opacity={0.7} />
      </line>
      <Label position={[-10.4, 0.1, 2.9]} text={label} className="tx-plane" anchor="left" />
    </group>
  );
}

/* ------------------------------------------------------------------ scene */
function Scene({ overview, shock, selected, onSelect, companies }: Props) {
  const drivers = overview.drivers;
  const sectors = overview.sectors;
  const dPts = useMemo(() => spread(drivers.length, 17, 0.6).map((p) => p.setY(Y.driver)), [drivers.length]);
  const sPts = useMemo(() => spread(sectors.length, 19.5, 1.5).map((p) => p.setY(Y.sector)), [sectors.length]);
  const cos = companies?.rows ?? [];
  const cPts = useMemo(() => spread(cos.length, 15, 1.4).map((p) => p.setY(Y.company)), [cos.length]);
  const rowOf = useMemo(() => new Map((shock?.rows ?? []).map((r) => [r.sector, r])), [shock]);
  const maxTotal = Math.max(1e-6, ...(shock?.rows ?? []).map((r) => Math.abs(r.total)));
  const maxCo = Math.max(1e-6, ...cos.map((r) => Math.abs(r.total)));
  const shocked = useMemo(() => new Set((shock?.shocks ?? []).map((s) => s.driver)), [shock]);

  const edges = useMemo(() => {
    const out: Edge[] = [];
    const sig = new Map(drivers.map((d) => [d.id, d.sigma ?? 0.03]));
    let strongest = 1e-9;
    const raw: { di: number; si: number; v: number; on: boolean }[] = [];
    sectors.forEach((s, si) => {
      drivers.forEach((d, di) => {
        const c = s.sens[d.id];
        if (!c || Math.abs(c.tstat) < 1.65) return;                          // only statistically meaningful links are drawn
        if (shock) {
          if (!shocked.has(d.id)) { raw.push({ di, si, v: c.beta * (sig.get(d.id) ?? 0.03) * 0.3, on: false }); return; }
          const cell = rowOf.get(s.sector)?.cells[d.id];
          raw.push({ di, si, v: cell?.impact ?? 0, on: cell?.impact != null });
        } else raw.push({ di, si, v: c.beta * (sig.get(d.id) ?? 0.03), on: false });
      });
    });
    raw.forEach((r) => { strongest = Math.max(strongest, Math.abs(r.v)); });
    raw.forEach((r) => out.push({ a: dPts[r.di], b: sPts[r.si], val: Math.sign(r.v) * Math.min(1, Math.sqrt(Math.abs(r.v) / strongest)), on: r.on }));
    if (selected) {
      const si = sectors.findIndex((s) => s.sector === selected);
      if (si >= 0) cos.forEach((c, ci) => out.push({ a: sPts[si], b: cPts[ci], val: Math.sign(c.total) * Math.min(1, Math.sqrt(Math.abs(c.total) / maxCo)), on: !!shock }));
    }
    return out;
  }, [drivers, sectors, shock, shocked, rowOf, dPts, sPts, cPts, cos, selected, maxCo]);

  const dCol = useMemo(() => drivers.map((d) => (shocked.has(d.id) ? new THREE.Color("#fff3c4").multiplyScalar(2) : NEUTRAL.clone())), [drivers, shocked]);
  const dScale = useMemo(() => drivers.map((d) => (shocked.has(d.id) ? 1.9 : 1)), [drivers, shocked]);
  const sCol = useMemo(() => sectors.map((s) => {
    const r = rowOf.get(s.sector);
    if (!r) return NEUTRAL.clone();
    const k = Math.min(1, Math.sqrt(Math.abs(r.total) / maxTotal));
    return NEUTRAL.clone().lerp(r.total >= 0 ? UP : DN, 0.25 + 0.75 * k).multiplyScalar(1 + 1.4 * k);
  }), [sectors, rowOf, maxTotal]);
  const sScale = useMemo(() => sectors.map((s) => {
    const r = rowOf.get(s.sector);
    return (s.sector === selected ? 1.6 : 1) * (r ? 1 + 1.6 * Math.min(1, Math.sqrt(Math.abs(r.total) / maxTotal)) : 1);
  }), [sectors, rowOf, maxTotal, selected]);
  const cCol = useMemo(() => cos.map((c) => (c.total >= 0 ? UP : DN).clone().multiplyScalar(1 + Math.min(1, Math.abs(c.total) / maxCo))), [cos, maxCo]);
  const cScale = useMemo(() => cos.map((c) => 0.8 + 1.2 * Math.min(1, Math.abs(c.total) / maxCo)), [cos, maxCo]);

  const topLabels = useMemo(() => {
    const ranked = [...(shock?.rows ?? [])].sort((a, b) => Math.abs(b.total) - Math.abs(a.total)).slice(0, 7).map((r) => r.sector);
    return new Set([...ranked, ...(selected ? [selected] : [])]);
  }, [shock, selected]);

  return (
    <>
      <Plane y={Y.driver} label="MACRO &amp; POLICY DRIVERS" />
      <Plane y={Y.sector} label="SECTORS" />
      {selected && <Plane y={Y.company} label={`COMPANIES · ${selected.toUpperCase()}`} />}
      <Edges edges={edges} active={!!shock} />
      <Nodes pts={dPts} colors={dCol} scales={dScale} />
      <Nodes pts={sPts} colors={sCol} scales={sScale} onClick={(i) => onSelect(sectors[i].sector === selected ? null : sectors[i].sector)} />
      {selected && <Nodes pts={cPts} colors={cCol} scales={cScale} />}
      {drivers.map((d, i) => (
        <Label key={d.id} position={[dPts[i].x, dPts[i].y + 0.5, dPts[i].z]} text={d.label} className={`tx-lbl ${shocked.has(d.id) ? "hot" : ""}`} />
      ))}
      {sectors.map((s, i) => (topLabels.has(s.sector) || (!shock && i % 2 === 0)) && (
        <Label key={s.sector} position={[sPts[i].x, sPts[i].y - 0.45, sPts[i].z]} className={`tx-lbl ${s.sector === selected ? "hot" : ""}`}
          text={`${s.sector}${rowOf.get(s.sector) ? ` ${rowOf.get(s.sector)!.total >= 0 ? "+" : "−"}${Math.abs(rowOf.get(s.sector)!.total * 100).toFixed(1)}%` : ""}`} />
      ))}
      {selected && cos.map((c, i) => (
        <Label key={c.security_id} position={[cPts[i].x, cPts[i].y - 0.42, cPts[i].z]} text={c.code} className="tx-lbl" />
      ))}
    </>
  );
}

type Props = { overview: TxOverview; shock?: ShockResult; selected: string | null; onSelect: (s: string | null) => void; companies?: ShockCompanies };

/* keep the whole of the planes in view whatever the shape of the panel */
function Fit() {
  const { camera, size } = useThree();
  useEffect(() => {
    const cam = camera as THREE.PerspectiveCamera;
    const t = Math.tan((cam.fov * Math.PI) / 360), aspect = size.width / Math.max(1, size.height);
    const d = Math.max(11 / (t * aspect), 9.2 / t) * 1.04;
    cam.position.setLength(Math.min(d, 38));
  }, [camera, size.width, size.height]);
  return null;
}

export default function TransmissionScene(props: Props) {
  return (
    <Canvas dpr={[1, 1.5]} flat camera={{ position: [0, 4.5, 15.5], fov: 38, near: 0.1, far: 80 }} gl={{ antialias: true }}>
      <color attach="background" args={["#060709"]} />
      <Environment resolution={64} frames={1}>
        <Lightformer form="rect" intensity={1.5} color="#fff1d2" position={[0, 6, 0]} rotation={[Math.PI / 2, 0, 0]} scale={[14, 6, 1]} />
      </Environment>
      <Fit />
      <Scene {...props} />
      <OrbitControls enablePan={false} enableDamping minDistance={9} maxDistance={40} minPolarAngle={0.5} maxPolarAngle={1.75} autoRotate autoRotateSpeed={0.18} target={[0, 0, 0]} />
      <EffectComposer multisampling={0}>
        <Bloom mipmapBlur intensity={0.55} luminanceThreshold={0.85} luminanceSmoothing={0.2} radius={0.6} />
        <Vignette offset={0.25} darkness={0.7} />
        <ToneMapping mode={ToneMappingMode.ACES_FILMIC} />
      </EffectComposer>
    </Canvas>
  );
}
