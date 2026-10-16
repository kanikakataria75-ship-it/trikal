"""Rule-based reading of earnings-call transcripts: forward-looking statements with a number ("promises") and word-list tone.

No model. A statement becomes a promise only when it has (a) a forward cue (expect, guide, target, will ...), (b) a metric word, (c) a
percentage, and (d) a stated period or a clear 'this/next year'. Questions, negations and statements about the past are skipped.
Everything keeps its sentence and page, so the reader can check it; whatever the rules cannot read stays out."""

from __future__ import annotations

import datetime as dt
import io
import re
from collections import Counter
from dataclasses import dataclass, field

MAX_PAGES = 120
QA_MARKERS = re.compile(
    r"(question[\s-]*and[\s-]*answer|\bQ\s*&\s*A\b|first question|take (?:the )?first question|open (?:the )?(?:floor|line)s? for questions|"
    r"begin the question|now (?:open|begin|start)[^.]{0,40}question)", re.I)
START_MARKERS = re.compile(r"(call participants|good (?:morning|afternoon|evening)|moderator|operator|welcome to)", re.I)

FORWARD = re.compile(r"\b(expect(?:s|ed|ing)?|guid(?:e|es|ed|ing|ance)|target(?:s|ed|ing)?|aim(?:s|ed|ing)?|will|would|should|plan(?:s|ned|ning)? to|"
                     r"on track|going to|anticipat\w+|project(?:s|ed|ing)?|aspir\w+|endeavou?r\w*|confident (?:of|that|about)|looking (?:at|to))\b", re.I)
STRONG = re.compile(r"\b(expect\w*|target\w*|aim\w*|on track|anticipat\w+|going to|plan\w* to|aspir\w+|endeavou?r\w*|will|guidance (?:for|is|stands|range|remains|of)|guid(?:e|ing) (?:to|for|at))\b", re.I)
ADDRESSED = re.compile(r"\byou(?:r|rs|'ve|'re|'d)?\b|\bguided\b", re.I)          # an analyst speaking to management, or a reminder of an old guide
PAST = re.compile(r"\b(was|were|had|achieved|reported|delivered|grew|stood|came in|declined|rose|fell|registered|clocked|finished|ended|closed|exited)\b", re.I)
NEGATED = re.compile(r"\b(?:do not|don't|does not|doesn't|not|never|cannot|can't|unlikely)\s+(?:\w+\s+){0,2}?(?:expect|guide|target|anticipate|see)\b", re.I)
QUESTION = re.compile(r"\?\s*$|\b(?:can you|could you|would you|do you|are you|what is|what are|how do|how are)\b", re.I)

