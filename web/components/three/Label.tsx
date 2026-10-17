"use client";

/* A text label pinned to a point in a 3D scene.

   The element is created, moved and removed by hand rather than through drei's <Html> (a React portal): the docking layout moves
   panels around (maximise, drag between groups) and a portal into a container that has been moved throws on unmount and takes the
   whole canvas down with it. Plain DOM nodes inside the canvas' own wrapper simply travel with it. */

import { useFrame, useThree } from "@react-three/fiber";
import { useEffect, useRef } from "react";
import * as THREE from "three";

type Props = {
  position: [number, number, number] | THREE.Vector3;
  text: string;
  sub?: string;                 // small figure after the text (a count)
  className?: string;
  anchor?: "center" | "left";
  dy?: number;                  // pixel offset, negative = up
  facing?: boolean;             // for points on a sphere centred at the origin: hide when on the far side
};

export function Label({ position, text, sub, className = "", anchor = "center", dy = 0, facing = false }: Props) {
  const gl = useThree((s) => s.gl);
  const el = useRef<HTMLDivElement | null>(null);
  const anchorObj = useRef<THREE.Object3D>(null);
  const tmp = useRef(new THREE.Vector3());
  const cam = useRef(new THREE.Vector3());

  useEffect(() => {
    const host = gl.domElement.parentElement;
    if (!host) return;
    const d = document.createElement("div");
    d.style.cssText = "position:absolute;left:0;top:0;pointer-events:none;white-space:nowrap;will-change:transform;z-index:4;";
    host.appendChild(d);
    el.current = d;
    return () => { d.remove(); el.current = null; };
  }, [gl]);

  useEffect(() => {
    const d = el.current;
    if (!d) return;
    d.className = className;
    d.replaceChildren(document.createTextNode(text));
    if (sub) { const i = document.createElement("i"); i.className = "mono"; i.textContent = sub; d.append(i); }
  }, [text, sub, className, gl]);

  useFrame((state) => {
    const d = el.current, o = anchorObj.current;
    if (!d || !o) return;
    o.getWorldPosition(tmp.current);
    let visible = true;
    if (facing) {
      state.camera.getWorldPosition(cam.current);
      visible = tmp.current.dot(cam.current.sub(tmp.current)) > 0;
    }
    const p = tmp.current.project(state.camera);
    visible = visible && p.z < 1 && Math.abs(p.x) < 1.15 && Math.abs(p.y) < 1.15;
    d.style.opacity = visible ? "1" : "0";
    const x = (p.x * 0.5 + 0.5) * state.size.width, y = (-p.y * 0.5 + 0.5) * state.size.height + dy;
    d.style.transform = `translate(${x.toFixed(1)}px, ${y.toFixed(1)}px) translate(${anchor === "center" ? "-50%" : "0"}, -50%)`;
  });

  const pos = Array.isArray(position) ? position : position.toArray();
  return <object3D ref={anchorObj} position={pos as [number, number, number]} />;
}
