"""NSE Indices (niftyindices.com): constituent snapshots + the press-release archive (1998 ->).

There is no official membership-history file, so history is reconstructed from press releases
(DATA_SOURCES §2, RISKS R-4). See trikal_pipeline.index_history for the parser/reconstruction.
"""

from __future__ import annotations

import datetime as dt
import html
import re

import duckdb

from trikal_core.db import insert_many

from trikal_core.timeutil import utcnow
from trikal_pipeline.http import Fetcher
from trikal_pipeline.raw import RawStore

BASE = "https://www.niftyindices.com"
SNAPSHOT_FILES = {
    "NIFTY50": "/IndexConstituent/ind_nifty50list.csv",
    "NIFTY100": "/IndexConstituent/ind_nifty100list.csv",
    "NIFTY200": "/IndexConstituent/ind_nifty200list.csv",
    "NIFTY500": "/IndexConstituent/ind_nifty500list.csv",
    "NIFTYTOTALMARKET": "/IndexConstituent/ind_niftytotalmarket_list.csv",
    "NIFTYMICROCAP250": "/IndexConstituent/ind_niftymicrocap250_list.csv",
}

# Press releases about debt indices or product launches never change equity index membership.
_IRRELEVANT = re.compile(r"fixed income|g-sec|gilt|bharat bond|\bsdl\b|t-bill|treasury|debt|bond index|"
                         r"launch|webinar|award|anniversary|agreement|mou\b|licens", re.I)


def fetch_snapshots(fetcher: Fetcher, raw: RawStore) -> dict[str, str]:
    today = dt.date.today().isoformat()
    out = {}
    for code, path in SNAPSHOT_FILES.items():
        url = BASE + path
        r = fetcher.get(url)
        ok = r.status == 200 and r.body[:40].decode("latin-1").startswith("Company Name")
        key = f"nifty.snapshot.{code}"
        if ok:
            sha = raw.put(key, url, r.body, r.content_type, "csv")
            raw.log(key, today, url, "ok", r.status, sha)
            out[code] = sha
        else:
            raw.log(key, today, url, "error", r.status, None, "unexpected payload")
    return out


def load_snapshots(con: duckdb.DuckDBPyConnection, raw: RawStore) -> int:
    import csv
    import io

    n = 0
    for code in SNAPSHOT_FILES:
        for part, sha in raw.latest_ok(f"nifty.snapshot.{code}").items():
            snap = dt.date.fromisoformat(part)
            con.execute("DELETE FROM index_snapshot WHERE index_code = ? AND snapshot_date = ?", [code, snap])
            rows = list(csv.DictReader(io.StringIO(raw.read(sha).decode("utf-8-sig"))))
            insert_many(con, 
                "INSERT INTO index_snapshot VALUES (?,?,?,?,?,?,?,?)",
                [(code, snap, r["Symbol"].strip().upper(), r["ISIN Code"].strip(), r["Company Name"].strip(),
                  r["Industry"].strip(), utcnow(), sha) for r in rows],
            )
            n += len(rows)
    return n


def fetch_press_index(fetcher: Fetcher, raw: RawStore) -> list[tuple[dt.date, str, str]]:
    url = BASE + "/media"
    r = fetcher.get(url)
    sha = raw.put("nifty.media", url, r.body, r.content_type, "html")
    raw.log("nifty.media", dt.date.today().isoformat(), url, "ok", r.status, sha)
    return parse_press_index(r.body.decode("utf-8", errors="replace"))


def parse_press_index(page: str) -> list[tuple[dt.date, str, str]]:
    out = []
    for body in re.findall(r"<li data-publishdate=\"[^\"]*\">(.*?)</li>", page, re.S):
        a = re.search(r'href="([^"]*Press_Release[^"]*)"[^>]*>(.*?)</a>', body, re.S)
        d = re.search(r"([A-Z][a-z]+ \d{1,2}, \d{4})", re.sub("<[^>]+>", " ", body))
        if not (a and d):
            continue
        title = html.unescape(re.sub(r"\s+", " ", re.sub("<[^>]+>", "", a.group(2)))).strip()
        out.append((dt.datetime.strptime(d.group(1), "%B %d, %Y").date(), a.group(1).strip(), title))
    return out


def pdf_url(path: str) -> str:
    """Absolute URL; repairs malformed links seen on the media page ('..._1', '...2008pdf')."""
    url = BASE + path if path.startswith("/") else path
    if url.lower().endswith("pdf") and not url.lower().endswith(".pdf"):
        url = url[:-3] + ".pdf"
    elif not url.lower().endswith(".pdf"):
        url += ".pdf"
    return url


def is_relevant(title: str) -> bool:
    return not _IRRELEVANT.search(title)


def fetch_press_pdfs(fetcher: Fetcher, raw: RawStore) -> dict[str, int]:
    items = fetch_press_index(fetcher, raw)
    done = raw.done_partitions("nifty.press")
    stats = {"ok": 0, "skipped_irrelevant": 0, "already": 0, "error": 0}
    for published, path, title in items:
        url = pdf_url(path)
        if not is_relevant(title):
            stats["skipped_irrelevant"] += 1
            continue
        if url in done:
            stats["already"] += 1
            continue
        try:
            r = fetcher.get(url)
        except Exception as exc:
            raw.log("nifty.press", url, url, "error", None, None, str(exc)[:200])
            stats["error"] += 1
            continue
        if r.status == 200 and r.body.startswith(b"%PDF"):
            sha = raw.put("nifty.press", url, r.body, r.content_type, "pdf")
            raw.log("nifty.press", url, url, "ok", r.status, sha)
            stats["ok"] += 1
        else:
            # the site answers its HTML 'page not found' with status 200
            missing = r.status == 404 or r.body.lstrip()[:15].lower().startswith(b"<!doctype")
            raw.log("nifty.press", url, url, "not_found" if missing else "error", r.status, None,
                    "site returned an HTML page instead of the PDF" if missing else None)
            stats["not_found" if missing else "error"] = stats.get("not_found" if missing else "error", 0) + 1
    return stats


def load_press_index(con: duckdb.DuckDBPyConnection, raw: RawStore) -> int:
    """Rebuild `press_release` from the latest raw copy of the media page + the PDF fetch log."""
    pages = raw.latest_ok("nifty.media")
    if not pages:
        return 0
    items = parse_press_index(raw.read(pages[max(pages)]).decode("utf-8", errors="replace"))
    pdfs = raw.latest_ok("nifty.press")
    con.execute("DELETE FROM press_release")
    rows = {}
    for published, path, title in items:
        url = pdf_url(path)
        sha = pdfs.get(url)
        status = "irrelevant_title" if not is_relevant(title) else ("fetched" if sha else "missing")
        rows[url] = (url, published, title, sha, status)
    insert_many(con, "INSERT INTO press_release VALUES (?, ?, ?, ?, ?)", list(rows.values()))
    return len(rows)
