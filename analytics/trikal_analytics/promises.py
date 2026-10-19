"""Promise Tracker: judge a management statement against the company's own later results, deterministically, as of a date.

The statement comes from the transcript (rules, see pipeline/call_parse.py); the verdict comes only from point-in-time financials. A
verdict needs the results of the year the statement is about, public at the as-of date; before that it is 'pending', and a statement the
rules cannot place in a single financial year is 'not judged', never guessed."""

from __future__ import annotations

import datetime as dt
import re

from trikal_analytics import metrics as M
from trikal_analytics.result import ForbiddenMetric, Value
from trikal_core.timeutil import AsOf

RESULTS_LAG_DAYS = 75               # full-year results are public within 60 days of the year end (LODR Reg 33)
MIN_JUDGED_FOR_CREDIBILITY = 4
SCORE = {"delivered": 1.0, "partially": 0.5, "missed": 0.0}
# Statements the rules read as company-wide growth or margin guidance but that are really about part of the business, or a share. Found by
# reading 14 judged statements on 18-Oct-2026; they are listed, never judged.
_SCOPE = re.compile(r"\b(segments?|divisions?|verticals?|subsidiar\w+|geograph\w+|regions?|business unit|us business|india business|international business|"
                    r"domestic business|(?:in|from|across|within) (?:the )?(?:india|us|u\.s\.|usa|europe|americas?|emea|apac|international|overseas|domestic))\b", re.I)
_SHARE = re.compile(r"\d\s*%\s+of\s+(?:our\s+|the\s+|total\s+|overall\s+|fy\s*'?\d|revenue|sales|business|income|profit|ebitda|assets|book|portfolio|loans|advances)", re.I)

# A statement is judged only when it names its financial year. Reading an unnamed year as "the year in progress" was tried on 18-Oct-2026 and
# rejected: in a sample of 12 such verdicts most were about a segment, an analyst's question or an old guide, and half the verdicts were "missed".
# A wrong "missed" about a real management is worse than "not judged".


def place_year(p: dict) -> tuple[dt.date | None, bool]:
    """(financial year end, inferred?) for a statement; (None, False) when it names no single year. `inferred` is always False."""
    if p["horizon_kind"] == "fy" and p["horizon_end"] is not None:
        return p["horizon_end"], False
    return None, False


JUDGE_WITH = {"revenue_growth": "revenue_growth", "ebitda_margin": "ebitda_margin", "ebit_margin": "ebit_margin", "profit_growth": "profit_growth"}
NOT_COMPARABLE = {"revenue_growth_cc": "guided in constant currency or for one business, while the filings report total revenue in rupees",
                  "margin_generic": "the statement says only 'margin': which one is not clear"}


def verdict_for(op: str, low: float, high: float, actual: float) -> str:
    """actual, low and high are in percent."""
    if op in ("range", "at_least"):
        if actual >= low:
            return "delivered"
        return "partially" if actual >= low - max(1.0, 0.2 * abs(low)) else "missed"
    if op == "at_most":
        if actual <= high:
            return "delivered"
        return "partially" if actual <= high * 1.2 else "missed"
    tol = max(1.0, 0.15 * abs(low))                                       # 'about': all four judged figures are better when higher,
    if actual >= low - tol:                                               # so doing better than the figure is not a broken promise
        return "delivered"
    return "partially" if actual >= low - 2 * tol else "missed"


