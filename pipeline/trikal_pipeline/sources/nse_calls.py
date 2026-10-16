"""Earnings-call transcripts: raw downloads only. Companies file them with the exchange (LODR Reg 30 / 46); NSE lists them under the
announcement subject 'Analysts/Institutional Investor Meet/Con. Call Updates' with the text 'Transcript'. Same raw-zone pattern as the
results decks (nse_decks.py): list per symbol, then the newest PDFs, resumable and polite (ADR-006)."""

from __future__ import annotations

import datetime as dt
import json
from urllib.parse import quote

from trikal_pipeline.http import Fetcher
from trikal_pipeline.raw import RawStore
from trikal_pipeline.sources.nse_decks import MAX_PDF_BYTES, REFERER, announced

LIST_KEY = "nse.calls.list"
PDF_KEY = "nse.calls.pdf"
API = ("https://www.nseindia.com/api/corporate-announcements?index=equities&symbol={s}"
       "&subject=Analysts%2FInstitutional%20Investor%20Meet%2FCon.%20Call%20Updates")


def is_transcript(row: dict) -> bool:
    text = f"{row.get('attchmntText') or ''} {row.get('desc') or ''}".lower()
    f = (row.get("attchmntFile") or "").lower()
    return f.startswith("http") and f.endswith(".pdf") and ("transcript" in text or "transcript" in f)


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
        if r.status == 200 and isinstance(rows, list) and any(is_transcript(x) for x in rows):
            sha = raw.put(LIST_KEY, url, r.body, r.content_type, "json")
            raw.log(LIST_KEY, sym, url, "ok", r.status, sha)
            stats["ok"] = stats.get("ok", 0) + 1
        else:
            raw.log(LIST_KEY, sym, url, "not_found", r.status, None, "no transcripts listed")
            stats["empty"] = stats.get("empty", 0) + 1
    return stats


def call_rows(raw: RawStore, symbols: list[str] | None = None, since: dt.date = dt.date(2021, 4, 1)) -> list[tuple[str, dict]]:
    """(symbol, announcement row) of every listed transcript, newest first within a symbol."""
    want = set(symbols) if symbols else None
    out = []
    for sym, sha in raw.latest_ok(LIST_KEY).items():
        if want is not None and sym not in want:
            continue
        try:
            rows = json.loads(raw.read(sha))
        except Exception:
            continue
        seen = set()
        for row in rows if isinstance(rows, list) else []:
            t = announced(row)
            u = (row.get("attchmntFile") or "").strip()
            if is_transcript(row) and t and t.date() >= since and u not in seen:
                seen.add(u)
                out.append((sym, row))
    out.sort(key=lambda x: (x[0], -announced(x[1]).timestamp()))
    return out


def fetch_pdfs(fetcher: Fetcher, raw: RawStore, symbols: list[str], per_symbol: int = 8) -> dict[str, int]:
    done = raw.done_partitions(PDF_KEY)
    stats: dict[str, int] = {}
    taken: dict[str, int] = {}
    for sym, row in call_rows(raw, symbols):
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
