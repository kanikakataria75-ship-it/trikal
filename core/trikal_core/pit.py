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


# ----------------------------------------------------------------------------------------------
# Financial statements (M2)

import functools  # noqa: E402
from pathlib import Path  # noqa: E402


@dataclass(frozen=True)
class FinValue:
    line_item: str
    basis: str
    period_start: dt.date | None
    period_end: dt.date
    months: int | None        # 3 = quarter, 6/9 = year-to-date, 12 = year, None = balance-sheet date
    value: float
    concept: str              # source taxonomy concept (lineage)
    source_rank: int          # 0 = preferred concept; > 0 = fallback (e.g. old HTML label)
    known_at: dt.datetime
    known_precision: str
    is_restated: bool
    filing_id: str


@functools.lru_cache(maxsize=1)
def load_line_items(path: str | None = None) -> dict:
    import yaml

    p = Path(path) if path else Path(__file__).resolve().parents[2] / "config" / "line_items.yaml"
    return yaml.safe_load(p.read_text(encoding="utf-8"))["line_items"]


def _financials(self: PitReader, security_id: str, as_of: AsOf, line_items: list[str] | None = None,
                basis: str = "auto", months: int | None = None) -> list[FinValue]:
    """Line items for a security as known at `as_of` (latest-known version of every value).

    basis 'auto' = consolidated where the company reported it by then, else standalone. Values are INR
    (EPS and face value in INR per share). Segment (dimensional) facts are not included."""
    cfg = load_line_items()
    wanted = line_items or list(cfg)
    rank: dict[str, list[tuple[str, int]]] = {}
    for li in wanted:
        for r, src in enumerate(cfg[li]["sources"]):
            rank.setdefault(src["concept"], []).append((li, r))
    concepts = list(rank)
    if not concepts:
        return []
    ph = ",".join("?" * len(concepts))
    bases = ("consolidated", "standalone") if basis == "auto" else (basis,)
    rows = self.con.execute(
        f"""SELECT basis, concept, period_start, period_end, period_months, value, known_at, known_precision,
                   is_restated, filing_id
            FROM fact_financial
            WHERE security_id = ? AND known_at <= ? AND dims = '' AND concept IN ({ph}) AND basis IN ({",".join("?" * len(bases))})
            QUALIFY row_number() OVER (PARTITION BY basis, concept, period_start, period_end, unit
                                       ORDER BY known_at DESC, filing_id DESC) = 1""",
        [security_id, as_of.ts, *concepts, *bases]).fetchall()
    best: dict[tuple, FinValue] = {}
    for b, concept, ps, pe, pm, val, ka, kp, restated, fid in rows:
        for li, r in rank[concept]:
            if months is not None and pm != months:
                continue
            key = (li, b, ps, pe)
            cur = best.get(key)
            if cur is None or r < cur.source_rank:
                best[key] = FinValue(li, b, ps, pe, pm, val, concept, r, ka, kp, bool(restated), fid)
    out = list(best.values())
    if basis == "auto":  # one basis per (line item, period): consolidated wins
        pick: dict[tuple, FinValue] = {}
        for v in out:
            k = (v.line_item, v.period_start, v.period_end)
            if k not in pick or (v.basis == "consolidated" and pick[k].basis != "consolidated"):
                pick[k] = v
        out = list(pick.values())
    return sorted(out, key=lambda v: (v.line_item, v.period_end, v.months or 0))


PitReader.financials = _financials  # type: ignore[attr-defined]


# ----------------------------------------------------------------------------------------------
# Ownership & classification (M2)

OWNERSHIP_GROUPS = {
    "promoter": ["ShareholdingOfPromoterAndPromoterGroup"],
    "public": ["PublicShareholding"],
    "mutual_funds": ["MutualFundsOrUTI"],
    "insurance": ["InsuranceCompanies"],
    "fpi": ["InstitutionsForeignPortfolioInvestorCategoryOne", "InstitutionsForeignPortfolioInvestorCategoryTwo"],
    "foreign_institutions": ["InstitutionsForeign"],
    "domestic_institutions": ["InstitutionsDomestic"],
    "retail": ["ResidentIndividualShareholdersHoldingNominalShareCapitalUpToRsTwoLakh",
               "ResidentIndividualShareholdersHoldingNominalShareCapitalInExcessOfRsTwoLakh"],
}


def _ownership(self: PitReader, security_id: str, as_of: AsOf, periods: int = 8) -> list[dict]:
    """Shareholding by group (percent) for the latest `periods` quarters known at `as_of`.

    Each row: period_end, known_at, revised flag and one key per group. A group missing from a quarter's
    filing (e.g. category detail unavailable before Sep-2021) is None, never zero."""
    rows = self.con.execute(
        """SELECT period_end, category, pct, known_at, revision_flag, filing_id
           FROM shareholding WHERE security_id = ? AND known_at <= ?
           QUALIFY row_number() OVER (PARTITION BY period_end, category ORDER BY known_at DESC) = 1
           ORDER BY period_end DESC""", [security_id, as_of.ts]).fetchall()
    by_period: dict[dt.date, dict] = {}
    for pe, cat, pct, ka, flag, fid in rows:
        d = by_period.setdefault(pe, {"period_end": pe, "known_at": ka, "revised": bool(flag), "filing_id": fid})
        d[cat] = pct
        d["known_at"] = max(d["known_at"], ka)
    out = []
    for pe in sorted(by_period, reverse=True)[:periods]:
        d = by_period[pe]
        row = {"period_end": pe, "known_at": d["known_at"], "revised": d["revised"]}
        for g, cats in OWNERSHIP_GROUPS.items():
            vals = [d[c] for c in cats if d.get(c) is not None]
            row[g] = sum(vals) if vals else None
        out.append(row)
    return out


def _pledge(self: PitReader, security_id: str, as_of: AsOf) -> list[tuple]:
    """Promoter pledge snapshots known at as_of (history only from the first fetch onward)."""
    return self.con.execute(
        """SELECT as_on, promoter_pct, pledged_pct_of_promoter, pledged_pct_of_total, shares_pledged, known_at
           FROM pledge_snapshot WHERE security_id = ? AND known_at <= ? ORDER BY as_on DESC""",
        [security_id, as_of.ts]).fetchall()


def _classification(self: PitReader, security_id: str, as_of: AsOf, scheme: str = "NSE_INDUSTRY",
                    min_confidence: float = 0.0) -> tuple | None:
    """(code, method, confidence) in force on the as-of date, or None. Rows with method
    'assumed_static_backward' have confidence 0.5; pass min_confidence=1.0 for official-only."""
    d = as_of.date_ist
    row = self.con.execute(
        """SELECT code, method, confidence FROM classification
           WHERE security_id = ? AND scheme = ? AND valid_from <= ? AND ? < valid_to AND confidence >= ?
             AND known_at <= ? OR (security_id = ? AND scheme = ? AND valid_from <= ? AND ? < valid_to
                                   AND confidence >= ? AND method = 'assumed_static_backward')
           ORDER BY confidence DESC, valid_from DESC LIMIT 1""",
        [security_id, scheme, d, d, min_confidence, as_of.ts, security_id, scheme, d, d, min_confidence]).fetchone()
    return tuple(row) if row else None


PitReader.ownership = _ownership  # type: ignore[attr-defined]
PitReader.pledge = _pledge  # type: ignore[attr-defined]
PitReader.classification = _classification  # type: ignore[attr-defined]
