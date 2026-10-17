"use client";

import { useQueries, useQuery } from "@tanstack/react-query";

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
  strata: { date: string; members: number; still_trading: number; gone: number; unresolved: number }[];
  ghosts: { on: string; members: { security_id: string; symbol: string; name: string; last_trade: string }[] };
  streaks: Streak[];
  rules: { code: string; name: string; playbook: string; label: string; metrics: Record<string, MetricResult> }[];
};

export type Mover = { code: string; security_id: string | null; change: number; turnover: number; close: number; name: string; trades_today?: boolean };
export type MarketDay = {
  session: string; securities: number; advances: number; declines: number; unchanged: number; median_change: number | null;
  turnover: number; members_priced: number; members_total: number; members_eqw_change: number | null;
  gainers: Mover[]; losers: Mover[]; most_traded: Mover[];
};
export type Market = Envelope & { market: MarketDay; hindsight: boolean };

export type Fate = { security_id: string; symbol: string; name: string; last_trade: string | null; fate: "alive" | "gone" | "unresolved" };
export type Survivors = Envelope & { on: string; members: Fate[]; alive: number; gone: number; unresolved: number };

export type MacroLatest = { series_id: string; period_end: string; value: number; known_at: string; precision: "vintage" | "imputed"; year_ago: number | null };
export type MacroSeries = { series_id: string; name: string; unit: string; freq: "D" | "M"; category: string; source: string; known_rule: string; note: string | null; n_obs: number; first_period: string; last_period: string; latest?: MacroLatest | null };
export type MacroObs = { period_start: string; period_end: string; value: number; known_at: string; precision: "vintage" | "imputed" };

export type TimeMachine = Envelope & {
  market: MarketDay;
  map: { session: string; tiles: import("./treemap").Tile[]; universe: "nifty500" | "all_equities"; members_total: number };
};
export const useTimeMachine = (asOf: string) =>
  useQuery({ queryKey: ["tm", asOf, false], queryFn: () => api<TimeMachine>(`/api/timemachine?${q(asOf, { hindsight: false })}`), staleTime: Infinity, placeholderData: (p) => p });

export type LiveQuote = { code: string; ltp: number; open: number | null; high: number | null; low: number | null; prev_close: number | null; change: number | null; change_pct: number | null; volume: number | null; exchange_time: string | null };
export type Live = Envelope & ({ state: "value"; quote: LiveQuote; market_open: boolean; source: string; note: string } | { state: "na"; reason: string; market_open: boolean; configured: boolean; missing: string[] });

/* Live price (own broker account). Only for NOW. Polls every 5 s while the market is open; stops entirely if the
   broker is not configured (the answer will not change by asking again). */
export const useLive = (code: string | null, asOf: string) =>
  useQuery({
    queryKey: ["live", code],
    queryFn: () => api<Live>(`/api/live/${encodeURIComponent(code!)}?as_of=NOW`),
    enabled: !!code && asOf === "NOW",
    staleTime: 0,
    retry: false,
    refetchInterval: (qq) => {
      const d = qq.state.data;
      if (!d) return false;
      if (d.state === "na" && !d.configured) return false;
      return d.market_open ? 5000 : 60000;
    },
  });

export type SensCell = { beta: number | null; tstat: number | null; n: number | null; confidence: "high" | "medium" | "low"; impact: number | null };
export type DriverState = { id: string; label: string; kind: "log" | "pp"; series: string; note: string; aliases?: string; latest: { value: number; period_end: string; known_at: string; precision: string } | null; year_ago?: number | null; sigma?: number | null };
export type TxOverview = Envelope & {
  drivers: DriverState[]; method: string; estimates: number;
  sectors: { sector: string; sens: Record<string, { beta: number; tstat: number; n: number; confidence: "high" | "medium" | "low"; window_end: string }> }[];
  market: Record<string, { beta: number; tstat: number; n: number; confidence: "high" | "medium" | "low" }>;
};
export type ShockRow = { sector: string; cells: Record<string, SensCell>; relative: number; market: number; total: number; confidence: "high" | "medium" | "low"; missing: string[] };
export type ShockResult = Envelope & {
  shocks: { driver: string; label: string; delta: number; text: string; kind: "log" | "pp" }[];
  market: { cells: Record<string, SensCell>; total: number }; rows: ShockRow[]; notes: string[];
};
export type ShockCompanies = Envelope & { sector: string; shocks: string[]; notes: string[]; rows: (ShockRow & { security_id: string; code: string; name: string; turnover: number })[] };

