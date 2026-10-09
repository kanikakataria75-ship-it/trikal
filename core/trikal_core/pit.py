"""The one door to canonical data for analytics (ARCHITECTURE §2.2, ADR-004).

Every method requires an `AsOf`. Results only include facts with known_at <= as_of; derived values
(adjusted prices) only use events effective on or before the as-of date. With the DuckDB stand-in
(ADR-010) the database cannot enforce role grants, so a test asserts that analytics/kasauti code
never imports `trikal_core.db` directly.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass

import duckdb

from trikal_core.timeutil import AsOf


@dataclass(frozen=True)
class PriceBar:
    trade_date: dt.date
    open: float | None
    high: float | None
    low: float | None
    close: float | None
    volume: float | None
    turnover: float | None
    factor: float  # cumulative adjustment applied (1.0 = unadjusted)
    source_sha: str


class PitReader:
    def __init__(self, con: duckdb.DuckDBPyConnection) -> None:
        self.con = con

    # -- identity -------------------------------------------------------------------------------

    def resolve(self, code: str, as_of: AsOf, exchange: str = "NSE") -> str | None:
        """Exchange code (as used on the as-of date) -> security_id. Old symbols of renamed securities
        resolve correctly for past dates; a symbol that did not exist yet resolves to None."""
        d = as_of.date_ist
        row = self.con.execute(
            """SELECT security_id FROM listing
               WHERE exchange = ? AND code = ? AND valid_from <= ?
               ORDER BY (? BETWEEN valid_from AND valid_to) DESC, valid_to DESC LIMIT 1""",
            [exchange, code.upper(), d, d],
        ).fetchone()
        return row[0] if row else None

    def listings(self, security_id: str, as_of: AsOf) -> list[tuple]:
        d = as_of.date_ist
        return self.con.execute(
            """SELECT exchange, code, valid_from, least(valid_to, ?::DATE) AS valid_to, method, confidence
               FROM listing WHERE security_id = ? AND valid_from <= ? ORDER BY exchange, valid_from""",
            [d, security_id, d],
        ).fetchall()

    def universe(self, as_of: AsOf, exchange: str = "NSE", active_within_sessions: int = 10) -> list[str]:
        """Securities that traded on `exchange` in the last N sessions up to the as-of date."""
        d = as_of.date_ist
        return [r[0] for r in self.con.execute(
            """WITH s AS (SELECT DISTINCT trade_date FROM price_eod
                          WHERE exchange = ? AND trade_date <= ? AND known_at <= ?
                          ORDER BY trade_date DESC LIMIT ?)
               SELECT DISTINCT l.security_id FROM listing l
               JOIN price_eod p ON p.exchange = l.exchange AND p.code = l.code
                               AND p.trade_date BETWEEN l.valid_from AND l.valid_to
               WHERE l.exchange = ? AND p.trade_date IN (SELECT trade_date FROM s) AND p.known_at <= ?
               ORDER BY 1""",
            [exchange, d, as_of.ts, active_within_sessions, exchange, as_of.ts],
        ).fetchall()]

    # -- prices ----------------------------------------------------------------------------------

    def prices(self, security_id: str, as_of: AsOf, exchange: str = "NSE", start: dt.date | None = None,
               adjusted: bool = True) -> list[PriceBar]:
        """Daily bars known by `as_of`. Adjusted bars use only adjustment events with ex_date <= as-of
        date, i.e. exactly what a terminal would have shown on that day."""
        d = as_of.date_ist
        rows = self.con.execute(
            """WITH p AS (
                   SELECT e.trade_date, e.open, e.high, e.low, e.close, e.volume, e.turnover, e.source_sha
                   FROM price_eod e JOIN listing l ON l.exchange = e.exchange AND l.code = e.code
                                                  AND e.trade_date BETWEEN l.valid_from AND l.valid_to
                   WHERE l.security_id = ? AND e.exchange = ? AND e.known_at <= ? AND e.trade_date >= ?
                   QUALIFY row_number() OVER (PARTITION BY e.trade_date ORDER BY
                       CASE e.series WHEN 'EQ' THEN 0 WHEN 'BE' THEN 1 WHEN 'BZ' THEN 2 ELSE 3 END) = 1),
               ev AS (
                   SELECT ex_date, factor FROM adj_event
                   WHERE security_id = ? AND exchange = ? AND applied AND ex_date <= ? AND known_at <= ?)
               SELECT p.*, coalesce((SELECT exp(sum(ln(ev.factor))) FROM ev WHERE ev.ex_date > p.trade_date), 1.0) AS f
               FROM p ORDER BY p.trade_date""",
            [security_id, exchange, as_of.ts, start or dt.date(1900, 1, 1),
             security_id, exchange, d, as_of.ts],
        ).fetchall()
        out = []
        for td, o, h, lo, c, v, t, sha, f in rows:
            k = f if adjusted else 1.0
            vol_k = (1.0 / k) if (adjusted and v is not None and k) else 1.0
            out.append(PriceBar(td, _m(o, k), _m(h, k), _m(lo, k), _m(c, k),
                                v * vol_k if v is not None else None, t, k, sha))
        return out

    def adjustment_events(self, security_id: str, as_of: AsOf, exchange: str = "NSE") -> list[tuple]:
        return self.con.execute(
            """SELECT ex_date, factor, method, agreement, applied, parsed_kind, subject FROM adj_event
               WHERE security_id = ? AND exchange = ? AND ex_date <= ? AND known_at <= ? ORDER BY ex_date""",
            [security_id, exchange, as_of.date_ist, as_of.ts],
        ).fetchall()

    # -- index membership -------------------------------------------------------------------------

    def index_members(self, index_code: str, as_of: AsOf) -> list[tuple[str, str, str, float]]:
        """(security_id, symbol, method, confidence) for members effective on the as-of date, using
        only membership knowledge published by then (latest-known version of each interval)."""
        d = as_of.date_ist
        return self.con.execute(
            """WITH known AS (
                   SELECT * FROM index_membership WHERE index_code = ? AND known_at <= ?
                   QUALIFY row_number() OVER (PARTITION BY security_id, valid_from ORDER BY known_at DESC) = 1)
               SELECT security_id, symbol, method, confidence FROM known
               WHERE valid_from <= ? AND ? < valid_to ORDER BY symbol""",
            [index_code, as_of.ts, d, d],
        ).fetchall()


def _m(x: float | None, k: float) -> float | None:
    return None if x is None else x * k
