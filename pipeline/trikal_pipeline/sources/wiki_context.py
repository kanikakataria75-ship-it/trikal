"""World and India context for a day, from Wikipedia (CC BY-SA 4.0) — the Time Machine's "that day" news layer.

Sources (DATA_SOURCES §11):
  wiki.day     Portal:Current_events/<YYYY>_<Month>_<D>   daily pages, 2003 onward; every item ends with the
                                                           original outlet as an external link, e.g. "(Reuters)"
  wiki.year    <YYYY>            world events by date (used where no daily page exists, i.e. before 2003)
  wiki.india   <YYYY>_in_India   Indian events by date, every year

What this is and is not:
  * Editorial summaries written by Wikipedia editors, often after the fact. They are CONTEXT shown beside the
    market of a day, labelled with source and licence. They are never an input to any metric, score or backtest,
    and they carry no known_at: the UI shows only items dated on or before the session it is showing.
  * Fetched as raw wikitext from /wiki/<title>?action=raw (robots.txt allows /wiki/, not /w/ or /api/), stored in
    the raw zone like every other source, parsed into `context_event` with page and raw sha for lineage.
"""

from __future__ import annotations

import datetime as dt
import re
from urllib.parse import quote

from trikal_core.db import insert_many
from trikal_core.timeutil import utcnow
from trikal_pipeline.http import Fetcher
from trikal_pipeline.raw import RawStore

BASE = "https://en.wikipedia.org/wiki/"
UA = "TRIKAL-research/0.3 (personal, non-commercial research terminal; contact: kanikakataria75@gmail.com)"
DAILY_FROM = dt.date(2003, 1, 1)
LICENCE = "CC BY-SA 4.0 · Wikipedia contributors"
MONTHS = ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"]
_MON = {m.lower(): i + 1 for i, m in enumerate(MONTHS)}


def day_title(d: dt.date) -> str:
    return f"Portal:Current_events/{d.year}_{MONTHS[d.month - 1]}_{d.day}"


def _url(title: str) -> str:
    return BASE + quote(title, safe=":/_") + "?action=raw"


def _get(fetcher: Fetcher, raw: RawStore, source_key: str, partition: str, title: str) -> str:
    url = _url(title)
    try:
        r = fetcher.get(url, headers={"User-Agent": UA})
    except Exception as e:  # network trouble: logged, retried on the next run
        raw.log(source_key, partition, url, "error", None, None, f"{type(e).__name__}: {e}"[:300])
        return "error"
    if r.status == 404 or not r.body.strip():
        raw.log(source_key, partition, url, "not_found", r.status, None)
        return "not_found"
    if r.status != 200:
        raw.log(source_key, partition, url, "error", r.status, None)
        return "error"
    sha = raw.put(source_key, url, r.body, r.content_type, "wikitext")
    raw.log(source_key, partition, url, "ok", r.status, sha)
    return "ok"


def fetch(fetcher: Fetcher, raw: RawStore, days: list[dt.date], years: list[int], refetch: bool = False) -> dict[str, int]:
    out: dict[str, int] = {}
    done = set() if refetch else raw.done_partitions("wiki.day") | {f"y{p}" for p in raw.done_partitions("wiki.year")} \
        | {f"i{p}" for p in raw.done_partitions("wiki.india")}
    for y in years:
        for key, title, tag in (("wiki.year", str(y), "y"), ("wiki.india", f"{y}_in_India", "i")):
            if f"{tag}{y}" in done:
                continue
            s = _get(fetcher, raw, key, str(y), title)
            out[f"{key}:{s}"] = out.get(f"{key}:{s}", 0) + 1
    for d in days:
        if d < DAILY_FROM or d.isoformat() in done:
            continue
        s = _get(fetcher, raw, "wiki.day", d.isoformat(), day_title(d))
        out[f"wiki.day:{s}"] = out.get(f"wiki.day:{s}", 0) + 1
    return out


# ---------------------------------------------------------------------------------------------- wikitext → text
_EXT = re.compile(r"\[(https?://[^\s\]]+)\s+([^\]]*)\]")


def _strip_templates(w: str) -> str:
    prev = None
    while prev != w:
        prev, w = w, re.sub(r"\{\{[^{}]*\}\}", "", w)
    return w


def clean(w: str) -> tuple[str, list[tuple[str, str]]]:
    """Wikitext line -> (plain text, [(source name, url)])."""
    w = re.sub(r"<ref[^>/]*/>", "", w)
    w = re.sub(r"<ref[^>]*>.*?</ref>", "", w, flags=re.S)
    w = re.sub(r"<!--.*?-->", "", w, flags=re.S)
    w = _strip_templates(w)
    sources = [(name.strip(" ()'\""), url) for url, name in _EXT.findall(w)]
    w = _EXT.sub("", w)
    w = re.sub(r"\[\[(?:[^|\]]*\|)?([^\]]+)\]\]", r"\1", w)        # [[target|label]] -> label
    w = re.sub(r"'{2,}", "", w)
    w = re.sub(r"<[^>]+>", "", w)
    w = w.replace("&ndash;", "–").replace("&mdash;", "—").replace("&nbsp;", " ").replace("&amp;", "&")
    w = re.sub(r"\s+", " ", w).strip(" -–—:")
    return w, sources


