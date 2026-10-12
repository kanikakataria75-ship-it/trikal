"use client";

import { create } from "zustand";

export type FnCode = "DES" | "GP" | "FA" | "DUP" | "CR" | "RV" | "WC" | "OWN" | "DCF" | "EVT" | "HELP";

type State = {
  asOf: string;                 // "NOW" or YYYY-MM-DD — the global as-of every "follow" panel uses
  code: string;                 // link group A: the active security
  lineage: boolean;
  dense: boolean;
  colorBlind: boolean;
  paletteOpen: boolean;
  history: string[];
  toast: { text: string; tone: "info" | "warn" | "lock" } | null;
  setAsOf: (a: string) => void;
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
  lineage: false,
  dense: false,
  colorBlind: false,
  paletteOpen: false,
  history: typeof window !== "undefined" ? load("trikal.history", []) : [],
  toast: null,
  setAsOf: (a) => set({ asOf: a }),
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
