"""NSE reference files (security master inputs) and the corporate-actions feed.

Master files are current snapshots; each fetch is kept in raw (dated), so history accrues from the
first fetch onward. The change files themselves carry effective dates, which is what we use as
`valid_from`; `known_at` is the effective date (precision 'imputed': the exchange circular usually
precedes it, so this is conservative, never early).
"""

from __future__ import annotations

import csv
import datetime as dt
import io
import json

import duckdb

from trikal_core.db import insert_many

from trikal_core.timeutil import IST, at_ist, utcnow
from trikal_pipeline.http import Fetcher
from trikal_pipeline.raw import RawStore

ARCH = "https://nsearchives.nseindia.com/content/equities/"
MASTER_FILES = {
    "nse.symbol_change": ARCH + "symbolchange.csv",
    "nse.name_change": ARCH + "namechange.csv",
    "nse.delisted": ARCH + "delisted.csv",
    "nse.equity_list": ARCH + "EQUITY_L.csv",
}


def fetch_masters(fetcher: Fetcher, raw: RawStore) -> dict[str, str]:
    out = {}
    today = dt.date.today().isoformat()
    for key, url in MASTER_FILES.items():
        r = fetcher.get(url)
        if r.status == 200 and not r.body.lstrip().startswith(b"<"):
            sha = raw.put(key, url, r.body, r.content_type, "csv")
            raw.log(key, today, url, "ok", r.status, sha)
            out[key] = sha
        else:
            raw.log(key, today, url, "error", r.status, None, "unexpected payload")
    return out


def _date(s: str, fmts=("%d-%b-%Y", "%d-%b-%y", "%d-%m-%Y")) -> dt.date | None:
    s = (s or "").strip()
    for f in fmts:
        try:
            return dt.datetime.strptime(s, f).date()
        except ValueError:
            continue
    return None


def _rows(body: bytes) -> list[list[str]]:
    text = body.decode("utf-8-sig", errors="replace")
    return [[c.strip() for c in r] for r in csv.reader(io.StringIO(text)) if any(c.strip() for c in r)]


def _latest_sha(raw: RawStore, key: str) -> str | None:
    by_partition = raw.latest_ok(key)
    return by_partition[max(by_partition)] if by_partition else None


def load_masters(con: duckdb.DuckDBPyConnection, raw: RawStore) -> dict[str, int]:
    latest = {k: _latest_sha(raw, k) for k in MASTER_FILES}
    now = utcnow()
    counts = {}

    sha = latest["nse.symbol_change"]
    if sha:
        con.execute("DELETE FROM nse_symbol_change")
        rows = []
        for r in _rows(raw.read(sha)):
            if len(r) < 4 or r[0].upper().startswith("SM_"):
                continue
            d = _date(r[3])
            if d is None:
                continue
            rows.append((r[0], r[1].upper(), r[2].upper(), d, at_ist(d, dt.time(0, 0)), "imputed", now, sha))
        insert_many(con, "INSERT INTO nse_symbol_change VALUES (?,?,?,?,?,?,?,?)", rows)
        counts["symbol_change"] = len(rows)

    sha = latest["nse.name_change"]
    if sha:
        con.execute("DELETE FROM nse_name_change")
        rows = []
        for r in _rows(raw.read(sha))[1:]:
            d = _date(r[3]) if len(r) >= 4 else None
            if d:
                rows.append((r[0].upper(), r[1], r[2], d, at_ist(d, dt.time(0, 0)), "imputed", now, sha))
        insert_many(con, "INSERT INTO nse_name_change VALUES (?,?,?,?,?,?,?,?)", rows)
        counts["name_change"] = len(rows)

    sha = latest["nse.delisted"]
    if sha:
        con.execute("DELETE FROM nse_delisted")
        rows = []
        for r in _rows(raw.read(sha))[1:]:
            d = _date(r[2]) if len(r) >= 3 else None
            if d:
                rows.append((r[0].upper(), r[1], d, (r[3] if len(r) > 3 else "").strip(),
                             at_ist(d, dt.time(23, 59, 59)), "day", now, sha))
        insert_many(con, "INSERT INTO nse_delisted VALUES (?,?,?,?,?,?,?,?)", rows)
        counts["delisted"] = len(rows)

    sha = latest["nse.equity_list"]
    if sha:
        snap = dt.date.fromisoformat(max(raw.latest_ok("nse.equity_list")))
        con.execute("DELETE FROM nse_equity_list WHERE snapshot_date = ?", [snap])
        rows = []
        for r in _rows(raw.read(sha))[1:]:
            if len(r) < 8:
                continue
            rows.append((snap, r[0].upper(), r[1], r[2], _date(r[3]), float(r[4] or 0), int(r[5] or 0),
                         r[6].upper(), float(r[7] or 0), now, sha))
        insert_many(con, "INSERT INTO nse_equity_list VALUES (?,?,?,?,?,?,?,?,?,?,?)", rows)
        counts["equity_list"] = len(rows)
    return counts


