"""Build the survivorship-free security master from price history + NSE reference files (ADR-011).

Identity rules, in order of confidence:
  1. isin            Row carries a valid company-equity ISIN -> security_id = 'S:' + ISIN[:9]  (conf 1.0)
  2. code_continuity Same exchange code, same trading episode, rows before the file format carried
                     ISINs -> inherit the episode's first ISIN stem                         (conf 0.95)
  3. symbol_chain    NSE symbol was renamed (symbolchange.csv) into an episode that has an ISIN (conf 0.9)
  4. synthetic       No ISIN reachable (e.g. delisted before Aug-2011) -> 'X:<exch>:<code>:<first>' (conf 0.8)

A trading *episode* is a run of sessions for one exchange code without a gap of more than
EPISODE_GAP sessions and without an NSE delisting record inside it; symbol reuse after a delisting
therefore starts a new episode and never inherits the old company's identity.
"""

from __future__ import annotations

import datetime as dt
from collections import defaultdict

import duckdb

from trikal_core.db import insert_many

from trikal_core.ids import security_id_for_stem, synthetic_security_id
from trikal_core.timeutil import utcnow

EPISODE_GAP = 250  # sessions (~1 year): long suspensions stay one episode, reuse after delisting does not

NSE_EQUITY_SERIES = ("EQ", "BE", "BZ", "BT", "SM", "ST", "SZ")
BSE_EQUITY_TYPES = ("Q", "STK")

EQUITY_VIEW = f"""
CREATE OR REPLACE TEMP VIEW eq AS
SELECT exchange, trade_date, code, series, isin, name, close, prev_close, volume, turnover
FROM price_eod
WHERE ((exchange = 'NSE' AND series IN {NSE_EQUITY_SERIES})
    OR (exchange = 'BSE' AND coalesce(instr_type, 'Q') IN {BSE_EQUITY_TYPES}))
  AND (isin IS NULL OR (substr(isin, 1, 3) IN ('INE', 'IN9') AND substr(isin, 8, 2) = '01'))
"""


