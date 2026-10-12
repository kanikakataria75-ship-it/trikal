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


# ----------------------------------------------------------------------------------------------
# Helpers for the analytics layer (M4)

def _profile(self: PitReader, security_id: str, as_of: AsOf) -> dict:
    """Name, sector label (+method/confidence), and the reporting family of the latest filing known at as_of."""
    name = self.con.execute("SELECT latest_name FROM security WHERE security_id = ?", [security_id]).fetchone()
    fam = self.con.execute(
        """SELECT family FROM filing WHERE security_id = ? AND kind LIKE 'results%' AND known_at <= ?
           ORDER BY period_end DESC, known_at DESC LIMIT 1""", [security_id, as_of.ts]).fetchone()
    cl = self.classification(security_id, as_of)
    return {"security_id": security_id, "name": name[0] if name else None,
            "sector": cl[0] if cl else None, "sector_method": cl[1] if cl else None,
            "sector_confidence": cl[2] if cl else None, "family": fam[0] if fam else None}


def _last_price(self: PitReader, security_id: str, as_of: AsOf, exchange: str = "NSE",
                max_age_days: int = 10) -> tuple[dt.date, float] | None:
    """Latest unadjusted close known at as_of, or None if older than max_age_days (stale quotes are not used).
    One session can carry several NSE series (EQ, BE, IL institutional lots, N1.. debt): the main equity series
    wins, the same priority as `prices`, never an arbitrary one."""
    row = self.con.execute(
        """SELECT e.trade_date, e.close FROM price_eod e JOIN listing l ON l.exchange = e.exchange AND l.code = e.code
                  AND e.trade_date BETWEEN l.valid_from AND l.valid_to
           WHERE l.security_id = ? AND e.exchange = ? AND e.known_at <= ? AND e.close > 0
           ORDER BY e.trade_date DESC,
                    CASE e.series WHEN 'EQ' THEN 0 WHEN 'BE' THEN 1 WHEN 'BZ' THEN 2 WHEN '' THEN 3 ELSE 9 END,
                    e.volume DESC NULLS LAST
           LIMIT 1""", [security_id, exchange, as_of.ts]).fetchone()
    if not row or (as_of.date_ist - row[0]).days > max_age_days:
        return None
    return row[0], row[1]


def _sector_peers(self: PitReader, sector: str, as_of: AsOf, limit: int = 400) -> list[str]:
    """Securities carrying the same sector label at as_of that had published results by then."""
    d = as_of.date_ist
    return [r[0] for r in self.con.execute(
        """SELECT DISTINCT c.security_id FROM classification c
           WHERE c.scheme = 'NSE_INDUSTRY' AND c.code = ? AND c.valid_from <= ? AND ? < c.valid_to
             AND EXISTS (SELECT 1 FROM filing f WHERE f.security_id = c.security_id AND f.known_at <= ?
                         AND f.kind LIKE 'results%')
           ORDER BY 1 LIMIT ?""", [sector, d, d, as_of.ts, limit]).fetchall()]


PitReader.profile = _profile  # type: ignore[attr-defined]
PitReader.last_price = _last_price  # type: ignore[attr-defined]
PitReader.sector_peers = _sector_peers  # type: ignore[attr-defined]


# ----------------------------------------------------------------------------------------------
# Read views for the terminal UI (M3). Same rule as everything above: nothing known after as_of.

def open_reader(read_only: bool = True) -> PitReader:
    """A reader on the canonical database. The API layer uses this instead of touching trikal_core.db."""
    from trikal_core.db import connect

    return PitReader(connect(read_only=read_only))