METRICS = {
    "revenue_growth": re.compile(r"\b(revenue|sales|top[\s-]?line|turnover)\b(?:[^.]{0,40}\b(growth|grow|growing|increase))?", re.I),
    "ebitda_margin": re.compile(r"\b(ebitda|operating|ebit|oi)\s+margins?\b|\bmargins?\b", re.I),
    "profit_growth": re.compile(r"\b(pat|profit after tax|net profit|bottom[\s-]?line|earnings|eps)\b", re.I),
    "capex": re.compile(r"\bcap(?:ital )?ex(?:penditure)?\b|\binvest(?:ment)?s?\b", re.I),
    "volume_growth": re.compile(r"\bvolumes?\b", re.I),
    "return_ratio": re.compile(r"\b(roce|roe|return on)\b", re.I),
    "debt": re.compile(r"\b(net debt|debt|leverage)\b", re.I),
}
JUDGEABLE = {"revenue_growth": "revenue_growth", "ebitda_margin": "ebitda_margin", "profit_growth": "profit_growth"}
GROWTH_WORD = re.compile(r"\b(growth|grow|growing|increase|expand|cagr|y-?o-?y)\b", re.I)
RANGE = re.compile(r"(\d+(?:\.\d+)?)\s*(?:%|per\s?cent)?\s*(?:-|–|—|to)\s*(\d+(?:\.\d+)?)\s*(?:%|per\s?cent)", re.I)
PCT = re.compile(r"(\d+(?:\.\d+)?)\s*(?:%|per\s?cent)", re.I)
DOUBLE_DIGIT = re.compile(r"\bdouble[\s-]?digit\b", re.I)
AT_LEAST = re.compile(r"\b(at least|more than|above|over|minimum|north of|greater than|exceed\w*|upwards of|[\d.]+\s*%\s*(?:\+|plus|and above|or more))", re.I)
AT_MOST = re.compile(r"\b(up to|at most|below|under|less than|not more than|capped at|within)\b", re.I)
ABOUT = re.compile(r"\b(around|about|approximately|roughly|~|close to|in the region of|circa)\b", re.I)
MULTI = re.compile(r"\b(cagr|compounded|over the next \w+ years?|next (?:\d+|two|three|four|five|ten) years?|(?:two|three|four|five|ten|\d+)[\s-]years?|medium[\s-]term|long[\s-]term)\b", re.I)
FY_TOKEN = re.compile(r"\bFY\s*['’]?\s*(\d{2}|\d{4})\b|\b(?:fiscal|financial year)\s*(?:ending|ended)?\s*(?:march|mar)[\s,'’-]*(\d{4})\b", re.I)
THIS_YEAR = re.compile(r"\b(this (?:fiscal|financial)? ?year|current (?:fiscal|financial)? ?year|full[\s-]year|for the (?:financial |fiscal )?year)\b", re.I)
NEXT_YEAR = re.compile(r"\b(next (?:fiscal|financial)? ?year|following year|year ahead|coming year)\b", re.I)

POSITIVE = ("strong", "robust", "growth", "improve", "improved", "improving", "improvement", "momentum", "record", "confident", "healthy", "accelerate",
            "accelerating", "outperform", "opportunity", "opportunities", "benefit", "tailwind", "tailwinds", "resilient", "expand", "expanding", "gain", "gains")
NEGATIVE = ("decline", "declined", "declining", "weak", "weaker", "weakness", "pressure", "pressures", "headwind", "headwinds", "challenging", "challenge",
            "challenges", "difficult", "slowdown", "slow", "softness", "soft", "deteriorate", "deterioration", "loss", "losses", "delay", "delays", "delayed",
            "volatile", "volatility", "disruption", "disruptions", "stress", "stressed", "concern", "concerns", "impacted", "adverse", "lower")
HEDGE = ("may", "might", "could", "possibly", "perhaps", "approximately", "roughly", "around", "uncertain", "uncertainty", "depends", "depending", "cautious",
         "cautiously", "visibility", "assume", "assuming", "tentative", "tentatively", "probably", "hopefully", "hope", "broadly", "somewhat", "subject")
EVASIVE_PHRASES = ("can't comment", "cannot comment", "not in a position", "take that offline", "offline", "too early to say", "too early to comment",
                   "we don't give guidance", "we do not give guidance", "don't guide", "do not guide", "will not disclose", "won't disclose", "not able to share",
                   "can't share", "cannot share", "not going to comment", "prefer not to", "will come back to you", "come back on that")


def fy_end_of(call_quarter: dt.date) -> dt.date:
    """Financial year (ends 31 March) the company is talking about on a call for the quarter ended `call_quarter`."""
    return dt.date(call_quarter.year + 1, 3, 31)


@dataclass
class Promise:
    metric: str
    op: str                      # range | at_least | at_most | about
    low: float
    high: float
    horizon_end: dt.date | None  # 31 March of the financial year it is about
    horizon_kind: str            # fy | multi | none
    quote: str
    page: int


@dataclass
class CallParse:
    status: str = "ok"
    words: int = 0
    pages: int = 0
    promises: list[Promise] = field(default_factory=list)
    tone: dict = field(default_factory=dict)
    examples: dict = field(default_factory=dict)


