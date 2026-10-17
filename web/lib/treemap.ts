/* Squarified treemap of one session: sectors → securities, area = turnover. Shared by the 3D city and the 2D map. */

export type Tile = { security_id: string; code: string; name: string; open: number | null; close: number; prev_close: number | null; turnover: number; sector: string | null; change: number | null; gap: number | null; comparable: boolean };

export const W = 15, D = 9;

/* ---------- squarified treemap ---------- */
export type R = { x: number; y: number; w: number; h: number };
export function squarify<T>(items: { v: number; d: T }[], rect: R): { r: R; d: T }[] {
  const out: { r: R; d: T }[] = [];
  const total = items.reduce((a, b) => a + b.v, 0) || 1;
  const scale = (rect.w * rect.h) / total;
  const list = items.map((x) => ({ a: x.v * scale, d: x.d })).sort((a, b) => b.a - a.a);
  let { x, y, w, h } = rect;
  let row: typeof list = [];
  const worst = (rw: typeof list, side: number) => {
    const s = rw.reduce((a, b) => a + b.a, 0);
    const mx = Math.max(...rw.map((r) => r.a)), mn = Math.min(...rw.map((r) => r.a));
    return Math.max((side * side * mx) / (s * s), (s * s) / (side * side * mn));
  };
  const flush = () => {
    const s = row.reduce((a, b) => a + b.a, 0);
    if (w >= h) {
      const cw = s / h;
      let cy = y;
      for (const r of row) { const ch = r.a / cw; out.push({ r: { x, y: cy, w: cw, h: ch }, d: r.d }); cy += ch; }
      x += cw; w -= cw;
    } else {
      const chh = s / w;
      let cx = x;
      for (const r of row) { const cw = r.a / chh; out.push({ r: { x: cx, y, w: cw, h: chh }, d: r.d }); cx += cw; }
      y += chh; h -= chh;
    }
    row = [];
  };
  for (const it of list) {
    const side = Math.min(w, h);
    if (!row.length || worst([...row, it], side) <= worst(row, side)) row.push(it);
    else { flush(); row.push(it); }
  }
  if (row.length) flush();
  return out;
}

export type Placed = { t: Tile; x: number; z: number; w: number; d: number };
export type District = { name: string; x: number; z: number; w: number; d: number; n: number; avg: number | null };

export function layoutCity(tiles: Tile[]): { placed: Placed[]; districts: District[] } {
  const groups = new Map<string, Tile[]>();
  for (const t of tiles) {
    const k = t.sector ?? "Unclassified";
    groups.set(k, [...(groups.get(k) ?? []), t]);
  }
  const weight = (t: Tile) => Math.pow(Math.max(t.turnover, 1e5), 0.55);
  const sec = squarify([...groups.entries()].map(([k, ts]) => ({ v: ts.reduce((a, t) => a + weight(t), 0), d: k })), { x: -W / 2, y: -D / 2, w: W, h: D });
  const placed: Placed[] = [];
  const districts: District[] = [];
  for (const s of sec) {
    const pad = 0.09;
    const inner = { x: s.r.x + pad, y: s.r.y + pad, w: Math.max(0.01, s.r.w - 2 * pad), h: Math.max(0.01, s.r.h - 2 * pad) };
    const ts = groups.get(s.d)!;
    const ch = ts.filter((t) => t.change !== null).map((t) => t.change!);
    districts.push({ name: s.d, x: s.r.x, z: s.r.y, w: s.r.w, d: s.r.h, n: ts.length, avg: ch.length ? ch.reduce((a, b) => a + b, 0) / ch.length : null });
    for (const c of squarify(ts.map((t) => ({ v: weight(t), d: t })), inner)) {
      const g = Math.min(0.03, c.r.w * 0.12, c.r.h * 0.12);
      placed.push({ t: c.d, x: c.r.x + c.r.w / 2, z: c.r.y + c.r.h / 2, w: Math.max(0.01, c.r.w - 2 * g), d: Math.max(0.01, c.r.h - 2 * g) });
    }
  }
  return { placed, districts };
}
