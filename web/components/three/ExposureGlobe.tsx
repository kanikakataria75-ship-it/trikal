"use client";

/* The Exposure Theatre: a dark globe centred on India. Land is drawn as dots (Natural Earth, public domain), India's trade
   arteries as great-circle arcs with light travelling along them, and the chokepoints as rings whose size and brightness
   follow how many dated news items mentioned the area in the last three months (relative to its own history). */

import { Canvas, useFrame, useThree } from "@react-three/fiber";
import { OrbitControls } from "@react-three/drei";
import { Bloom, EffectComposer, ToneMapping, Vignette } from "@react-three/postprocessing";
import { ToneMappingMode } from "postprocessing";
import { geoEquirectangular, geoPath } from "d3-geo";
import { feature } from "topojson-client";
import { useEffect, useMemo, useRef } from "react";
import * as THREE from "three";
import land110 from "world-atlas/land-110m.json";
import { Label } from "./Label";

export type Choke = { id: string; label: string; lat: number; lon: number; intensity: number; last_90d: number };
export type Corridor = { id: string; label: string; via: string[]; path: number[][]; dashed?: boolean };

const R = 3;
export function ll(lat: number, lon: number, r = R): THREE.Vector3 {
  const la = (lat * Math.PI) / 180, lo = (lon * Math.PI) / 180;
  return new THREE.Vector3(r * Math.cos(la) * Math.sin(lo), r * Math.sin(la), r * Math.cos(la) * Math.cos(lo));
}
const INDIA = { lat: 21, lon: 79 };

/* great-circle arc through waypoints, lifted off the surface */
function arc(path: number[][], lift = 0.35, per = 56): THREE.Vector3[] {
  const out: THREE.Vector3[] = [];
  for (let i = 0; i < path.length - 1; i++) {
    const a = ll(path[i][0], path[i][1], 1), b = ll(path[i + 1][0], path[i + 1][1], 1);
    const ang = a.angleTo(b);
    const n = Math.max(12, Math.round((per * ang) / 1.2));
    for (let k = i ? 1 : 0; k <= n; k++) {
      const t = k / n;
      const p = new THREE.Vector3().copy(a).multiplyScalar(Math.sin((1 - t) * ang)).addScaledVector(b, Math.sin(t * ang)).divideScalar(Math.sin(ang) || 1);
      out.push(p.normalize().multiplyScalar(R * (1.004 + lift * Math.sin(Math.PI * t) * (ang / 1.4))));
    }
  }
  return out;
}

/* land as a grid of dots: the coastline is painted once on a small canvas and sampled (fast, unlike testing every dot against the polygon) */
function useLandDots() {
  return useMemo(() => {
    const W = 720, H = 360;
    const cv = document.createElement("canvas");
    cv.width = W; cv.height = H;
    const g = cv.getContext("2d", { willReadFrequently: true });
    if (!g) return new Float32Array(0);
    const land = feature(land110 as never, (land110 as never as { objects: { land: never } }).objects.land) as never;
    const proj = geoEquirectangular().scale(W / (2 * Math.PI)).translate([W / 2, H / 2]);
    g.fillStyle = "#fff";
    g.beginPath();
    geoPath(proj, g)(land);
    g.fill();
    const px = g.getImageData(0, 0, W, H).data;
    const pts: number[] = [];
    for (let lat = -58; lat <= 82; lat += 1.4) {
      const step = 1.4 / Math.max(0.2, Math.cos((lat * Math.PI) / 180));
      const y = Math.min(H - 1, Math.max(0, Math.round(((90 - lat) / 180) * H)));
      for (let lon = -180; lon < 180; lon += step) {
        const x = Math.min(W - 1, Math.max(0, Math.round(((lon + 180) / 360) * W)));
        if (px[(y * W + x) * 4 + 3] > 0) {
          const p = ll(lat, lon, R * 1.002);
          pts.push(p.x, p.y, p.z);
        }
      }
    }
    return new Float32Array(pts);
  }, []);
}

function Land() {
  const dots = useLandDots();
  const mat = useMemo(() => new THREE.ShaderMaterial({
    transparent: true, depthWrite: false,
    vertexShader: `varying float vF; void main(){ vec4 mv = modelViewMatrix * vec4(position,1.0); vec3 n = normalize(normalMatrix * normalize(position));
      vF = clamp(dot(n, normalize(-mv.xyz)), 0.0, 1.0); gl_PointSize = 2.1 * (7.5 / -mv.z) * (0.5 + 0.9 * vF); gl_Position = projectionMatrix * mv; }`,
    fragmentShader: `varying float vF; void main(){ vec2 c = gl_PointCoord - 0.5; if (dot(c,c) > 0.25) discard;
      float a = smoothstep(0.0, 0.55, vF); gl_FragColor = vec4(mix(vec3(0.30,0.27,0.18), vec3(0.80,0.62,0.24), pow(vF, 2.0)), a * 0.85); }`,
  }), []);
  return <points material={mat}><bufferGeometry><bufferAttribute attach="attributes-position" args={[dots, 3]} /></bufferGeometry></points>;
}

