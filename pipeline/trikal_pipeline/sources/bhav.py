"""Daily bhavcopies (EOD prices) for NSE and BSE: fetch to raw, stage, load (DATA_SOURCES §1).

Formats (verified 2026-10-09):
  nse_udiff   2024-07-08 ->  nsearchives .../content/cm/BhavCopy_NSE_CM_0_0_0_YYYYMMDD_F_0000.csv.zip
  nse_legacy  1994-11 -> 2024-07-05 .../historical/EQUITIES/YYYY/MON/cmDDMONYYYYbhav.csv.zip
              (ISIN + TOTALTRADES columns from Aug-2011; earlier files have no ISIN)
  bse_udiff   2024 ->        www.bseindia.com/download/BhavCopy/Equity/BhavCopy_BSE_CM_0_0_0_YYYYMMDD_F_0000.CSV
  bse_isin    ~2017 -> 2024  .../EQ_ISINCODE_DDMMYY.zip  (legacy columns + ISIN_CODE)
  bse_legacy  ~2007 ->       .../EQDDMMYY_CSV.ZIP
NSE answers 404 for days without a file. BSE answers 200 with an HTML page, so every payload is
validated by content, never by status code alone.
"""

from __future__ import annotations

import datetime as dt
import io
import zipfile
from dataclasses import dataclass
from pathlib import Path

from trikal_core.db import data_dir
from trikal_pipeline.http import Fetcher
from trikal_pipeline.raw import RawStore

NSE_UDIFF_FROM = dt.date(2024, 7, 8)
BSE_UDIFF_TRY_FROM = dt.date(2023, 1, 1)


@dataclass(frozen=True)
class Candidate:
    fmt: str
    url: str
    ext: str


def nse_candidates(d: dt.date) -> list[Candidate]:
    if d >= NSE_UDIFF_FROM:
        return [Candidate("nse_udiff", f"https://nsearchives.nseindia.com/content/cm/BhavCopy_NSE_CM_0_0_0_{d:%Y%m%d}_F_0000.csv.zip", "zip")]
    mon = d.strftime("%b").upper()
    return [Candidate("nse_legacy", f"https://nsearchives.nseindia.com/content/historical/EQUITIES/{d:%Y}/{mon}/cm{d:%d}{mon}{d:%Y}bhav.csv.zip", "zip")]


def bse_candidates(d: dt.date) -> list[Candidate]:
    base = "https://www.bseindia.com/download/BhavCopy/Equity/"
    ddmmyy = d.strftime("%d%m%y")
    out = []
    if d >= BSE_UDIFF_TRY_FROM:
        out.append(Candidate("bse_udiff", f"{base}BhavCopy_BSE_CM_0_0_0_{d:%Y%m%d}_F_0000.CSV", "csv"))
    out.append(Candidate("bse_isin", f"{base}EQ_ISINCODE_{ddmmyy}.zip", "zip"))
    if d.weekday() < 5:  # legacy fallback only on weekdays to limit requests on non-sessions
        out.append(Candidate("bse_legacy", f"{base}EQ{ddmmyy}_CSV.ZIP", "zip"))
    return out


SOURCE_KEY = {"NSE": "nse.bhav", "BSE": "bse.bhav"}
CANDIDATES = {"NSE": nse_candidates, "BSE": bse_candidates}

EXPECTED_HEADER = {
    "nse_udiff": "TradDt,BizDt,Sgmt,Src",
    "bse_udiff": "TradDt,BizDt,Sgmt,Src",
    "nse_legacy": "SYMBOL,SERIES,OPEN",
    "bse_isin": "SC_CODE,SC_NAME",
    "bse_legacy": "SC_CODE,SC_NAME",
}


