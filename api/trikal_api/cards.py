"""Three views that answer "what is going on with this company" from stored point-in-time facts: the latest results compared with the
quarter before and the year before, the KASAUTI score over time, and the sector heatmap rows.

Nothing here is estimated: a figure that is not in the filings is None. Everything is as of a date, so the card of an old date shows the
results that were public then."""

from __future__ import annotations

import datetime as dt

from trikal_core.pit import PitReader
from trikal_core.timeutil import AsOf

ITEMS = ["revenue_from_operations", "interest_earned", "other_income", "profit_before_exceptional_and_tax", "profit_before_tax", "finance_costs",
         "depreciation_amortisation", "profit_after_tax", "profit_attributable_to_owners", "eps_diluted", "bank_operating_profit_before_provisions"]
GROUPS = [("promoter", "Promoter"), ("fpi", "Foreign portfolio investors"), ("mutual_funds", "Mutual funds"), ("insurance", "Insurance"), ("retail", "Retail")]


def _near(periods: list[dt.date], target: dt.date, slack: int = 12) -> dt.date | None:
    best = min(periods, key=lambda p: abs((p - target).days), default=None)
    return best if best is not None and abs((best - target).days) <= slack else None


def _series(r: PitReader, sid: str, a: AsOf) -> dict[dt.date, dict]:
    """Quarterly (3-month) values by period end, with the date each became public."""
    out: dict[dt.date, dict] = {}
    for v in r.financials(sid, a, ITEMS, basis="auto"):
        if v.months != 3:
            continue
        q = out.setdefault(v.period_end, {"known_at": v.known_at})
        q[v.line_item] = v.value
        if v.known_at > q["known_at"]:
            q["known_at"] = v.known_at
    return out


def _q(x: dict | None) -> dict:
    """One quarter's figures in the shape the card shows."""
    if not x:
        return {}
    bank = x.get("revenue_from_operations") is None and x.get("interest_earned") is not None
    rev = x.get("interest_earned") if bank else x.get("revenue_from_operations")
    pat = x.get("profit_attributable_to_owners")
    if pat is None:
        pat = x.get("profit_after_tax")
    ebitda = None
    if bank:
        ebitda = x.get("bank_operating_profit_before_provisions")
    else:
        pbt = x.get("profit_before_exceptional_and_tax")
        if pbt is None:
            pbt = x.get("profit_before_tax")
        if pbt is not None and x.get("finance_costs") is not None and x.get("depreciation_amortisation") is not None:
            ebitda = pbt + x["finance_costs"] + x["depreciation_amortisation"] - (x.get("other_income") or 0.0)
    return {"revenue": rev, "ebitda": ebitda, "ebitda_margin": (ebitda / rev) if ebitda is not None and rev else None,
            "pbt": x.get("profit_before_tax"), "pat": pat, "net_margin": (pat / rev) if pat is not None and rev else None, "eps": x.get("eps_diluted"), "bank": bank}


def _pct(a: float | None, b: float | None) -> float | None:
    return None if a is None or not b or (b < 0) else a / b - 1


