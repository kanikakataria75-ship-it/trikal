"""Price-adjustment events (ADR-009, FORMULAS.md §Corporate actions).

Primary signal: the exchange's own base-price adjustment. On an ex-date the bhavcopy's PREVCLOSE is
the *adjusted* previous close, so  implied_factor = prev_close(t) / close(previous session).
That is cross-checked against the announced action parsed from the corporate-actions feed:

  match         |implied/parsed - 1| <= 2%        -> apply implied (the factor the market used)
  mismatch      both present, disagree            -> apply implied, DQ issue
  implied_only  exchange adjusted, no announcement -> apply if the security traded within
                parsed in our feed (dividend-only, demerger, unparsed)    MAX_GAP sessions, else DQ
  parsed_only   announced split/bonus/consolidation, but no base-price change seen -> apply parsed, DQ

Events take effect at the pre-open of the first session on/after the ex-date (known_at 09:00 IST,
precision 'convention'). Adjusted series as of D use only events with ex_date <= D (no look-ahead).
"""

from __future__ import annotations

import math

import duckdb

from trikal_core.db import insert_many

from trikal_core.timeutil import utcnow
from trikal_pipeline.corp_actions import ADJUSTING, parse_subject
from trikal_pipeline.security_master import EQUITY_VIEW

MAX_GAP = 5
TOLERANCE = 0.02


