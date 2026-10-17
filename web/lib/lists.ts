"use client";

/* The user's own lists, kept in this browser (localStorage): the watchlist, and price alerts. A tiny external store so the star button in a
   company's header, the watchlist panel and the alert badge in the top bar all see the same list at once. Nothing here is sent anywhere
   except as the symbol list of a request the data server answers and forgets. */

import { useCallback, useMemo, useSyncExternalStore } from "react";
import { useQuery } from "@tanstack/react-query";
import { api, type Envelope } from "./api";
import { todayIST } from "./format";

const WKEY = "trikal.watch.v1";
const AKEY = "trikal.pricealerts.v1";
const EVT = "trikal-lists";

export type Watch = { codes: string[]; seen: string; notify: boolean };
export type PriceAlert = { id: string; code: string; op: "above" | "below"; price: number };

function raw(key: string): string {
  try { return localStorage.getItem(key) ?? ""; } catch { return ""; }
}
function put(key: string, v: unknown) {
  try { localStorage.setItem(key, JSON.stringify(v)); } catch { /* blocked storage: lasts for the session only */ }
  window.dispatchEvent(new Event(EVT));
}
function subscribe(cb: () => void) {
  window.addEventListener(EVT, cb);
  window.addEventListener("storage", cb);
  return () => { window.removeEventListener(EVT, cb); window.removeEventListener("storage", cb); };
}
const parse = <T,>(s: string, d: T): T => { try { return s ? (JSON.parse(s) as T) : d; } catch { return d; } };

export function useWatch(): [Watch, (patch: Partial<Watch>) => void] {
  const s = useSyncExternalStore(subscribe, () => raw(WKEY), () => "");
  const w = useMemo(() => ({ codes: [], seen: todayIST(), notify: false, ...parse<Partial<Watch>>(s, {}) }) as Watch, [s]);
  const set = useCallback((patch: Partial<Watch>) => put(WKEY, { codes: [], seen: todayIST(), notify: false, ...parse<Partial<Watch>>(raw(WKEY), {}), ...patch }), []);
  return [w, set];
}

export function usePriceAlerts(): [PriceAlert[], (a: PriceAlert[]) => void] {
  const s = useSyncExternalStore(subscribe, () => raw(AKEY), () => "");
  const list = useMemo(() => parse<PriceAlert[]>(s, []), [s]);
  return [list, useCallback((a: PriceAlert[]) => put(AKEY, a), [])];
}

export const newId = () => Math.random().toString(36).slice(2, 9);

/* ───────────── the alert feed: one query for the whole page, shared by the bell, the watchlist panel and the buttons ───────────── */
export type FeedItem = {
  code: string; name?: string; sector?: string | null; error?: string; price: number | null; price_date: string | null; change_1d: number | null; pos_52w: number | null; return_1y: number | null;
  score: number | null; score_prev: number | null; last_results: { period: string | null; known_at: string } | null; upcoming: { ex_date: string; kind: string; subject: string }[];
};
export type FeedAlert = { code: string; type: string; severity: "info" | "good" | "warn"; text: string };
export type WatchResponse = Envelope & { items: FeedItem[]; alerts: FeedAlert[]; note: string };

export function useAlertFeed() {
  const [w] = useWatch();
  const [prices] = usePriceAlerts();
  const codes = useMemo(() => [...new Set([...w.codes, ...prices.map((a) => a.code)])], [w.codes, prices]);
  const q = useQuery({
    queryKey: ["watch", codes.join(","), w.seen], enabled: codes.length > 0, refetchInterval: 300_000, retry: false, staleTime: 120_000,
    queryFn: () => api<WatchResponse>(`/api/watch?as_of=NOW&codes=${encodeURIComponent(codes.join(","))}&since=${w.seen}`),
  });
  const items = q.data?.items ?? [];
  const price = (code: string) => items.find((i) => i.code === code)?.price ?? null;
  const hits = prices.filter((a) => { const p = price(a.code); return p !== null && (a.op === "above" ? p >= a.price : p <= a.price); });
  const server = (q.data?.alerts ?? []).filter((a) => w.codes.includes(a.code));
  const all: FeedAlert[] = [
    ...hits.map((a) => ({ code: a.code, type: "price-level", severity: (a.op === "above" ? "good" : "warn") as "good" | "warn", text: `${a.code}: price is ${a.op} your level ₹${a.price.toLocaleString("en-IN")} (now ₹${price(a.code)?.toLocaleString("en-IN")})` })),
    ...server,
  ];
  return { q, items, hits, server, all, count: all.length, codes };
}
