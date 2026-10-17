"""Report card: does the score rank forward returns? Pure statistics over stored scores and a PriceBook.

Conventions (docs/ARCHITECTURE §2.1, ADR-003): a score computed after the close of day D is tradable at the open of the next
session; the forward return over h months runs from that open to the open on or after (entry date + h months). A share that
stops trading before the exit is closed at its last close (never dropped silently). Returns are price returns on split/bonus
adjusted prices: dividends are not included. The benchmark is the equal-weight average of the scored universe."""

from __future__ import annotations

import calendar
import datetime as dt
import math
from collections import defaultdict

import numpy as np

from trikal_kasauti.factors import PriceBook


def add_months(d: dt.date, n: int) -> dt.date:
    y, m = divmod(d.year * 12 + d.month - 1 + n, 12)
    return dt.date(y, m + 1, min(d.day, calendar.monthrange(y, m + 1)[1]))


def forward_returns(book: PriceBook, sids: list[str], day: dt.date, months: int, data_end: dt.date) -> dict[str, tuple[float, bool]]:
    """security -> (return, closed_at_last_price_because_delisted). Securities not tradable at the entry are left out."""
    out = {}
    for s in sids:
        e = book.entry_open(s, day)
        if e is None or (e[0] - day).days > 10:
            continue
        x = book.exit_price(s, add_months(e[0], months), data_end)
        if x is None or not e[1]:
            continue
        out[s] = (x[0] / e[1] - 1, x[1])
    return out


def rank_ic(scores: list[float], rets: list[float]) -> float | None:
    if len(scores) < 20:
        return None
    a = np.argsort(np.argsort(scores)).astype(float)
    b = np.argsort(np.argsort(rets)).astype(float)
    if a.std() == 0 or b.std() == 0:
        return None
    return float(np.corrcoef(a, b)[0, 1])


def newey_west_t(x: list[float], lag: int) -> float | None:
    """t-statistic of the mean of a serially correlated series (Bartlett weights, `lag` autocovariances)."""
    n = len(x)
    if n < 4:
        return None
    a = np.asarray(x, dtype=float)
    mu = a.mean()
    d = a - mu
    var = float(d @ d) / n
    for k in range(1, min(lag, n - 1) + 1):
        var += 2 * (1 - k / (lag + 1)) * float(d[k:] @ d[:-k]) / n
    se = math.sqrt(max(var, 0.0) / n)
    return float(mu / se) if se > 0 else None


def decile_of(rank: int, n: int, k: int = 10) -> int:
    """1 = lowest score, k = highest; ranks run 0..n-1."""
    return min(k, int(rank * k / n) + 1)


def evaluate(scores_by_date: dict[dt.date, dict[str, float]], book: PriceBook, horizons: list[int], data_end: dt.date,
             top_fraction: float = 0.1, cost_per_side: float = 0.0025) -> dict:
    """The whole report card. `scores_by_date`: date -> {security: score} (only securities with a score)."""
    dates = sorted(scores_by_date)
    report: dict = {"dates": [d.isoformat() for d in dates], "horizons": {}}
    for h in horizons:
        per_date = []
        for d in dates:
            sc = scores_by_date[d]
            fr = forward_returns(book, list(sc), d, h, data_end)
            if len(fr) < 40:
                continue
            ids = sorted(fr, key=lambda s: (sc[s], s))
            n = len(ids)
            dec = defaultdict(list)
            for i, s in enumerate(ids):
                dec[decile_of(i, n)].append(fr[s][0])
            top = ids[-max(1, round(n * top_fraction)):]
            allr = [fr[s][0] for s in ids]
            ic = rank_ic([sc[s] for s in ids], [fr[s][0] for s in ids])
            per_date.append({"date": d, "n": n, "delisted_exits": sum(1 for s in ids if fr[s][1]), "ic": ic,
                             "deciles": {k: float(np.mean(v)) for k, v in dec.items()},
                             "top": float(np.mean([fr[s][0] for s in top])), "all": float(np.mean(allr))})
        if not per_date:
            report["horizons"][h] = {"dates": 0}
            continue
        ics = [p["ic"] for p in per_date if p["ic"] is not None]
        lag = max(0, math.ceil(h / 3) - 1)                      # quarterly rebalances: windows longer than 3 months overlap
        dmean = {k: float(np.mean([p["deciles"][k] for p in per_date if k in p["deciles"]])) for k in range(1, 11)}
        report["horizons"][h] = {
            "dates": len(per_date), "avg_n": float(np.mean([p["n"] for p in per_date])),
            "decile_mean_return": dmean,
            "top_minus_universe": float(np.mean([p["top"] - p["all"] for p in per_date])),
            "d10_minus_d1": dmean[10] - dmean[1],
            "ic_mean": float(np.mean(ics)) if ics else None, "ic_t_newey_west": newey_west_t(ics, lag) if ics else None,
            "ic_positive_share": float(np.mean([i > 0 for i in ics])) if ics else None,
            "hit_rate_top_beats_universe": float(np.mean([p["top"] > p["all"] for p in per_date])),
            "delisted_exits": sum(p["delisted_exits"] for p in per_date),
            "by_year_ic": _by_year(per_date),
        }
    report["portfolio"] = portfolio(scores_by_date, book, data_end, top_fraction, cost_per_side)
    return report


