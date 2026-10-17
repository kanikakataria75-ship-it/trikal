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
  CAL: { label: "Calendar", desc: "Upcoming board meetings: results, dividends, fund raising; each with when it was announced" },
  RES: { label: "Results card", desc: "Latest results against the quarter and the year before, what moved with them (holding, score, price) and what management had said" },
  HEAT: { label: "Sector heatmap", desc: "A sector's companies as a grid of KASAUTI pillar scores; sort, spot the odd one out" },
  NOTE: { label: "Notes", desc: "Your own notes and tags per company, with the price when you first noted it (kept in this browser)" },
  WL: { label: "Watchlist", desc: "Your watched companies with alerts: new results, score moves, big price moves, ex-dates (kept in this browser)" },
  PORT: { label: "Portfolio", desc: "Value your holdings: P&L, weights, sector mix, KASAUTI score of the book (kept in this browser)" },
  SCRN: { label: "Screener", desc: "Find companies by a condition (roce > 20% and pe < 25 ...) over the KASAUTI panel, as of any scoring date" },
  CALC: { label: "Return calculator", desc: "If you had put an amount in on a date: what it became, counting splits, bonuses and (optionally) dividends" },
  CALL: { label: "Concalls", desc: "What management said it would do, judged against its own later results; tone drift across calls (rule-based, quotes shown)" },
  KAS: { label: "KASAUTI", desc: "Sector-relative score with pillars, drivers, what was left out, and the report card that audits it" },
  SEG: { label: "Segments", desc: "Reportable segments as the company files them: revenue, result, assets, mix over time" },
  DCF: { label: "Valuation Lab", desc: "Methods the sector allows; assumptions labelled; ranges, never targets" },
  EVT: { label: "Events", desc: "Corporate actions, results, index changes — each with its public time" },
  TX: { label: "Transmission", desc: "Macro driver → sector → company, with the SHOCK simulator (estimated price response, with method and confidence)" },
  GEO: { label: "Exposure theatre", desc: "India's trade arteries and chokepoints on a globe; event intensity and the sectors exposed" },
  MAP: { label: "Market map", desc: "That day's index members as a heatmap: sector → stock, area = turnover, colour = move" },
  MACRO: { label: "Macro desk", desc: "FX, rates, inflation, commodities — every value as known at the as-of" },
  HELP: { label: "Help", desc: "Function codes and keys" },
};

export const LATER: Record<string, string> = {
  SEC: "M4/M5 sector desk", POL: "M5",
  NOTE: "M8", FRX: "M9 forensics",
};

export type Parsed =
  | { kind: "asof"; value: string }
  | { kind: "fn"; fn: FnCode }
  | { kind: "entity"; code: string; fn: FnCode }
  | { kind: "later"; word: string; milestone: string }
  | { kind: "compare"; codes: string[] }
  | { kind: "report" }
  | { kind: "mode"; mode: "cinema" | "pro" }
  | { kind: "shock"; text: string }
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
  const t = input.trim().toUpperCase().split(/\s+/).filter(Boolean).map((w, i) => (w === "CC" || w === "CONCALL" ? "CALL" : w === "KASAUTI" ? "KAS" : w === "SEGMENTS" ? "SEG" : w === "RESULTS" ? "RES" : w === "HEATMAP" ? "HEAT" : w === "NOTES" ? "NOTE" : w));
  if (!t.length) return { kind: "empty" };
  if (t[0] === "?" || t[0] === "HELP") return { kind: "help" };
  if (t[0] === "ASOF") {
    if (!t[1]) return { kind: "bad", why: "ASOF needs a date: ASOF 2020-03-14 · ASOF -5Y · ASOF NOW" };
    const v = resolveAsOf(t[1], today);
    return v ? { kind: "asof", value: v } : { kind: "bad", why: `“${t[1]}” is not a past date (YYYY-MM-DD, -5Y, -6M, NOW). The future holds scenarios, not data.` };
  }
  if (t[0] === "SHOCK") {
    const text = input.trim().replace(/^shocks*/i, "");
    return text ? { kind: "shock", text } : { kind: "bad", why: "SHOCK CRUDE +20 · SHOCK INR 90 · SHOCK REPO +50bp · combine with &" };
  }
  if (t[0] === "RPT" || t[0] === "REPORT") return { kind: "report" };
  if (t[0] === "CMP" || t[0] === "COMPARE") {
    const codes = t.slice(1, 4);
    return codes.length >= 2 ? { kind: "compare", codes } : { kind: "bad", why: "CMP needs two or three symbols: CMP TCS INFY WIPRO" };
  }
  if (t[0] === "MODE") {
    const m = (t[1] ?? "").startsWith("PRO") ? "pro" : (t[1] ?? "").startsWith("CIN") ? "cinema" : null;
    return m ? { kind: "mode", mode: m } : { kind: "bad", why: "MODE PRO (dense workstation) · MODE CINEMA (3D experience)" };
  }
  if (t[0] in LATER) return { kind: "later", word: t[0], milestone: LATER[t[0]] };
  if (t.length === 1 && t[0] in FUNCTIONS) return { kind: "fn", fn: t[0] as FnCode };
  const fn = (t[1] ?? "DES") as FnCode;
  if (t[1] && !(t[1] in FUNCTIONS)) {
    if (t[1] in LATER) return { kind: "later", word: t[1], milestone: LATER[t[1]] };
    return { kind: "bad", why: `Unknown function “${t[1]}”. Try DES, GP, FA, DUP, CR, RV, WC, OWN, SEG, KAS, CALL, CALC, SCRN, WL, PORT, CAL, RES, HEAT, NOTE, DCF, EVT.` };
  }
  return { kind: "entity", code: t[0], fn };
}
