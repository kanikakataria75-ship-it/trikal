"""Historical price sensitivity of sectors and companies to macro drivers, and the SHOCK simulator built on it.

What this is — and is not (FORMULAS.md §Sensitivity):
  * An OLS estimate on monthly data:  r_s,t = a + b · Δd_t + m · r_mkt,t + e   over the trailing 60 months (>= 36).
    r_s is the sector's equal-weight return, r_mkt the equal-weight return of the whole universe, Δd the driver's change
    (log change for prices, FX and indices; percentage-point change for interest rates).
    So `b` is the sector's response to the driver RELATIVE TO THE MARKET; the market's own response to the driver is
    estimated separately (sector "__MKT__") and the shock table shows both and their sum.
  * A statistical association, not a causal channel and not an earnings forecast. Each estimate carries its t-statistic,
    number of observations, R² and a confidence label; combined shocks add the individual responses, which double counts
    where drivers move together (the output says so).
  * Point in time: an estimate computed with data through month m is usable only from the moment the driver value for
    month m was public (`usable_from`); nothing later is read.
"""

from __future__ import annotations

import datetime as dt
import math
import re
from dataclasses import dataclass

import numpy as np

WINDOW = 60
MIN_OBS = 36
MARKET = "__MKT__"


@dataclass(frozen=True)
class Driver:
    id: str
    label: str
    series: str            # macro_series id
    kind: str              # log: log change (prices, FX, indices) · pp: percentage-point change (rates)
    aliases: tuple[str, ...]
    note: str = ""


DRIVERS: dict[str, Driver] = {d.id: d for d in (
    Driver("brent", "Brent crude", "brent", "log", ("CRUDE", "BRENT", "OIL")),
    Driver("usdinr", "USD/INR", "usdinr", "log", ("INR", "USDINR", "RUPEE", "USD")),
    Driver("callrate", "Call-money rate", "ind_interbank", "pp", ("REPO", "CALL", "POLICY"),
           "OECD monthly call-money rate: a proxy for the RBI repo rate (the policy-rate series itself is not ingested yet)"),
    Driver("ind10y", "India 10Y G-sec yield", "ind_10y", "pp", ("GSEC", "G-SEC", "IND10Y", "YIELD")),
    Driver("ust10y", "US 10Y Treasury yield", "ust10y", "pp", ("UST", "UST10Y", "US10Y")),
    Driver("copper", "Copper", "wb_copper", "log", ("COPPER", "CU")),
    Driver("iron_ore", "Iron ore", "wb_iron_ore", "log", ("IRON", "IRONORE", "STEEL")),
    Driver("coal", "Coal (Australian)", "wb_coal_aus", "log", ("COAL",)),
    Driver("gold", "Gold", "wb_gold", "log", ("GOLD",)),
    Driver("vix", "VIX", "vix", "log", ("VIX", "FEAR")),
)}
ALIASES = {a: d.id for d in DRIVERS.values() for a in (*d.aliases, d.id.upper())}


# ---------------------------------------------------------------------------------------------- monthly series
def month_key(d: dt.date) -> tuple[int, int]:
    return d.year, d.month


def month_end(y: int, m: int) -> dt.date:
    return (dt.date(y, m, 28) + dt.timedelta(days=4)).replace(day=1) - dt.timedelta(days=1)


def prev_month(y: int, m: int) -> tuple[int, int]:
    return (y - 1, 12) if m == 1 else (y, m - 1)


def monthly_levels(obs: list[tuple[dt.date, float, dt.datetime]]) -> dict[tuple[int, int], tuple[float, dt.datetime]]:
    """Last observation of every calendar month: (value, known_at). `obs` = (period_end, value, known_at), any order."""
    out: dict[tuple[int, int], tuple[dt.date, float, dt.datetime]] = {}
    for pe, v, ka in obs:
        k = month_key(pe)
        if k not in out or pe >= out[k][0]:
            out[k] = (pe, v, ka)
    return {k: (v, ka) for k, (_, v, ka) in out.items()}


def monthly_changes(levels: dict[tuple[int, int], tuple[float, dt.datetime]], kind: str) -> dict[tuple[int, int], tuple[float, dt.datetime]]:
    """Change of consecutive months only (a gap is a missing month, never bridged). log: ln(v1/v0) · pp: v1 - v0."""
    out = {}
    for (y, m), (v, ka) in levels.items():
        p = levels.get(prev_month(y, m))
        if not p:
            continue
        if kind == "log":
            if v <= 0 or p[0] <= 0:
                continue
            out[(y, m)] = (math.log(v / p[0]), ka)
        else:
            out[(y, m)] = (v - p[0], ka)
    return out


# ---------------------------------------------------------------------------------------------- regression
def ols(y: np.ndarray, X: np.ndarray) -> dict | None:
    """OLS with intercept already in X. Returns beta, standard errors, R², n; None if rank deficient / too few rows."""
    n, k = X.shape
    if n <= k + 2:
        return None
    try:
        xtx_inv = np.linalg.inv(X.T @ X)
    except np.linalg.LinAlgError:
        return None
    beta = xtx_inv @ X.T @ y
    resid = y - X @ beta
    dof = n - k
    s2 = float(resid @ resid) / dof
    se = np.sqrt(np.diag(xtx_inv) * s2)
    tss = float(((y - y.mean()) ** 2).sum())
    return {"beta": beta, "se": se, "r2": (1 - float(resid @ resid) / tss) if tss > 0 else 0.0, "n": n}


def confidence(n: int, t: float, back_projected_share: float) -> str:
    """high: >= 48 obs, |t| >= 2.5 and sector labels mostly real · medium: >= 36 obs, |t| >= 1.65 · low otherwise."""
    if n >= 48 and abs(t) >= 2.5 and back_projected_share < 0.5:
        return "high"
    if n >= MIN_OBS and abs(t) >= 1.65:
        return "medium"
    return "low"


