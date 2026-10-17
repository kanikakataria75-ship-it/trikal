"""Transmission Engine and SHOCK: macro driver → sector → company, from point-in-time historical sensitivities.

Everything here is read through PitReader at the requested as-of. The output is an ESTIMATED PRICE RESPONSE from a
historical regression, labelled with its method, t-statistic, sample size and confidence. It is not an earnings
forecast, and combined shocks are summed, which double counts drivers that move together (the response says so)."""

from __future__ import annotations

import datetime as dt

from trikal_analytics import sensitivity as S
from trikal_core.pit import PitReader
from trikal_core.timeutil import AsOf

METHOD = ("Rolling OLS on monthly returns, trailing 60 months (at least 36): sector return = a + b·driver change + m·market return. "
          "b is the response relative to the market; the market's own response is added back to give the total. "
          "A statistical association, not a causal channel and not an earnings forecast.")
RANK = {"high": 3, "medium": 2, "low": 1}


def driver_state(r: PitReader, a: AsOf) -> list[dict]:
    out = []
    for d in S.DRIVERS.values():
        obs = r.macro(d.series, a, start=a.date_ist - dt.timedelta(days=365 * 6))
        sigma = _sigma(obs, d.kind)
        if not obs:
            out.append({"id": d.id, "label": d.label, "kind": d.kind, "series": d.series, "note": d.note, "latest": None})
            continue
        last = obs[-1]
        year_ago = next((o for o in reversed(obs) if (last["period_end"] - o["period_end"]).days >= 330), None)
        out.append({"id": d.id, "label": d.label, "kind": d.kind, "series": d.series, "note": d.note, "aliases": d.aliases[0],
                    "latest": {"value": last["value"], "period_end": last["period_end"], "known_at": last["known_at"], "precision": last["precision"]},
                    "year_ago": year_ago["value"] if year_ago else None, "sigma": sigma})
    return out


def _sigma(obs: list[dict], kind: str) -> float | None:
    """Standard deviation of the last 60 monthly changes of the driver (its typical monthly move, in its own units)."""
    ch = S.monthly_changes(S.monthly_levels([(o["period_end"], o["value"], o["known_at"]) for o in obs]), kind)
    v = [x for _, (x, _) in sorted(ch.items())][-60:]
    if len(v) < 12:
        return None
    m = sum(v) / len(v)
    return (sum((x - m) ** 2 for x in v) / (len(v) - 1)) ** 0.5


def current_levels(states: list[dict]) -> dict[str, float]:
    return {s["id"]: s["latest"]["value"] for s in states if s["latest"]}


def _market_betas(est: list[dict]) -> dict[str, dict]:
    return {e["driver"]: e for e in est if e["sector"] == S.MARKET}


def overview(r: PitReader, a: AsOf) -> dict:
    """The three planes: drivers (with their latest values), sectors (with their sensitivities), and the notes."""
    est = r.sector_sensitivities(a)
    sectors: dict[str, dict] = {}
    for e in est:
        if e["sector"] == S.MARKET:
            continue
        sectors.setdefault(e["sector"], {"sector": e["sector"], "sens": {}})["sens"][e["driver"]] = {
            "beta": e["beta"], "tstat": e["tstat"], "n": e["n_obs"], "confidence": e["confidence"], "window_end": e["window_end"]}
    mk = {k: {"beta": v["beta"], "tstat": v["tstat"], "n": v["n_obs"], "confidence": v["confidence"]} for k, v in _market_betas(est).items()}
    return {"drivers": driver_state(r, a), "sectors": sorted(sectors.values(), key=lambda x: x["sector"]), "market": mk,
            "estimates": len(est), "method": METHOD}


