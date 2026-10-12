/* Command grammar (UI_SPEC §3), the parts that exist in M3. Later desks answer with the milestone that brings them. */
import type { FnCode } from "./store";

export const FUNCTIONS: Record<FnCode, { label: string; desc: string }> = {
  DES: { label: "Description", desc: "Identity, listings, sector playbook and headline metrics" },
  GP: { label: "Price chart", desc: "Daily prices; adjusted for confirmed splits/bonuses, or raw" },
  FA: { label: "Financial statements", desc: "Quarterly / annual line items with lineage and restatements" },
  DUP: { label: "DuPont tree", desc: "ROE = net margin × asset turnover × equity multiplier" },
  CR: { label: "Cash River", desc: "Where a year's income went: costs, interest, tax, profit" },
  RV: { label: "Relative value", desc: "Peers in the same sector and playbook, same as-of" },
  WC: { label: "What changed", desc: "Metric moves and events in the last quarter" },
  OWN: { label: "Ownership", desc: "Promoter, institutions, public; pledge" },
  DCF: { label: "Valuation Lab", desc: "Methods the sector allows; assumptions labelled; ranges, never targets" },
  EVT: { label: "Events", desc: "Corporate actions, results, index changes — each with its public time" },
  HELP: { label: "Help", desc: "Function codes and keys" },
};

export const LATER: Record<string, string> = {
  SEC: "M4/M5 sector desk", MACRO: "M5", POL: "M5", GEO: "M5 Exposure Theatre", TX: "M5 Transmission Engine",
  SHOCK: "M5", CC: "M6 concalls", KAS: "M7 KASAUTI", NOTE: "M8", RPT: "M8", FRX: "M9 forensics", CAL: "M9", SCRN: "M9 screener",
};

export type Parsed =
  | { kind: "asof"; value: string }
  | { kind: "fn"; fn: FnCode }
  | { kind: "entity"; code: string; fn: FnCode }
  | { kind: "later"; word: string; milestone: string }
  | { kind: "help" }
  | { kind: "empty" }
  | { kind: "bad"; why: string };

const DATE = /^\d{4}-\d{2}-\d{2}$/;
const REL = /^-(\d+)([YMD])$/;

export function resolveAsOf(v: string, today: string): string | null {
  const u = v.toUpperCase();
  if (u === "NOW") return "NOW";
  if (DATE.test(u)) return u > today ? null : u;
  const m = REL.exec(u);
  if (m) {
    const d = new Date(today + "T00:00:00Z");
    const n = +m[1];
    if (m[2] === "Y") d.setUTCFullYear(d.getUTCFullYear() - n);
    if (m[2] === "M") d.setUTCMonth(d.getUTCMonth() - n);
    if (m[2] === "D") d.setUTCDate(d.getUTCDate() - n);
    return d.toISOString().slice(0, 10);
  }
  return null;
}

export function parse(input: string, today: string): Parsed {
  const t = input.trim().toUpperCase().split(/\s+/).filter(Boolean);
  if (!t.length) return { kind: "empty" };
  if (t[0] === "?" || t[0] === "HELP") return { kind: "help" };
  if (t[0] === "ASOF") {
    if (!t[1]) return { kind: "bad", why: "ASOF needs a date: ASOF 2020-03-14 · ASOF -5Y · ASOF NOW" };
    const v = resolveAsOf(t[1], today);
    return v ? { kind: "asof", value: v } : { kind: "bad", why: `“${t[1]}” is not a past date (YYYY-MM-DD, -5Y, -6M, NOW). The future holds scenarios, not data.` };
  }
  if (t[0] in LATER) return { kind: "later", word: t[0], milestone: LATER[t[0]] };
  if (t.length === 1 && t[0] in FUNCTIONS) return { kind: "fn", fn: t[0] as FnCode };
  const fn = (t[1] ?? "DES") as FnCode;
  if (t[1] && !(t[1] in FUNCTIONS)) {
    if (t[1] in LATER) return { kind: "later", word: t[1], milestone: LATER[t[1]] };
    return { kind: "bad", why: `Unknown function “${t[1]}”. Try DES, GP, FA, DUP, CR, RV, WC, OWN, DCF, EVT.` };
  }
  return { kind: "entity", code: t[0], fn };
}