def _search(self: PitReader, q: str, as_of: AsOf, limit: int = 20) -> list[dict]:
    """Securities whose code, ISIN or name matches `q`, listed on or before the as-of date, including
    delisted and renamed ones. A security that stopped trading more than 10 days before as_of is marked
    inactive. The display name is the security's latest known name (a label only, never used in a computation)."""
    d = as_of.date_ist
    s = q.strip().upper()
    if not s:
        return []
    like = f"%{s}%"
    rows = self.con.execute(
        """WITH l AS (
               SELECT security_id, exchange, code, valid_from, least(valid_to, ?::DATE) AS valid_to
               FROM listing WHERE valid_from <= ?),
           cand AS (
               SELECT l.security_id, l.exchange, l.code, l.valid_from, l.valid_to, s.latest_name, s.latest_isin,
                      CASE WHEN l.code = ? OR s.latest_isin = ? THEN 0 WHEN l.code LIKE ? THEN 1
                           WHEN upper(s.latest_name) LIKE ? THEN 2 ELSE 3 END AS score
               FROM l JOIN security s USING (security_id)
               WHERE l.code LIKE ? OR upper(s.latest_name) LIKE ? OR s.latest_isin = ?)
           SELECT security_id, exchange, code, valid_from, valid_to, latest_name, latest_isin, score
           FROM cand
           QUALIFY row_number() OVER (PARTITION BY security_id ORDER BY score, (exchange = 'NSE') DESC, valid_to DESC) = 1
           ORDER BY score, valid_to DESC, code LIMIT ?""",
        [d, d, s, s, s + "%", s + "%", like, like, s, limit]).fetchall()
    out = []
    for sid, ex, code, vf, vt, name, isin, _ in rows:
        first = self.con.execute("SELECT min(valid_from) FROM listing WHERE security_id = ?", [sid]).fetchone()[0]
        out.append({"security_id": sid, "exchange": ex, "code": code, "name": self.display_name(sid, name, ex, code),
                    "isin": isin, "listed_from": first, "last_trade": vt, "active": (d - vt).days <= 10})
    return out


def _is_id_like(s: str | None) -> bool:
    return not s or s.startswith(("S:", "X:"))


def _display_name(self: PitReader, security_id: str, name: str | None = None, exchange: str | None = None,
                  code: str | None = None) -> str:
    """A human label for a security. Securities built from pre-2011 files may have no recorded company
    name; then the name printed in the exchange's own price file is used, else the trading code."""
    if not _is_id_like(name):
        return name  # type: ignore[return-value]
    if exchange is None or code is None:
        row = self.con.execute("""SELECT exchange, code FROM listing WHERE security_id = ?
                                  ORDER BY (exchange = 'NSE') DESC, valid_to DESC LIMIT 1""", [security_id]).fetchone()
        if not row:
            return security_id
        exchange, code = row
    row = self.con.execute("""SELECT name FROM price_eod WHERE exchange = ? AND code = ? AND name IS NOT NULL
                              ORDER BY trade_date DESC LIMIT 1""", [exchange, code]).fetchone()
    return row[0] if row and row[0] else code


def _timeline(self: PitReader, security_id: str, as_of: AsOf) -> list[dict]:
    """Events for the Time Spine, each with the moment it became public (known_at <= as_of)."""
    ev: list[dict] = []
    for ex_date, factor, kind, subject, ka in self.con.execute(
            """SELECT ex_date, factor, parsed_kind, subject, known_at FROM adj_event
               WHERE security_id = ? AND applied AND known_at <= ? AND ex_date <= ?
               QUALIFY row_number() OVER (PARTITION BY ex_date ORDER BY (exchange = 'NSE') DESC) = 1
               ORDER BY ex_date""",
            [security_id, as_of.ts, as_of.date_ist]).fetchall():
        ev.append({"type": "corporate_action", "date": ex_date, "known_at": ka,
                   "label": (kind or "adjustment").replace("_", " "), "detail": subject, "factor": factor})
    for pe, label, fam, ka, kind in self.con.execute(
            """SELECT period_end, any_value(period_label), any_value(family), min(known_at), any_value(kind) FROM filing
               WHERE security_id = ? AND kind LIKE 'results%' AND known_at <= ? GROUP BY period_end ORDER BY 4""",
            [security_id, as_of.ts]).fetchall():
        ev.append({"type": "results", "date": ka.date(), "known_at": ka, "label": f"results {pe:%b-%Y}",
                   "detail": f"{label or ''} · {fam or ''}".strip(" ·"), "period_end": pe})
    for code, vf, vt, ka, conf in self.con.execute(
            """SELECT index_code, valid_from, valid_to, known_at, confidence FROM index_membership
               WHERE security_id = ? AND known_at <= ?
               QUALIFY row_number() OVER (PARTITION BY index_code, valid_from ORDER BY known_at DESC) = 1""",
            [security_id, as_of.ts]).fetchall():
        if vf <= as_of.date_ist:
            ev.append({"type": "index_in", "date": vf, "known_at": ka, "label": f"joins {code}",
                       "detail": f"membership confidence {conf}"})
        if vt <= as_of.date_ist:
            ev.append({"type": "index_out", "date": vt, "known_at": ka, "label": f"leaves {code}",
                       "detail": f"membership confidence {conf}"})
    return sorted(ev, key=lambda e: e["date"])


