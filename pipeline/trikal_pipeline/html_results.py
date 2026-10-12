"""Parse NSE's old 'Financial Results Details' HTML pages (filings 2008 - 2017, before XBRL).

Layout (verified on 75 real pages): a header block of `label | value` pairs (Symbol, Audited, Cumulative,
Consolidated, Period, Relating to, Financial Year, Period Ended), then Part I (income statement lines)
and Part II (public/promoter shareholding, pledged shares), each as `label |` followed by `value |`.
The amount unit is declared in the table header ("Amount (Rs. in lakhs)").

Lossless first: every labelled numeric value becomes a fact named `html:<slug>`; nothing is interpreted
here beyond slugging, scaling money to INR, and deriving the period. Mapping to canonical line items is
configuration (config/line_items.yaml). A '-' value means "not reported" and is skipped (never zero).
"""

from __future__ import annotations

import datetime as dt
import html as htmllib
import re
from dataclasses import dataclass, field

from trikal_pipeline.xbrl_results import Fact

_NUM = re.compile(r"^\(?-?\s*[\d,]+(?:\.\d+)?\)?$")
_UNIT_SCALE = {"lakh": 1e5, "lakhs": 1e5, "crore": 1e7, "crores": 1e7, "million": 1e6, "millions": 1e6,
               "thousand": 1e3, "thousands": 1e3, "rs": 1.0}
# Lines whose value is not money (no unit scaling): per-share data, counts, percentages, face value.
_NATIVE = re.compile(r"eps|earnings_per_share|face_value|percent|_pct|number_of_shares|shareholding_number|"
                     r"no_of_shares|dividend_|basic|diluted")
_META_LABELS = {
    "symbol": "symbol", "company": "company", "industry": "industry", "audited / un-audited": "audited",
    "cumulative / non-cumulative": "cumulative", "consolidated / non-consolidated": "consolidated",
    "period": "period", "relating to": "relating_to", "financial year": "financial_year",
    "period ended": "period_ended",
}
_NOISE = re.compile(r"^(notes to accounts|click here|description|part i+|income from operations|expenses|"
                    r"search for another company|top|other info|non banking|banking|other related items|"
                    r"segment reporting|investor complaints|particulars of shareholding)\b", re.I)


@dataclass
class HtmlParsed:
    meta: dict[str, str] = field(default_factory=dict)
    facts: list[Fact] = field(default_factory=list)
    period_start: dt.date | None = None
    period_end: dt.date | None = None
    fy_start: dt.date | None = None
    problems: list[str] = field(default_factory=list)


def to_lines(raw: bytes) -> list[str]:
    t = raw.decode("utf-8", "replace")
    t = re.sub(r"(?is)<script.*?</script>|<style.*?</style>|<!--.*?-->", "", t)
    t = re.sub(r"(?i)<br\s*/?>|</tr>|</td>|</th>|</p>|</div>|</li>", "\n", t)
    t = re.sub(r"<[^>]+>", "", t)
    t = htmllib.unescape(t).replace("\xa0", " ")
    out = []
    for ln in t.split("\n"):
        ln = re.sub(r"\s+", " ", ln.replace("|", " ")).strip()
        if ln and ln != "-->":
            out.append(ln)
    return out


def slug(label: str) -> str:
    s = re.sub(r"^\(?[a-z]\)\s*|^\(?[ivx]+\)\s*", "", label.strip(), flags=re.I)
    s = re.sub(r"\(.*?\)", " ", s)  # drop parentheticals like "(not annualised)" "( a + b)"
    s = re.sub(r"[^a-z0-9]+", "_", s.lower()).strip("_")
    return s[:90]


def parse_number(tok: str) -> float | None:
    tok = tok.strip()
    if not _NUM.match(tok):
        return None
    neg = tok.startswith("(") or tok.lstrip("(").startswith("-")
    v = float(re.sub(r"[^\d.]", "", tok))
    return -v if neg else v


def _date(s: str) -> dt.date | None:
    try:
        return dt.datetime.strptime(s.strip().title(), "%d-%b-%Y").date()
    except ValueError:
        return None


