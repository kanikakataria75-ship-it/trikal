"""Reconstruct point-in-time index membership from NSE Indices press releases (RISKS R-4).

1. text      every relevant press-release PDF -> plain text (cached in staging by PDF sha)
2. events    find the sections about the target index; read "excluded"/"included" lists -> index_event
3. rebuild   walk backwards from the official current snapshot, undoing each change at its effective
             date; check the member count against the index's fixed size at every step
"""

from __future__ import annotations

import datetime as dt
import re
from pathlib import Path

from trikal_core.db import data_dir
from trikal_pipeline.raw import RawStore


def text_dir() -> Path:
    p = data_dir() / "staging" / "press_text"
    p.mkdir(parents=True, exist_ok=True)
    return p


def pdf_text(raw: RawStore, sha: str) -> str:
    """Layout-preserving text of a press-release PDF, cached by sha."""
    out = text_dir() / f"{sha}.txt"
    if out.exists():
        return out.read_text(encoding="utf-8")
    import io
    import logging

    import pdfplumber

    logging.getLogger("pdfminer").setLevel(logging.ERROR)
    parts = []
    try:
        with pdfplumber.open(io.BytesIO(raw.read(sha))) as pdf:
            for page in pdf.pages:
                parts.append(page.extract_text() or "")
    except Exception as exc:  # corrupt / encrypted PDFs are recorded, not skipped silently
        parts = [f"__EXTRACT_ERROR__ {type(exc).__name__}: {exc}"]
    text = "\n".join(parts)
    out.write_text(text, encoding="utf-8")
    return text


_DATE_PAT = r"([A-Z][a-z]+\.?\s+\d{1,2},?\s+\d{4})"


def parse_date(s: str) -> dt.date | None:
    s = re.sub(r"\s+", " ", s.replace(".", "").replace(",", ", ")).replace(" ,", ",").strip()
    s = re.sub(r",\s*", ", ", s)
    for f in ("%B %d, %Y", "%b %d, %Y", "%B %d %Y", "%b %d %Y"):
        try:
            return dt.datetime.strptime(s, f).date()
        except ValueError:
            continue
    return None


def effective_date(title: str, text: str) -> dt.date | None:
    """'w.e.f. <date>' in the title, else 'effective from <date>' in the body."""
    for src, pat in ((title, r"w\.?\s*e\.?\s*f\.?\s*" + _DATE_PAT),
                     (text, r"effective\s+(?:from|on|date)?\s*:?\s*" + _DATE_PAT),
                     (text, r"w\.?\s*e\.?\s*f\.?\s*" + _DATE_PAT)):
        m = re.search(pat, src or "", re.I)
        if m and (d := parse_date(m.group(1))):
            return d
    return None


# ----------------------------------------------------------------------------------------------
# 2. Event parsing

# Names the broad 500-stock index has had: Crisil 500 (to 1998) -> S&P CNX 500 -> CNX 500 (2013)
# -> NIFTY 500 (2015). Variants such as "Nifty500 Multicap 50:25:25" or "Nifty 500 Equal Weight"
# are different indices and must not match.
INDEX_ALIASES = {
    "NIFTY500": {"nifty 500", "cnx 500", "s&p cnx 500", "crisil 500", "crisil 500 equity",
                 "s&p cnx 500 equity", "nifty500"},
}

# Web-page chrome that pre-2010 releases (saved from nseindia.com) interleave with content lines.
_CHROME = re.compile(
    r"^(?:-{3,}|iisl(?: press| - publications)?|products? ?&?|services|iisl indices|index concepts|statistics|"
    r"index funds|releases|faqs|licensing|contact us|press release|equities|futidx|page \d+|"
    r"national stock exchange of india ltd\.?|http\S+.*)\s*", re.I)

_HEADING = re.compile(r"^\s*(?:\(?\s*(?:\d{1,2}|[a-z]|[ivx]{1,4})\s*[\)\.]\s*)(.{3,80}?)\s*:?\s*$", re.I)
_ROW = re.compile(r"^\s*(\d{1,3})[\.\)]?\s+(\S.*?)\s*$")
# "...being excluded from S&P CNX 500 w.e.f. ..." names the index the list belongs to. A mention after
# "on account of" ("excluded on account of inclusion in Nifty 500") is a reason, not the list's index.
_INLINE_INDEX = re.compile(r"(?<!account of )(?:excluded from|included in)\s+(?:the\s+)?"
                           r"((?:s&p\s+)?(?:cnx|nifty|crisil)\s*[\w&\-]*(?:\s+[\w&\-]+){0,3}?)\s*(?:index)?"
                           r"(?:\s+w\.?e\.?f|\s+as\b|\s*:|\s*$|\s+on\b|\s+from\b)", re.I)
