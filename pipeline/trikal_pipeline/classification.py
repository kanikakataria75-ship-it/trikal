"""Sector classification history with explicit provenance (RISKS R-3, the gap that sank an earlier study).

Rows per security, scheme 'NSE_INDUSTRY' (NSE India Industry Classification, sector level as published in the
Nifty constituent files; 22 labels):

  official_snapshot         confidence 1.0   an NSE constituent file said so on that date. Forward-accumulating:
                                             every `trikal fetch-index` adds a dated snapshot, so true history grows.
  assumed_static_backward   confidence 0.5   the earliest official label projected back in time (NSE did not publish
                                             history before 2022; companies rarely change sector). Never silent:
                                             consumers can require min_confidence.

Scheme 'NSE_LEGACY': the industry printed beside the company in NSE Indices' press releases (1999 - ~2010),
valid from the date the company was added to the S&P CNX 500; method 'press_release', confidence 0.8.
These are genuine point-in-time observations but use the old industry vocabulary.
"""

from __future__ import annotations

import datetime as dt
import re

import duckdb

from trikal_core.db import insert_many
from trikal_core.timeutil import end_of_day_ist

OPEN = dt.date(9999, 12, 31)
BEGINNING = dt.date(1990, 1, 1)
_SPLIT = re.compile(r"\b(?:ltd|limited)\b\.?\s*(.*)$", re.I)


def legacy_industry(company: str) -> str | None:
    m = _SPLIT.search(company or "")
    ind = re.sub(r"\s+", " ", (m.group(1) if m else "").replace("*", " ")).strip(" .-–")
    # industry text is a short phrase; anything long or containing digits is a parsing leftover
    if not (2 < len(ind) <= 40) or re.search(r"\d", ind):
        return None
    return ind.title() if ind.isupper() else ind


def build(con: duckdb.DuckDBPyConnection) -> dict[str, int]:
    rows = []
    # ---- official snapshots, collapsed to intervals per security ------------------------------------------
    snaps = con.execute("""
        SELECT 'S:' || substr(isin, 1, 9) AS sid, snapshot_date, mode(industry) AS industry, min(recorded_at) AS rec
        FROM index_snapshot WHERE industry IS NOT NULL AND industry <> '' AND isin LIKE 'INE%'
        GROUP BY ALL ORDER BY 1, 2""").fetchall()
    by_sid: dict[str, list] = {}
    for sid, d, ind, rec in snaps:
        by_sid.setdefault(sid, []).append((d, ind, rec))
    for sid, seq in by_sid.items():
        runs = []
        for d, ind, rec in seq:
            if not runs or runs[-1][1] != ind:
                runs.append([d, ind, rec])
        first_d, first_ind, first_rec = runs[0]
        rows.append((sid, "NSE_INDUSTRY", first_ind, BEGINNING, first_d, BEGINNING_TS(), "assumed_static_backward", 0.5,
                     "earliest official label projected back"))
        for i, (d, ind, rec) in enumerate(runs):
            end = runs[i + 1][0] if i + 1 < len(runs) else OPEN
            rows.append((sid, "NSE_INDUSTRY", ind, d, end, rec, "official_snapshot", 1.0, f"nse constituent file {d}"))
    # ---- press-release industries (pre-2011) ---------------------------------------------------------------
    ev = con.execute("""
        SELECT security_id, effective_date, announced_date, company, parse_confidence, source_url
        FROM index_event
        WHERE index_code = 'NIFTY500' AND action = 'in' AND parse_confidence > 0 AND security_id NOT LIKE 'U:%'
          AND symbol IS NULL ORDER BY security_id, effective_date""").fetchall()
    seen: dict[str, list] = {}
    for sid, eff, ann, company, conf, url in ev:
        ind = legacy_industry(company)
        if ind:
            seen.setdefault(sid, []).append((eff, ann, ind, conf, url))
    n_legacy = 0
    for sid, seq in seen.items():
        runs = []
        for eff, ann, ind, conf, url in seq:
            if not runs or runs[-1][2] != ind:
                runs.append((eff, ann, ind, conf, url))
        for i, (eff, ann, ind, conf, url) in enumerate(runs):
            end = runs[i + 1][0] if i + 1 < len(runs) else OPEN
            rows.append((sid, "NSE_LEGACY", ind, eff, end, end_of_day_ist(ann or eff), "press_release",
                         round(0.8 * (conf or 1.0), 3), url.rsplit("/", 1)[-1]))
            n_legacy += 1
    con.execute("BEGIN")
    con.execute("DELETE FROM classification")
    insert_many(con, "INSERT INTO classification VALUES (?,?,?,?,?,?,?,?,?)", rows)
    con.execute("COMMIT")
    return {"rows": len(rows), "securities_official": len(by_sid), "legacy_rows": n_legacy}


def BEGINNING_TS():
    import datetime as _dt

    from trikal_core.timeutil import IST

    return _dt.datetime(1990, 1, 1, tzinfo=IST)