def shock_table(r: PitReader, a: AsOf, text: str) -> dict:
    """Impact of a (combined) shock on every sector: relative response + the market's response = total."""
    states = driver_state(r, a)
    shocks = S.parse_shocks(text, current_levels(states))
    est = r.sector_sensitivities(a)
    mk = _market_betas(est)
    by_sector: dict[str, dict[str, dict]] = {}
    for e in est:
        if e["sector"] != S.MARKET:
            by_sector.setdefault(e["sector"], {})[e["driver"]] = e
    market_cells = {s.driver: _cell(mk.get(s.driver), s) for s in shocks}
    market_total = sum(c["impact"] for c in market_cells.values() if c["impact"] is not None)
    rows = []
    for sector, per in by_sector.items():
        cells = {s.driver: _cell(per.get(s.driver), s) for s in shocks}
        rel = sum(c["impact"] for c in cells.values() if c["impact"] is not None)
        known = [c for c in cells.values() if c["impact"] is not None]
        conf = min((c["confidence"] for c in known), key=lambda x: RANK[x], default="low")
        rows.append({"sector": sector, "cells": cells, "relative": rel, "market": market_total, "total": rel + market_total,
                     "confidence": conf, "missing": [s.driver for s in shocks if cells[s.driver]["impact"] is None]})
    rows.sort(key=lambda x: x["total"])
    notes = [METHOD]
    if len(shocks) > 1:
        notes.append("Combined shock: the responses to each driver are added. Drivers that move together (crude and the rupee, "
                     "US and Indian yields) are double counted, so treat the total as an upper bound on the interaction.")
    if any(c["confidence"] == "low" for row in rows for c in row["cells"].values() if c["impact"] is not None):
        notes.append("Cells marked low confidence rest on weak statistics (|t| < 1.65, or fewer than 36 observations).")
    sig = {d["id"]: d["sigma"] for d in states if d.get("sigma")}
    big = [f"{S.DRIVERS[s.driver].label} {s.text} (≈{abs(s.delta) / sig[s.driver]:.0f}× its typical monthly move)" for s in shocks
           if s.driver in sig and abs(s.delta) > 3 * sig[s.driver]]
    if big:
        notes.append("Far outside the history this was estimated on: " + "; ".join(big) + ". The response is a straight-line extension of "
                     "ordinary monthly moves, so treat it as an order of magnitude, not a forecast; real stress is usually non-linear.")
    if any(s.driver == "callrate" for s in shocks):
        notes.append(DRIVER_NOTE["callrate"])
    return {"shocks": [{"driver": s.driver, "label": S.DRIVERS[s.driver].label, "delta": s.delta, "text": s.text, "kind": S.DRIVERS[s.driver].kind}
                       for s in shocks],
            "market": {"cells": market_cells, "total": market_total}, "rows": rows, "notes": notes, "as_of_estimates": len(est)}


DRIVER_NOTE = {"callrate": S.DRIVERS["callrate"].note}


def _cell(e: dict | None, s: S.Shock) -> dict:
    if not e:
        return {"beta": None, "tstat": None, "n": None, "confidence": "low", "impact": None}
    return {"beta": e["beta"], "tstat": e["tstat"], "n": e["n_obs"], "confidence": e["confidence"], "impact": S.apply(e["beta"], s)}


def company_table(r: PitReader, a: AsOf, sector: str, text: str, limit: int = 15) -> dict:
    """The sector's largest members with their own estimated response to the same shock (on-demand regressions)."""
    states = driver_state(r, a)
    shocks = S.parse_shocks(text, current_levels(states))
    mkt = dict(r.sector_returns(a, S.MARKET))
    mkt_m = {(d.year, d.month): v for d, v in mkt.items()}
    deltas = {}
    for sh in shocks:
        drv = S.DRIVERS[sh.driver]
        obs = r.macro(drv.series, a)
        deltas[sh.driver] = S.monthly_changes(S.monthly_levels([(o["period_end"], o["value"], o["known_at"]) for o in obs]), drv.kind)
    market = _market_betas(r.sector_sensitivities(a))
    mk_total = sum((market[s.driver]["beta"] * s.delta) for s in shocks if s.driver in market)
    out = []
    for c in r.sector_top(sector, a, limit):
        bars = [(b.trade_date, b.close) for b in r.prices(c["security_id"], a, adjusted=True) if b.close]
        ret = S.monthly_returns_from_closes(bars)
        cells, total, conf = {}, 0.0, "high"
        for sh in shocks:
            dl = deltas.get(sh.driver) or {}
            end = S.latest_window_end(dl, a.ts)
            e = S.estimate(ret, mkt_m, dl, end) if end else None
            if not e:
                cells[sh.driver] = {"beta": None, "tstat": None, "n": None, "confidence": "low", "impact": None}
                conf = "low"
                continue
            cf = S.confidence(e["n"], e["tstat"], 0.0)
            cells[sh.driver] = {"beta": e["beta"], "tstat": e["tstat"], "n": e["n"], "confidence": cf, "impact": S.apply(e["beta"], sh)}
            total += cells[sh.driver]["impact"]
            conf = min(conf, cf, key=lambda x: RANK[x])
        out.append({**c, "cells": cells, "relative": total, "market": mk_total, "total": total + mk_total, "confidence": conf})
    out.sort(key=lambda x: x["total"])
    return {"sector": sector, "shocks": [s.text for s in shocks], "rows": out,
            "notes": [METHOD, "Company estimates use that company's own monthly returns (split/bonus adjusted) over the same window; "
                              "companies listed for fewer than 36 months have no estimate."]}