def judge(engine: M.Engine, security_id: str, p: dict, as_of: AsOf) -> dict:
    out = {"verdict": "not judged", "why": None, "actual": None}
    if p["metric"] == "revenue_growth" and engine.resolution(security_id, as_of).playbook.id == "it_services":
        out["why"] = NOT_COMPARABLE["revenue_growth_cc"] + " (IT services guide in constant currency)"
        return out
    if p["metric"] in NOT_COMPARABLE:
        out["why"] = NOT_COMPARABLE[p["metric"]]
        return out
    judge_metric = JUDGE_WITH.get(p["metric"])
    if judge_metric is None:
        out["why"] = "this kind of statement is listed but not judged yet"
        return out
    quote = p.get("quote") or ""
    scope = _SCOPE.search(quote)
    if scope or _SHARE.search(quote):
        out["why"] = ("the statement is about a segment, business unit or geography, not the company as a whole" if scope
                      else "the percentage is a share of something (of revenue, of the business), not a growth or margin figure")
        return out
    horizon_end, inferred = place_year(p)
    if horizon_end is None:
        out["why"] = "no single financial year in the statement" if p["horizon_kind"] == "none" else "a multi-year target"
        return out
    out["inferred_year"] = inferred
    note = f" (no year was named: read as the financial year in progress at the call, to {horizon_end:%d %b %Y})" if inferred else ""
    when = horizon_end + dt.timedelta(days=RESULTS_LAG_DAYS)
    if as_of.date_ist < when:
        out.update(verdict="pending", why=f"results for the year to {horizon_end:%d %b %Y} are not public yet" + note)
        return out
    try:
        v = engine.compute(judge_metric, security_id, AsOf.end_of(when))
    except ForbiddenMetric as e:                                          # e.g. EBITDA margin for a bank: the sector rules forbid the number
        out["why"] = f"{judge_metric} is not defined for this company's sector ({e.args[0] if e.args else 'playbook rule'})"[:200]
        return out
    if not isinstance(v, Value) or not v.inputs or max(i.period_end for i in v.inputs if i.period_end) != horizon_end:
        out.update(verdict="no data", why="the results of that year are not in the database")
        return out
    actual = v.value * 100
    out.update(verdict=verdict_for(p["op"], p["low"], p["high"], actual), actual=actual,
               why=f"the filing for the year to {horizon_end:%d %b %Y} shows {actual:.1f}%"
               + (" (EBIT margin from the filing; the company's own definition of operating margin may differ slightly)" if p["metric"] == "ebit_margin" else "") + note)
    return out


def dedupe(promises: list[dict]) -> list[dict]:
    """The same figure repeated within one call (prepared remarks, then again in answers) counts once."""
    seen, out = set(), []
    for p in promises:
        k = (p["source_url"], p["metric"], p["op"], p["low"], p["high"], p["horizon_end"])
        if k not in seen:
            seen.add(k)
            out.append(p)
    return out


def credibility(judged: list[dict]) -> dict:
    """Share of judged statements kept (delivered = 1, partially = 0.5, missed = 0), None until enough have been judged."""
    scored = [SCORE[j["verdict"]] for j in judged if j["verdict"] in SCORE]
    n = len(scored)
    return {"judged": n, "score": (sum(scored) / n) if n >= MIN_JUDGED_FOR_CREDIBILITY else None,
            "delivered": sum(1 for j in judged if j["verdict"] == "delivered"), "partially": sum(1 for j in judged if j["verdict"] == "partially"),
            "missed": sum(1 for j in judged if j["verdict"] == "missed"), "pending": sum(1 for j in judged if j["verdict"] == "pending"),
            "needs": MIN_JUDGED_FOR_CREDIBILITY}


def tone_series(calls: list[dict]) -> list[dict]:
    """Per call: the management tone and its change against the previous call and the average of the four before it."""
    out = []
    keys = ("net_tone", "hedge_rate", "negative_rate", "evasive_count")
    for i, c in enumerate(calls):
        t = (c.get("tone") or {}).get("all") or {}
        row = {"announced_at": c["announced_at"], "period_end": c["call_period_end"], "words": t.get("words"), "has_qa": (c.get("tone") or {}).get("has_qa")}
        for k in keys:
            row[k] = t.get(k)
            prev = [x for x in ((p.get("tone") or {}).get("all", {}).get(k) for p in calls[max(0, i - 4):i]) if x is not None]
            row[f"{k}_vs_prev"] = (t.get(k) - ((calls[i - 1].get("tone") or {}).get("all", {}).get(k) or 0)) if i and t.get(k) is not None and (calls[i - 1].get("tone") or {}).get("all", {}).get(k) is not None else None
            row[f"{k}_vs_avg4"] = (t.get(k) - sum(prev) / len(prev)) if len(prev) >= 2 and t.get(k) is not None else None
        out.append(row)
    return out