def clean_pages(pages: list[str]) -> list[tuple[int, str]]:
    """(page number, text) from the first page that looks like the start of the call (the covering letter is dropped)."""
    start = 0
    for i, t in enumerate(pages):
        if START_MARKERS.search(t) and not re.search(r"regulation\s*30|dear sirs|scrip code", t[:600], re.I):
            start = i
            break
    out = []
    for i in range(start, len(pages)):
        t = re.sub(r"[\r\f]", " ", pages[i])
        t = re.sub(r"\n(?=[a-z,;])", " ", t)                                  # a line break inside a sentence
        out.append((i + 1, t))
    return out


def sentences(text: str) -> list[str]:
    flat = re.sub(r"\s+", " ", text)
    return [s.strip() for s in re.split(r"(?<=[.!?])\s+(?=[A-Z\"“(])", flat) if len(s.strip()) > 25]


def _horizon(sentence: str, call_fy: dt.date) -> tuple[dt.date | None, str]:
    if MULTI.search(sentence):
        return None, "multi"
    m = FY_TOKEN.search(sentence)
    if m:
        y = m.group(1) or m.group(2)
        y = int(y)
        y = y if y > 100 else 2000 + y
        return dt.date(y, 3, 31), "fy"
    if NEXT_YEAR.search(sentence):
        return dt.date(call_fy.year + 1, 3, 31), "fy"
    if THIS_YEAR.search(sentence):
        return call_fy, "fy"
    return None, "none"


def _metric(sentence: str) -> str | None:
    for name, rx in METRICS.items():
        if rx.search(sentence):
            if name == "revenue_growth" and not GROWTH_WORD.search(sentence) and not DOUBLE_DIGIT.search(sentence):
                continue
            if name == "profit_growth" and not GROWTH_WORD.search(sentence) and not DOUBLE_DIGIT.search(sentence):
                continue
            return name
    return None


CLAUSE_SPLIT = re.compile(r",?\s+(?:and|while|whereas|but)\s+(?=(?:our|the|we|its|for)\b)|;\s*|,\s+(?=(?:our|the)\s+\w+(?:\s+\w+)?\s+(?:guidance|margin))", re.I)


def _metrics_in(text: str) -> list[str]:
    found = []
    for name in METRICS:
        if METRICS[name].search(text):
            if name in ("revenue_growth", "profit_growth") and not GROWTH_WORD.search(text) and not DOUBLE_DIGIT.search(text):
                continue
            found.append(name)
    return found


def read_promise(sentence: str, page: int, call_fy: dt.date) -> Promise | None:
    ps = read_promises(sentence, page, call_fy)
    return ps[0] if ps else None


def read_promises(sentence: str, page: int, call_fy: dt.date) -> list[Promise]:
    """Every statement with a number in a sentence. A sentence that gives two figures for two metrics gives two promises."""
    if QUESTION.search(sentence) or NEGATED.search(sentence) or ADDRESSED.search(sentence) or not FORWARD.search(sentence):
        return []
    if PAST.search(sentence) and not STRONG.search(sentence):
        return []
    horizon, kind = _horizon(sentence, call_fy)
    out: list[Promise] = []
    for clause in CLAUSE_SPLIT.split(sentence):
        if not clause or not (RANGE.search(clause) or PCT.search(clause) or DOUBLE_DIGIT.search(clause)):
            continue
        ms = _metrics_in(clause)
        if not ms and GROWTH_WORD.search(clause) and re.search(r"guidance", sentence, re.I) and not METRICS["ebitda_margin"].search(clause):
            ms = ["revenue_growth"]                                      # 'FY27 growth guidance is 2.5% to 4%': growth of revenue
        if len(ms) != 1:
            continue                                                     # none, or two metrics sharing one number: ambiguous, left out
        metric = ms[0]
        m = RANGE.search(clause)
        if m:
            lo, hi = sorted((float(m.group(1)), float(m.group(2))))
            op = "range"
        elif DOUBLE_DIGIT.search(clause) and metric in ("revenue_growth", "profit_growth"):
            lo, hi, op = 10.0, 99.0, "at_least"
        else:
            m = PCT.search(clause)
            if not m:
                continue
            lo = hi = float(m.group(1))
            op = "at_least" if AT_LEAST.search(clause) else "at_most" if AT_MOST.search(clause) else "about"
            if op == "about" and not ABOUT.search(clause) and not STRONG.search(sentence):
                continue                                                 # a bare percentage with no stance: could be anything
        if not (0 < hi <= 150):
            continue
        out.append(Promise(metric, op, lo, hi, horizon, kind, sentence[:420], page))
    return out