def _by_year(per_date: list[dict]) -> dict:
    y = defaultdict(list)
    for p in per_date:
        if p["ic"] is not None:
            y[p["date"].year].append(p["ic"])
    return {str(k): {"ic_mean": float(np.mean(v)), "dates": len(v)} for k, v in sorted(y.items())}


def portfolio(scores_by_date: dict[dt.date, dict[str, float]], book: PriceBook, data_end: dt.date, top_fraction: float,
              cost_per_side: float) -> dict:
    """Long-only top fraction, equal weight, rebalanced at each score date and held to the next; costs on the names that change."""
    dates = sorted(scores_by_date)
    held: set[str] = set()
    eq, bm, rows = 1.0, 1.0, []
    peak, mdd, bpeak, bmdd = 1.0, 0.0, 1.0, 0.0
    for d, nxt in zip(dates, dates[1:]):
        sc = scores_by_date[d]
        ids = sorted(sc, key=lambda s: (sc[s], s))
        top = set(ids[-max(1, round(len(ids) * top_fraction)):])
        rets, gone = {}, 0
        for s in sc:
            e = book.entry_open(s, d)
            x = book.entry_open(s, nxt) if nxt <= data_end else None          # next rebalance's entry open = this period's exit
            if e and e[1] and (e[0] - d).days <= 10:
                if x and x[1]:
                    rets[s] = x[1] / e[1] - 1
                else:                                                         # stopped trading: closed at its last close, counted
                    last = book.last_close_if_gone(s, nxt)
                    if last:
                        rets[s] = last / e[1] - 1
                        gone += 1
        t = [rets[s] for s in top if s in rets]
        if len(t) < 5 or len(rets) < 40:
            continue
        turnover = 1.0 if not held else 1 - len(held & top) / len(top)
        gross = float(np.mean(t))
        net = gross - 2 * cost_per_side * turnover if held else gross - cost_per_side
        b = float(np.mean(list(rets.values())))
        eq *= 1 + net
        bm *= 1 + b
        peak, bpeak = max(peak, eq), max(bpeak, bm)
        mdd, bmdd = min(mdd, eq / peak - 1), min(bmdd, bm / bpeak - 1)
        rows.append({"date": d.isoformat(), "gross": gross, "net": net, "benchmark": b, "turnover": turnover, "n_top": len(top), "delisted_exits": gone})
        held = top
    if not rows:
        return {"periods": 0}
    years = (dt.date.fromisoformat(rows[-1]["date"]) - dt.date.fromisoformat(rows[0]["date"])).days / 365.25 + 0.25
    nets = [r["net"] for r in rows]
    return {"periods": len(rows), "years": years, "cagr_net": eq ** (1 / years) - 1, "cagr_benchmark": bm ** (1 / years) - 1,
            "max_drawdown": mdd, "max_drawdown_benchmark": bmdd, "avg_turnover": float(np.mean([r["turnover"] for r in rows])),
            "quarterly_vol": float(np.std(nets)), "cost_per_side": cost_per_side, "rows": rows}