def results_card(r: PitReader, sid: str, a: AsOf, promises: list[dict]) -> dict:
    series = _series(r, sid, a)
    done = sorted(p for p, x in series.items() if _q(x).get("revenue") is not None)
    if not done:
        return {"available": False, "reason": "no quarterly results are stored for this company at this date"}
    cur_end = done[-1]
    prev_end = _near(done, cur_end - dt.timedelta(days=91))
    yago_end = _near(done, cur_end - dt.timedelta(days=365))
    cur, prev, yago = _q(series[cur_end]), _q(series.get(prev_end)), _q(series.get(yago_end))
    bank = cur.get("bank")

    def money(key: str, label: str) -> dict:
        return {"label": label, "kind": "money", "now": cur.get(key), "prev": prev.get(key), "yago": yago.get(key),
                "qoq": _pct(cur.get(key), prev.get(key)), "yoy": _pct(cur.get(key), yago.get(key))}

    def ratio(key: str, label: str) -> dict:
        n, p, y = cur.get(key), prev.get(key), yago.get(key)
        return {"label": label, "kind": "ratio", "now": n, "prev": p, "yago": y, "qoq": None if n is None or p is None else n - p, "yoy": None if n is None or y is None else n - y}

    rows = [money("revenue", "Interest earned" if bank else "Revenue"), money("ebitda", "Operating profit before provisions" if bank else "EBITDA (computed)"),
            ratio("ebitda_margin", "Operating profit / interest earned" if bank else "Operating margin"), money("pbt", "Profit before tax"), money("pat", "Net profit"), ratio("net_margin", "Net profit / interest earned" if bank else "Net margin"), money("eps", "EPS (diluted)")]
    rows = [x for x in rows if x["now"] is not None]
    known = series[cur_end]["known_at"]

    own = r.ownership(sid, a, 3)
    holding = []
    if len(own) >= 2:
        for k, lab in GROUPS:
            n, p = own[0].get(k), own[1].get(k)
            if n is not None and p is not None:
                holding.append({"label": lab, "now": n, "prev": p, "delta": n - p})
    ks = [d for d in r.kasauti_dates(1) if d <= a.date_ist][-2:]
    score = []
    for d in ks:
        s = (r.kasauti_scores(1, d, sid) or [None])[0]
        score.append({"date": d, "score": s["score"] if s else None, "pillars": ({k: v["score"] for k, v in s["detail"]["pillars"].items()} if s and s.get("detail") else {})})
    moved = []
    if len(score) == 2:
        for k in score[1]["pillars"]:
            n, p = score[1]["pillars"].get(k), score[0]["pillars"].get(k)
            if n is not None and p is not None:
                moved.append({"pillar": k, "now": n * 100, "prev": p * 100, "delta": (n - p) * 100})
        moved.sort(key=lambda x: -abs(x["delta"]))

    # what management had said about the year that this result completes (the latest March year-end already filed)
    fy_end = max((p for p in done if p.month == 3 and p <= cur_end), default=None)
    said = [{k: p.get(k) for k in ("call_period_end", "quote", "metric", "verdict", "actual", "low", "high", "op", "why")} for p in promises
            if fy_end and p.get("horizon_end") == fy_end and p.get("verdict") in ("delivered", "partially", "missed")][:6]

    # the price around the day the numbers came out
    react = None
    day = (known + dt.timedelta(hours=5, minutes=30)).date()      # the exchange's calendar day (known_at is UTC)
    if day <= a.date_ist:
        bars = [b for b in r.prices(sid, a, start=day - dt.timedelta(days=12)) if b.close]
        before = [b for b in bars if b.trade_date < day]
        after = [b for b in bars if b.trade_date >= day]
        if before and after:
            base = before[-1].close
            react = {"base_date": before[-1].trade_date, "day1": after[0].close / base - 1 if len(after) >= 1 else None,
                     "day5": after[4].close / base - 1 if len(after) >= 5 else None}
    return {"available": True, "period_end": cur_end, "prev_end": prev_end, "yago_end": yago_end, "known_at": known, "rows": rows, "holding": holding,
            "holding_periods": [own[0]["period_end"], own[1]["period_end"]] if len(own) >= 2 else None, "score": score, "pillar_moves": moved[:4],
            "said": said, "said_fy": fy_end, "reaction": react,
            "note": "figures are from the filings public at the as-of date (consolidated where reported); EBITDA is computed as profit before tax + interest + depreciation - other income"}


def score_history(r: PitReader, sid: str, a: AsOf, version: int = 1) -> dict:
    """The stored KASAUTI score at every scoring date up to as-of, with the price at each date (adjusted as known then)."""
    days = [d for d in r.kasauti_dates(version) if d <= a.date_ist]
    pts = []
    for d in days:
        s = (r.kasauti_scores(version, d, sid) or [None])[0]
        if not s or s["score"] is None:
            continue
        pil = {k: v["score"] for k, v in (s["detail"] or {}).get("pillars", {}).items()}
        pts.append({"date": d, "score": s["score"], "confidence": s["confidence"], "peer_group": s["peer_group"], "n_peers": s["n_peers"], "pillars": pil,
                    "reconstructed": bool(s["computed_at"] and (s["computed_at"].date() - d).days > 7)})
    if not pts:
        return {"available": False, "reason": "not scored at any date up to this as-of"}
    bars = [b for b in r.prices(sid, a, start=pts[0]["date"] - dt.timedelta(days=10)) if b.close]
    j = 0
    for p in pts:
        while j + 1 < len(bars) and bars[j + 1].trade_date <= p["date"]:
            j += 1
        p["price"] = bars[j].close if bars and bars[j].trade_date <= p["date"] else None
    return {"available": True, "points": pts, "note": "scores are in-sample reconstructions from point-in-time inputs unless marked live; price is the adjusted close on the scoring date"}