def tone_of(sentences_: list[str]) -> tuple[dict, dict]:
    """Word-list tone of management statements (questions excluded): rates per 1,000 words, and a few quotes."""
    pos = neg = hed = words = 0
    evasive = 0
    ex: dict[str, list[str]] = {"hedged": [], "evasive": [], "negative": []}
    for s in sentences_:
        if QUESTION.search(s):
            continue
        toks = re.findall(r"[a-z']+", s.lower())
        words += len(toks)
        c = Counter(toks)
        p, n, h = sum(c[w] for w in POSITIVE), sum(c[w] for w in NEGATIVE), sum(c[w] for w in HEDGE)
        pos, neg, hed = pos + p, neg + n, hed + h
        low = s.lower()
        if any(ph in low for ph in EVASIVE_PHRASES):
            evasive += 1
            if len(ex["evasive"]) < 3:
                ex["evasive"].append(s[:260])
        if h >= 3 and len(ex["hedged"]) < 3:
            ex["hedged"].append(s[:260])
        if n >= 3 and len(ex["negative"]) < 3:
            ex["negative"].append(s[:260])
    k = 1000.0 / words if words else 0.0
    tone = {"words": words, "positive_rate": pos * k, "negative_rate": neg * k, "hedge_rate": hed * k, "evasive_count": evasive,
            "net_tone": (pos - neg) / (pos + neg) if pos + neg else None}
    return tone, ex


def parse_text(pages: list[str], announced: dt.date, call_quarter: dt.date) -> CallParse:
    out = CallParse(pages=len(pages))
    kept = clean_pages(pages)
    body = " ".join(t for _, t in kept)
    out.words = len(body.split())
    if out.words < 1500:
        out.status = "too short to be a transcript"
        return out
    call_fy = fy_end_of(call_quarter)
    all_s: list[tuple[int, str]] = []
    for n, t in kept:
        all_s += [(n, s) for s in sentences(t)]
    seen = set()
    for n, s in all_s:
        if s[:80] in seen:
            continue
        ps = read_promises(s, n, call_fy)
        if ps:
            seen.add(s[:80])
            out.promises.extend(ps)
    qa = next((m for m in QA_MARKERS.finditer(body) if m.start() > 0.08 * len(body)), None)        # not the opening 'we will take questions later'
    split_at = qa.start() if qa else len(body)
    prepared = sentences(body[:split_at])
    answers = sentences(body[split_at:]) if qa else []
    t_all, ex = tone_of([s for _, s in all_s])
    t_prep, _ = tone_of(prepared)
    t_qa, _ = tone_of(answers) if answers else ({}, {})
    out.tone = {"all": t_all, "prepared": t_prep, "qa": t_qa, "has_qa": bool(qa)}
    out.examples = ex
    return out


def parse_pdf(pdf_bytes: bytes, announced: dt.date, call_quarter: dt.date) -> CallParse:
    import pdfplumber

    pages = []
    with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
        for pg in pdf.pages[:MAX_PAGES]:
            try:
                pages.append(pg.extract_text() or "")
            except Exception:
                pages.append("")
    return parse_text(pages, announced, call_quarter)
