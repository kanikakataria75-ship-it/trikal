"""Valuation maths: pure functions, no data access, every assumption an explicit argument.

There are no hidden default rates here: discount rates and growth rates are always parameters. The Lab (lab.py)
labels each one as taken from point-in-time data, supplied by the user, or a template to be confirmed.

Conventions: cash flows at year end; year 1 is the first forecast year; growth fades linearly from `g_start` in
year 1 to `g_terminal` in year `years`, then grows at `g_terminal` forever. Requires rate > g_terminal.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Sequence


class ValuationError(ValueError):
    """The inputs make the model meaningless (rate <= growth, non-positive base, no solution)."""


def _check_rate(rate: float, g: float, what: str) -> None:
    if rate <= g:
        raise ValuationError(f"{what}: discount rate {rate:.4f} must exceed terminal growth {g:.4f}")


def growth_path(g_start: float, g_terminal: float, years: int) -> list[float]:
    """Linear fade from g_start (year 1) to g_terminal (year `years`)."""
    if years < 1:
        raise ValuationError("years must be >= 1")
    if years == 1:
        return [g_start]
    return [g_start + (g_terminal - g_start) * t / (years - 1) for t in range(years)]


def project(base: float, g_start: float, g_terminal: float, years: int) -> list[float]:
    out, cur = [], base
    for g in growth_path(g_start, g_terminal, years):
        cur *= 1 + g
        out.append(cur)
    return out


def present_value(flows: Sequence[float], rate: float) -> float:
    return sum(cf / (1 + rate) ** t for t, cf in enumerate(flows, start=1))


def terminal_value(last_flow: float, rate: float, g: float) -> float:
    _check_rate(rate, g, "terminal value")
    return last_flow * (1 + g) / (rate - g)


@dataclass(frozen=True)
class DcfResult:
    enterprise_value: float | None       # None for FCFE/DDM (equity-level models)
    equity_value: float
    per_share: float | None
    pv_explicit: float
    pv_terminal: float
    terminal_share: float                # how much of the value sits beyond the explicit years
    flows: tuple[float, ...]


def dcf_fcff(fcff0: float, wacc: float, g_start: float, g_terminal: float, years: int, net_debt: float,
             minorities: float = 0.0, shares: float | None = None) -> DcfResult:
    """Enterprise value = PV of free cash flow to the firm; equity = EV - net debt - minorities."""
    if fcff0 <= 0:
        raise ValuationError("FCFF base <= 0: a growth-fade DCF needs a positive base cash flow")
    flows = project(fcff0, g_start, g_terminal, years)
    pv_e = present_value(flows, wacc)
    pv_t = terminal_value(flows[-1], wacc, g_terminal) / (1 + wacc) ** years
    ev = pv_e + pv_t
    eq = ev - net_debt - minorities
    return DcfResult(ev, eq, eq / shares if shares else None, pv_e, pv_t, pv_t / ev, tuple(flows))


def dcf_fcfe(fcfe0: float, cost_of_equity: float, g_start: float, g_terminal: float, years: int,
             shares: float | None = None) -> DcfResult:
    """Equity value = PV of free cash flow to equity at the cost of equity (no debt adjustment)."""
    if fcfe0 <= 0:
        raise ValuationError("FCFE base <= 0")
    flows = project(fcfe0, g_start, g_terminal, years)
    pv_e = present_value(flows, cost_of_equity)
    pv_t = terminal_value(flows[-1], cost_of_equity, g_terminal) / (1 + cost_of_equity) ** years
    eq = pv_e + pv_t
    return DcfResult(None, eq, eq / shares if shares else None, pv_e, pv_t, pv_t / eq, tuple(flows))


def reverse_dcf_growth(equity_value_market: float, fcff0: float, wacc: float, g_terminal: float, years: int,
                       net_debt: float, minorities: float = 0.0, lo: float = -0.30, hi: float = 0.80) -> float:
    """The year-1 growth rate (fading to g_terminal) at which the DCF equity value equals the market value.

    Bisection; raises ValuationError when the market value is outside what any rate in [lo, hi] can produce
    (the honest answer is then "no solution", not the nearest bound)."""
    def f(g: float) -> float:
        return dcf_fcff(fcff0, wacc, g, g_terminal, years, net_debt, minorities).equity_value - equity_value_market

    flo, fhi = f(lo), f(hi)
    if flo > 0:
        raise ValuationError(f"market value is below the value at {lo:.0%} growth: no solution in range")
    if fhi < 0:
        raise ValuationError(f"market value exceeds the value at {hi:.0%} growth: no solution in range")
    a, b = lo, hi
    for _ in range(200):
        m = (a + b) / 2
        fm = f(m)
        if abs(fm) < 1e-9 * max(1.0, abs(equity_value_market)):
            return m
        a, b = (m, b) if fm < 0 else (a, m)
    return (a + b) / 2


def ddm(dps0: float, cost_of_equity: float, g_start: float, g_terminal: float, years: int) -> DcfResult:
    """Dividend discount model per share (multi-stage with a linear fade)."""
    if dps0 <= 0:
        raise ValuationError("DPS base <= 0")
    flows = project(dps0, g_start, g_terminal, years)
    pv_e = present_value(flows, cost_of_equity)
    pv_t = terminal_value(flows[-1], cost_of_equity, g_terminal) / (1 + cost_of_equity) ** years
    return DcfResult(None, pv_e + pv_t, pv_e + pv_t, pv_e, pv_t, pv_t / (pv_e + pv_t), tuple(flows))


def justified_pb(roe: float, cost_of_equity: float, g: float) -> float:
    """Justified P/B = (ROE - g) / (Ke - g)  (Damodaran, Investment Valuation 3e ch.21)."""
    _check_rate(cost_of_equity, g, "justified P/B")
    return (roe - g) / (cost_of_equity - g)


def justified_pe(payout: float, cost_of_equity: float, g: float) -> float:
    _check_rate(cost_of_equity, g, "justified P/E")
    return payout * (1 + g) / (cost_of_equity - g)


def residual_income(book0: float, roe_path: Sequence[float], cost_of_equity: float, g_terminal: float,
                    payout: float = 0.0, persistence: float = 1.0, shares: float | None = None) -> DcfResult:
    """Residual income value of equity: B0 + sum PV(RI_t) + PV(terminal RI).

    Book value rolls forward B_t = B_{t-1} (1 + ROE_t (1 - payout)). RI_t = (ROE_t - Ke) B_{t-1}.
    After the explicit years the residual income is carried at `persistence` x last RI growing at g_terminal."""
    if book0 <= 0:
        raise ValuationError("book value <= 0")
    b, pv, last_ri = book0, 0.0, 0.0
    flows = []
    for t, roe in enumerate(roe_path, start=1):
        ri = (roe - cost_of_equity) * b
        flows.append(ri)
        pv += ri / (1 + cost_of_equity) ** t
        b *= 1 + roe * (1 - payout)
        last_ri = ri
    n = len(roe_path)
    _check_rate(cost_of_equity, g_terminal, "residual income terminal")
    tv = persistence * last_ri * (1 + g_terminal) / (cost_of_equity - g_terminal) / (1 + cost_of_equity) ** n
    eq = book0 + pv + tv
    return DcfResult(None, eq, eq / shares if shares else None, book0 + pv, tv, tv / eq if eq else 0.0, tuple(flows))


@dataclass(frozen=True)
class SotpPart:
    name: str
    value: float                 # 100% value of the part (market cap of a listed subsidiary, or an EV)
    stake: float                 # fraction owned by the holding company
    basis: str                   # 'market' (listed, point-in-time price) or 'assumed' (unlisted: user multiple)


def sotp(parts: Sequence[SotpPart], holdco_net_debt: float, holdco_discount: float,
         shares: float | None = None) -> DcfResult:
    """Sum of the parts: sum(stake x value) - holdco net debt, then a holding-company discount (G5)."""
    if not 0 <= holdco_discount < 1:
        raise ValuationError("holdco discount must be in [0, 1)")
    gross = sum(p.value * p.stake for p in parts)
    nav_ = gross - holdco_net_debt
    eq = nav_ * (1 - holdco_discount)
    return DcfResult(gross, eq, eq / shares if shares else None, gross, 0.0, 0.0, tuple(p.value * p.stake for p in parts))


def nav_per_share(asset_values: dict[str, float], haircuts: dict[str, float], liabilities: float,
                  shares: float) -> float:
    """Net asset value: sum(asset x (1 - haircut)) - liabilities, per share (real estate developers)."""
    net = sum(v * (1 - haircuts.get(k, 0.0)) for k, v in asset_values.items()) - liabilities
    return net / shares


def per_unit(enterprise_value: float, capacity: float) -> float:
    """EV per tonne / per MW: capacity must be a positive physical quantity."""
    if capacity <= 0:
        raise ValuationError("capacity <= 0")
    return enterprise_value / capacity


# ---- scenarios and sensitivities ------------------------------------------------------------------------------

@dataclass(frozen=True)
class Scenario:
    name: str                    # bear | base | bull (or any label)
    probability: float
    assumptions: dict


@dataclass(frozen=True)
class ScenarioRange:
    values: dict[str, float]     # name -> value per share
    probabilities: dict[str, float]
    expected: float
    low: float
    high: float


def scenario_range(scenarios: Sequence[Scenario], value_fn: Callable[[dict], float]) -> ScenarioRange:
    """Fair-value RANGE from explicit scenarios (never a single point/target). Probabilities must sum to 1."""
    total = sum(s.probability for s in scenarios)
    if abs(total - 1.0) > 1e-9:
        raise ValuationError(f"scenario probabilities sum to {total}, not 1")
    vals = {s.name: value_fn(s.assumptions) for s in scenarios}
    probs = {s.name: s.probability for s in scenarios}
    return ScenarioRange(vals, probs, sum(vals[n] * probs[n] for n in vals), min(vals.values()), max(vals.values()))


def sensitivity(value_fn: Callable[..., float], row_name: str, row_values: Sequence[float], col_name: str,
                col_values: Sequence[float], **fixed) -> list[list[float | None]]:
    """Grid of value_fn(row=..., col=..., **fixed); None where the combination is invalid (e.g. rate <= growth)."""
    grid: list[list[float | None]] = []
    for r in row_values:
        line: list[float | None] = []
        for c in col_values:
            try:
                line.append(value_fn(**{row_name: r, col_name: c}, **fixed))
            except ValuationError:
                line.append(None)
        grid.append(line)
    return grid


def percentile_rank(value: float, population: Sequence[float]) -> float | None:
    """Share of the population strictly below `value`, plus half of ties (0..1). None if the population is empty."""
    pop = [x for x in population if x is not None]
    if not pop:
        return None
    below = sum(1 for x in pop if x < value)
    ties = sum(1 for x in pop if x == value)
    return (below + 0.5 * ties) / len(pop)
