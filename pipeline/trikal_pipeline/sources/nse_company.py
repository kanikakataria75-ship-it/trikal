"""M2 raw downloads for the pilot universe: per-company filing lists and XBRL result documents.

Fetch-only (raw zone). Parsing into canonical tables is M2 work. Everything is resumable: a
(source, partition) that already has an 'ok' answer is skipped, so the job can be stopped and restarted.
Website JSON endpoints are used politely (ADR-006): ~1.5 s between calls to www.nseindia.com.
"""

from __future__ import annotations

import datetime as dt
import json
import sys
import time
from urllib.parse import quote

from trikal_pipeline.http import Fetcher
from trikal_pipeline.raw import RawStore

API = "https://www.nseindia.com/api/"
LISTS = {
    "nse.results.quarterly": "corporates-financial-results?index=equities&period=Quarterly&symbol={s}",
    "nse.results.annual": "corporates-financial-results?index=equities&period=Annual&symbol={s}",
    # SEBI 'Integrated Filing' (from the Dec-2024 quarter): results are no longer in the endpoint above
    "nse.results.integrated": "integrated-filing-results?index=equities&symbol={s}&size=500",
    "nse.shareholding": "corporate-share-holdings-master?index=equities&symbol={s}",
    "nse.pledge": "corporate-pledgedata?index=equities&symbol={s}",
    "nse.annual_reports": "annual-reports?index=equities&symbol={s}",
}
REFERER = "https://www.nseindia.com/companies-listing/corporate-filings-financial-results"


def _log(msg: str) -> None:
    print(f"{dt.datetime.now():%H:%M:%S} {msg}", flush=True)


def fetch_lists(symbols: list[str], fetcher: Fetcher, raw: RawStore) -> dict[str, int]:
    stats: dict[str, int] = {}
    done = {k: raw.done_partitions(k) for k in LISTS}
    for i, sym in enumerate(symbols, 1):
        for key, path in LISTS.items():
            if sym in done[key]:
                stats["skipped"] = stats.get("skipped", 0) + 1
                continue
            url = API + path.format(s=quote(sym, safe=""))
            try:
                r = fetcher.get(url, referer=REFERER)
                body = r.body.strip()
                json.loads(body or b"null")
            except Exception as exc:
                raw.log(key, sym, url, "error", None, None, f"{type(exc).__name__}: {exc}"[:300])
                stats["error"] = stats.get("error", 0) + 1
                continue
            empty = body in (b"", b"[]", b"{}", b"null")
            if r.status == 200 and not empty:
                sha = raw.put(key, url, r.body, r.content_type, "json")
                raw.log(key, sym, url, "ok", r.status, sha)
                stats["ok"] = stats.get("ok", 0) + 1
            else:
                # empty answer is a definitive "no data for this symbol" (common for delisted names)
                raw.log(key, sym, url, "not_found" if r.status in (200, 404) else "error", r.status, None,
                        "empty response" if empty else None)
                stats["empty"] = stats.get("empty", 0) + 1
        if i % 25 == 0:
            _log(f"lists {i}/{len(symbols)} {stats}")
    return stats


def xbrl_urls(raw: RawStore, since: dt.date) -> list[tuple[str, str]]:
    """(published date, XBRL url) from every fetched results list, newest first."""
    out = {}
    for key in ("nse.results.quarterly", "nse.results.annual", "nse.results.integrated"):
        for _, sha in raw.latest_ok(key).items():
            try:
                rows = json.loads(raw.read(sha))
            except Exception:
                continue
            if isinstance(rows, dict):
                rows = rows.get("data") or []
            for row in rows if isinstance(rows, list) else []:
                url = (row.get("xbrl") or "").strip()
                if not url.lower().startswith("http") or not url.lower().endswith(".xml"):
                    continue
                period_end = row.get("toDate") or row.get("qe_Date") or ""
                try:
                    to = dt.datetime.strptime(period_end.title(), "%d-%b-%Y").date()
                except ValueError:
                    continue
                if to >= since:
                    out[url] = to.isoformat()
    return sorted(((d, u) for u, d in out.items()), reverse=True)


def fetch_xbrl(fetcher: Fetcher, raw: RawStore, since: dt.date) -> dict[str, int]:
    key = "nse.xbrl.results"
    done = raw.done_partitions(key)
    todo = [(d, u) for d, u in xbrl_urls(raw, since) if u not in done]
    _log(f"xbrl: {len(todo)} documents to fetch (period end >= {since})")
    stats: dict[str, int] = {}
    for i, (_, url) in enumerate(todo, 1):
        try:
            r = fetcher.get(url)
        except Exception as exc:
            raw.log(key, url, url, "error", None, None, str(exc)[:300])
            stats["error"] = stats.get("error", 0) + 1
            continue
        if r.status == 200 and b"<" in r.body[:200] and b"xbrl" in r.body[:4000].lower():
            sha = raw.put(key, url, r.body, r.content_type, "xml")
            raw.log(key, url, url, "ok", r.status, sha)
            stats["ok"] = stats.get("ok", 0) + 1
        else:
            raw.log(key, url, url, "not_found" if r.status == 404 else "error", r.status, None)
            stats["missing"] = stats.get("missing", 0) + 1
        if i % 200 == 0:
            _log(f"xbrl {i}/{len(todo)} {stats}")
    return stats


def run_overnight(symbols_file: str, since: str = "2011-04-01") -> None:
    symbols = [s.strip() for s in open(symbols_file, encoding="utf-8") if s.strip()]
    raw, fetcher = RawStore(), Fetcher()
    t0 = time.monotonic()
    _log(f"start: {len(symbols)} symbols")
    _log(f"lists done: {fetch_lists(symbols, fetcher, raw)}")
    _log(f"xbrl done: {fetch_xbrl(fetcher, raw, dt.date.fromisoformat(since))}")
    _log(f"finished in {(time.monotonic() - t0) / 3600:.1f} h")
    fetcher.close()


if __name__ == "__main__":
    run_overnight(*sys.argv[1:])
