"use client";

import { createPortal } from "react-dom";
import { useCallback, useEffect, useState } from "react";

/* One lightweight tooltip for the whole app: follows the pointer, never steals focus. */
export function useTip() {
  const [tip, setTip] = useState<{ x: number; y: number; node: React.ReactNode } | null>(null);
  const show = useCallback((e: React.MouseEvent, node: React.ReactNode) => setTip({ x: e.clientX, y: e.clientY, node }), []);
  const move = useCallback((e: React.MouseEvent) => setTip((t) => (t ? { ...t, x: e.clientX, y: e.clientY } : t)), []);
  const hide = useCallback(() => setTip(null), []);
  return { tip, show, move, hide };
}

export function TipLayer({ tip }: { tip: { x: number; y: number; node: React.ReactNode } | null }) {
  const [mounted, setMounted] = useState(false);
  useEffect(() => setMounted(true), []);
  if (!mounted || !tip) return null;
  const w = typeof window !== "undefined" ? window.innerWidth : 1200;
  const left = tip.x + 16 + 380 > w ? tip.x - 396 : tip.x + 16;
  return createPortal(<div className="tip" style={{ left, top: tip.y + 14 }}>{tip.node}</div>, document.body);
}

export function Tip({ content, children, className }: { content: React.ReactNode; children: React.ReactNode; className?: string }) {
  const { tip, show, move, hide } = useTip();
  return (
    <span className={className} onMouseEnter={(e) => show(e, content)} onMouseMove={move} onMouseLeave={hide}>
      {children}
      <TipLayer tip={tip} />
    </span>
  );
}
