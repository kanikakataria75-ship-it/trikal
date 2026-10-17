"""Build the sector return panel and the point-in-time sector sensitivities (M5). Math lives in
trikal_analytics.sensitivity; this module only assembles the inputs from the database and stores the results.

Inputs (all point-in-time safe):
  month-end ADJUSTED closes of every security that was ever in the Nifty 500 (split/bonus-adjusted with the applied events;
  the adjustment only rescales earlier prices uniformly, so returns between two dates before an event are unaffected by it);
  membership and sector label of each security at the START of each month (so a month's return is not selected by
  what happened in it); macro drivers from `macro_obs` with their release times.
"""

from __future__ import annotations

import bisect
import csv
import datetime as dt
import math
import os
import tempfile
from collections import defaultdict
from pathlib import Path

import duckdb

from trikal_analytics import sensitivity as S
from trikal_core.timeutil import IST

MAX_ABS_RETURN = 3.0      # a monthly move beyond +300% / -100% is a data error, not a market move
MIN_SECTOR_MEMBERS = 5
MIN_MARKET_MEMBERS = 30


def _copy(con: duckdb.DuckDBPyConnection, table: str, rows: list[tuple], cols: str) -> None:
    if not rows:
        return
    with tempfile.NamedTemporaryFile("w", suffix=".csv", delete=False, newline="", encoding="utf-8") as tmp:
        w = csv.writer(tmp)
        for r in rows:
            w.writerow(["" if v is None else (v.isoformat() if isinstance(v, (dt.date, dt.datetime)) else v) for v in r])
        path = tmp.name
    try:
        con.execute(f"INSERT INTO {table} SELECT * FROM read_csv('{Path(path).as_posix()}', header = false, columns = {cols}, nullstr = '')")
    finally:
        os.unlink(path)


def month_end_closes(con: duckdb.DuckDBPyConnection) -> dict[str, dict[tuple[int, int], tuple[dt.date, float]]]:
    rows = con.execute("""
        WITH ids AS (SELECT DISTINCT security_id FROM index_membership WHERE index_code = 'NIFTY500'),
        p AS (
            SELECT l.security_id, e.trade_date, e.close
            FROM price_eod e JOIN listing l ON l.exchange = e.exchange AND l.code = e.code AND e.trade_date BETWEEN l.valid_from AND l.valid_to
            WHERE e.exchange = 'NSE' AND e.series = 'EQ' AND e.close > 0 AND l.security_id IN (SELECT security_id FROM ids)
            QUALIFY row_number() OVER (PARTITION BY l.security_id, e.trade_date ORDER BY e.volume DESC NULLS LAST) = 1)
        SELECT security_id, year(trade_date), month(trade_date), max(trade_date), arg_max(close, trade_date)
        FROM p GROUP BY 1, 2, 3""").fetchall()
    out: dict[str, dict] = defaultdict(dict)
    for sid, y, m, d, c in rows:
        out[sid][(y, m)] = (d, c)
    return out


def adjusted(closes: dict[str, dict], events: dict[str, list[tuple[dt.date, float]]]) -> dict[str, dict]:
    """Same month-end closes multiplied by every applied factor whose ex-date is later."""
    out: dict[str, dict] = {}
    for sid, months in closes.items():
        ev = sorted(events.get(sid, []))
        dates = [d for d, _ in ev]
        # suffix products: product of factors with ex_date > d
        suffix = [1.0] * (len(ev) + 1)
        for i in range(len(ev) - 1, -1, -1):
            suffix[i] = suffix[i + 1] * ev[i][1]
        out[sid] = {k: (d, c * suffix[bisect.bisect_right(dates, d)]) for k, (d, c) in months.items()}
    return out