def parse_results_html(raw: bytes) -> HtmlParsed:
    out = HtmlParsed()
    lines = to_lines(raw)
    # unit declared in the table header
    scale, unit_seen = 1.0, False
    for ln in lines:
        m = re.search(r"amount\s*\(\s*rs\.?\s*in\s*([a-z]+)", ln, re.I)
        if m:
            scale, unit_seen = _UNIT_SCALE.get(m.group(1).lower(), 1.0), True
            if m.group(1).lower() not in _UNIT_SCALE:
                out.problems.append(f"unknown unit {m.group(1)}")
            break
    # header block
    for i, ln in enumerate(lines[:60]):
        key = _META_LABELS.get(ln.lower().rstrip(":"))
        if key and i + 1 < len(lines):
            out.meta.setdefault(key, lines[i + 1])
    fy = re.search(r"(\d{2}-[A-Za-z]{3}-\d{4})\s*to\s*(\d{2}-[A-Za-z]{3}-\d{4})", out.meta.get("financial_year", ""), re.I)
    out.fy_start = _date(fy.group(1)) if fy else None
    out.period_end = _date(out.meta.get("period_ended", ""))
    rel = (out.meta.get("relating_to") or "").lower()
    cumulative = (out.meta.get("cumulative") or "").lower().startswith("cumulative")
    if out.period_end:
        q = {"first": 1, "second": 2, "third": 3, "fourth": 4}.get(rel.split(" ")[0], None)
        if rel in ("annual", "yearly") or (q is None and "year" in rel):
            out.period_start = out.fy_start
        elif q:
            if cumulative and out.fy_start:
                out.period_start = out.fy_start
            else:
                e = out.period_end
                y, m = (e.year, e.month - 2) if e.month > 2 else (e.year - 1, e.month + 10)
                out.period_start = dt.date(y, m, 1)
        else:
            out.problems.append(f"unrecognised 'relating to': {rel!r}")
    if out.period_end is None:
        out.problems.append("no period end")
        return out
    # Part I = income-statement lines, up to the first marker of Part II / notes / segments.
    start = next((i for i, ln in enumerate(lines) if re.match(r"description", ln, re.I)), 0)
    markers = re.compile(r"^(-\s*number of shares|public shareholding|particulars of shareholding|promoters? and promoter|"
                         r"pending beginning|investor complaints|notes to accounts|segment|search for another)", re.I)
    end = next((i for i in range(start + 1, len(lines)) if markers.match(lines[i])), len(lines))
    header = ""
    i = start
    while i < end - 1:
        ln, nxt = lines[i], lines[i + 1]
        val = parse_number(nxt)
        if parse_number(ln) is None and not _NOISE.match(ln):
            if val is not None:
                label = (header + " " + ln).strip() if re.match(r"^\(?[ab]\)?\s*(basic|diluted)", ln, re.I) else ln
                sl = slug(label)
                if sl and sl != "total":
                    native = bool(_NATIVE.search(sl))
                    out.facts.append(Fact("html:" + sl, "", "One", out.period_start, out.period_end, False,
                                          val * (1.0 if native else scale), "native" if native else "INR"))
                i += 2
                continue
            if nxt.strip() in ("-", "--"):
                i += 2
                continue
            if len(ln) < 120:
                header = ln
        i += 1
    if not unit_seen and out.facts:
        out.problems.append("amount unit not declared")
    out.facts.extend(_part2_facts(lines[end:], out))
    return out


_P2 = [
    ("num", re.compile(r"^-\s*number of shares", re.I)),
    ("pct_group", re.compile(r"^-\s*percentage of shares.*total shareholding of (the )?promoter", re.I)),
    ("pct_total", re.compile(r"^-\s*percentage of shares.*total share capital", re.I)),
    ("pct_public", re.compile(r"^-\s*percentage of shareholding", re.I)),
]


def _part2_facts(rest: list[str], doc: HtmlParsed) -> list[Fact]:
    """Public / promoter shareholding and pledge from Part II, accepted only if internally consistent.

    Template order of the value rows (pages render the 'Number of shares' rows one group early):
      public: num, pct_public | pledged: num | pct_group, pct_total | non-enc: num, pct_group, pct_total.
    The assignment is verified arithmetically; on any mismatch no fact is emitted."""
    vals: list[tuple[str, float | None]] = []
    for k in range(len(rest) - 1):
        for kind, rx in _P2:
            if rx.match(rest[k]):
                v = parse_number(rest[k + 1])
                if v is not None or rest[k + 1].strip() in ("-", "--"):
                    vals.append((kind, v))
                break
    nums = [v for kd, v in vals if kd == "num"]
    pg = [v for kd, v in vals if kd == "pct_group"]
    pt = [v for kd, v in vals if kd == "pct_total"]
    pub = [v for kd, v in vals if kd == "pct_public"]
    if len(nums) != 3 or len(pub) != 1 or any(n is None for n in nums) or doc.period_end is None:
        return []
    public_n, pledged_n, nonenc_n = nums
    promoter_n = pledged_n + nonenc_n
    if promoter_n <= 0 or public_n <= 0:
        return []
    total = public_n + promoter_n
    ok = abs(pub[0] / 100 - public_n / total) < 0.01
    if len(pt) == 2 and pt[1] is not None:
        ok = ok and abs(pt[1] / 100 - nonenc_n / total) < 0.01
    if len(pg) == 2 and pg[1] is not None:
        ok = ok and abs(pg[1] / 100 - nonenc_n / promoter_n) < 0.01
    if len(pg) == 2 and pg[0] is not None:
        ok = ok and abs(pg[0] / 100 - pledged_n / promoter_n) < 0.01
    if not ok:
        return []
    pe = doc.period_end
    mk = lambda name, v, unit="shares": Fact("html:" + name, "", "One", None, pe, True, v, unit)  # noqa: E731
    return [mk("public_shares", public_n), mk("promoter_pledged_shares", pledged_n),
            mk("promoter_nonencumbered_shares", nonenc_n)]