def _index_strata(self: PitReader, index_code: str, as_of: AsOf, dates: list[dt.date]) -> list[dict]:
    """For each date: the members then (as known at as_of), how many still traded at as_of, how many have
    vanished ('gone': what a survivorship-biased dataset silently drops), and how many old index names were
    never matched to a security ('unresolved': fate unknown, counted neither way)."""
    out = []
    d_now = as_of.date_ist
    for d in dates:
        if d > d_now:
            continue
        n_alive_unres = self.con.execute(
            """WITH known AS (
                   SELECT * FROM index_membership WHERE index_code = ? AND known_at <= ?
                   QUALIFY row_number() OVER (PARTITION BY security_id, valid_from ORDER BY known_at DESC) = 1),
               m AS (SELECT DISTINCT security_id FROM known WHERE valid_from <= ? AND ? < valid_to)
               SELECT count(*),
                      count(*) FILTER (WHERE EXISTS (SELECT 1 FROM listing l WHERE l.security_id = m.security_id
                                                     AND l.valid_from <= ? AND l.valid_to >= ?::DATE - INTERVAL 15 DAY)),
                      count(*) FILTER (WHERE NOT EXISTS (SELECT 1 FROM listing l WHERE l.security_id = m.security_id))
               FROM m""",
            [index_code, as_of.ts, d, d, d_now, d_now]).fetchone()
        n, alive, unresolved = n_alive_unres
        out.append({"date": d, "members": n, "still_trading": alive, "gone": n - alive - unresolved,
                    "unresolved": unresolved})
    return out


def _gone_members(self: PitReader, index_code: str, on: dt.date, as_of: AsOf, limit: int = 40) -> list[dict]:
    """Members on `on` that no longer traded at as_of: the names survivorship bias erases."""
    d_now = as_of.date_ist
    rows = self.con.execute(
        """WITH known AS (
               SELECT * FROM index_membership WHERE index_code = ? AND known_at <= ?
               QUALIFY row_number() OVER (PARTITION BY security_id, valid_from ORDER BY known_at DESC) = 1),
           m AS (SELECT DISTINCT security_id, symbol FROM known WHERE valid_from <= ? AND ? < valid_to)
           SELECT m.security_id, any_value(m.symbol), any_value(s.latest_name), max(least(l.valid_to, ?::DATE)) AS last_trade
           FROM m JOIN security s USING (security_id) JOIN listing l USING (security_id)
           WHERE l.valid_from <= ?
           GROUP BY m.security_id HAVING max(least(l.valid_to, ?::DATE)) < ?::DATE - INTERVAL 15 DAY
           ORDER BY last_trade LIMIT ?""",
        [index_code, as_of.ts, on, on, d_now, d_now, d_now, d_now, limit]).fetchall()
    # old press releases list company names in the symbol column; prefer a recorded name, else that text
    return [{"security_id": r[0], "symbol": r[1],
             "name": r[2] if not _is_id_like(r[2]) else (r[1] if r[1] and " " in r[1] else self.display_name(r[0])),
             "last_trade": r[3]} for r in rows]


def _watermark(self: PitReader, as_of: AsOf) -> dict:
    """The newest data a screen can be showing at as_of: last price session and last filing known."""
    p = self.con.execute("SELECT max(trade_date), max(known_at) FROM price_eod WHERE exchange = 'NSE' AND known_at <= ?",
                         [as_of.ts]).fetchone()
    f = self.con.execute("SELECT max(known_at) FROM filing WHERE known_at <= ?", [as_of.ts]).fetchone()
    return {"last_session": p[0], "prices_known_at": p[1], "last_filing_known_at": f[0]}