def extract_csv(body: bytes) -> bytes | None:
    """Return the CSV bytes inside a zip (or the body itself if it is plain CSV); None if not a bhavcopy."""
    if body.startswith(b"PK\x03\x04"):
        try:
            with zipfile.ZipFile(io.BytesIO(body)) as z:
                names = [n for n in z.namelist() if n.lower().endswith(".csv")]
                return z.read(names[0]) if names else None
        except zipfile.BadZipFile:
            return None
    head = body[:200].lstrip(b"\xef\xbb\xbf").lower()
    if head.startswith(b"<") or b"<html" in head:
        return None
    return body


def valid_for(fmt: str, csv_bytes: bytes | None) -> bool:
    if not csv_bytes:
        return False
    first = csv_bytes[:300].lstrip(b"\xef\xbb\xbf").decode("latin-1").splitlines()[0].replace(" ", "")
    return first.upper().startswith(EXPECTED_HEADER[fmt].upper()) and len(csv_bytes.splitlines()) > 1


def fetch_day(fetcher: Fetcher, raw: RawStore, exchange: str, d: dt.date) -> str:
    """Fetch one day's bhavcopy. Returns status: ok | not_found | error."""
    key = SOURCE_KEY[exchange]
    partition = d.isoformat()
    last_status, last_http, last_url, note = "not_found", None, "", None
    for c in CANDIDATES[exchange](d):
        last_url = c.url
        try:
            r = fetcher.get(c.url)
        except Exception as exc:  # network failure after retries
            last_status, note = "error", f"{type(exc).__name__}: {exc}"[:300]
            continue
        last_http = r.status
        if r.status == 404:
            continue
        if r.status != 200:
            last_status, note = "error", f"http {r.status}"
            continue
        csv_bytes = extract_csv(r.body)
        if valid_for(c.fmt, csv_bytes):
            sha = raw.put(key, c.url, r.body, r.content_type, c.ext)
            raw.log(key, partition, c.url, "ok", r.status, sha, c.fmt)
            return "ok"
        note = f"{c.fmt}: placeholder/invalid payload ({len(r.body)} B)"
    raw.log(key, partition, last_url, last_status, last_http, None, note)
    return last_status


def daterange(start: dt.date, end: dt.date):
    d = start
    while d <= end:
        yield d
        d += dt.timedelta(days=1)


# ----------------------------------------------------------------------------------------------
# Staging: write each day's CSV to data/staging/<fmt>/<date>__<sha>.csv for bulk loading by DuckDB.

def staging_dir(fmt: str) -> Path:
    p = data_dir() / "staging" / fmt
    p.mkdir(parents=True, exist_ok=True)
    return p


def fmt_from_url(url: str) -> str:
    u = url.lower()
    if "bhavcopy_nse_cm" in u:
        return "nse_udiff"
    if "bhavcopy_bse_cm" in u:
        return "bse_udiff"
    if "/historical/equities/" in u:
        return "nse_legacy"
    if "eq_isincode_" in u:
        return "bse_isin"
    return "bse_legacy"


def stage_all(raw: RawStore, exchange: str) -> dict[str, int]:
    """Materialise every successfully fetched day into staging CSVs (idempotent)."""
    key = SOURCE_KEY[exchange]
    rows = raw.db.execute(
        """SELECT f.partition_key, f.sha256, o.url FROM fetch_log f JOIN raw_object o USING (sha256)
           WHERE f.source_key = ? AND f.status = 'ok'""",
        (key,),
    ).fetchall()
    counts: dict[str, int] = {}
    seen: set[str] = set()
    for partition, sha, url in sorted(rows):
        if partition in seen:
            continue  # first successful payload per day; re-fetches with identical bytes share the sha
        seen.add(partition)
        fmt = fmt_from_url(url)
        out = staging_dir(fmt) / f"{partition}__{sha}.csv"
        if not out.exists():
            csv_bytes = extract_csv(raw.read(sha))
            assert csv_bytes is not None
            out.write_bytes(csv_bytes)
        counts[fmt] = counts.get(fmt, 0) + 1
    return counts