export const useTransmission = (asOf: string) => useQuery({ queryKey: ["tx", asOf], queryFn: () => api<TxOverview>(`/api/transmission?${q(asOf)}`), staleTime: Infinity });
export const useShock = (text: string, asOf: string) =>
  useQuery({ queryKey: ["shock", text, asOf], queryFn: () => api<ShockResult>(`/api/shock?${q(asOf, { q: text })}`), enabled: text.trim().length > 0, staleTime: Infinity, retry: false });
export const useShockCompanies = (text: string, sector: string | null, asOf: string) =>
  useQuery({ queryKey: ["shockco", text, sector, asOf], queryFn: () => api<ShockCompanies>(`/api/shock/companies?${q(asOf, { q: text, sector: sector! })}`), enabled: !!sector && text.trim().length > 0, staleTime: Infinity, retry: false });

export type CtxMarker = { day: string; scope: string; tag: string; kind: "policy" | "geo" | "macro"; label: string; text: string; source_name: string; source_url: string; page: string };
export type CtxMarkers = Envelope & { markers: CtxMarker[]; licence: string; note: string };
export type ChokeItem = { day: string; scope: string; text: string; source_name: string; source_url: string; page: string };
export type Chokepoint = { id: string; label: string; lat: number; lon: number; carries: string; channel: string; driver: string | null; sectors: string[]; source: string; last_90d: number; intensity: number; monthly: { month: string; n: number }[]; recent: ChokeItem[] };
export type GeoCorridor = { id: string; label: string; via: string[]; path: number[][]; dashed?: boolean };
export type GeoData = Envelope & { chokepoints: Chokepoint[]; corridors: GeoCorridor[]; note: string };
export const useContextMarkers = (asOf: string) => useQuery({ queryKey: ["ctxm", asOf], queryFn: () => api<CtxMarkers>(`/api/context/markers?${q(asOf)}`), staleTime: Infinity });
export const useGeo = (asOf: string) => useQuery({ queryKey: ["geo", asOf], queryFn: () => api<GeoData>(`/api/geo?${q(asOf)}`), staleTime: Infinity });

export type KasMetric = { value: number | null; percentile: number | null; weight?: number; direction?: number };
export type KasPillar = { score: number | null; coverage: number; metrics: Record<string, KasMetric> };
export type KasDriver = { pillar: string; metric: string; value: number; percentile: number; points: number };
export type Kasauti = Envelope & {
  security_id: string; available: boolean; reason?: string; version?: number; scoring_date?: string; kind?: string; kind_note?: string; frozen?: boolean;
  score?: number | null; confidence?: number | null; status?: string; playbook?: string; peer_group?: string; n_peers?: number; note?: string;
  pillar_weights?: Record<string, { pillar: string; weight: number }[]>;
  detail?: { profile: string; peer_fallback: boolean; pillars: Record<string, KasPillar>; dropped: Record<string, string>; skipped: Record<string, string>; drivers: KasDriver[] } | null;
};
export type KasHorizon = { dates: number; avg_n?: number; decile_mean_return?: Record<string, number>; top_minus_universe?: number; d10_minus_d1?: number;
  ic_mean?: number | null; ic_t_newey_west?: number | null; ic_positive_share?: number | null; hit_rate_top_beats_universe?: number; delisted_exits?: number;
  by_year_ic?: Record<string, { ic_mean: number; dates: number }> };
export type KasReport = Envelope & { available: boolean; reason?: string; frozen?: { version: number; sha256: string; frozen_at: string } | null;
  report?: { label: string; data_end: string; dates: string[]; horizons: Record<string, KasHorizon>; conventions: Record<string, string | number>;
    portfolio: { periods: number; years?: number; cagr_net?: number; cagr_benchmark?: number; max_drawdown?: number; max_drawdown_benchmark?: number; avg_turnover?: number; cost_per_side?: number } } };
export const useKasauti = companyHook<Kasauti>("kasauti");
export const useKasautiReport = (asOf: string) => useQuery({ queryKey: ["kasauti-report", asOf], queryFn: () => api<KasReport>(`/api/kasauti/report?${q(asOf)}`), staleTime: Infinity });

export type CallPromise = { source_url: string; announced_at: string; call_period_end: string; metric: string; op: string; low: number; high: number;
  horizon_end: string | null; horizon_kind: string; quote: string; page: number; verdict: string; why: string | null; actual: number | null };