def _stats(self: PitReader, as_of: AsOf) -> dict:
    """Headline counts of what the database holds, as known at as_of."""
    d = as_of.date_ist

    def q(sql: str, *a):
        return self.con.execute(sql, list(a)).fetchone()

    prices = q("SELECT count(*), min(trade_date), count(DISTINCT trade_date) FROM price_eod WHERE known_at <= ?", as_of.ts)
    secs = q("""SELECT count(DISTINCT security_id) FROM listing WHERE valid_from <= ?""", d)
    alive = q("""SELECT count(DISTINCT security_id) FROM listing WHERE valid_from <= ? AND valid_to >= ?::DATE - INTERVAL 15 DAY""", d, d)
    adj = q("SELECT count(*) FROM adj_event WHERE applied AND known_at <= ?", as_of.ts)
    ca = q("SELECT count(*) FROM corp_action WHERE known_at <= ?", as_of.ts)
    ever = q("""SELECT count(DISTINCT security_id) FROM index_membership
                WHERE index_code = 'NIFTY500' AND known_at <= ? AND valid_from <= ?""", as_of.ts, d)
    fil = q("SELECT count(*), count(DISTINCT security_id) FROM filing WHERE known_at <= ?", as_of.ts)
    facts = q("SELECT count(*) FROM fact_financial WHERE known_at <= ?", as_of.ts)
    shp = q("SELECT count(DISTINCT filing_id) FROM shareholding WHERE known_at <= ?", as_of.ts)
    pr = q("SELECT count(*) FROM press_release WHERE published_date <= ?", d)
    return {"price_rows": prices[0], "first_session": prices[1], "sessions": prices[2],
            "securities": secs[0], "securities_inactive": secs[0] - alive[0], "adjustments_applied": adj[0],
            "corporate_announcements": ca[0], "nifty500_ever_members": ever[0], "filings": fil[0],
            "companies_with_filings": fil[1], "financial_facts": facts[0], "shareholding_filings": shp[0],
            "index_press_releases": pr[0]}


