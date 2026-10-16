"""Investor presentations (the results decks companies file with the exchange): raw downloads only.

Source: the exchange's corporate-announcements API filtered by subject 'Investor Presentation' (free, public). The attachment PDF of each
announcement is stored content-addressed in the raw zone. Parsing into numbers is deck_metrics.py. Resumable and polite (ADR-006)."""

from __future__ import annotations

import datetime as dt
import json
from urllib.parse import quote

from trikal_pipeline.http import Fetcher
from trikal_pipeline.raw import RawStore

LIST_KEY = "nse.decks.list"
PDF_KEY = "nse.decks.pdf"
API = "https://www.nseindia.com/api/corporate-announcements?index=equities&symbol={s}&subject=Investor%20Presentation"
REFERER = "https://www.nseindia.com/companies-listing/corporate-filings-announcements"
MAX_PDF_BYTES = 40_000_000


def _log(msg: str) -> None:
    print(f"{dt.datetime.now():%H:%M:%S} {msg}", flush=True)


def announced(row: dict) -> dt.datetime | None:
    """Broadcast time of an announcement row (IST), None when the exchange gave none."""
    from trikal_core.timeutil import IST

    for k in ("exchdisstime", "an_dt", "sort_date"):
        v = (row.get(k) or "").strip()
        for fmt in ("%d-%b-%Y %H:%M:%S", "%Y-%m-%d %H:%M:%S"):
            try:
                return dt.datetime.strptime(v.title() if "-" in v and v[:2].isdigit() else v, fmt).replace(tzinfo=IST)
            except ValueError:
                continue
    return None


def fetch_lists(symbols: list[str], fetcher: Fetcher, raw: RawStore) -> dict[str, int]:
    done = raw.done_partitions(LIST_KEY)
    stats: dict[str, int] = {}
    for sym in symbols:
        if sym in done:
            stats["skipped"] = stats.get("skipped", 0) + 1
            continue
        url = API.format(s=quote(sym, safe=""))
        try:
            r = fetcher.get(url, referer=REFERER)
            rows = json.loads(r.body or b"null")
        except Exception as exc:
            raw.log(LIST_KEY, sym, url, "error", None, None, f"{type(exc).__name__}: {exc}"[:300])
            stats["error"] = stats.get("error", 0) + 1
            continue
        if r.status == 200 and isinstance(rows, list) and rows:
            sha = raw.put(LIST_KEY, url, r.body, r.content_type, "json")
            raw.log(LIST_KEY, sym, url, "ok", r.status, sha)
            stats["ok"] = stats.get("ok", 0) + 1
        else:
            raw.log(LIST_KEY, sym, url, "not_found", r.status, None, "no presentations")
            stats["empty"] = stats.get("empty", 0) + 1
    return stats


def deck_rows(raw: RawStore, symbols: list[str] | None = None, since: dt.date = dt.date(2019, 4, 1)) -> list[tuple[str, dict]]:
    """(symbol, announcement row) for every listed presentation with an attachment, newest first within each symbol."""
    want = set(symbols) if symbols else None
    out = []
    for sym, sha in raw.latest_ok(LIST_KEY).items():
        if want is not None and sym not in want:
            continue
        try:
            rows = json.loads(raw.read(sha))
        except Exception:
            continue
        for row in rows if isinstance(rows, list) else []:
            f = (row.get("attchmntFile") or "").strip()
            t = announced(row)
            if f.lower().startswith("http") and f.lower().endswith(".pdf") and t and t.date() >= since:
                out.append((sym, row))
    out.sort(key=lambda x: (x[0], -(announced(x[1]).timestamp())))
    return out


def fetch_pdfs(fetcher: Fetcher, raw: RawStore, symbols: list[str], per_symbol: int = 12) -> dict[str, int]:
    done = raw.done_partitions(PDF_KEY)
    stats: dict[str, int] = {}
    taken: dict[str, int] = {}
    for sym, row in deck_rows(raw, symbols):
        if taken.get(sym, 0) >= per_symbol:
            continue
        taken[sym] = taken.get(sym, 0) + 1
        url = row["attchmntFile"].strip()
        if url in done:
            stats["skipped"] = stats.get("skipped", 0) + 1
            continue
        try:
            r = fetcher.get(url, referer="https://www.nseindia.com/")
        except Exception as exc:
            raw.log(PDF_KEY, url, url, "error", None, None, f"{type(exc).__name__}: {exc}"[:300])
            stats["error"] = stats.get("error", 0) + 1
            continue
        if r.status == 200 and r.body[:4] == b"%PDF" and len(r.body) <= MAX_PDF_BYTES:
            sha = raw.put(PDF_KEY, url, r.body, r.content_type, "pdf")
            raw.log(PDF_KEY, url, url, "ok", r.status, sha)
            stats["ok"] = stats.get("ok", 0) + 1
        else:
            raw.log(PDF_KEY, url, url, "not_found" if r.status == 404 else "error", r.status, None, f"{len(r.body)} bytes")
            stats["bad"] = stats.get("bad", 0) + 1
    return stats
