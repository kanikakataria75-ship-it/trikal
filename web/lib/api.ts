"use client";

import { useQuery } from "@tanstack/react-query";

/* ---- shapes returned by the TRIKAL API (api/trikal_api) ---- */
export type Input = { name: string; value: number; period_end: string | null; concept: string; filing_id: string; known_at: string };
export type MetricResult =
  | { state: "value"; metric: string; value: number | null; unit: string; formula: string; basis: string | null; warnings: string[]; low_confidence: boolean; inputs: Input[] }
  | { state: "forbidden"; metric: string; playbook: string; rule: string; reason: string }
  | { state: "undefined"; metric: string; reason: string }
  | { state: "na"; metric: string; missing: string[]; reason: string };

export type Envelope = { as_of: string; demo: boolean };

export type Stats = {
  price_rows: number; first_session: string; sessions: number; securities: number; securities_inactive: number;
  adjustments_applied: number; corporate_announcements: number; nifty500_ever_members: number; filings: number;
  companies_with_filings: number; financial_facts: number; shareholding_filings: number; index_press_releases: number;
};
export type Watermark = { last_session: string | null; prices_known_at: string | null; last_filing_known_at: string | null };
export type Meta = Envelope & { watermark: Watermark; stats: Stats; disclaimer: string; now: string };

export type SearchHit = { security_id: string; exchange: string; code: string; name: string; isin: string | null; listed_from: string; last_trade: string; active: boolean };

export type Playbook = {
  id: string; label: string; chain: string[]; overlays: string[]; how: string; confidence: number; why: string;
  key_metrics: string[]; primary: string[]; secondary: string[]; not_primary: string[]; forbidden_metrics: string[];
  forbidden_methods: string[]; forbidden_reason: string; cautions: { metric: string; reason: string }[];
  red_flags: string[]; requires: Record<string, string>; cyclical: boolean; sources: string[];
};
export type Company = Envelope & {
  security_id: string; code: string; name: string; sector: string | null; sector_method: string | null; sector_confidence: number | null;
  family: string | null; listings: { exchange: string; code: string; valid_from: string; valid_to: string; method: string; confidence: number }[];
  active: boolean; last_price: { date: string; close: number } | null; nifty500_member: boolean; playbook: Playbook;
  metrics: Record<string, MetricResult>;
};
export type Prices = Envelope & {
  security_id: string; exchange: string; adjusted: boolean; source: string;
  bars: { t: string[]; o: (number | null)[]; h: (number | null)[]; l: (number | null)[]; c: number[]; v: (number | null)[]; f: number[] };
  adjustments: { ex_date: string; factor: number; method: string; agreement: string; applied: boolean; kind: string | null; subject: string | null }[];
};
export type TimelineEvent = { type: "corporate_action" | "results" | "index_in" | "index_out"; date: string; known_at: string; label: string; detail?: string; factor?: number; period_end?: string };
export type Timeline = Envelope & { security_id: string; events: TimelineEvent[] };
export type Cell = { value: number; concept: string; source_rank: number; filing_id: string; known_at: string; restated: boolean; basis: string; low_confidence: boolean };
export type Financials = Envelope & { security_id: string; period: string; periods: string[]; rows: { line_item: string; statement: string; kind: string; cells: Record<string, Cell> }[]; note: string };
export type Ownership = Envelope & { security_id: string; note: string; quarters: Record<string, number | string | boolean | null>[]; pledge: Record<string, number | string | null>[] };
export type Dupont = Envelope & { security_id: string; tree: Record<string, MetricResult | { state: "value"; value: number; unit: string; formula: string }> };
export type CashRiver = Envelope & { security_id: string; groups: Record<string, string[]>; years: { period_end: string; items: Record<string, { value: number; concept: string; filing_id: string; known_at: string } | null> }[] };
export type Peers = Envelope & { security_id: string; playbook: string; sector: string | null; columns: string[]; note: string; rows: { security_id: string; name: string; self: boolean; metrics: Record<string, MetricResult> }[] };
export type Changes = Envelope & { security_id: string; since: string; metrics: { metric: string; now: MetricResult; then: MetricResult; delta: number | null }[]; events: TimelineEvent[] };
export type ValuationMethods = Envelope & { security_id: string; playbook: string; primary: string[]; secondary: string[]; forbidden: string[]; not_primary: string[]; reason: string; required: Record<string, string[]>; templates: Record<string, Record<string, unknown>>; note: string };