export type ToneRow = { announced_at: string; period_end: string; words: number | null; has_qa: boolean | null; net_tone: number | null; hedge_rate: number | null;
  negative_rate: number | null; evasive_count: number | null; net_tone_vs_prev: number | null; hedge_rate_vs_prev: number | null; net_tone_vs_avg4: number | null; hedge_rate_vs_avg4: number | null };
export type Concalls = Envelope & { security_id: string; calls: number; promises: CallPromise[]; note: string;
  credibility: { judged: number; score: number | null; delivered: number; partially: number; missed: number; pending: number; needs: number };
  tone: ToneRow[]; examples: { hedged?: string[]; evasive?: string[]; negative?: string[] } | null };
export const useConcalls = companyHook<Concalls>("concalls");

export type Returns = Envelope & { security_id: string; mode: string; buy_date: string; end_date: string; years: number; amount: number;
  buy_price_traded: number; end_price_traded: number; shares_bought: number; shares_at_end: number; value_price_only: number; value_shares: number;
  dividend_cash_kept: number; total_value: number; gain: number; return: number; return_price_only: number; cagr: number | null; cagr_price_only: number | null;
  dividends_received: { date: string; per_share: number; shares: number; cash: number; subject?: string }[]; dividends_total: number; dividends_ignored: number;
  events: { date: string; share_multiplier: number; kind?: string | null; subject?: string | null }[]; peak_value: number; max_drawdown: number;
  curve: { date: string; value: number }[]; notes: string[] };
export const useReturns = companyHook<Returns>("returns");

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
export const useMarket = (asOf: string, hindsight = false) =>
  useQuery({ queryKey: ["market", asOf, hindsight], queryFn: () => api<Market>(`/api/market?${q(asOf, { hindsight })}`), placeholderData: (p) => p });
export const useMacro = (asOf: string) => useQuery({ queryKey: ["macro", asOf], queryFn: () => api<Envelope & { series: MacroSeries[]; note: string }>(`/api/macro?${q(asOf)}`) });
export const useMacroSeries = (id: string | null, asOf: string) =>
  useQuery({ queryKey: ["macro", id, asOf], queryFn: () => api<Envelope & { series: MacroSeries; obs: MacroObs[] }>(`/api/macro/${id}?${q(asOf)}`), enabled: !!id, placeholderData: (p) => p });
export const useSurvivors = (on: string) =>
  useQuery({ queryKey: ["survivors", on], queryFn: () => api<Survivors>(`/api/survivors?${q("NOW", { on })}`), staleTime: Infinity, placeholderData: (p) => p });
export const useShowcase = () =>useQuery({ queryKey: ["showcase"], queryFn: () => api<Showcase>(`/api/showcase?${q("NOW")}`), staleTime: Infinity });
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

/* the same company endpoints for several companies at once (the compare screen); shares the cache with the single-company hooks */
function companyQueries<T>(kind: string, extra: Record<string, string | number | boolean | undefined> = {}) {
  return (codes: string[], asOf: string) =>
    useQueries({
      queries: codes.map((code) => ({
        queryKey: ["company", kind, code, asOf, { ...extra }],
        queryFn: () => api<T>(`/api/company/${encodeURIComponent(code)}${kind ? "/" + kind : ""}?${q(asOf, { ...extra })}`),
        retry: false,
      })),
    });
}
export const useCompanies = companyQueries<Company>("");
export const usePricesMany = companyQueries<Prices>("prices", { adjusted: true });
export const useFinancialsMany = companyQueries<Financials>("financials", { period: "FY" });
export const useKasautiMany = companyQueries<Kasauti>("kasauti");
export const useOwnershipMany = companyQueries<Ownership>("ownership");

export const useCompany = companyHook<Company>("");
export const usePrices = companyHook<Prices>("prices");
export const useTimeline = companyHook<Timeline>("timeline");
export const useFinancials = companyHook<Financials>("financials");
export type SegRow = { label: string; revenue?: number; result?: number; assets?: number; liabilities?: number; share: number | null; margin: number | null };
export type Segments = Envelope & { security_id: string; period: "FY" | "Q"; months: number; note: string;
  periods: { period_end: string; basis: string; known_at: string; filing_id: string; total_revenue: number | null; segments: SegRow[] }[] };
export const useOwnership = companyHook<Ownership>("ownership");
export const useSegments = companyHook<Segments>("segments");
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
