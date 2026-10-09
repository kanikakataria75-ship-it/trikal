"""Price-adjustment events (ADR-012, FORMULAS.md §Corporate actions).

Two independent signals per (security, exchange, first session on/after an ex-date):

  parsed    factor from the announced action (corporate-actions feed + subject parser)
  implied   prev_close(t) / close(previous session) - the exchange's own base-price adjustment.
            Only meaningful in file formats where PREVCLOSE is adjusted (verified: NSE legacy
            bhavcopies do NOT adjust it, e.g. TCS bonus 31-May-2018 shows the unadjusted 3514.10).

Both comparisons need our "previous close" to be the close of the *immediately previous session*.
Gaps are measured on the true exchange calendar (trikal_pipeline.calendar): if the security has no
row on an intervening session (source files do have holes, e.g. BSE 15-Jul-2022 omits TCS) or any
day in between is UNKNOWN, neither the implied factor nor the observed price ratio is used.

Decision rules (agreement -> applied?):
  match / mismatch       parsed + trusted implied                         -> apply implied (mismatch: DQ)
  parsed_confirmed       parsed; observed close/prev close within PRICE_BAND of the factor  -> apply
  parsed_unconfirmed     parsed; no clean observation (gap / unknown days)                 -> apply, DQ
  parsed_price_disagrees parsed; observed move contradicts it                      -> NOT applied, DQ
  implied_only           trusted implied, no announcement in our feed                     -> apply
  unverifiable           implied over a gap, no announcement                       -> NOT applied, DQ
Events take effect at the pre-open of that session (known_at 09:00 IST, precision 'convention').
"""

from __future__ import annotations

import bisect
import math

import duckdb

from trikal_core.db import insert_many
from trikal_core.timeutil import utcnow
from trikal_pipeline.corp_actions import parse_subject
from trikal_pipeline.security_master import EQUITY_VIEW

TOLERANCE = 0.02  # parsed vs implied
PRICE_BAND = (0.80, 1.25)  # observed ratio / factor must fall inside (normal daily move + circuit)
JUMP_BAND = (0.60, 1.60)  # beyond any circuit band: needs an explanation