# ----------------------------------------------------------------------------------------------
# Corporate actions (www.nseindia.com JSON, monthly date ranges). Website API: used politely, ADR-006.

CA_URL = "https://www.nseindia.com/api/corporates-corporateActions?index=equities&from_date={f}&to_date={t}"


def month_ranges(start: dt.date, end: dt.date):
    d = start.replace(day=1)
    while d <= end:
        nxt = (d.replace(day=28) + dt.timedelta(days=4)).replace(day=1)
        yield d, min(nxt - dt.timedelta(days=1), end)
        d = nxt


def fetch_corp_actions(fetcher: Fetcher, raw: RawStore, start: dt.date, end: dt.date, refresh_recent: int = 2) -> dict:
    key = "nse.corp_actions"
    done = raw.done_partitions(key)
    recent_cut = (dt.date.today().replace(day=1) - dt.timedelta(days=31 * refresh_recent))
    stats = {"ok": 0, "error": 0, "skipped": 0}
    for f, t in month_ranges(start, end):
        part = f.strftime("%Y-%m")
        if part in done and f < recent_cut:
            stats["skipped"] += 1
            continue
        url = CA_URL.format(f=f.strftime("%d-%m-%Y"), t=t.strftime("%d-%m-%Y"))
        try:
            r = fetcher.get(url, referer="https://www.nseindia.com/companies-listing/corporate-filings-actions")
            json.loads(r.body)  # validate
        except Exception as exc:
            raw.log(key, part, url, "error", None, None, str(exc)[:300])
            stats["error"] += 1
            continue
        sha = raw.put(key, url, r.body, r.content_type, "json")
        raw.log(key, part, url, "ok", r.status, sha)
        stats["ok"] += 1
    return stats


def load_corp_actions(con: duckdb.DuckDBPyConnection, raw: RawStore) -> int:
    from trikal_pipeline.corp_actions import parse_subject

    latest = raw.latest_ok("nse.corp_actions")
    now = utcnow()
    rows = []
    for part, sha in sorted(latest.items()):
        for a in json.loads(raw.read(sha)):
            ex = _date(a.get("exDate") or "")
            if ex is None:
                continue
            bcast = a.get("caBroadcastDate")
            known = None
            prec = "imputed"
            if bcast:
                try:
                    known = dt.datetime.strptime(bcast.strip(), "%d-%b-%Y %H:%M:%S").replace(tzinfo=IST)
                    prec = "exact"
                except ValueError:
                    known = None
            if known is None:
                known = at_ist(ex, dt.time(9, 0))  # conservative: no later than the ex-date pre-open
            try:
                fv = float(a.get("faceVal"))
            except (TypeError, ValueError):
                fv = None
            p = parse_subject(a.get("subject") or "", face_value=fv)
            rows.append(("NSE", (a.get("symbol") or "").upper(), a.get("series"), a.get("isin"), a.get("comp"),
                         a.get("subject"), ex, _date(a.get("recDate") or ""), fv,
                         p.kind, p.num, p.den, p.amount, known, prec, now, sha))
    con.execute("DELETE FROM corp_action WHERE exchange = 'NSE'")
    insert_many(con, "INSERT INTO corp_action VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)", rows)
    # identical announcements can appear in overlapping month windows; keep one
    con.execute("""CREATE OR REPLACE TEMP TABLE _ca AS SELECT DISTINCT ON (exchange, code, series, ex_date, subject) *
                   FROM corp_action ORDER BY exchange, code, series, ex_date, subject, recorded_at""")
    con.execute("DELETE FROM corp_action; INSERT INTO corp_action SELECT * FROM _ca")
    return con.execute("SELECT count(*) FROM corp_action").fetchone()[0]