def _market_day(self: PitReader, as_of: AsOf, movers: int = 8) -> dict | None:
    """The last NSE session known at as_of: breadth, turnover, and the day's movers among the Nifty 500
    members of that date. Day change uses the exchange's previous close, so securities with a split/bonus
    ex-date that session are excluded (their previous close is not comparable)."""
    row = self.con.execute("SELECT max(trade_date) FROM price_eod WHERE exchange = 'NSE' AND trade_date <= ? AND known_at <= ?",
                           [as_of.date_ist, as_of.ts]).fetchone()
    if not row or not row[0]:
        return None
    d = row[0]
    rows = self.con.execute(
        """SELECT e.code, l.security_id, e.close, e.prev_close, e.turnover, e.name
           FROM price_eod e LEFT JOIN listing l ON l.exchange = 'NSE' AND l.code = e.code AND e.trade_date BETWEEN l.valid_from AND l.valid_to
           WHERE e.exchange = 'NSE' AND e.trade_date = ? AND e.series = 'EQ' AND e.known_at <= ? AND e.close > 0 AND e.prev_close > 0
             AND NOT EXISTS (SELECT 1 FROM adj_event a WHERE a.exchange = 'NSE' AND a.ex_date = e.trade_date
                             AND (a.security_id = l.security_id OR a.code = e.code))""",
        [d, as_of.ts]).fetchall()
    members = {r[0] for r in self.index_members("NIFTY500", as_of)}
    chg = [(code, sid, c / p - 1, t or 0.0, nm, c) for code, sid, c, p, t, nm in rows]
    adv = sum(1 for x in chg if x[2] > 0.0005)
    dec = sum(1 for x in chg if x[2] < -0.0005)
    mem = [x for x in chg if x[1] in members]
    srt = sorted(mem, key=lambda x: x[2])

    def item(x):
        return {"code": x[0], "security_id": x[1], "change": x[2], "turnover": x[3], "close": x[5],
                "name": self.display_name(x[1], None, "NSE", x[0]) if x[1] else (x[4] or x[0])}

    def median(v):
        v = sorted(v)
        return v[len(v) // 2] if v else None

    return {"session": d, "securities": len(chg), "advances": adv, "declines": dec, "unchanged": len(chg) - adv - dec,
            "median_change": median([x[2] for x in chg]), "turnover": sum(x[3] for x in chg),
            "members_priced": len(mem), "members_total": len(members),
            "members_eqw_change": (sum(x[2] for x in mem) / len(mem)) if mem else None,
            "gainers": [item(x) for x in srt[::-1][:movers]], "losers": [item(x) for x in srt[:movers]],
            "most_traded": [item(x) for x in sorted(mem, key=lambda x: -x[3])[:movers * 3]]}


def _still_trading(self: PitReader, security_ids: list[str], ref: AsOf) -> set[str]:
    """Which of these securities still traded within 15 days of `ref`. Used only to annotate a past date
    with hindsight on purpose (e.g. '† no longer trades'), never inside a computation for that date."""
    ids = [s for s in security_ids if s]
    if not ids:
        return set()
    ph = ",".join("?" * len(ids))
    return {r[0] for r in self.con.execute(
        f"""SELECT DISTINCT security_id FROM listing WHERE security_id IN ({ph}) AND valid_from <= ?
            AND valid_to >= ?::DATE - INTERVAL 15 DAY""", [*ids, ref.date_ist, ref.date_ist]).fetchall()}


def _members_fate(self: PitReader, index_code: str, on: dt.date, ref: AsOf) -> list[dict]:
    """Every member of `index_code` on `on` (membership as known at ref) with its last trading date up to ref
    and its fate at ref: alive | gone | unresolved (old index name never matched to a security). A deliberate
    look back from `ref`; never used inside a computation."""
    d_ref = ref.date_ist
    rows = self.con.execute(
        """WITH known AS (
               SELECT * FROM index_membership WHERE index_code = ? AND known_at <= ?
               QUALIFY row_number() OVER (PARTITION BY security_id, valid_from ORDER BY known_at DESC) = 1),
           m AS (SELECT security_id, any_value(symbol) AS symbol FROM known WHERE valid_from <= ? AND ? < valid_to GROUP BY 1)
           SELECT m.security_id, m.symbol, any_value(s.latest_name), max(CASE WHEN l.valid_to IS NOT NULL THEN least(l.valid_to, ?::DATE) END) AS last_trade
           FROM m LEFT JOIN security s USING (security_id) LEFT JOIN listing l ON l.security_id = m.security_id AND l.valid_from <= ?
           GROUP BY m.security_id, m.symbol ORDER BY last_trade""",
        [index_code, ref.ts, on, on, d_ref, d_ref]).fetchall()
    out = []
    for sid, sym, name, last in rows:
        # least() skips NULLs, so an unmatched member must be caught explicitly: no listing = fate unknown
        fate = "unresolved" if last is None else ("alive" if (d_ref - last).days <= 15 else "gone")
        label = name if not _is_id_like(name) else (sym if sym and (" " in sym or sid.startswith("U:")) else self.display_name(sid))
        out.append({"security_id": sid, "symbol": sym, "name": label, "last_trade": last, "fate": fate})
    return out


def _session_map(self: PitReader, as_of: AsOf) -> dict | None:
    """Every Nifty 500 member of the last session known at as_of (before the index history begins in 1998:
    the 500 most-traded equities of the day), with that day's open/close/previous close, turnover and a sector label (NSE industry, else the legacy press-release label, else None).
    `comparable` is False on a split/bonus ex-date (previous close not comparable; no change is reported)."""
    row = self.con.execute("SELECT max(trade_date) FROM price_eod WHERE exchange = 'NSE' AND trade_date <= ? AND known_at <= ?",
                           [as_of.date_ist, as_of.ts]).fetchone()
    if not row or not row[0]:
        return None
    d = row[0]
    members = {r[0] for r in self.index_members("NIFTY500", as_of)}
    # one pass over the day's prints (fast, zone-mapped on trade_date), then keep the members in Python
    rows = self.con.execute(
        """SELECT l.security_id, e.code, e.open, e.close, e.prev_close, e.turnover, e.name, e.series,
                  a.security_id IS NOT NULL AS ex_day
           FROM price_eod e
           JOIN listing l ON l.exchange = 'NSE' AND l.code = e.code AND e.trade_date BETWEEN l.valid_from AND l.valid_to
           -- announcement-only events carry no code, so ex-dates are matched on the security
           LEFT JOIN (SELECT DISTINCT security_id FROM adj_event WHERE exchange = 'NSE' AND ex_date = ?) a ON a.security_id = l.security_id
           WHERE e.exchange = 'NSE' AND e.trade_date = ? AND e.known_at <= ? AND e.series IN ('EQ', 'BE') AND e.close > 0""",
        [d, d, as_of.ts]).fetchall()
    universe = "nifty500" if members else "all_equities"   # index history starts in 1998
    best: dict[str, tuple] = {}
    for row in rows:
        sid = row[0]
        if members and sid not in members:
            continue
        if sid not in best or (row[7] == "EQ" and best[sid][7] != "EQ"):
            best[sid] = row
    picked = list(best.values())
    if not members:
        picked = sorted(picked, key=lambda x: -(x[5] or 0))[:500]
    ids = [x[0] for x in picked]
    sectors: dict[str, str] = {}
    if ids:
        ph = ",".join("?" * len(ids))
        sectors = {r[0]: r[1] for r in self.con.execute(
            f"""SELECT security_id, code FROM classification
                WHERE security_id IN ({ph}) AND valid_from <= ? AND ? < valid_to
                QUALIFY row_number() OVER (PARTITION BY security_id ORDER BY (scheme = 'NSE_INDUSTRY') DESC, confidence DESC) = 1""",
            [*ids, d, d]).fetchall()}
        names = {r[0]: r[1] for r in self.con.execute(
            f"SELECT security_id, latest_name FROM security WHERE security_id IN ({ph})", ids).fetchall()}
    else:
        names = {}
    tiles = []
    for sid, code, o, c, p, t, nm, _series, ex_day in picked:
        ok = bool(p) and not ex_day
        label = names.get(sid) if not _is_id_like(names.get(sid)) else (nm or code)
        tiles.append({"security_id": sid, "code": code, "name": label,
                      "open": o, "close": c, "prev_close": p, "turnover": t or 0.0, "sector": sectors.get(sid),
                      "change": (c / p - 1) if ok else None, "gap": (o / p - 1) if ok and o else None, "comparable": ok})
    return {"session": d, "tiles": tiles, "universe": universe, "members_total": len(members) or len(tiles)}


def _ew_path(self: PitReader, security_ids: list[str], start: dt.date, end: dt.date, known_by: AsOf) -> list[dict]:
    """Equal-weight average daily return of a FIXED set of securities (e.g. that day's index members) for
    every NSE session in [start, end], using prints known by `known_by`. Split/bonus ex-dates are skipped
    per security. Returns per session: mean return, advances, declines, count."""
    ids = [s for s in security_ids if s]
    if not ids:
        return []
    ph = ",".join("?" * len(ids))
    rows = self.con.execute(
        f"""WITH p AS (
               SELECT e.trade_date, l.security_id, e.close / e.prev_close - 1 AS r
               FROM price_eod e JOIN listing l ON l.exchange = 'NSE' AND l.code = e.code AND e.trade_date BETWEEN l.valid_from AND l.valid_to
               WHERE e.exchange = 'NSE' AND e.series = 'EQ' AND e.trade_date BETWEEN ? AND ? AND e.known_at <= ?
                 AND e.close > 0 AND e.prev_close > 0 AND l.security_id IN ({ph})
                 AND NOT EXISTS (SELECT 1 FROM adj_event a WHERE a.exchange = 'NSE' AND a.security_id = l.security_id
                                 AND a.ex_date = e.trade_date))
           SELECT trade_date, avg(r), count(*) FILTER (WHERE r > 0.0005), count(*) FILTER (WHERE r < -0.0005), count(*)
           FROM p GROUP BY 1 ORDER BY 1""",
        [start, end, known_by.ts, *ids]).fetchall()
    return [{"d": d, "r": r, "adv": a, "dec": dc, "n": n} for d, r, a, dc, n in rows]


def _day_tape(self: PitReader, as_of: AsOf, limit: int = 40) -> list[dict]:
    """What the exchange itself announced for the session at as_of: corporate actions going ex that day,
    results broadcast that day, and Nifty 500 changes announced or taking effect that day."""
    d = as_of.date_ist
    out: list[dict] = []
    for code, subj, kind in self.con.execute(
            """SELECT code, any_value(subject), any_value(kind) FROM corp_action
               WHERE exchange = 'NSE' AND ex_date = ? AND known_at <= ? AND kind <> 'other'
               GROUP BY code ORDER BY (any_value(kind) IN ('split', 'bonus', 'demerger')) DESC, code LIMIT ?""",
            [d, as_of.ts, limit]).fetchall():
        out.append({"kind": "corporate_action", "code": code, "text": f"{code} goes ex: {(subj or kind).strip()}"})
    for sym, fam, label in self.con.execute(
            """SELECT symbol, any_value(family), any_value(period_label) FROM filing
               WHERE kind LIKE 'results%' AND CAST(known_at AT TIME ZONE 'Asia/Kolkata' AS DATE) = ? AND known_at <= ?
               GROUP BY symbol LIMIT ?""", [d, as_of.ts, limit]).fetchall():
        out.append({"kind": "results", "code": sym, "text": f"{sym} files {(label or 'results').lower()} results"})
    for action, sym, company, eff, ann in self.con.execute(
            """SELECT action, symbol, company, effective_date, announced_date FROM index_event
               WHERE index_code = 'NIFTY500' AND (effective_date = ? OR announced_date = ?) AND coalesce(announced_date, effective_date) <= ?
               ORDER BY action LIMIT ?""", [d, d, d, limit]).fetchall():
        verb = "joins" if action == "in" else "leaves"
        when = "today" if eff == d else f"on {eff:%d-%b-%Y}"
        out.append({"kind": "index", "code": sym, "text": f"{company or sym} {verb} the Nifty 500 {when}"})
    return out


def _context(self: PitReader, day: dt.date, before_days: int = 3) -> dict:
    """Editorial context (Wikipedia) for a session: items dated from day-before_days up to the day itself —
    never after it. Not point-in-time data: summaries were written later; the UI labels them as such."""
    rows = self.con.execute(
        """SELECT day, scope, category, story, text, source_name, source_url, page FROM context_event
           WHERE day BETWEEN ? AND ? ORDER BY day DESC, scope, category NULLS LAST""",
        [day - dt.timedelta(days=before_days), day]).fetchall()
    keys = ["day", "scope", "category", "story", "text", "source_name", "source_url", "page"]
    items = [dict(zip(keys, r)) for r in rows]
    return {"world": [x for x in items if x["scope"] == "world"], "india": [x for x in items if x["scope"] == "india"]}


PitReader.day_tape = _day_tape  # type: ignore[attr-defined]
PitReader.context = _context  # type: ignore[attr-defined]
PitReader.session_map = _session_map  # type: ignore[attr-defined]
PitReader.ew_path = _ew_path  # type: ignore[attr-defined]
PitReader.members_fate = _members_fate  # type: ignore[attr-defined]
PitReader.market_day = _market_day  # type: ignore[attr-defined]
PitReader.still_trading = _still_trading  # type: ignore[attr-defined]
PitReader.search = _search  # type: ignore[attr-defined]
PitReader.display_name = _display_name  # type: ignore[attr-defined]
PitReader.timeline = _timeline  # type: ignore[attr-defined]
PitReader.index_strata = _index_strata  # type: ignore[attr-defined]
PitReader.gone_members = _gone_members  # type: ignore[attr-defined]
PitReader.watermark = _watermark  # type: ignore[attr-defined]
PitReader.stats = _stats  # type: ignore[attr-defined]