def build(con: duckdb.DuckDBPyConnection) -> dict:
    stats: dict = {}
    ev: dict[str, list] = defaultdict(list)
    for sid, d, f in con.execute("SELECT security_id, ex_date, factor FROM adj_event WHERE applied AND exchange = 'NSE'").fetchall():
        ev[sid].append((d, f))
    closes = adjusted(month_end_closes(con), ev)
    stats["securities"] = len(closes)

    # membership intervals and sector labels
    mem: dict[str, list[tuple[dt.date, dt.date]]] = defaultdict(list)
    for sid, vf, vt in con.execute("""
            SELECT security_id, valid_from, valid_to FROM index_membership WHERE index_code = 'NIFTY500'
            QUALIFY row_number() OVER (PARTITION BY security_id, valid_from ORDER BY known_at DESC) = 1""").fetchall():
        mem[sid].append((vf, vt))
    lab: dict[str, list] = defaultdict(list)
    for sid, code, vf, vt, method in con.execute(
            "SELECT security_id, code, valid_from, valid_to, method FROM classification WHERE scheme = 'NSE_INDUSTRY' ORDER BY security_id, (method = 'official_snapshot') DESC").fetchall():
        lab[sid].append((code, vf, vt, method != "official_snapshot"))

    def sector_at(sid: str, d: dt.date):
        for code, vf, vt, back in lab.get(sid, ()):
            if vf <= d < vt:
                return code, back
        return None

    def member_at(sid: str, d: dt.date) -> bool:
        return any(vf <= d < vt for vf, vt in mem.get(sid, ()))

    # monthly returns by sector (membership/sector measured at the START of the month)
    panel: dict[tuple[int, int], dict[str, list[tuple[float, bool]]]] = defaultdict(lambda: defaultdict(list))
    bad = 0
    for sid, months in closes.items():
        for (y, m), (d, c) in months.items():
            py, pm = S.prev_month(y, m)
            prev = months.get((py, pm))
            if not prev:
                continue
            start = S.month_end(py, pm)
            if not member_at(sid, start):
                continue
            r = c / prev[1] - 1.0
            if not math.isfinite(r) or r > MAX_ABS_RETURN or r <= -1.0:
                bad += 1
                continue
            sec = sector_at(sid, start)
            panel[(y, m)]["__ALL__"].append((r, False))
            if sec:
                panel[(y, m)][sec[0]].append((r, sec[1]))
    stats["excluded_bad_returns"] = bad

    rets: dict[str, dict[tuple[int, int], float]] = defaultdict(dict)
    back: dict[str, dict[tuple[int, int], float]] = defaultdict(dict)
    rows = []
    for (y, m), secs in sorted(panel.items()):
        for sec, vals in secs.items():
            if len(vals) < (MIN_SECTOR_MEMBERS if sec != "__ALL__" else MIN_MARKET_MEMBERS):
                continue
            name = S.MARKET if sec == "__ALL__" else sec
            r = sum(v for v, _ in vals) / len(vals)
            b = sum(1 for _, bk in vals if bk) / len(vals)
            rets[name][(y, m)] = r
            back[name][(y, m)] = b
            rows.append((S.month_end(y, m), name, r, len(vals), b))
    con.execute("DELETE FROM sector_return_monthly")
    _copy(con, "sector_return_monthly", rows, "{'month_end': 'DATE', 'sector': 'VARCHAR', 'ret': 'DOUBLE', 'n': 'INTEGER', 'backproj_share': 'DOUBLE'}")
    stats["sector_months"] = len(rows)
    stats["sectors"] = len([k for k in rets if k != S.MARKET])

    # driver changes
    deltas: dict[str, dict] = {}
    for did, drv in S.DRIVERS.items():
        obs = con.execute("""SELECT period_end, value, known_at FROM macro_obs WHERE series_id = ?
                             QUALIFY row_number() OVER (PARTITION BY period_start ORDER BY known_at DESC) = 1""", [drv.series]).fetchall()
        if obs:
            deltas[did] = S.monthly_changes(S.monthly_levels(obs), drv.kind)
    stats["drivers"] = sorted(deltas)

    # rolling estimates for every month end
    out = []
    mkt = rets.get(S.MARKET, {})
    all_months = sorted(mkt)
    for sector, sr in rets.items():
        for did, dl in deltas.items():
            for ym in all_months:
                if ym not in dl:
                    continue
                e = S.estimate(sr, mkt, dl, ym, market_only=(sector == S.MARKET))
                if not e:
                    continue
                bshare = sum(back[sector].get(k, 0.0) for k in e["months"]) / len(e["months"])
                end = S.month_end(*ym)
                usable = max(e["usable_from"], dt.datetime.combine(end, dt.time(16, 0), IST))
                out.append((end, usable, sector, did, e["beta"], e["tstat"], e["r2"], e["n"], S.WINDOW, S.DRIVERS[did].kind,
                            e["beta_mkt"], bshare, S.confidence(e["n"], e["tstat"], bshare),
                            "OLS monthly, trailing 60m (min 36), market-controlled" if sector != S.MARKET else "OLS monthly, trailing 60m (min 36)"))
    con.execute("DELETE FROM sector_sensitivity")
    _copy(con, "sector_sensitivity", out,
          "{'window_end': 'DATE', 'usable_from': 'TIMESTAMPTZ', 'sector': 'VARCHAR', 'driver': 'VARCHAR', 'beta': 'DOUBLE', 'tstat': 'DOUBLE', "
          "'r2': 'DOUBLE', 'n_obs': 'INTEGER', 'window_months': 'INTEGER', 'unit': 'VARCHAR', 'beta_mkt': 'DOUBLE', "
          "'backproj_share': 'DOUBLE', 'confidence': 'VARCHAR', 'method': 'VARCHAR'}")
    stats["estimates"] = len(out)
    return stats