def parse_day(wikitext: str) -> list[dict]:
    """Daily portal page: ';Category' headings; nested bullets where the leaf (with a source link) is the item
    and its parents are the story it belongs to."""
    items: list[dict] = []
    category = None
    stack: list[str] = []
    for line in wikitext.splitlines():
        line = line.rstrip()
        if line.startswith(";"):
            category = clean(line[1:])[0] or None
            stack = []
            continue
        m = re.match(r"^(\*+)\s*(.*)$", line)
        if not m:
            continue
        depth, body = len(m.group(1)), m.group(2)
        text, sources = clean(body)
        stack = stack[: depth - 1] + [text]
        if sources and len(text) > 12:
            items.append({"category": category, "story": " › ".join(s for s in stack[:-1] if s) or None,
                          "text": text, "source_name": sources[0][0], "source_url": sources[0][1]})
    return items


def _section(wikitext: str, name: str) -> str:
    m = re.search(rf"^==\s*{name}\s*==\s*$", wikitext, flags=re.M)
    if not m:
        return ""
    rest = wikitext[m.end():]
    n = re.search(r"^==[^=].*?==\s*$", rest, flags=re.M)
    return rest[: n.start()] if n else rest


_DATE_MD = re.compile(r"^\[?\[?(" + "|".join(MONTHS) + r")\s+(\d{1,2})\]?\]?")   # "[[May 11]]" / "May 11"
_DATE_DM = re.compile(r"^\[?\[?(\d{1,2})\s+(" + "|".join(MONTHS) + r")\]?\]?")   # "11 May"


def _lead_date(s: str, year: int) -> tuple[dt.date | None, str]:
    s = s.strip()
    m = _DATE_MD.match(s) or _DATE_DM.match(s)
    if not m:
        return None, s
    a, b = m.group(1), m.group(2)
    mon, day = (_MON[a.lower()], int(b)) if a[0].isalpha() else (_MON[b.lower()], int(a))
    rest = s[m.end():]
    rest = re.sub(r"^\s*(?:[–—-]|&ndash;|&mdash;)\s*\[?\[?[^\]–—]*?\]?\]?\s*(?=[–—]|&ndash;)", "", rest)  # date ranges
    rest = re.sub(r"^\s*(?:[–—:-]|&ndash;|&mdash;)\s*", "", rest)
    try:
        return dt.date(year, mon, day), rest
    except ValueError:
        return None, s


def parse_year(wikitext: str, year: int) -> list[dict]:
    """Year articles ('1998', '1998 in India'): the Events section, '* <date> – text' or '* <date>' + '** text'."""
    events = _section(wikitext, "Events")
    items: list[dict] = []
    current: dt.date | None = None
    for line in events.splitlines():
        m = re.match(r"^(\*+)\s*(.*)$", line)
        if not m:
            if line.startswith("="):
                current = None
            continue
        depth, body = len(m.group(1)), m.group(2)
        d, rest = _lead_date(body, year)
        if depth == 1:
            current = d
            if d and rest.strip():
                text, sources = clean(rest)
                if len(text) > 12:
                    items.append({"day": d, "text": text, "source_name": sources[0][0] if sources else None,
                                  "source_url": sources[0][1] if sources else None})
        elif current or d:
            text, sources = clean(rest if d else body)
            if len(text) > 12:
                items.append({"day": d or current, "text": text, "source_name": sources[0][0] if sources else None,
                              "source_url": sources[0][1] if sources else None})
    return items


def load(con, raw: RawStore) -> dict[str, int]:
    """Rebuild context_event from the latest successful fetch of every page."""
    rows = []
    now = utcnow()
    for key, scope in (("wiki.day", "world"), ("wiki.year", "world"), ("wiki.india", "india")):
        for part, sha in raw.latest_ok(key).items():
            text = raw.read(sha).decode("utf-8", "replace")
            if key == "wiki.day":
                d = dt.date.fromisoformat(part)
                for it in parse_day(text):
                    rows.append((d, scope, it["category"], it["story"], it["text"], it["source_name"], it["source_url"],
                                 day_title(d), sha, now))
            else:
                title = part if key == "wiki.year" else f"{part}_in_India"
                for it in parse_year(text, int(part)):
                    # world events come from daily pages from 2003 on; the year article fills the years before
                    if key == "wiki.year" and it["day"] >= DAILY_FROM:
                        continue
                    rows.append((it["day"], scope, None, None, it["text"], it["source_name"], it["source_url"], title, sha, now))
    con.execute("BEGIN")
    con.execute("DELETE FROM context_event")
    insert_many(con, "INSERT INTO context_event VALUES (?,?,?,?,?,?,?,?,?,?)", rows)
    con.execute("COMMIT")
    out: dict[str, int] = {}
    for r in rows:
        out[r[1]] = out.get(r[1], 0) + 1
    return out