def build(con: duckdb.DuckDBPyConnection) -> dict[str, int]:
    con.execute(EQUITY_VIEW)
    # Sessions calendar per exchange = days with a bhavcopy.
    con.execute("""
        CREATE OR REPLACE TEMP TABLE cal AS
        SELECT exchange, trade_date, row_number() OVER (PARTITION BY exchange ORDER BY trade_date) AS idx
        FROM (SELECT DISTINCT exchange, trade_date FROM price_eod)""")
    con.execute(f"""
        CREATE OR REPLACE TEMP TABLE ep_rows AS
        WITH d AS (
            SELECT DISTINCT e.exchange, e.code, e.trade_date, c.idx FROM eq e JOIN cal c USING (exchange, trade_date)),
        g AS (
            SELECT *, idx - lag(idx) OVER w AS gap, lag(trade_date) OVER w AS prev_date
            FROM d WINDOW w AS (PARTITION BY exchange, code ORDER BY trade_date)),
        b AS (
            SELECT g.*, (gap IS NULL OR gap > {EPISODE_GAP}
                         OR EXISTS (SELECT 1 FROM nse_delisted x
                                    WHERE g.exchange = 'NSE' AND x.symbol = g.code
                                      AND x.delisted_date >= g.prev_date AND x.delisted_date < g.trade_date)) AS brk
            FROM g)
        SELECT exchange, code, trade_date,
               sum(CASE WHEN brk THEN 1 ELSE 0 END) OVER (PARTITION BY exchange, code ORDER BY trade_date) AS ep
        FROM b""")
    nodes = con.execute("""
        SELECT exchange, code, ep, min(trade_date), max(trade_date), count(*) FROM ep_rows GROUP BY ALL""").fetchall()
    stem_segs = con.execute("""
        SELECT r.exchange, r.code, r.ep, substr(e.isin, 1, 9) AS stem, min(r.trade_date), max(r.trade_date)
        FROM ep_rows r JOIN eq e USING (exchange, code, trade_date)
        WHERE e.isin IS NOT NULL GROUP BY ALL ORDER BY 1, 2, 3, 5""").fetchall()

    node_range = {(x, c, ep): (f, l) for x, c, ep, f, l, _ in nodes}
    segs: dict[tuple, list[tuple[str, dt.date, dt.date]]] = defaultdict(list)
    for x, c, ep, stem, f, l in stem_segs:
        segs[(x, c, ep)].append((stem, f, l))

    # NSE symbol-change successors.
    by_code: dict[tuple[str, str], list[tuple]] = defaultdict(list)
    for (x, c, ep), (f, l) in node_range.items():
        by_code[(x, c)].append((ep, f, l))
    successor: dict[tuple, tuple] = {}
    unmatched_changes = []
    for old, new, d in con.execute(
            "SELECT old_symbol, new_symbol, change_date FROM nse_symbol_change ORDER BY change_date").fetchall():
        o = [n for n in by_code.get(("NSE", old), []) if d - dt.timedelta(days=60) <= n[2] <= d]
        nw = [n for n in by_code.get(("NSE", new), []) if d - dt.timedelta(days=10) <= n[1] <= d + dt.timedelta(days=60)]
        if o and nw:
            successor[("NSE", old, max(o, key=lambda n: n[2])[0])] = ("NSE", new, min(nw, key=lambda n: n[1])[0])
        elif o or nw:
            unmatched_changes.append((old, new, d))

    def first_stem_via_chain(node: tuple, depth: int = 0) -> str | None:
        if depth > 20 or node not in successor:
            return None
        nxt = successor[node]
        if segs.get(nxt):
            return segs[nxt][0][0]
        return first_stem_via_chain(nxt, depth + 1)

    listing_rows = []
    for node, (f, l) in node_range.items():
        x, c, ep = node
        ss = segs.get(node, [])
        if ss:
            first_stem, first_isin_day = ss[0][0], ss[0][1]
            if f < first_isin_day:
                listing_rows.append((security_id_for_stem(first_stem), x, c, f,
                                     first_isin_day - dt.timedelta(days=1), "code_continuity", 0.95))
            for stem, sf, sl in ss:
                listing_rows.append((security_id_for_stem(stem), x, c, sf, sl, "isin", 1.0))
            continue
        stem = first_stem_via_chain(node)
        if stem:
            listing_rows.append((security_id_for_stem(stem), x, c, f, l, "symbol_chain", 0.9))
        else:
            listing_rows.append((synthetic_security_id(x, c, f.isoformat()), x, c, f, l, "synthetic", 0.8))

    con.execute("BEGIN")
    con.execute("DELETE FROM listing")
    insert_many(con, "INSERT INTO listing VALUES (?,?,?,?,?,?,?)", listing_rows)

    con.execute("DELETE FROM security_isin")
    con.execute("""
        INSERT INTO security_isin
        SELECT 'S:' || substr(isin, 1, 9), isin, min(trade_date), max(trade_date) FROM eq
        WHERE isin IS NOT NULL GROUP BY ALL""")

    con.execute("DELETE FROM security")
    con.execute("""
        INSERT INTO security
        WITH l AS (
            SELECT security_id, min(valid_from) AS first_trade, max(valid_to) AS last_trade,
                   min(confidence) AS confidence,
                   arg_min(method, confidence) AS id_method
            FROM listing GROUP BY 1),
        latest_isin AS (SELECT security_id, arg_max(isin, last_seen) AS isin FROM security_isin GROUP BY 1),
        names AS (
            SELECT security_id, arg_max(name, trade_date) AS name FROM (
                SELECT l.security_id, e.trade_date, e.name FROM eq e
                JOIN listing l ON l.exchange = e.exchange AND l.code = e.code
                               AND e.trade_date BETWEEN l.valid_from AND l.valid_to
                WHERE e.name IS NOT NULL) GROUP BY 1),
        nse_names AS (
            SELECT 'S:' || substr(isin, 1, 9) AS security_id, arg_max(name, snapshot_date) AS name
            FROM nse_equity_list GROUP BY 1)
        SELECT l.security_id,
               CASE WHEN l.security_id LIKE 'S:%' THEN substr(l.security_id, 3) END,
               li.isin, coalesce(nn.name, n.name, l.security_id),
               l.first_trade, l.last_trade, l.id_method, l.confidence
        FROM l LEFT JOIN latest_isin li USING (security_id) LEFT JOIN names n USING (security_id)
        LEFT JOIN nse_names nn USING (security_id)""")

    # Data-quality records.
    con.execute("DELETE FROM dq_issue WHERE kind IN ('symbol_change_unmatched', 'multi_stem_episode')")
    now = utcnow()
    insert_many(con, "INSERT INTO dq_issue VALUES ('symbol_change_unmatched','NSE',?,?,?, 'low', ?)",
                    [(o, d, f"{o} -> {n}: no matching trading episodes", now) for o, n, d in unmatched_changes])
    multi = [(x, c, ss[0][1], f"stems {[s for s, _, _ in ss]}", now) for (x, c, ep), ss in segs.items()
             if len({s for s, _, _ in ss}) > 1]
    insert_many(con, "INSERT INTO dq_issue VALUES ('multi_stem_episode',?,?,?,?, 'medium', ?)", multi)
    con.execute("COMMIT")

    return {
        "episodes": len(node_range),
        "listings": len(listing_rows),
        "securities": con.execute("SELECT count(*) FROM security").fetchone()[0],
        "symbol_links": len(successor),
        "symbol_changes_unmatched": len(unmatched_changes),
        "multi_stem_episodes": len(multi),
    }