def build(con: duckdb.DuckDBPyConnection) -> dict[str, int]:
    con.execute(EQUITY_VIEW)
    # Session index (sessions only) and known-day index (sessions + confirmed holidays) per exchange.
    con.execute("""
        CREATE OR REPLACE TEMP TABLE xcal AS
        SELECT exchange, d,
               sum(CASE WHEN status = 'session' THEN 1 ELSE 0 END) OVER w AS sidx,
               row_number() OVER w AS kidx
        FROM exchange_day WINDOW w AS (PARTITION BY exchange ORDER BY d)""")
    con.execute("""
        CREATE OR REPLACE TEMP TABLE px AS
        WITH p AS (
            SELECT l.security_id, e.exchange, e.code, e.trade_date, e.close, e.prev_close
            FROM eq e JOIN listing l ON l.exchange = e.exchange AND l.code = e.code
                                    AND e.trade_date BETWEEN l.valid_from AND l.valid_to
            -- one row per exchange CODE and day: PREVCLOSE always refers to the same code's last close
            QUALIFY row_number() OVER (PARTITION BY l.security_id, e.exchange, e.code, e.trade_date
                ORDER BY CASE e.series WHEN 'EQ' THEN 0 WHEN 'BE' THEN 1 WHEN 'BZ' THEN 2 ELSE 3 END,
                         e.volume DESC NULLS LAST) = 1),
        q AS (
            SELECT p.*, c.sidx, c.kidx,
                   lag(p.close) OVER w AS prev_actual, lag(p.trade_date) OVER w AS prev_date,
                   lag(c.sidx) OVER w AS prev_sidx, lag(c.kidx) OVER w AS prev_kidx
            FROM p LEFT JOIN xcal c ON c.exchange = p.exchange AND c.d = p.trade_date
            WINDOW w AS (PARTITION BY p.security_id, p.exchange, p.code ORDER BY p.trade_date))
        SELECT security_id, exchange, code, trade_date, close, prev_close, prev_actual, prev_date,
               sidx - prev_sidx AS gap,
               (trade_date - prev_date - 1) - (kidx - prev_kidx - 1) AS unknown_days
        FROM q""")
    # clean = previous close is from the immediately previous session with no unknown days between
    implied = con.execute("""
        SELECT security_id, exchange, code, trade_date, prev_close / prev_actual
        FROM px
        WHERE prev_actual > 0 AND prev_close > 0 AND gap = 1 AND unknown_days = 0
          AND abs(prev_close - prev_actual) > greatest(0.0015 * prev_actual, 0.051)""").fetchall()
    suspect = con.execute("""
        SELECT security_id, exchange, code, trade_date, prev_close / prev_actual, gap, unknown_days
        FROM px
        WHERE prev_actual > 0 AND prev_close > 0 AND NOT (coalesce(gap, 0) = 1 AND coalesce(unknown_days, 1) = 0)
          AND abs(prev_close - prev_actual) > greatest(0.0015 * prev_actual, 0.051)""").fetchall()

    ann = con.execute("""
        SELECT DISTINCT l.security_id, ca.ex_date, ca.subject, ca.face_value
        FROM corp_action ca
        JOIN listing l ON l.exchange = 'NSE' AND l.code = ca.code
                      AND ca.ex_date BETWEEN l.valid_from - 30 AND l.valid_to + 30
        WHERE regexp_matches(ca.kind, 'split|consolidation|bonus|rights|demerger|capital_reduction')""").fetchall()
    ann_by_sec: dict[str, list] = {}
    for sid, ex, subj, fv in ann:
        ann_by_sec.setdefault(sid, []).append((ex, subj, fv))

    rows_by_sec = {}
    for sid, x, dates, closes, prevs, gaps, unk in con.execute("""
            SELECT security_id, exchange, list(trade_date ORDER BY trade_date), list(close ORDER BY trade_date),
                   list(prev_actual ORDER BY trade_date), list(gap ORDER BY trade_date),
                   list(unknown_days ORDER BY trade_date)
            FROM px
            WHERE (security_id, exchange, code) IN (
                SELECT security_id, exchange, arg_max(code, n) FROM (
                    SELECT security_id, exchange, code, count(*) n FROM px GROUP BY ALL) GROUP BY 1, 2)
            GROUP BY 1, 2""").fetchall():
        rows_by_sec[(sid, x)] = (dates, closes, prevs, gaps, unk)

    def blank(sid, x, code, d):
        return dict(sid=sid, x=x, code=code, d=d, implied=None, suspect=None, parsed=None, observed=None,
                    kind=None, subject=None, note="")

    events: dict[tuple, dict] = {}
    for sid, x, code, d, f in implied:
        events[(sid, x, d)] = blank(sid, x, code, d) | {"implied": f}
    for sid, x, code, d, f, gap, unk in suspect:
        e = events.setdefault((sid, x, d), blank(sid, x, code, d))
        e["suspect"], e["note"] = f, f"gap={gap} unknown_days={unk}"

    for (sid, x), (dates, closes, prevs, gaps, unk) in rows_by_sec.items():
        for ex, subj, fv in ann_by_sec.get(sid, []):
            i = bisect.bisect_left(dates, ex)
            if i >= len(dates) or (dates[i] - ex).days > 10:
                continue
            d, pa = dates[i], prevs[i]
            clean = gaps[i] == 1 and unk[i] == 0 and pa
            p = parse_subject(subj, face_value=fv)
            f = p.static_factor()
            r = next((a for a in p.actions if a.kind == "rights"), None)
            if r and r.num and r.den and pa and r.amount is not None:
                issue = r.amount + (fv or 0) if r.note == "premium" else r.amount
                f = (f or 1.0) * ((r.den * pa + r.num * issue) / (r.num + r.den)) / pa
            e = events.setdefault((sid, x, d), blank(sid, x, None, d))
            e["kind"] = "+".join(filter(None, [e["kind"], p.kind]))
            e["subject"] = " | ".join(filter(None, [e["subject"], subj]))
            if f is not None:
                e["parsed"] = (e["parsed"] or 1.0) * f
            if clean and closes[i]:
                e["observed"] = closes[i] / pa

    rows, dq = [], []
    now = utcnow()
    for e in events.values():
        imp, par, obs = e["implied"], e["parsed"], e["observed"]
        if par is not None and imp is not None:
            agreement = "match" if abs(imp / par - 1) <= TOLERANCE else "mismatch"
            factor, method, applied = imp, "exchange_base_price", True
        elif par is not None:
            method, factor = "announcement", par
            if obs is None:
                agreement, applied = "parsed_unconfirmed", True
            elif PRICE_BAND[0] <= obs / par <= PRICE_BAND[1]:
                agreement, applied = "parsed_confirmed", True
            else:
                agreement, applied = "parsed_price_disagrees", False
        elif imp is not None:
            agreement, factor, method, applied = "implied_only", imp, "exchange_base_price", True
        elif e["suspect"] is not None:
            agreement, factor, method, applied = "unverifiable", e["suspect"], "exchange_base_price", False
        else:
            continue  # announced non-static action (e.g. demerger) with no price signal: nothing to apply
        if factor is None or not math.isfinite(factor) or factor <= 0:
            continue
        if agreement in ("mismatch", "parsed_unconfirmed", "parsed_price_disagrees", "unverifiable"):
            sev = {"mismatch": "medium", "parsed_price_disagrees": "medium"}.get(agreement, "low")
            dq.append(("adj_" + agreement, e["x"], e["sid"], e["d"],
                       f"implied={imp} parsed={par} observed={obs} suspect={e['suspect']} {e['note']} "
                       f"subject={e['subject']}", sev, now))
        rows.append((e["sid"], e["x"], e["code"], e["d"], factor, method, imp, par, e["kind"], e["subject"],
                     agreement, applied))

    con.execute("BEGIN")
    con.execute("DELETE FROM adj_event")
    insert_many(con,
        """INSERT INTO adj_event (security_id, exchange, code, ex_date, factor, method, implied_factor, parsed_factor,
                                  parsed_kind, subject, agreement, applied, known_at, known_precision)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?, (?::TIMESTAMP + INTERVAL 9 HOUR)::TIMESTAMPTZ, 'convention')""",
        [r + (r[3],) for r in rows])
    con.execute("DELETE FROM dq_issue WHERE kind LIKE 'adj_%' OR kind = 'unexplained_price_jump'")
    insert_many(con, "INSERT INTO dq_issue VALUES (?,?,?,?,?,?,?)", dq)
    # Safety net for actions missing from our feed (e.g. BSE-only companies): a clean session-to-session
    # move outside JUMP_BAND with no applied event is reported with a suggested factor, never auto-applied.
    con.execute(f"""
        INSERT INTO dq_issue
        SELECT 'unexplained_price_jump', p.exchange, p.security_id, p.trade_date,
               'code=' || p.code || ' close/prev_close=' || round(p.close / p.prev_actual, 4)
                 || ' suggested_factor=' || round(p.close / p.prev_actual, 4),
               'medium', now()
        FROM px p
        WHERE p.gap = 1 AND p.unknown_days = 0 AND p.prev_actual > 0 AND p.close > 0
          AND (p.close / p.prev_actual < {JUMP_BAND[0]} OR p.close / p.prev_actual > {JUMP_BAND[1]})
          AND abs(p.close - p.prev_actual) > 0.10  -- two ticks: penny-stock tick effects are not events
          AND NOT EXISTS (SELECT 1 FROM adj_event a WHERE a.security_id = p.security_id
                          AND a.exchange = p.exchange AND a.ex_date = p.trade_date AND a.applied)""")
    con.execute("COMMIT")
    out: dict[str, int] = {}
    for r in rows:
        k = r[10] + ("" if r[11] else " (not applied)")
        out[k] = out.get(k, 0) + 1
    return dict(sorted(out.items()))
