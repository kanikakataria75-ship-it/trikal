"""The corporate calendar: board meetings (results, dividends, fund raising) the companies announced to NSE.

Source: the exchange's public board-meetings feed (`corporate-board-meetings`), fetched through the raw zone. `bm_timestamp` is when the
intimation reached the exchange, so every meeting carries the moment it became public."""

from __future__ import annotations

import datetime as dt
import json

import duckdb

from trikal_core.db import insert_many
from trikal_core.timeutil import IST, utcnow
from trikal_pipeline.http import Fetcher
from trikal_pipeline.load_financials import symbol_security_map
from trikal_pipeline.raw import RawStore

SOURCE_KEY = "nse.board_meetings"
URL = "https://www.nseindia.com/api/corporate-board-meetings?index=equities&from_date={a}&to_date={b}"
REFERER = "https://www.nseindia.com/companies-listing/corporate-filings-board-meetings"


def _d(s: str | None) -> dt.date | None:
    try:
        return dt.datetime.strptime((s or "").strip().title(), "%d-%b-%Y").date()
    except ValueError:
        return None


def _ts(s: str | None) -> dt.datetime | None:
    try:
        return dt.datetime.strptime((s or "").strip().title(), "%d-%b-%Y %H:%M:%S").replace(tzinfo=IST)
    except ValueError:
        return None


def fetch(raw: RawStore, fetcher: Fetcher, back_days: int = 45, ahead_days: int = 90) -> dict[str, int]:
    """One raw snapshot per day: the window from `back_days` ago to `ahead_days` ahead."""
    today = dt.datetime.now(IST).date()
    url = URL.format(a=(today - dt.timedelta(days=back_days)).strftime("%d-%m-%Y"), b=(today + dt.timedelta(days=ahead_days)).strftime("%d-%m-%Y"))
    part = today.isoformat()
    if part in raw.done_partitions(SOURCE_KEY):
        return {"skipped": 1}
    r = fetcher.get(url, referer=REFERER)
    rows = json.loads(r.body or b"[]")
    if r.status == 200 and isinstance(rows, list) and rows:
        sha = raw.put(SOURCE_KEY, url, r.body, r.content_type, "json")
        raw.log(SOURCE_KEY, part, url, "ok", r.status, sha)
        return {"ok": 1, "rows": len(rows)}
    raw.log(SOURCE_KEY, part, url, "error", r.status, None, "empty or bad answer")
    return {"error": 1}


def load(con: duckdb.DuckDBPyConnection, raw: RawStore) -> dict[str, int]:
    """Every raw snapshot, newest wins; the table is rebuilt from the snapshots (cheap, and idempotent)."""
    sec = symbol_security_map(con)
    seen: dict[tuple, tuple] = {}
    now = utcnow()
    for part, sha in sorted(raw.latest_ok(SOURCE_KEY).items()):
        try:
            rows = json.loads(raw.read(sha))
        except Exception:
            continue
        for x in rows if isinstance(rows, list) else []:
            sym = (x.get("bm_symbol") or "").strip()
            day, at = _d(x.get("bm_date")), _ts(x.get("bm_timestamp"))
            if not sym or not day or not at:
                continue
            purpose = (x.get("bm_purpose") or "").strip()
            if purpose.lower() == "board meeting intimation":          # the generic notice duplicates the specific purpose row
                continue
            seen[(sym, day, purpose, at)] = (sym, sec.get(sym), day, purpose, (x.get("bm_desc") or "").strip()[:400], at, sha, now)
    con.execute("BEGIN")
    con.execute("DELETE FROM board_meeting")
    insert_many(con, "INSERT INTO board_meeting VALUES (?,?,?,?,?,?,?,?)", list(seen.values()))
    con.execute("COMMIT")
    return {"meetings": len(seen)}
