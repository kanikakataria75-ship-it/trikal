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


def result_docs(raw: RawStore, since: dt.date) -> list[tuple[str, str, str]]:
    """(period end, url, kind) for every result document listed, newest period first.

    kind 'xbrl': Ind-AS / Integrated-Filing XML (2017 onward). kind 'html': the older 'Financial Results
    Details' page that NSE hosts for filings before XBRL became mandatory (2008 - 2017)."""
    out: dict[str, tuple[str, str]] = {}
    for key in ("nse.results.quarterly", "nse.results.annual", "nse.results.integrated"):
        for _, sha in raw.latest_ok(key).items():
            try:
                rows = json.loads(raw.read(sha))
            except Exception:
                continue
            if isinstance(rows, dict):
                rows = rows.get("data") or []
            for row in rows if isinstance(rows, list) else []:
                if row.get("type") and "financials" not in row["type"].lower():
                    continue  # SEBI Integrated Filing also lists governance/compliance XBRL: not statements
                period_end = row.get("toDate") or row.get("qe_Date") or ""
                try:
                    to = dt.datetime.strptime(period_end.title(), "%d-%b-%Y").date()
                except ValueError:
                    continue
                if to < since:
                    continue
                x = (row.get("xbrl") or "").strip()
                h = (row.get("resultDetailedDataLink") or "").strip()
                if x.lower().startswith("http") and x.lower().endswith(".xml"):
                    out[x] = (to.isoformat(), "xbrl")
                elif h.lower().startswith("http"):
                    out[h] = (to.isoformat(), "html")
    return sorted(((d, u, k) for u, (d, k) in out.items()), reverse=True)


def shp_docs(raw: RawStore) -> list[tuple[str, str, str]]:
    """(period end ISO, url, 'shp') for every shareholding-pattern XBRL listed, newest first."""
    out = {}
    for _, sha in raw.latest_ok("nse.shareholding").items():
        try:
            rows = json.loads(raw.read(sha))
        except Exception:
            continue
        for row in rows if isinstance(rows, list) else []:
            u = (row.get("xbrl") or "").strip()
            if u.lower().startswith("http") and u.lower().endswith(".xml"):
                try:
                    out[u] = dt.datetime.strptime(row["date"].title(), "%d-%b-%Y").date().isoformat()
                except (KeyError, ValueError):
                    continue
    return sorted(((d, u, "shp") for u, d in out.items()), reverse=True)


def fetch_docs(fetcher: Fetcher, raw: RawStore, since: dt.date, kind: str) -> dict[str, int]:
    key = {"xbrl": "nse.xbrl.results", "html": "nse.results.html", "shp": "nse.xbrl.shp"}[kind]
    ext = {"xbrl": "xml", "html": "html", "shp": "xml"}[kind]
    done = raw.done_partitions(key)
    docs = shp_docs(raw) if kind == "shp" else result_docs(raw, since)
    todo = [(d, u) for d, u, k in docs if k == kind and u not in done]
    _log(f"{kind}: {len(todo)} documents to fetch (period end >= {since})")
    stats: dict[str, int] = {}
    for i, (_, url) in enumerate(todo, 1):
        try:
            r = fetcher.get(url)
        except Exception as exc:
            raw.log(key, url, url, "error", None, None, str(exc)[:300])
            stats["error"] = stats.get("error", 0) + 1
            continue
        head = r.body[:6000].lower()
        valid = r.status == 200 and ((kind in ("xbrl", "shp") and b"<" in head[:200] and b"xbrl" in head)
                                     or (kind == "html" and b"financial results" in head))
        if valid:
            sha = raw.put(key, url, r.body, r.content_type, ext)
            raw.log(key, url, url, "ok", r.status, sha)
            stats["ok"] = stats.get("ok", 0) + 1
        else:
            raw.log(key, url, url, "not_found" if r.status in (200, 404) else "error", r.status, None,
                    "unexpected payload" if r.status == 200 else None)
            stats["missing"] = stats.get("missing", 0) + 1
        if i % 200 == 0:
            _log(f"{kind} {i}/{len(todo)} {stats}")
    return stats


def keep_system_awake() -> None:
    """Ask Windows not to idle-sleep while this process runs (per-process request, like a video player;
    no system setting is changed and it ends with the process). Closing the lid still sleeps."""
    if sys.platform == "win32":
        import ctypes

        ES_CONTINUOUS, ES_SYSTEM_REQUIRED = 0x80000000, 0x00000001
        ctypes.windll.kernel32.SetThreadExecutionState(ES_CONTINUOUS | ES_SYSTEM_REQUIRED)


def run_overnight(symbols_file: str, since: str = "2011-04-01") -> None:
    keep_system_awake()
    symbols = [s.strip() for s in open(symbols_file, encoding="utf-8") if s.strip()]
    raw, fetcher = RawStore(), Fetcher()
    t0 = time.monotonic()
    _log(f"start: {len(symbols)} symbols (keep-awake requested)")
    _log(f"lists done: {fetch_lists(symbols, fetcher, raw)}")
    _log(f"xbrl done: {fetch_docs(fetcher, raw, dt.date.fromisoformat(since), 'xbrl')}")
    _refresh()
    _log(f"shp done: {fetch_docs(fetcher, raw, dt.date.fromisoformat(since), 'shp')}")
    _log(f"html done: {fetch_docs(fetcher, raw, dt.date.fromisoformat(since), 'html')}")
    _refresh()
    _log(f"finished in {(time.monotonic() - t0) / 3600:.1f} h")
    fetcher.close()


def _refresh() -> None:
    """Parse what has arrived and rewrite the coverage report (same as `trikal refresh-m2`)."""
    import subprocess

    log = data_dir_logs() / "m2_refresh.log"
    with open(log, "a", encoding="utf-8") as fh:
        fh.write(f"\n=== refresh {dt.datetime.now():%Y-%m-%d %H:%M:%S} ===\n")
        fh.flush()
        r = subprocess.run([sys.executable, "-c", "from trikal_pipeline.cli import app; app(['refresh-m2'])"],
                           stdout=fh, stderr=subprocess.STDOUT)
    _log(f"refresh-m2 exit code {r.returncode} (details: data/logs/m2_refresh.log)")


def data_dir_logs():
    from trikal_core.db import data_dir

    p = data_dir() / "logs"
    p.mkdir(exist_ok=True)
    return p


if __name__ == "__main__":
    run_overnight(*sys.argv[1:])
