"""Rule-based reading of results decks (investor presentations) for the bank / NBFC metrics the results filings do not carry:
NIM, CASA ratio, provision coverage, slippage ratio, capital adequacy.

No model and no guessing. A number is accepted only when
  (a) it sits in a table row whose header names the periods, the header has as many periods as the row has numbers, and one of them is
      the deck's reporting quarter (the latest quarter ended before the announcement), or
  (b) it is a single number in a sentence that itself names the reporting period;
and it passes a plausibility range. Anything else is not extracted: the metric stays 'n/a'. Every accepted value keeps its page and the
line it came from."""

from __future__ import annotations

import datetime as dt
import io
import re
from dataclasses import dataclass

MONTHS = {"jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6, "jul": 7, "aug": 8, "sep": 9, "oct": 10, "nov": 11, "dec": 12}
QUARTER_END_MONTH = {3: (3, 31), 6: (6, 30), 9: (9, 30), 12: (12, 31)}
MAX_PAGES = 90
HEADER_LOOKBACK = 12
MAX_COLUMNS = 8                 # longer rows are histories whose last column is easy to misalign

# concept -> (label pattern, lines to ignore, plausible percent range, qualifiers that make a row a sub-segment)
CONCEPTS: dict[str, dict] = {
    "nim": {"label": r"net\s+interest\s+margins?(?:\s*\((?:nim|%)\))?|\bNIMs?\b(?!\s*\()", "range": (0.5, 12.0),
            "skip": r"\bdomestic\b|\binternational\b|\boverseas\b|\bexcluding\b|\bcumulative\b|\bproxy\b|\bon\s+average\b|\bestimated\b",
            "qualifiers": r"\b(?:domestic|international|overseas|retail|corporate|housing|vehicle)\b"},
    "casa_ratio": {"label": r"\bCASA(?:\s+ratio)?(?:\s*\(%\))?", "range": (5.0, 85.0),
                   "skip": r"\bgrowth\b|\byoy\b|\bqoq\b|\bavg\b|\baverage\b|\bdeposits?\s+\(", "qualifiers": r"\b(?:domestic|period[- ]end|average)\b"},
    "pcr": {"label": r"provision\s+coverage(?:\s+ratio)?(?:\s*\(%\))?|\bPCR\b", "range": (20.0, 100.0),
            "skip": r"\bexcluding\b|\bgross\s+npa\b|\bincluding\b|\btechnical\b", "qualifiers": r"\b(?:domestic|retail|corporate)\b"},
    "slippage_ratio": {"label": r"(?:gross\s+)?slippage(?:s)?\s+ratio(?:\s*\(%\))?", "range": (0.0, 15.0),
                       "skip": r"\bnet\b", "qualifiers": r"\b(?:retail|corporate|agri|sme|msme)\b"},
    "car": {"label": r"(?:total\s+)?capital\s+adequacy(?:\s+ratio)?(?:\s*\((?:crar|%|car)\))?|\bCRAR\b", "range": (8.0, 45.0),
            "skip": r"\bcet\s*1\b|\btier\s*[-]?\s*[12i]\b|\bleverage\b|\bat1\b", "qualifiers": r"\b(?:including|excluding)\b"},
}
_NUM = re.compile(r"(?<![\w.])(-?\d{1,3}(?:,\d{3})*(?:\.\d+)?|-?\d+(?:\.\d+)?)(\s*%)?(?![\w])")
_QFY = re.compile(r"\bQ\s*([1-4])\s*[-–/ ]?\s*(?:FY|F\.Y\.)\s*[\'’]?\s*(\d{2}|\d{4})\b", re.I)
_MONYR = re.compile(r"\b(Mar|Jun|Sep|Dec)[a-z]*\.?\s*[-\'’,]?\s*(?:\d{1,2}\s*,?\s*)?[\'’-]?\s*(\d{4}|\d{2})\b", re.I)
_FY = re.compile(r"\bFY\s*[\'’]?\s*(\d{2}|\d{4})\b", re.I)


def _year(s: str) -> int:
    y = int(s)
    return y if y > 100 else 2000 + y


def quarter_end(year: int, month: int) -> dt.date:
    return dt.date(year, *QUARTER_END_MONTH[month])


def reporting_quarter(announced: dt.date) -> dt.date | None:
    """The latest March/June/September/December quarter end at least 5 days before the announcement and at most 130 days earlier."""
    best = None
    for y in (announced.year - 1, announced.year):
        for m in (3, 6, 9, 12):
            q = quarter_end(y, m)
            if q <= announced - dt.timedelta(days=5) and (best is None or q > best):
                best = q
    return best if best and (announced - best).days <= 130 else None


def period_tokens(line: str) -> list[tuple[int, dt.date, str]]:
    """Every period named in a line, left to right: (position, quarter or year end, kind) with kind 'q' or 'fy'."""
    found: list[tuple[int, dt.date, str]] = []
    spans = []
    for m in _QFY.finditer(line):
        q, fy = int(m.group(1)), _year(m.group(2))
        month = {1: 6, 2: 9, 3: 12, 4: 3}[q]
        found.append((m.start(), quarter_end(fy if q == 4 else fy - 1, month), "q"))
        spans.append(m.span())
    for m in _MONYR.finditer(line):
        if any(a <= m.start() < b for a, b in spans):
            continue
        found.append((m.start(), quarter_end(_year(m.group(2)), MONTHS[m.group(1).lower()[:3]]), "q"))
        spans.append(m.span())
    for m in _FY.finditer(line):
        if any(a <= m.start() < b for a, b in spans):
            continue
        found.append((m.start(), quarter_end(_year(m.group(1)), 3), "fy"))
    return sorted(found)


def numbers(rest: str) -> list[tuple[float, bool]]:
    out = []
    for m in _NUM.finditer(rest):
        try:
            out.append((float(m.group(1).replace(",", "")), bool(m.group(2))))
        except ValueError:
            continue
    return out


@dataclass
class Hit:
    concept: str
    period_end: dt.date
    value: float            # ratio (0.043 = 4.3%)
    page: int
    line: str
    kind: str               # table | sentence
    qualified: bool


def _header_for(lines: list[str], i: int, n: int) -> list[tuple[int, dt.date, str]] | None:
    for j in range(i - 1, max(-1, i - 1 - HEADER_LOOKBACK), -1):
        toks = period_tokens(lines[j])
        if len(toks) == n and n >= 2:
            return toks
        if len(toks) > n >= 2 and len(set(t[1] for t in toks)) == n:        # a header that repeats a period (e.g. 'Q1FY27 ... Q1FY27 vs Q1FY26')
            return None
    return None


def scan_page(text: str, page: int, target: dt.date) -> list[Hit]:
    lines = [ln.strip() for ln in text.splitlines()]
    hits: list[Hit] = []
    for i, line in enumerate(lines):
        if not line or len(line) > 400:
            continue
        for concept, spec in CONCEPTS.items():
            m = re.search(spec["label"], line, re.I)
            if not m or re.search(spec["skip"], line, re.I):
                continue
            rest = _FY.sub(" ", _MONYR.sub(" ", _QFY.sub(" ", line[m.end():])))      # dates in the sentence are not values
            nums = numbers(rest)
            if not nums:
                continue
            lo, hi = spec["range"]
            qualified = bool(re.search(spec["qualifiers"], line, re.I))
            header = _header_for(lines, i, len(nums))
            value = None
            prose = len(re.findall(r"[A-Za-z]{2,}", re.sub(r"(?i)\b(?:n\.?a\.?|nm|bps|pp)\b", " ", rest)))
            if header is not None and len(nums) <= MAX_COLUMNS and prose <= 2:          # a row is a label and numbers, not prose
                idx = [k for k, (_, d, kind) in enumerate(header) if d == target and kind == "q"]
                if len(idx) == 1:
                    value, kind = nums[idx[0]][0], "table"
            if value is None and len(nums) == 1 and nums[0][1]:                           # one explicit percentage in a sentence
                toks = period_tokens(line)
                if toks and all(d == target and k == "q" for _, d, k in toks):             # that names the quarter itself, never a year
                    value, kind = nums[0][0], "sentence"
            if value is None or not (lo <= value <= hi):
                continue
            hits.append(Hit(concept, target, value / 100.0, page, line[:200], kind, qualified))
    return hits


def choose(hits: list[Hit]) -> tuple[dict[str, Hit], dict[str, str]]:
    """One value per concept, or none: prefer unqualified table rows; disagreement between equally good candidates drops the metric."""
    chosen: dict[str, Hit] = {}
    dropped: dict[str, str] = {}
    by: dict[str, list[Hit]] = {}
    for h in hits:
        by.setdefault(h.concept, []).append(h)
    for concept, hs in by.items():
        rank = lambda h: (h.qualified, h.kind != "table")          # noqa: E731  (lower is better)
        best = min(rank(h) for h in hs)
        top = [h for h in hs if rank(h) == best]
        values = {round(h.value, 6) for h in top}
        if len(values) == 1:
            chosen[concept] = top[0]
        else:
            dropped[concept] = f"conflicting values {sorted(values)} on pages {sorted({h.page for h in top})}"
    return chosen, dropped


def parse_deck(pdf_bytes: bytes, announced: dt.date) -> dict:
    """{'period_end', 'values': {concept: Hit}, 'dropped': {...}, 'status'} for one presentation."""
    import pdfplumber

    target = reporting_quarter(announced)
    if target is None:
        return {"status": "no reporting quarter near the announcement date", "values": {}, "dropped": {}}
    hits: list[Hit] = []
    mentions_period = False
    with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
        for n, pg in enumerate(pdf.pages[:MAX_PAGES], 1):
            try:
                text = pg.extract_text() or ""
            except Exception:
                continue
            if not mentions_period and any(d == target for _, d, _ in (t for ln in text.splitlines() for t in period_tokens(ln))):
                mentions_period = True
            hits.extend(scan_page(text, n, target))
    if not mentions_period:
        return {"status": "the deck never names its reporting quarter", "values": {}, "dropped": {}, "period_end": target}
    chosen, dropped = choose(hits)
    return {"status": "ok" if chosen else "nothing matched", "values": chosen, "dropped": dropped, "period_end": target}
