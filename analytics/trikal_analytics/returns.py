"""What would an amount invested on one date be worth on another? Split and bonus adjusted; dividends optional.

Pure function over the point-in-time price bars and dividend list the reader gives it. Prices are the exchange's closes; the buy is at the
close of the first session on or after the start date, the valuation at the close of the last session on or before the end date.
Splits and bonuses change the number of shares (shown), never the value. A dividend belongs to the holder of the share the day BEFORE it
goes ex; it is either ignored, kept as cash (no interest), or reinvested at the ex-date close."""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass

MODES = ("ignore", "cash", "reinvest")
MAX_POINTS = 700


class ReturnError(ValueError):
    pass


@dataclass(frozen=True)
class Bar:
    day: dt.date
    adj_close: float          # split/bonus adjusted close (latest basis)
    factor: float             # raw close x factor = adjusted close


def simulate(bars: list[Bar], dividends: list[dict], start: dt.date, end: dt.date, amount: float, mode: str = "cash") -> dict:
    if mode not in MODES:
        raise ReturnError(f"dividends must be one of {MODES}")
    if amount <= 0:
        raise ReturnError("amount must be positive")
    if start >= end:
        raise ReturnError("the start date must be before the end date")
    inside = [b for b in bars if start <= b.day <= end and b.adj_close and b.adj_close > 0]
    if len(inside) < 2:
        raise ReturnError("no traded prices in that period (the company may not have been listed yet, or had stopped trading)")
    first, last = inside[0], inside[-1]
    if (first.day - start).days > 10:
        raise ReturnError(f"the first price on or after {start:%d %b %Y} is {first.day:%d %b %Y}: the company was not trading at the start date")
    n_adj = amount / first.adj_close                       # holdings in latest-basis units: value(t) = n_adj * adjusted close(t)
    cash = 0.0
    paid: list[dict] = []
    skipped = 0
    by_day = {b.day: i for i, b in enumerate(inside)}
    div_by_idx: dict[int, list[dict]] = {}
    for d in sorted(dividends, key=lambda x: x["ex_date"]):
        if not (first.day < d["ex_date"] <= last.day):
            continue
        idx = next((i for i, b in enumerate(inside) if b.day >= d["ex_date"]), None)
        if idx is None or idx == 0:
            continue
        div_by_idx.setdefault(idx, []).append(d)
    curve, events = [], []
    peak, max_dd, peak_day = amount, 0.0, first.day
    for i, b in enumerate(inside):
        if i and abs(b.factor / inside[i - 1].factor - 1) > 1e-9:
            events.append({"date": b.day, "share_multiplier": b.factor / inside[i - 1].factor})
        for d in div_by_idx.get(i, []):
            if mode == "ignore":
                skipped += 1
                continue
            shares_before_ex = n_adj * inside[i - 1].factor        # shares in the units that traded the day before it went ex
            got = d["amount"] * shares_before_ex
            row = {"date": d["ex_date"], "per_share": d["amount"], "shares": shares_before_ex, "cash": got, "subject": d.get("subject")}
            if mode == "reinvest":
                bought = got / b.adj_close
                n_adj += bought
                row["reinvested_at"] = b.adj_close / b.factor
            else:
                cash += got
            paid.append(row)
        v = n_adj * b.adj_close + cash
        if v > peak:
            peak, peak_day = v, b.day
        max_dd = min(max_dd, v / peak - 1)
        curve.append((b.day, v))
    end_value_price = n_adj * last.adj_close
    total = end_value_price + cash
    years = (last.day - first.day).days / 365.25
    step = max(1, len(curve) // MAX_POINTS)
    pts = curve[::step] + ([curve[-1]] if (len(curve) - 1) % step else [])
    price_only = amount * last.adj_close / first.adj_close
    return {
        "mode": mode, "buy_date": first.day, "end_date": last.day, "years": years, "amount": amount,
        "buy_price_traded": first.adj_close / first.factor, "end_price_traded": last.adj_close / last.factor,
        "shares_bought": amount / (first.adj_close / first.factor), "shares_at_end": n_adj * last.factor,
        "value_price_only": price_only, "value_shares": end_value_price, "dividend_cash_kept": cash, "total_value": total,
        "gain": total - amount, "return": total / amount - 1,
        "return_price_only": price_only / amount - 1,
        "cagr": (total / amount) ** (1 / years) - 1 if years >= 1 / 12 else None,
        "cagr_price_only": (price_only / amount) ** (1 / years) - 1 if years >= 1 / 12 else None,
        "dividends_received": paid, "dividends_total": sum(p["cash"] for p in paid), "dividends_ignored": skipped,
        "events": events, "peak_value": peak, "peak_day": peak_day, "max_drawdown": max_dd,
        "curve": [{"date": d, "value": v} for d, v in pts],
    }