export type Streak = { code: string; name: string; security_id: string; from: string; to: string; sessions: number; first: number; last: number; t: string[]; c: number[]; source: string };
export type Showcase = Envelope & {
  disclaimer: string; stats: Stats; watermark: Watermark;
  strata: { date: string; members: number; still_trading: number; gone: number }[];
  ghosts: { on: string; members: { security_id: string; symbol: string; name: string; last_trade: string }[] };
  streaks: Streak[];
  rules: { code: string; name: string; playbook: string; label: string; metrics: Record<string, MetricResult> }[];
};

export class ApiError extends Error {
  constructor(public status: number, message: string) { super(message); }
}

export async function api<T>(path: string, init?: RequestInit): Promise<T> {
  const r = await fetch(path, init);
  if (!r.ok) {
    let msg = r.statusText;
    try { const j = await r.json(); msg = typeof j.detail === "string" ? j.detail : JSON.stringify(j.detail); } catch { /* not json */ }
    throw new ApiError(r.status, msg);
  }
  return r.json() as Promise<T>;
}

const q = (asOf: string, extra: Record<string, string | number | boolean | undefined> = {}) => {
  const p = new URLSearchParams({ as_of: asOf });
  for (const [k, v] of Object.entries(extra)) if (v !== undefined) p.set(k, String(v));
  return p.toString();
};

export const useMeta = (asOf: string) => useQuery({ queryKey: ["meta", asOf], queryFn: () => api<Meta>(`/api/meta?${q(asOf)}`) });
export const useShowcase = () => useQuery({ queryKey: ["showcase"], queryFn: () => api<Showcase>(`/api/showcase?${q("NOW")}`), staleTime: Infinity });
export const useSearch = (term: string, asOf: string) =>
  useQuery({ queryKey: ["search", term, asOf], queryFn: () => api<{ results: SearchHit[] }>(`/api/search?${q(asOf, { q: term })}`), enabled: term.trim().length > 0 });

function companyHook<T>(kind: string, extra: Record<string, string | number | boolean | undefined> = {}) {
  return (code: string | null, asOf: string, more: Record<string, string | number | boolean | undefined> = {}) =>
    useQuery({
      queryKey: ["company", kind, code, asOf, { ...extra, ...more }],
      queryFn: () => api<T>(`/api/company/${encodeURIComponent(code!)}${kind ? "/" + kind : ""}?${q(asOf, { ...extra, ...more })}`),
      enabled: !!code,
    });
}

export const useCompany = companyHook<Company>("");
export const usePrices = companyHook<Prices>("prices");
export const useTimeline = companyHook<Timeline>("timeline");
export const useFinancials = companyHook<Financials>("financials");
export const useOwnership = companyHook<Ownership>("ownership");
export const useDupont = companyHook<Dupont>("dupont");
export const useCashRiver = companyHook<CashRiver>("cashriver");
export const usePeers = companyHook<Peers>("peers");
export const useChanges = companyHook<Changes>("changes");
export const useValuationMethods = companyHook<ValuationMethods>("valuation");

export async function runValuation(code: string, asOf: string, method: string, assumptions: Record<string, unknown>) {
  return api<Envelope & { state: string; valuation?: Record<string, unknown>; reason?: string; rule?: string; playbook?: string; method?: string }>(
    `/api/company/${encodeURIComponent(code)}/valuation/run?${q(asOf)}`,
    { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify({ method, assumptions }) },
  );
}
