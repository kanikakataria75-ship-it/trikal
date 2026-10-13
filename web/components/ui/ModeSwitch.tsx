"use client";

import { useT, type Mode } from "@/lib/store";

/* ◆ CINEMA · ▮ PRO — one switch for the whole product.
   CINEMA: the 3D experience (home, Time Machine, touchstones). PRO: flat, dense, keyboard-first workstation that
   opens straight into the terminal. Same data, same sector rules, same lineage in both. */
export default function ModeSwitch({ onPick, className = "" }: { onPick?: (m: Mode) => void; className?: string }) {
  const { mode, setMode } = useT();
  const pick = (m: Mode) => { setMode(m); onPick?.(m); };
  return (
    <div className={`mode-switch ${className}`} role="group" aria-label="Interface mode">
      <button className={mode === "cinema" ? "on" : ""} onClick={() => pick("cinema")} title="CINEMA: the 3D experience (command: MODE CINEMA)">◆ CINEMA</button>
      <button className={mode === "pro" ? "on" : ""} onClick={() => pick("pro")} title="PRO: dense, flat, keyboard-first workstation (command: MODE PRO)">▮ PRO</button>
    </div>
  );
}