function Graticule() {
  const geo = useMemo(() => {
    const seg: number[] = [];
    for (let lat = -60; lat <= 60; lat += 30) for (let lon = -180; lon < 180; lon += 6) {
      const a = ll(lat, lon, R * 1.001), b = ll(lat, lon + 6, R * 1.001); seg.push(a.x, a.y, a.z, b.x, b.y, b.z);
    }
    for (let lon = -180; lon < 180; lon += 30) for (let lat = -84; lat < 84; lat += 6) {
      const a = ll(lat, lon, R * 1.001), b = ll(lat + 6, lon, R * 1.001); seg.push(a.x, a.y, a.z, b.x, b.y, b.z);
    }
    const g = new THREE.BufferGeometry();
    g.setAttribute("position", new THREE.Float32BufferAttribute(seg, 3));
    return g;
  }, []);
  return <lineSegments geometry={geo}><lineBasicMaterial color="#8c6f1e" transparent opacity={0.1} depthWrite={false} /></lineSegments>;
}

function Atmosphere() {
  const mat = useMemo(() => new THREE.ShaderMaterial({
    transparent: true, side: THREE.BackSide, depthWrite: false, blending: THREE.AdditiveBlending,
    vertexShader: `varying vec3 vN; void main(){ vN = normalize(normalMatrix * normal); gl_Position = projectionMatrix * modelViewMatrix * vec4(position,1.0); }`,
    fragmentShader: `varying vec3 vN; void main(){ float i = pow(0.62 - dot(vN, vec3(0.0,0.0,1.0)), 2.6); gl_FragColor = vec4(0.83,0.66,0.22, 1.0) * i * 0.42; }`,
  }), []);
  return <mesh scale={1.16} material={mat}><sphereGeometry args={[R, 64, 64]} /></mesh>;
}

/* light packets travelling along an arc */
function Packets({ pts, speed, color, dashed }: { pts: THREE.Vector3[]; speed: number; color: THREE.Color; dashed?: boolean }) {
  const ref = useRef<THREE.Points>(null);
  const N = 5;
  const geo = useMemo(() => { const g = new THREE.BufferGeometry(); g.setAttribute("position", new THREE.Float32BufferAttribute(new Float32Array(N * 3), 3)); return g; }, []);
  useFrame((s) => {
    const a = geo.attributes.position as THREE.BufferAttribute;
    for (let i = 0; i < N; i++) {
      const u = ((s.clock.elapsedTime * speed + i / N) % 1) * (pts.length - 1);
      const k = Math.floor(u), f = u - k;
      const p = pts[k].clone().lerp(pts[Math.min(pts.length - 1, k + 1)], f);
      a.setXYZ(i, p.x, p.y, p.z);
    }
    a.needsUpdate = true;
  });
  return <points ref={ref} geometry={geo} frustumCulled={false}><pointsMaterial color={color} size={dashed ? 0.05 : 0.085} sizeAttenuation transparent opacity={dashed ? 0.5 : 1} toneMapped={false} depthWrite={false} /></points>;
}

function Corridors({ corridors, chokes }: { corridors: Corridor[]; chokes: Choke[] }) {
  const byId = new Map(chokes.map((c) => [c.id, c]));
  return (
    <>
      {corridors.map((c) => {
        const pts = arc(c.path, c.dashed ? 0.22 : 0.3);
        const heat = Math.max(0, ...c.via.map((v) => byId.get(v)?.intensity ?? 0));
        const col = new THREE.Color("#f2d27a").lerp(new THREE.Color("#ff4d6d"), Math.max(0, (heat - 0.6) / 0.4)).multiplyScalar(c.dashed ? 0.8 : 1.6);
        const line = new THREE.Line(new THREE.BufferGeometry().setFromPoints(pts), c.dashed
          ? new THREE.LineDashedMaterial({ color: col, dashSize: 0.08, gapSize: 0.08, transparent: true, opacity: 0.55, toneMapped: false })
          : new THREE.LineBasicMaterial({ color: col, transparent: true, opacity: 0.8, toneMapped: false }));
        line.computeLineDistances();
        return (
          <group key={c.id}>
            <primitive object={line} />
            <Packets pts={pts} speed={c.dashed ? 0.04 : 0.07 + 0.05 * heat} color={col} dashed={c.dashed} />
          </group>
        );
      })}
    </>
  );
}