def estimate(sector_ret: dict[tuple[int, int], float], mkt_ret: dict[tuple[int, int], float],
             delta: dict[tuple[int, int], tuple[float, dt.datetime]], end: tuple[int, int], window: int = WINDOW,
             market_only: bool = False) -> dict | None:
    """One regression with the window ending at month `end`. market_only: sector IS the market, so no market control."""
    months, y, d, x_m = [], [], [], []
    ym = end
    for _ in range(window):
        if ym in sector_ret and ym in delta and ym in mkt_ret:
            months.append(ym)
            y.append(sector_ret[ym])
            d.append(delta[ym][0])
            x_m.append(mkt_ret[ym])
        ym = prev_month(*ym)
    if len(months) < MIN_OBS:
        return None
    cols = [np.ones(len(d)), np.array(d)] + ([] if market_only else [np.array(x_m)])
    fit = ols(np.array(y), np.column_stack(cols))
    if not fit:
        return None
    t = float(fit["beta"][1] / fit["se"][1]) if fit["se"][1] > 0 else 0.0
    return {"beta": float(fit["beta"][1]), "tstat": t, "r2": fit["r2"], "n": fit["n"],
            "beta_mkt": None if market_only else float(fit["beta"][2]),
            "usable_from": max(delta[m][1] for m in months[:1]), "months": months}


# ---------------------------------------------------------------------------------------------- the shock grammar
class ShockError(ValueError):
    pass


@dataclass(frozen=True)
class Shock:
    driver: str
    delta: float            # in the driver's own units: log change (kind log) or percentage points (kind pp)
    text: str               # human form, e.g. "+20%", "to 90", "+50 bp"


_NUM = r"[+-]?\d+(?:\.\d+)?"


def parse_shocks(text: str, current: dict[str, float] | None = None) -> list[Shock]:
    """`CRUDE +20` · `INR 90` · `REPO +50bp` · `UST10Y -25bp & GOLD +10%` (separator: & or ,).
    A signed number means a change (percent for prices, bp or pp for rates); an unsigned number is a target LEVEL
    (needs the driver's current value). Raises ShockError with a message the UI can show."""
    out: list[Shock] = []
    for part in re.split(r"\s*(?:&|,|\bAND\b)\s*", text.strip(), flags=re.I):
        if not part:
            continue
        m = re.fullmatch(rf"([A-Za-z0-9\-]+)\s+({_NUM})\s*(%|bp|bps|pp)?", part.strip(), flags=re.I)
        if not m:
            raise ShockError(f"cannot read “{part}”: use e.g. CRUDE +20 · INR 90 · REPO +50bp")
        name, num, unit = m.group(1).upper(), float(m.group(2)), (m.group(3) or "").lower()
        did = ALIASES.get(name)
        if not did:
            raise ShockError(f"unknown driver “{name}”. Known: " + ", ".join(sorted({d.aliases[0] for d in DRIVERS.values()})))
        d = DRIVERS[did]
        signed = m.group(2)[0] in "+-"
        if d.kind == "pp":
            if unit in ("bp", "bps"):
                out.append(Shock(did, num / 100.0, f"{num:+g} bp"))
            elif unit == "pp":
                out.append(Shock(did, num, f"{num:+g} pp"))
            elif signed:                                   # "REPO +50": rates are quoted in basis points
                out.append(Shock(did, num / 100.0, f"{num:+g} bp"))
            else:                                          # an unsigned number is a target level, in percent
                cur = (current or {}).get(did)
                if cur is None:
                    raise ShockError(f"{name}: current level unknown; give a change such as {name} +50bp")
                out.append(Shock(did, num - cur, f"to {num:g}%"))
        else:
            if unit in ("bp", "bps", "pp"):
                raise ShockError(f"{name}: use a percent change (e.g. {name} +10) or a target level")
            if signed or unit == "%":
                if num <= -100:
                    raise ShockError(f"{name}: a fall of {num:g}% is impossible")
                out.append(Shock(did, math.log1p(num / 100.0), f"{num:+g}%"))
            else:
                cur = (current or {}).get(did)
                if cur is None or cur <= 0 or num <= 0:
                    raise ShockError(f"{name}: current level unknown; give a change such as {name} +10")
                out.append(Shock(did, math.log(num / cur), f"to {num:g}"))
    if not out:
        raise ShockError("empty shock")
    return out


def apply(beta: float, shock: Shock) -> float:
    """Estimated return impact (decimal) of one shock on something with sensitivity `beta` to that driver."""
    return beta * shock.delta


# ---------------------------------------------------------------------------------------------- company level
def monthly_returns_from_closes(bars: list[tuple[dt.date, float]]) -> dict[tuple[int, int], float]:
    """Monthly returns from (date, adjusted close) bars: last bar of each month; consecutive months only."""
    last: dict[tuple[int, int], tuple[dt.date, float]] = {}
    for d, c in bars:
        k = month_key(d)
        if c and c > 0 and (k not in last or d >= last[k][0]):
            last[k] = (d, c)
    out = {}
    for (y, m), (_, c) in last.items():
        p = last.get(prev_month(y, m))
        if p:
            r = c / p[1] - 1.0
            if -1.0 < r <= 3.0:
                out[(y, m)] = r
    return out


def latest_window_end(delta: dict[tuple[int, int], tuple[float, dt.datetime]], now: dt.datetime) -> tuple[int, int] | None:
    """The last month whose driver change was already public at `now` (and whose month had ended)."""
    ok = [k for k, (_, ka) in delta.items() if ka <= now and month_end(*k) < now.date()]
    return max(ok) if ok else None