# A list-opening sentence. Company names containing "Inclusion" (Bharat Financial Inclusion) must not match.
_ACTION = re.compile(r"\b(?:being|are|is|be)\s+(excluded|included)\b|^(exclusions?|inclusions?)\s*:?\s*$", re.I)


def norm_index_name(s: str) -> str:
    s = s.lower().replace("–", "-")
    s = re.sub(r"\bindex\b|\bindices\b", " ", s)
    s = re.sub(r"[^a-z0-9& ]+", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def index_code_for(name: str) -> str | None:
    n = norm_index_name(name)
    for code, aliases in INDEX_ALIASES.items():
        if n in aliases:
            return code
    return None


def _clean_lines(text: str) -> list[str]:
    out = []
    for line in text.splitlines():
        line = line.replace(" ", " ").strip()
        # strip leading chrome repeatedly ("----- IISL Press ...")
        prev = None
        while prev != line:
            prev = line
            line = _CHROME.sub("", line).strip()
        if line:
            out.append(line)
    return out


def parse_events(title: str, text: str, published: dt.date) -> list[dict]:
    """Return [{index_code, action, rank, raw, effective_date, section}] for target indices."""
    pr_eff = effective_date(title, text)
    events: list[dict] = []
    cur_index: str | None = None      # code of the section we are in (None = some other index)
    cur_section = ""
    action: str | None = None
    has_symbol_col = False
    sentence_eff: dt.date | None = None
    for line in _clean_lines(text):
        low = line.lower()
        # Section heading such as "(4) S&P CNX 500 Index" or "1) NIFTY 500".
        m = _HEADING.match(line)
        if m and not _ROW.match(line.replace(m.group(0), "", 1) or "x") and re.search(r"cnx|nifty|crisil|index", m.group(1), re.I) \
                and not re.search(r"exclu|inclu", low):
            cur_section = m.group(1)
            cur_index = index_code_for(m.group(1))
            action, sentence_eff = None, None
            continue
        if re.search(r"no (?:inclusion|exclusion|change)", low):
            action = None
            continue
        if re.match(r"^s(?:r|l)\.?\s*no", low) or low.startswith("sr.") or "company name" in low:
            has_symbol_col = "symbol" in low
            continue
        mr = _ROW.match(line)
        ma = _ACTION.search(line)
        if ma and not (mr and action):
            word = (ma.group(1) or ma.group(2)).lower()
            action = "out" if word.startswith("exclu") else "in"
            mi = _INLINE_INDEX.search(line)
            if mi and re.search(r"cnx|nifty|crisil", mi.group(1), re.I):
                cur_index, cur_section = index_code_for(mi.group(1)), mi.group(1)
            md = re.search(r"w\.?\s*e\.?\s*f\.?\s*" + _DATE_PAT, line, re.I)
            sentence_eff = parse_date(md.group(1)) if md else sentence_eff
            has_symbol_col = False
            continue
        if mr and action and cur_index:
            body = mr.group(2)
            sym = None
            if has_symbol_col:
                parts = body.rsplit(" ", 1)
                if len(parts) == 2 and re.fullmatch(r"[A-Z0-9&\-\.]{1,20}", parts[1]):
                    body, sym = parts[0], parts[1]
            events.append(dict(index_code=cur_index, action=action, rank=int(mr.group(1)), company=body.strip(),
                               symbol=sym, effective_date=sentence_eff or pr_eff or published,
                               eff_source="sentence" if sentence_eff else ("release" if pr_eff else "published"),
                               section=cur_section))
            continue
        # anything else ends a list only when a new paragraph obviously starts
        if action and re.match(r"^(the |these |place|date|about|note|in addition|further)", low):
            action = None
    return events


# ----------------------------------------------------------------------------------------------
# 3. Resolving events to securities

_NAME_DROP = re.compile(r"\b(limited|ltd|the|co|company|corporation|corpn|corp|inc|pvt|private|and|of|india|indian)\b")


def norm_company(s: str) -> str:
    s = s.lower().replace("&", " and ").replace("(", " ").replace(")", " ")
    # pre-2010 lists append the industry after "Ltd."; keep only the name part when we can
    m = re.search(r"^(.*?\b(?:ltd|limited)\b\.?)", s)
    if m and len(m.group(1)) > 4:
        s = m.group(1)
    s = re.sub(r"[^a-z0-9 ]+", " ", s)
    s = _NAME_DROP.sub(" ", s)
    return re.sub(r"\s+", " ", s).strip()


def _similarity(a: str, b: str) -> float:
    from difflib import SequenceMatcher

    if not a or not b:
        return 0.0
    ta, tb = set(a.split()), set(b.split())
    jac = len(ta & tb) / len(ta | tb)
    return max(SequenceMatcher(None, a, b).ratio(), jac, SequenceMatcher(None, a.replace(" ", ""), b.replace(" ", "")).ratio())


class Resolver:
    """Map (symbol | company name, date) -> security_id using everything we know about names."""

    def __init__(self, con) -> None:
        self.con = con
        # (security_id, name) pairs from every name source we hold
        rows = con.execute("""
            WITH n AS (
                SELECT l.security_id, nc.prev_name AS name FROM nse_name_change nc
                  JOIN listing l ON l.exchange = 'NSE' AND l.code = nc.symbol AND nc.change_date BETWEEN l.valid_from AND l.valid_to + 5
                UNION SELECT l.security_id, nc.new_name FROM nse_name_change nc
                  JOIN listing l ON l.exchange = 'NSE' AND l.code = nc.symbol AND nc.change_date BETWEEN l.valid_from AND l.valid_to + 5
                UNION SELECT l.security_id, d.company FROM nse_delisted d
                  JOIN listing l ON l.exchange = 'NSE' AND l.code = d.symbol AND d.delisted_date BETWEEN l.valid_from AND l.valid_to + 60
                UNION SELECT 'S:' || substr(isin, 1, 9), name FROM nse_equity_list
                UNION SELECT 'S:' || substr(isin, 1, 9), name FROM index_snapshot
                UNION SELECT security_id, latest_name FROM security WHERE latest_name NOT LIKE 'S:%' AND latest_name NOT LIKE 'X:%'
                UNION SELECT DISTINCT 'S:' || substr(isin, 1, 9), name FROM price_eod
                  WHERE name IS NOT NULL AND isin IS NOT NULL AND substr(isin, 8, 2) = '01')
            SELECT DISTINCT security_id, name FROM n WHERE name IS NOT NULL""").fetchall()
        self.names: dict[str, list[tuple[str, str]]] = {}
        for sid, name in rows:
            key = norm_company(name)
            if key:
                self.names.setdefault(key[:1], []).append((key, sid))
        self._nse_ranges: dict[str, list[tuple[dt.date, dt.date]]] = {}
        for sid, f, t in con.execute("SELECT security_id, valid_from, valid_to FROM listing WHERE exchange = 'NSE'").fetchall():
            self._nse_ranges.setdefault(sid, []).append((f, t))

    def traded_near(self, sid: str, d: dt.date, before: int = 120, after: int = 10) -> bool:
        return any(f <= d + dt.timedelta(days=after) and t >= d - dt.timedelta(days=before)
                   for f, t in self._nse_ranges.get(sid, []))

    def by_symbol(self, sym: str, d: dt.date) -> str | None:
        rows = self.con.execute(
            """SELECT security_id FROM listing WHERE exchange = 'NSE' AND code = ?
               AND valid_from <= ? AND valid_to >= ? ORDER BY valid_to DESC""",
            [sym.upper(), d + dt.timedelta(days=10), d - dt.timedelta(days=120)]).fetchall()
        if rows:
            return rows[0][0]
        # constituents outside the equity master (REIT/InvIT units): identify by the ISIN the code traded under
        row = self.con.execute(
            """SELECT 'S:' || substr(isin, 1, 9) FROM price_eod WHERE exchange = 'NSE' AND code = ?
               AND isin IS NOT NULL AND trade_date BETWEEN ? AND ? ORDER BY trade_date DESC LIMIT 1""",
            [sym.upper(), d - dt.timedelta(days=120), d + dt.timedelta(days=10)]).fetchone()
        return row[0] if row else None

    def by_name(self, company: str, d: dt.date) -> tuple[str | None, float]:
        key = norm_company(company)
        if not key:
            return None, 0.0
        best: tuple[str | None, float] = (None, 0.0)
        for bucket in {key[:1]} | ({k[:1] for k in [key.split()[0]]} if key.split() else set()):
            for cand, sid in self.names.get(bucket, []):
                s = _similarity(key, cand)
                if s > best[1] and self.traded_near(sid, d):
                    best = (sid, s)
        return best

    def resolve(self, ev: dict) -> tuple[str | None, str, float]:
        d = ev["effective_date"]
        if ev.get("symbol"):
            sid = self.by_symbol(ev["symbol"], d)
            if sid:
                return sid, "symbol", 1.0
        sid, score = self.by_name(ev["company"], d)
        if sid and score >= 0.80:
            return sid, "name", round(score, 3)
        return None, "unresolved", round(score, 3)


# ----------------------------------------------------------------------------------------------
# 4. Backward reconstruction

INDEX_SIZE = {"NIFTY500": 500}
BASE_PR = "https://www.niftyindices.com/Press_Release/"
OPEN_END = dt.date(9999, 12, 31)
SUPERSEDE_WINDOW = dt.timedelta(days=120)


def load_overrides() -> dict:
    import yaml

    path = Path(__file__).resolve().parents[2] / "config" / "index_overrides.yaml"
    return yaml.safe_load(path.read_text(encoding="utf-8")) or {}


def collect_events(con, raw: RawStore, index_code: str, resolver: Resolver) -> list[dict]:
    voids = {v["release"]: v for v in load_overrides().get("void_releases", [])
             if index_code not in (v.get("except_indices") or [])}
    prs = con.execute("""SELECT url, published_date, title, sha256 FROM press_release
                         WHERE sha256 IS NOT NULL ORDER BY published_date, url""").fetchall()
    out = []
    for url, published, title, sha in prs:
        void = voids.get(url.rsplit("/", 1)[-1])
        for e in parse_events(title, pdf_text(raw, sha), published):
            if e["index_code"] != index_code:
                continue
            sid, how, conf = resolver.resolve(e)
            if sid is None:
                sid = "U:" + (norm_company(e["company"]) or e["company"]).replace(" ", "_")[:60]
            out.append(e | dict(security_id=sid, resolve_method=how, confidence=conf, url=url, sha=sha,
                                published=published, title=title,
                                superseded_by=f"VOID per {void['source']}" if void else None))
    ov = load_overrides()
    void_ev = {(v["release"], v["action"], v["symbol"]): v for v in ov.get("void_events", [])
               if v.get("index") == index_code}
    for e in out:
        v = void_ev.get((e["url"].rsplit("/", 1)[-1], e["action"], e.get("symbol")))
        if v:
            e["superseded_by"] = f"VOID per {v['source']}"
    for a in ov.get("add_events", []):
        if a["index"] != index_code:
            continue
        ev = dict(index_code=index_code, action=a["action"], rank=0, company=a["company"], symbol=a["symbol"],
                  effective_date=a["effective_date"], eff_source="override", section="override",
                  published=a["announced_date"], title=f"override: {a['reason']}",
                  url=BASE_PR + a["source"], sha=None, superseded_by=None)
        sid, how, conf = resolver.resolve(ev)
        out.append(ev | dict(security_id=sid or "U:" + a["symbol"], resolve_method="override:" + how,
                             confidence=conf))
    # A later release that repeats the same change (revised/deferred date) supersedes the earlier one.
    out.sort(key=lambda e: (e["published"], e["url"]))
    latest: dict[tuple, dict] = {}
    for e in out:
        k = (e["security_id"], e["action"])
        prev = latest.get(k)
        if e.get("superseded_by"):
            continue  # voided events neither supersede nor get superseded
        if prev and e["published"] - prev["published"] <= SUPERSEDE_WINDOW and prev["url"] != e["url"]:
            prev["superseded_by"] = e["url"]
        latest[k] = e
    return out


def rebuild(con, raw: RawStore, index_code: str = "NIFTY500") -> dict:
    from trikal_core.db import insert_many
    from trikal_core.timeutil import end_of_day_ist

    size = INDEX_SIZE[index_code]
    resolver = Resolver(con)
    events = collect_events(con, raw, index_code, resolver)
    snap_date, = con.execute("SELECT max(snapshot_date) FROM index_snapshot WHERE index_code = ?",
                             [index_code]).fetchone()
    from trikal_core.ids import is_valid_isin

    snap_rows = con.execute("SELECT isin, symbol, name FROM index_snapshot WHERE index_code = ? AND snapshot_date = ?",
                            [index_code, snap_date]).fetchall()
    # NSE inserts temporary placeholders during corporate actions (e.g. 'Dummy HEG Ltd.', ISIN 'DUM...').
    placeholders = [(sym, name, isin) for isin, sym, name in snap_rows if not is_valid_isin(isin)]
    members = {"S:" + isin[:9]: sym for isin, sym, _ in snap_rows if is_valid_isin(isin)}

    live = [e for e in events if not e.get("superseded_by") and e["effective_date"] <= snap_date]
    by_date: dict[dt.date, list[dict]] = {}
    for e in live:
        by_date.setdefault(e["effective_date"], []).append(e)

    # open[sid] = (end_date, out_event or None)
    open_iv: dict[str, tuple[dt.date, dict | None]] = {sid: (OPEN_END, None) for sid in members}
    symbol_of = dict(members)
    intervals, checks, flags = [], [], []
    checks.append((index_code, snap_date, size, len(members), len(members) == size,
                   "official snapshot" + (f" excluding placeholders {[p[0] for p in placeholders]}" if placeholders else "")))
    cur = set(members)
    for d in sorted(by_date, reverse=True):
        evs = by_date[d]
        for e in [x for x in evs if x["action"] == "in"]:
            sid = e["security_id"]
            symbol_of.setdefault(sid, e.get("symbol") or e["company"])
            if sid in cur:
                cur.discard(sid)
                end, out_ev = open_iv.pop(sid)
                intervals.append((sid, d, end, e, out_ev))
            else:
                flags.append(("index_in_not_member", sid, d, f"{e['company']} ({e['url']})"))
        for e in [x for x in evs if x["action"] == "out"]:
            sid = e["security_id"]
            symbol_of.setdefault(sid, e.get("symbol") or e["company"])
            if sid not in cur:
                cur.add(sid)
                open_iv[sid] = (d, e)
            else:
                flags.append(("index_out_already_member", sid, d, f"{e['company']} ({e['url']})"))
        # state in force just before d
        checks.append((index_code, d - dt.timedelta(days=1), size, len(cur), len(cur) == size,
                       f"before changes effective {d}"))
    coverage_start = min(by_date) if by_date else snap_date
    for sid, (end, out_ev) in open_iv.items():
        intervals.append((sid, None, end, None, out_ev))

    rows = []
    for sid, start, end, in_ev, out_ev in intervals:
        conf = min([1.0] + [x["confidence"] for x in (in_ev, out_ev) if x])
        if sid.startswith("U:"):
            conf = 0.0
        method = "reconstructed" if start else "pre_coverage"
        vfrom = start or dt.date(1990, 1, 1)
        k_in = end_of_day_ist(in_ev["published"]) if in_ev else end_of_day_ist(coverage_start)
        note = "" if start else f"member before the earliest parsed release ({coverage_start}); true start unknown"
        rows.append((index_code, sid, symbol_of.get(sid), vfrom, OPEN_END, k_in, method, conf, note))
        if end != OPEN_END:
            rows.append((index_code, sid, symbol_of.get(sid), vfrom, end, end_of_day_ist(out_ev["published"]),
                         method, conf, note))

    con.execute("BEGIN")
    con.execute("DELETE FROM index_event WHERE index_code = ?", [index_code])
    insert_many(con, "INSERT INTO index_event VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                [(index_code, e["effective_date"], e["published"], e["action"], e.get("symbol"), e["company"],
                  e["security_id"], e["url"], e["sha"], e["section"],
                  0.0 if e.get("superseded_by") else e["confidence"]) for e in events])
    con.execute("DELETE FROM index_membership WHERE index_code = ?", [index_code])
    insert_many(con, "INSERT INTO index_membership VALUES (?,?,?,?,?,?,?,?,?)", rows)
    con.execute("DELETE FROM index_count_check WHERE index_code = ?", [index_code])
    insert_many(con, "INSERT INTO index_count_check VALUES (?,?,?,?,?,?)", checks)
    con.execute("DELETE FROM dq_issue WHERE kind LIKE 'index_%'")
    from trikal_core.timeutil import utcnow
    insert_many(con, "INSERT INTO dq_issue VALUES (?, 'NSE', ?, ?, ?, 'medium', ?)",
                [(k, sid, d, det, utcnow()) for k, sid, d, det in flags])
    insert_many(con, "INSERT INTO dq_issue VALUES ('index_snapshot_placeholder', 'NSE', ?, ?, ?, 'low', ?)",
                [(sym, snap_date, f"{name} ({isin}) excluded from membership: not a real security", utcnow())
                 for sym, name, isin in placeholders])
    con.execute("COMMIT")
    n_ok = sum(1 for c in checks if c[4])
    return {
        "events": len(events), "superseded": sum(1 for e in events if e.get("superseded_by")),
        "unresolved": sum(1 for e in events if e["security_id"].startswith("U:")),
        "by_name": sum(1 for e in events if e["resolve_method"] == "name"),
        "count_checks_ok": f"{n_ok}/{len(checks)}", "flags": len(flags),
        "securities_ever": len({r[1] for r in rows}), "coverage_start": str(coverage_start),
    }