function Ring({ c, selected, onSelect }: { c: Choke; selected: boolean; onSelect: () => void }) {
  const pos = useMemo(() => ll(c.lat, c.lon, R * 1.012), [c.lat, c.lon]);
  const quat = useMemo(() => new THREE.Quaternion().setFromUnitVectors(new THREE.Vector3(0, 0, 1), pos.clone().normalize()), [pos]);
  const ring = useRef<THREE.Mesh>(null);
  const hot = c.intensity;
  const col = useMemo(() => new THREE.Color("#f2d27a").lerp(new THREE.Color("#ff2e63"), Math.max(0, (hot - 0.5) / 0.5)), [hot]);
  useFrame((s) => {
    if (!ring.current) return;
    const k = 1 + 0.25 * Math.sin(s.clock.elapsedTime * (1.4 + 2.2 * hot));
    ring.current.scale.setScalar(k);
  });
  const size = 0.1 + 0.2 * hot;
  return (
    <group position={pos} quaternion={quat}>
      <mesh ref={ring}>
        <ringGeometry args={[size * 0.82, size, 40]} />
        <meshBasicMaterial color={col.clone().multiplyScalar(2)} toneMapped={false} transparent opacity={selected ? 1 : 0.8} side={THREE.DoubleSide} depthWrite={false} />
      </mesh>
      <mesh><circleGeometry args={[0.04, 16]} /><meshBasicMaterial color={col.clone().multiplyScalar(3)} toneMapped={false} /></mesh>
      <mesh onClick={(e) => { e.stopPropagation(); onSelect(); }} onPointerOver={() => (document.body.style.cursor = "pointer")} onPointerOut={() => (document.body.style.cursor = "default")}>
        <circleGeometry args={[0.4, 16]} /><meshBasicMaterial transparent opacity={0} depthWrite={false} side={THREE.DoubleSide} />
      </mesh>
      <Label position={[0, 0.3, 0]} text={c.label} sub={String(c.last_90d)} className={`geo-lbl ${selected ? "on" : ""}`} facing dy={-6} />
    </group>
  );
}

function IndiaDot() {
  const p = useMemo(() => ll(INDIA.lat, INDIA.lon, R * 1.012), []);
  return <mesh position={p}><sphereGeometry args={[0.05, 16, 16]} /><meshBasicMaterial color={new THREE.Color(4, 3, 1.2)} toneMapped={false} /></mesh>;
}

/* glide the camera to India (or to a selected chokepoint), then hand control back to the user's orbiting */
function Rig({ focus }: { focus: { lat: number; lon: number } | null }) {
  const { camera, clock } = useThree();
  const target = useRef(ll(INDIA.lat - 6, INDIA.lon - 4, 11.8));
  const until = useRef(2.2);
  useEffect(() => {
    target.current = focus ? ll(focus.lat - 3, focus.lon - 2, 10.2) : ll(INDIA.lat - 6, INDIA.lon - 4, 11.8);
    until.current = clock.elapsedTime + 1.6;
  }, [focus, clock]);
  useFrame(() => {
    if (clock.elapsedTime < until.current) { camera.position.lerp(target.current, 0.06); camera.lookAt(0, 0, 0); }
  });
  return null;
}

export default function ExposureGlobe({ chokes, corridors, selected, onSelect }: { chokes: Choke[]; corridors: Corridor[]; selected: string | null; onSelect: (id: string | null) => void }) {
  const focus = chokes.find((c) => c.id === selected) ?? null;
  return (
    <Canvas dpr={[1, 1.5]} flat camera={{ position: ll(INDIA.lat - 6, INDIA.lon - 4, 11.8).toArray(), fov: 34, near: 0.1, far: 60 }} gl={{ antialias: true }}>
      <color attach="background" args={["#05060a"]} />
      <mesh><sphereGeometry args={[R * 0.998, 64, 64]} /><meshBasicMaterial color="#0a0c12" /></mesh>
      <Graticule />
      <Land />
      <Atmosphere />
      <Corridors corridors={corridors} chokes={chokes} />
      {chokes.map((c) => <Ring key={c.id} c={c} selected={c.id === selected} onSelect={() => onSelect(c.id === selected ? null : c.id)} />)}
      <IndiaDot />
      <Rig focus={focus} />
      <OrbitControls enablePan={false} enableDamping minDistance={5.2} maxDistance={16} rotateSpeed={0.5} />
      <EffectComposer multisampling={0}>
        <Bloom mipmapBlur intensity={0.6} luminanceThreshold={0.8} radius={0.6} />
        <Vignette offset={0.3} darkness={0.7} />
        <ToneMapping mode={ToneMappingMode.ACES_FILMIC} />
      </EffectComposer>
    </Canvas>
  );
}
