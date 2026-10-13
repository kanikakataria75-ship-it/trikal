"use client";

import { create } from "zustand";

export type FnCode = "DES" | "GP" | "FA" | "DUP" | "CR" | "RV" | "WC" | "OWN" | "DCF" | "EVT" | "MACRO" | "MAP" | "TX" | "GEO" | "HELP";

/* cinema = the premium 3D experience; pro = dense, flat, keyboard-first workstation (same data, same rules). */
export type Mode = "cinema" | "pro";
export const MODE_KEY = "trikal.mode";

type State = {
  asOf: string;                 // "NOW" or YYYY-MM-DD — the global as-of every "follow" panel uses
  code: string;                 // link group A: the active security
  mode: Mode;
  shock: string;                // the active SHOCK text, e.g. "CRUDE +20 & INR 90"
  lineage: boolean;
  dense: boolean;
  colorBlind: boolean;
  paletteOpen: boolean;
  history: string[];
  toast: { text: string; tone: "info" | "warn" | "lock" } | null;
  setAsOf: (a: string) => void;
  setMode: (m: Mode) => void;
  setShock: (t: string) => void;
  setCode: (c: string) => void;
  toggle: (k: "lineage" | "dense" | "colorBlind") => void;
  setPalette: (o: boolean) => void;
  pushHistory: (c: string) => void;
  say: (text: string, tone?: "info" | "warn" | "lock") => void;
};

const load = (k: string, d: string[]) => {
  try { return JSON.parse(localStorage.getItem(k) ?? "") as string[]; } catch { return d; }
};

export const useT = create<State>((set, get) => ({
  asOf: "NOW",
  code: "TCS",
  mode: "cinema",
  shock: "",
  lineage: false,
  dense: false,
  colorBlind: false,
  paletteOpen: false,
  history: typeof window !== "undefined" ? load("trikal.history", []) : [],
  toast: null,
  setAsOf: (a) => set({ asOf: a }),
  setShock: (t) => set({ shock: t }),
  setMode: (m) => {
    try { localStorage.setItem(MODE_KEY, m); } catch { /* private mode */ }
    set({ mode: m });
  },
  setCode: (c) => set({ code: c.toUpperCase() }),
  toggle: (k) => set({ [k]: !get()[k] } as Partial<State>),
  setPalette: (o) => set({ paletteOpen: o }),
  pushHistory: (c) => {
    const h = [c, ...get().history.filter((x) => x !== c)].slice(0, 30);
    try { localStorage.setItem("trikal.history", JSON.stringify(h)); } catch { /* private mode */ }
    set({ history: h });
  },
  say: (text, tone = "info") => {
    set({ toast: { text, tone } });
    setTimeout(() => { if (get().toast?.text === text) set({ toast: null }); }, 5200);
  },
}));

/* The workspace registers how to open a function panel; commands call it. */
export const workspace: { open: (fn: FnCode, opts?: { pin?: string }) => void; reset: () => void } = {
  open: () => {},
  reset: () => {},
};

export function storedMode(): Mode {
  try { return localStorage.getItem(MODE_KEY) === "pro" ? "pro" : "cinema"; } catch { return "cinema"; }
}
