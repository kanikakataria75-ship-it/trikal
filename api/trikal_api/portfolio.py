"""Watchlist and portfolio views: one company's market snapshot, alerts since a date, and a holdings valuation.

Stateless: the lists live in the user's browser and are sent with each request, so nothing about anyone's holdings is stored on the server.
Everything is as of a date (prices, scores and filings known by then); alerts compare with the `since` date the browser last looked."""

from __future__ import annotations

import datetime as dt

from trikal_core.pit import PitReader
from trikal_core.timeutil import AsOf

SCORE_MOVE = 5.0          # points of KASAUTI score
PRICE_MOVE = 0.05         # one-day move worth a mention
NEAR_EXTREME = 0.01       # within 1% of the 52-week high or low


def snapshot(r: PitReader, sid: str, a: AsOf, code: str) -> dict:
    prof = r.profile(sid, a)
    bars = [b for b in r.prices(sid, a, start=a.date_ist - dt.timedelta(days=380)) if b.close]
    last = r.last_price(sid, a)
    out: dict = {"code": code, "security_id": sid, "name": prof["name"], "sector": prof["sector"], "price": None, "price_date": None, "change_1d": None,
                 "high_52w": None, "low_52w": None, "pos_52w": None, "return_1y": None}
    if last:
        out["price_date"], out["price"] = last[0], last[1]
    if len(bars) >= 2:
        out["change_1d"] = bars[-1].close / bars[-2].close - 1
        yr = bars[-252:]
        hi, lo = max(b.close for b in yr), min(b.close for b in yr)
        out["high_52w"], out["low_52w"] = hi, lo
        out["pos_52w"] = (bars[-1].close - lo) / (hi - lo) if hi > lo else None
        if len(bars) > 250:
            out["return_1y"] = bars[-1].close / bars[-252].close - 1
    days = [d for d in r.kasauti_dates(1) if d <= a.date_ist]
    scores = []
    for d in days[-2:]:
        row = (r.kasauti_scores(1, d, sid) or [None])[0]
        scores.append(row["score"] if row and row["score"] is not None else None)
    out["score"] = scores[-1] if scores else None
    out["score_prev"] = scores[-2] if len(scores) > 1 else None
    out["score_date"] = days[-1] if days else None
    res = [e for e in r.timeline(sid, a) if e["type"] == "results"]
    out["last_results"] = {"period": res[-1].get("period_end"), "known_at": res[-1]["known_at"]} if res else None
    out["upcoming"] = r.upcoming_actions(sid, a, 14)
    out["meetings"] = [m for m in r.board_meetings(a, a.date_ist, a.date_ist + dt.timedelta(days=21), [code]) if m["purpose"]]
    return out


def alerts_for(snap: dict, since: dt.date | None) -> list[dict]:
    out: list[dict] = []
    c = snap["code"]
    if snap["last_results"] and since and snap["last_results"]["known_at"].date() > since:
        p = snap["last_results"]["period"]
        out.append({"code": c, "type": "results", "severity": "info", "text": f"{c}: results {'for ' + p.strftime('%b %Y') + ' ' if p else ''}published {snap['last_results']['known_at']:%d %b}"})
    if snap["score"] is not None and snap["score_prev"] is not None and abs(snap["score"] - snap["score_prev"]) >= SCORE_MOVE:
        up = snap["score"] > snap["score_prev"]
        out.append({"code": c, "type": "score", "severity": "good" if up else "warn", "text": f"{c}: KASAUTI score {snap['score_prev']:.0f} → {snap['score']:.0f}"})
    if snap["change_1d"] is not None and abs(snap["change_1d"]) >= PRICE_MOVE:
        out.append({"code": c, "type": "price", "severity": "good" if snap["change_1d"] > 0 else "warn", "text": f"{c}: {snap['change_1d'] * 100:+.1f}% on the last session"})
    if snap["pos_52w"] is not None and snap["high_52w"] and snap["price"]:
        if snap["pos_52w"] >= 1 - NEAR_EXTREME:
            out.append({"code": c, "type": "high", "severity": "info", "text": f"{c}: at its 52-week high"})
        elif snap["pos_52w"] <= NEAR_EXTREME:
            out.append({"code": c, "type": "low", "severity": "warn", "text": f"{c}: at its 52-week low"})
    for m in snap.get("meetings", []):
        out.append({"code": c, "type": "meeting", "severity": "info", "text": f"{c}: board meeting on {m['date']:%d %b} ({m['purpose']})"})
    for u in snap["upcoming"]:
        out.append({"code": c, "type": "action", "severity": "info", "text": f"{c}: {u['kind']} goes ex on {u['ex_date']:%d %b} ({u['subject']})"})
    return out


def parse_holdings(text: str) -> list[dict]:
    """'TCS:10:3200,INFY:5' -> code, quantity, optional average buy price."""
    out = []
    for part in [p for p in text.split(",") if p.strip()]:
        bits = part.strip().split(":")
        try:
            out.append({"code": bits[0].strip().upper(), "qty": float(bits[1]), "avg": float(bits[2]) if len(bits) > 2 and bits[2] else None})
        except (IndexError, ValueError) as e:
            raise ValueError(f"bad holding {part!r}: write CODE:quantity or CODE:quantity:average-price") from e
    return out


def valuation(rows: list[dict]) -> dict:
    """Totals and the sector mix of holdings that already carry a snapshot, qty and optional avg."""
    value = sum(h["value"] for h in rows if h.get("value") is not None)
    cost = sum(h["cost"] for h in rows if h.get("cost") is not None and h.get("value") is not None)
    day = sum(h["day_pnl"] for h in rows if h.get("day_pnl") is not None)
    sectors: dict[str, float] = {}
    for h in rows:
        if h.get("value"):
            sectors[h["sector"] or "Unclassified"] = sectors.get(h["sector"] or "Unclassified", 0.0) + h["value"]
    for h in rows:
        h["weight"] = (h["value"] / value) if value and h.get("value") else None
    scored = [(h["score"], h["value"]) for h in rows if h.get("score") is not None and h.get("value")]
    wscore = sum(s * v for s, v in scored) / sum(v for _, v in scored) if scored else None
    return {"value": value, "cost": cost or None, "pnl": (value - cost) if cost else None, "pnl_pct": (value / cost - 1) if cost else None,
            "day_pnl": day, "day_pct": (day / (value - day)) if value - day else None,
            "sectors": [{"sector": k, "value": v, "weight": v / value} for k, v in sorted(sectors.items(), key=lambda x: -x[1])] if value else [],
            "weighted_score": wscore, "scored_share": (sum(v for _, v in scored) / value) if value and scored else None}
