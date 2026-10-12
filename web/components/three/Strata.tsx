"use client";

/* Market strata: a geological core sample of the Nifty 500.
   One layer per year (oldest deepest). The solid obsidian arc = members of that year that still trade today;
   the hollow glass arc = members that have since vanished (delisted, merged, failed). A survivorship-biased
   dataset only has the solid part. Every number comes from the reconstructed index history. */

import { Canvas, useFrame } from "@react-three/fiber";
import { Environment, Html, Lightformer } from "@react-three/drei";
import { Bloom, EffectComposer, ToneMapping, Vignette } from "@react-three/postprocessing";
import { ToneMappingMode } from "postprocessing";
import { useMemo, useRef, useState } from "react";
import * as THREE from "three";

export type Stratum = { date: string; members: number; still_trading: number; gone: number };

const R = 1.55;
const H = 0.092;
const GAP = 0.03;

function Layer({ s, i, n, hovered, setHovered }: { s: Stratum; i: number; n: number; hovered: number | null; setHovered: (i: number | null) => void }) {
  const alive = s.members ? s.still_trading / s.members : 0;
  const y = (i - (n - 1) / 2) * (H + GAP);
  const aliveTheta = Math.max(0.0001, alive * Math.PI * 2);
  const goneTheta = Math.max(0.0001, Math.PI * 2 - aliveTheta);
  const isH = hovered === i;
  const dim = hovered !== null && !isH;
  const lift = useRef<THREE.Group>(null);
  useFrame(() => {
    if (!lift.current) return;
    const target = isH ? 0.5 : 0;
    lift.current.position.x = THREE.MathUtils.lerp(lift.current.position.x, target, 0.12);
  });
  const edge = useMemo(() => {
    const g = new THREE.CylinderGeometry(R, R, H, 64, 1, true, aliveTheta, goneTheta);
    return new THREE.EdgesGeometry(g, 30);
  }, [aliveTheta, goneTheta]);
  return (
    <group ref={lift} position={[0, y, 0]}
      onPointerOver={(e) => { e.stopPropagation(); setHovered(i); }}
      onPointerOut={() => setHovered(null)}>
      {/* survivors: polished obsidian with a gold seam */}
      <mesh castShadow>
        <cylinderGeometry args={[R, R, H, 96, 1, false, 0, aliveTheta]} />
        <meshPhysicalMaterial color={dim ? "#0a0b0d" : "#101216"} roughness={0.22} metalness={0.2} clearcoat={1} clearcoatRoughness={0.12}
          emissive="#d4af37" emissiveIntensity={isH ? 0.12 : 0.0} />
      </mesh>
      <mesh position={[0, H / 2 + 0.001, 0]} rotation={[-Math.PI / 2, 0, 0]}>
        {/* ring angle φ maps to cylinder angle θ = φ + π/2 after the -90° tilt */}
        <ringGeometry args={[R - 0.012, R, 96, 1, -Math.PI / 2, aliveTheta]} />
        <meshBasicMaterial color={new THREE.Color(isH ? 3 : 1.6, isH ? 2.3 : 1.2, isH ? 1 : 0.45)} toneMapped={false} side={THREE.DoubleSide} />
      </mesh>
      {/* the vanished: hollow glass, only an outline remains */}
      <mesh>
        <cylinderGeometry args={[R, R, H, 96, 1, false, aliveTheta, goneTheta]} />
        <meshPhysicalMaterial color="#c7d2ff" transparent opacity={dim ? 0.02 : isH ? 0.16 : 0.07} roughness={0.1} metalness={0} depthWrite={false} side={THREE.DoubleSide} />
      </mesh>
      <lineSegments geometry={edge}>
        <lineBasicMaterial color={isH ? "#f0577a" : "#5b6170"} transparent opacity={dim ? 0.15 : isH ? 0.95 : 0.45} />
      </lineSegments>
      {isH && (
        <Html position={[R + 0.75, 0, 0]} center className="strata-tip">
          <div className="strata-year">{s.date.slice(0, 4)}</div>
          <div><b className="mono">{s.members}</b> members on 30-Jun</div>
          <div className="pos"><b className="mono">{s.still_trading}</b> still trade</div>
          <div className="neg"><b className="mono">{s.gone}</b> gone ({Math.round((s.gone / Math.max(1, s.members)) * 100)}%)</div>
        </Html>
      )}
    </group>
  );
}

function Core({ strata }: { strata: Stratum[] }) {
  const g = useRef<THREE.Group>(null);
  const [hovered, setHovered] = useState<number | null>(null);
  useFrame((s, dt) => {
    if (g.current && hovered === null) g.current.rotation.y += dt * 0.18;
    s.camera.position.y = THREE.MathUtils.lerp(s.camera.position.y, 0.6 + s.pointer.y * 0.8, 0.04);
    s.camera.lookAt(0, 0, 0);
  });
  return (
    <group ref={g} rotation={[0, -0.6, 0]}>
      {strata.map((s, i) => (
        <Layer key={s.date} s={s} i={i} n={strata.length} hovered={hovered} setHovered={setHovered} />
      ))}
    </group>
  );
}

export default function Strata({ strata }: { strata: Stratum[] }) {
  return (
    <Canvas dpr={[1, 1.5]} flat camera={{ position: [5.2, 0.6, 5.2], fov: 34 }} gl={{ antialias: true }}>
      <color attach="background" args={["#07080a"]} />
      <Environment resolution={128} frames={1}>
        <Lightformer form="rect" intensity={2.4} color="#fff1d2" position={[0, 6, 0]} rotation={[Math.PI / 2, 0, 0]} scale={[6, 6, 1]} />
        <Lightformer form="rect" intensity={1.2} color="#d4af37" position={[-5, 0, 3]} rotation={[0, Math.PI / 3, 0]} scale={[2, 8, 1]} />
        <Lightformer form="rect" intensity={0.8} color="#9fb8ff" position={[5, 0, -3]} rotation={[0, -Math.PI / 3, 0]} scale={[2, 8, 1]} />
      </Environment>
      <spotLight position={[-3, 6, 4]} intensity={30} angle={0.5} penumbra={1} color="#ffe2a8" />
      <Core strata={strata} />
      <EffectComposer multisampling={0}>
        <Bloom mipmapBlur intensity={0.7} luminanceThreshold={0.9} radius={0.6} />
        <Vignette offset={0.25} darkness={0.8} />
        <ToneMapping mode={ToneMappingMode.ACES_FILMIC} />
      </EffectComposer>
    </Canvas>
  );
}