def build(con: duckdb.DuckDBPyConnection) -> dict[str, int]:
    con.execute(EQUITY_VIEW)
    con.execute("""
        CREATE OR REPLACE TEMP TABLE cal AS
        SELECT exchange, trade_date, row_number() OVER (PARTITION BY exchange ORDER BY trade_date) AS idx
        FROM (SELECT DISTINCT exchange, trade_date FROM price_eod)""")
    # One row per security/exchange/day (prefer the normal-market series), with the previous session.
    con.execute("""
        CREATE OR REPLACE TEMP TABLE px AS
        WITH p AS (
            SELECT l.security_id, e.exchange, e.code, e.trade_date, e.close, e.prev_close
            FROM eq e JOIN listing l ON l.exchange = e.exchange AND l.code = e.code
                                    AND e.trade_date BETWEEN l.valid_from AND l.valid_to
            QUALIFY row_number() OVER (PARTITION BY l.security_id, e.exchange, e.trade_date
                ORDER BY CASE e.series WHEN 'EQ' THEN 0 WHEN 'BE' THEN 1 WHEN 'BZ' THEN 2 ELSE 3 END, e.code) = 1)
        SELECT p.*, lag(p.close) OVER w AS prev_actual, lag(p.trade_date) OVER w AS prev_date,
               c.idx - lag(c.idx) OVER w AS gap
        FROM p JOIN cal c USING (exchange, trade_date)
        WINDOW w AS (PARTITION BY p.security_id, p.exchange ORDER BY p.trade_date)""")
    implied = con.execute("""
        SELECT security_id, exchange, code, trade_date, prev_date, gap, prev_close, prev_actual
        FROM px
        WHERE prev_actual > 0 AND prev_close > 0
          AND abs(prev_close - prev_actual) > greatest(0.0015 * prev_actual, 0.051)""").fetchall()

    # Announced actions mapped to securities (NSE feed applies to the company on both exchanges).
    ann = con.execute("""
        SELECT DISTINCT l.security_id, ca.ex_date, ca.subject, ca.face_value
        FROM corp_action ca
        JOIN listing l ON l.exchange = 'NSE' AND l.code = ca.code AND ca.ex_date BETWEEN l.valid_from - 30 AND l.valid_to + 30
        WHERE ca.kind SIMILAR TO '.*(split|consolidation|bonus|rights|demerger|capital_reduction).*'""").fetchall()
    ann_by_sec: dict[str, list] = {}
    for sid, ex, subj, fv in ann:
        ann_by_sec.setdefault(sid, []).append((ex, subj, fv))

    # Sessions per security/exchange, to place each announcement on its first session >= ex_date.
    sessions = con.execute("""
        SELECT security_id, exchange, list(trade_date ORDER BY trade_date), list(prev_actual ORDER BY trade_date)
        FROM px GROUP BY 1, 2""").fetchall()
    first_on_or_after: dict[tuple, list] = {(s, x): (dates, prevs) for s, x, dates, prevs in sessions}

    import bisect

    events: dict[tuple, dict] = {}
    for sid, x, code, d, prev_d, gap, pc, pa in implied:
        events[(sid, x, d)] = dict(sid=sid, x=x, code=code, d=d, gap=gap, implied=pc / pa, prev_actual=pa,
                                   parsed=None, kind=None, subject=None)
    for (sid, x), (dates, prevs) in first_on_or_after.items():
        for ex, subj, fv in ann_by_sec.get(sid, []):
            i = bisect.bisect_left(dates, ex)
            if i >= len(dates) or (dates[i] - ex).days > 10:
                continue
            d = dates[i]
            p = parse_subject(subj, face_value=fv)
            f = p.static_factor()
            r = next((a for a in p.actions if a.kind == "rights"), None)
            pa = prevs[i]
            if r and r.num and r.den and pa and r.amount is not None:
                issue = r.amount + (fv or 0) if r.note == "premium" else r.amount
                terp = (r.den * pa + r.num * issue) / (r.num + r.den)
                f = (f or 1.0) * terp / pa
            e = events.setdefault((sid, x, d), dict(sid=sid, x=x, code=None, d=d, gap=None, implied=None,
                                                    prev_actual=pa, parsed=None, kind=None, subject=None))
            e["kind"] = "+".join(filter(None, [e["kind"], p.kind]))
            e["subject"] = " | ".join(filter(None, [e["subject"], subj]))
            if f is not None:
                e["parsed"] = (e["parsed"] or 1.0) * f

    rows, dq = [], []
    now = utcnow()
    for e in events.values():
        imp, par = e["implied"], e["parsed"]
        if imp is not None and par is not None:
            agreement = "match" if abs(imp / par - 1) <= TOLERANCE else "mismatch"
            factor, method, applied = imp, "exchange_base_price", True
        elif imp is not None:
            agreement = "implied_only"
            applied = (e["gap"] or 0) <= MAX_GAP or bool(e["kind"])
            factor, method = imp, "exchange_base_price"
        else:
            agreement = "parsed_only"
            factor, method, applied = par, "announcement", par is not None and any(
                k in (e["kind"] or "") for k in ("split", "consolidation", "bonus"))
        if factor is None or not math.isfinite(factor) or factor <= 0:
            continue
        if agreement in ("mismatch", "parsed_only") or (agreement == "implied_only" and not applied):
            dq.append(("adj_" + agreement, e["x"], e["sid"], e["d"],
                       f"implied={imp} parsed={par} gap={e['gap']} subject={e['subject']}",
                       "medium" if agreement != "implied_only" else "low", now))
        rows.append((e["sid"], e["x"], e["code"], e["d"], factor, method, imp, par, e["kind"], e["subject"],
                     agreement, applied))

    con.execute("BEGIN")
    con.execute("DELETE FROM adj_event")
    insert_many(con, 
        """INSERT INTO adj_event (security_id, exchange, code, ex_date, factor, method, implied_factor, parsed_factor,
                                  parsed_kind, subject, agreement, applied, known_at, known_precision)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?, (?::TIMESTAMP + INTERVAL 9 HOUR)::TIMESTAMPTZ, 'convention')""",
        [r + (r[3],) for r in rows])
    con.execute("DELETE FROM dq_issue WHERE kind LIKE 'adj_%'")
    insert_many(con, "INSERT INTO dq_issue VALUES (?,?,?,?,?,?,?)", dq)
    con.execute("COMMIT")
    out: dict[str, int] = {}
    for _, _, _, _, _, _, _, _, _, _, agreement, applied in rows:
        k = f"{agreement}{'' if applied else '_not_applied'}"
        out[k] = out.get(k, 0) + 1
    return out


__all__ = ["build", "ADJUSTING"]
