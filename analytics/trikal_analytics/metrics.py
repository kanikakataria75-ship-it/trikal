"""Metric engine: financial-statement metrics with explicit formulas, lineage and sector enforcement.

`Engine.compute(metric, security, as_of)`:
  1. resolves the company's sector playbook (point in time) and raises ForbiddenMetric if the playbook forbids
     the metric. The forbidden computation never runs: there is no code path that returns a number for it.
  2. runs the metric on trailing (TTM / latest-balance-sheet) inputs known at `as_of`, returning
       Value        number + unit + inputs (concept, filing, known_at) + warnings
       Undefined    meaningless right now (P/E when profit <= 0; a multiple on a non-positive denominator)
       NotAvailable the inputs are missing (named), or the metric needs a data source we do not hold yet

Conventions (FORMULAS.md): trailing only; money in INR; consolidated if reported else standalone, never mixed;
EBITDA = revenue from operations - (total expenses - finance costs - depreciation) (other income and exceptional
items excluded); Ind AS 116: EBITDA is as reported (post-116) and carries a warning, because lease payments are
not in the results filings.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass
from typing import Callable

from trikal_analytics import playbook as pbmod
from trikal_analytics.result import Input, NotAvailable, Undefined, Value
from trikal_core.pit import FinValue, PitReader
from trikal_core.timeutil import AsOf

STALE_FINANCIALS_DAYS = 540
QUARTER_GAP = (80, 100)  # days between consecutive quarter-ends


@dataclass(frozen=True)
class MetricSpec:
    id: str
    unit: str
    formula: str
    fn: Callable
    external: str | None = None      # source needed when TRIKAL cannot derive it from the filings yet


REGISTRY: dict[str, MetricSpec] = {}


def metric(id: str, unit: str, formula: str):
    def deco(fn):
        REGISTRY[id] = MetricSpec(id, unit, formula, fn)
        return fn
    return deco


def _inp(name: str, v: FinValue) -> Input:
    return Input(name, v.value, v.period_end, v.concept, v.filing_id, v.known_at)


class Ctx:
    """Point-in-time inputs for one company. Every accessor returns None when the data is not there."""

    def __init__(self, reader: PitReader, security_id: str, as_of: AsOf, basis: str = "auto") -> None:
        self.r, self.sid, self.as_of = reader, security_id, as_of
        self._basis_arg = basis
        self._basis: str | None = None
        self._series: dict[str, list[FinValue]] = {}
        self.warnings: list[str] = []

    # ---- basis: one for the whole computation ---------------------------------------------------------
    @property
    def basis(self) -> str:
        if self._basis is None:
            if self._basis_arg != "auto":
                self._basis = self._basis_arg
            else:
                recent = [v for v in self.r.financials(self.sid, self.as_of, ["profit_after_tax", "total_income", "revenue_from_operations"], basis="consolidated")
                          if (self.as_of.date_ist - v.period_end).days <= 400]
                self._basis = "consolidated" if recent else "standalone"
        return self._basis

    def series(self, li: str) -> list[FinValue]:
        if li not in self._series:
            self._series[li] = self.r.financials(self.sid, self.as_of, [li], basis=self.basis)
        return self._series[li]

    def _note(self, vals: list[FinValue]) -> None:
        for v in vals:
            if v.concept.startswith("html:"):
                w = f"old_page_input:{v.line_item}"
                if w not in self.warnings:
                    self.warnings.append(w)
            if v.known_precision == "imputed" and "imputed_known_at" not in self.warnings:
                self.warnings.append("imputed_known_at")

    # ---- trailing flows ------------------------------------------------------------------------------
    def ttm(self, li: str) -> tuple[float, list[FinValue]] | None:
        """Trailing twelve months: four consecutive quarters, or the latest 12-month figure if it is newer."""
        qs = sorted((v for v in self.series(li) if v.months == 3), key=lambda v: v.period_end)
        best_q: tuple[dt.date, float, list[FinValue]] | None = None
        if len(qs) >= 4:
            for i in range(len(qs) - 4, -1, -1):
                win = qs[i:i + 4]
                gaps = [(win[k + 1].period_end - win[k].period_end).days for k in range(3)]
                if all(QUARTER_GAP[0] <= g <= QUARTER_GAP[1] for g in gaps):
                    best_q = (win[-1].period_end, sum(v.value for v in win), win)
                    break
        fy = [v for v in self.series(li) if v.months == 12]
        best_fy = max(fy, key=lambda v: v.period_end) if fy else None
        cand = []
        if best_fy:
            cand.append((best_fy.period_end, 1, best_fy.value, [best_fy]))
        if best_q:
            cand.append((best_q[0], 0, best_q[1], best_q[2]))
        if not cand:
            return None
        end, _, val, used = max(cand, key=lambda c: (c[0], c[1]))
        if (self.as_of.date_ist - end).days > STALE_FINANCIALS_DAYS:
            return None
        self._note(used)
        return val, used

    def latest_period(self, li: str, months: int) -> FinValue | None:
        vals = [v for v in self.series(li) if v.months == months]
        return max(vals, key=lambda v: v.period_end) if vals else None

    def instant(self, li: str, back_days: int = 0) -> FinValue | None:
        """Balance-sheet value at the latest reporting date (or the one about `back_days` earlier)."""
        vals = sorted((v for v in self.series(li) if v.months is None), key=lambda v: v.period_end)
        if not vals:
            return None
        latest = vals[-1]
        if (self.as_of.date_ist - latest.period_end).days > STALE_FINANCIALS_DAYS:
            return None
        if back_days:
            target = latest.period_end - dt.timedelta(days=back_days)
            older = [v for v in vals if abs((v.period_end - target).days) <= 60]
            return min(older, key=lambda v: abs((v.period_end - target).days)) if older else None
        self._note([latest])
        return latest

    # ---- market data ---------------------------------------------------------------------------------
    def price(self) -> tuple[dt.date, float] | None:
        return self.r.last_price(self.sid, self.as_of)

    def shares(self) -> tuple[float, list[FinValue]] | None:
        """Shares outstanding = paid-up equity capital / face value, rolled forward for splits and bonuses that
        went ex after the filing was known (so price and share count refer to the same instant)."""
        cap = self.latest_any("paid_up_equity_capital")
        fv = self.latest_any("face_value")
        if not cap or not fv or fv.value <= 0 or cap.value <= 0:
            return None
        n = cap.value / fv.value
        for ev in self.r.adjustment_events(self.sid, self.as_of):
            ex, factor, _m, _a, applied = ev[0], ev[1], ev[2], ev[3], ev[4]
            if applied and ex > cap.known_at.astimezone(self.as_of.ts.tzinfo).date() and factor > 0:
                n /= factor
        self._note([cap, fv])
        return n, [cap, fv]

    def latest_any(self, li: str) -> FinValue | None:
        vals = self.series(li)
        return max(vals, key=lambda v: (v.period_end, v.known_at)) if vals else None

    def mcap(self) -> tuple[float, list[Input]] | None:
        p, sh = self.price(), self.shares()
        if not p or not sh:
            return None
        return p[1] * sh[0], [Input("share_price", p[1], p[0], "price_eod", "", self.as_of.ts)] + [_inp(v.line_item, v) for v in sh[1]]


def _na(metric_id: str, *missing: str, reason: str = "") -> NotAvailable:
    return NotAvailable(metric_id, tuple(missing), reason)


def _val(c: Ctx, mid: str, value: float, inputs: list[Input], extra_warn: tuple[str, ...] = ()) -> Value:
    spec = REGISTRY[mid]
    return Value(mid, value, spec.unit, c.as_of.ts, tuple(inputs), c.basis, tuple(dict.fromkeys([*c.warnings, *extra_warn])), spec.formula)


# ---- flows ------------------------------------------------------------------------------------------------

def _ttm_value(c: Ctx, mid: str, li: str):
    t = c.ttm(li)
    if not t:
        return _na(mid, li)
    return t


@metric("revenue_ttm", "INR", "sum of the last four quarters of revenue from operations (or the latest 12-month figure)")
def revenue_ttm(c: Ctx):
    t = _ttm_value(c, "revenue_ttm", "revenue_from_operations")
    return t if isinstance(t, NotAvailable) else _val(c, "revenue_ttm", t[0], [_inp("revenue_from_operations", v) for v in t[1]])


@metric("pat_ttm", "INR", "trailing profit attributable to owners (falls back to profit after tax when no minorities are reported)")
def pat_ttm(c: Ctx):
    t = c.ttm("profit_attributable_to_owners") or c.ttm("profit_after_tax")
    if not t:
        return _na("pat_ttm", "profit_attributable_to_owners|profit_after_tax")
    return _val(c, "pat_ttm", t[0], [_inp(v.line_item, v) for v in t[1]])


def _ebitda_parts(c: Ctx):
    rev, exp, fin, dep = (c.ttm("revenue_from_operations"), c.ttm("total_expenses"),
                          c.ttm("finance_costs"), c.ttm("depreciation_amortisation"))
    miss = [n for n, v in (("revenue_from_operations", rev), ("total_expenses", exp), ("finance_costs", fin),
                           ("depreciation_amortisation", dep)) if not v]
    return rev, exp, fin, dep, miss


@metric("ebitda", "INR", "revenue from operations - (total expenses - finance costs - depreciation); excludes other income and exceptional items")
def ebitda(c: Ctx):
    rev, exp, fin, dep, miss = _ebitda_parts(c)
    if miss:
        return _na("ebitda", *miss)
    used = [*rev[1], *exp[1], *fin[1], *dep[1]]
    if any(v.source_rank > 0 for v in exp[1] + fin[1]):
        c.warnings.append("old_page_expense_convention_varies")
    return _val(c, "ebitda", rev[0] - (exp[0] - fin[0] - dep[0]), [_inp(v.line_item, v) for v in used],
                ("post_ind_as_116: lease payments are not in the filings",))


@metric("ebit", "INR", "ebitda - depreciation")
def ebit(c: Ctx):
    e, d = ebitda(c), c.ttm("depreciation_amortisation")
    if isinstance(e, NotAvailable):
        return e
    return _val(c, "ebit", e.value - d[0], list(e.inputs), e.warnings)


@metric("ebitda_margin", "ratio", "ebitda / revenue from operations")
def ebitda_margin(c: Ctx):
    e, r = ebitda(c), c.ttm("revenue_from_operations")
    if isinstance(e, NotAvailable):
        return e
    if r[0] <= 0:
        return Undefined("ebitda_margin", "revenue <= 0")
    return _val(c, "ebitda_margin", e.value / r[0], list(e.inputs), e.warnings)


@metric("ebit_margin", "ratio", "ebit / revenue from operations")
def ebit_margin(c: Ctx):
    e, r = ebit(c), c.ttm("revenue_from_operations")
    if isinstance(e, NotAvailable):
        return e
    if r[0] <= 0:
        return Undefined("ebit_margin", "revenue <= 0")
    return _val(c, "ebit_margin", e.value / r[0], list(e.inputs), e.warnings)


@metric("net_margin", "ratio", "trailing profit attributable to owners / revenue from operations")
def net_margin(c: Ctx):
    p, r = pat_ttm(c), c.ttm("revenue_from_operations")
    if isinstance(p, NotAvailable) or not r:
        return _na("net_margin", "pat_ttm", "revenue_from_operations")
    if r[0] <= 0:
        return Undefined("net_margin", "revenue <= 0")
    return _val(c, "net_margin", p.value / r[0], list(p.inputs))


@metric("revenue_growth", "ratio", "latest quarter revenue / revenue of the quarter a year earlier - 1")
def revenue_growth(c: Ctx):
    return _growth(c, "revenue_growth", "revenue_from_operations")


@metric("profit_growth", "ratio", "latest quarter profit attributable to owners / same quarter a year earlier - 1")
def profit_growth(c: Ctx):
    li = "profit_attributable_to_owners" if c.series("profit_attributable_to_owners") else "profit_after_tax"
    return _growth(c, "profit_growth", li)


def _growth(c: Ctx, mid: str, li: str):
    qs = sorted((v for v in c.series(li) if v.months == 3), key=lambda v: v.period_end)
    if not qs:
        return _na(mid, li)
    last = qs[-1]
    if (c.as_of.date_ist - last.period_end).days > STALE_FINANCIALS_DAYS:
        return _na(mid, li, reason="latest quarter is older than 18 months")
    prior = [v for v in qs if 350 <= (last.period_end - v.period_end).days <= 380]
    if not prior:
        return _na(mid, f"{li} (same quarter last year)")
    p = prior[0]
    c._note([last, p])
    if p.value <= 0:
        return Undefined(mid, "base-period value <= 0: growth rate is not meaningful")
    return _val(c, mid, last.value / p.value - 1, [_inp(li, last), _inp(li, p)])


# ---- balance sheet -----------------------------------------------------------------------------------------

@metric("net_debt", "INR", "borrowings (current + non-current) - cash and equivalents - other bank balances; investments are not netted")
def net_debt(c: Ctx):
    bc, bn = c.instant("borrowings_current"), c.instant("borrowings_non_current")
    cash, bank = c.instant("cash_and_equivalents"), c.instant("other_bank_balances")
    if not cash or (not bc and not bn):
        return _na("net_debt", *(["cash_and_equivalents"] if not cash else []), *(["borrowings"] if not bc and not bn else []))
    debt = (bc.value if bc else 0.0) + (bn.value if bn else 0.0)
    used = [v for v in (bc, bn, cash, bank) if v]
    return _val(c, "net_debt", debt - cash.value - (bank.value if bank else 0.0), [_inp(v.line_item, v) for v in used])


@metric("debt_to_equity", "x", "borrowings / total equity")
def debt_to_equity(c: Ctx):
    bc, bn, eq = c.instant("borrowings_current"), c.instant("borrowings_non_current"), c.instant("total_equity")
    if not eq or (not bc and not bn):
        return _na("debt_to_equity", *(["total_equity"] if not eq else []), *(["borrowings"] if not bc and not bn else []))
    if eq.value <= 0:
        return Undefined("debt_to_equity", "equity <= 0")
    debt = (bc.value if bc else 0.0) + (bn.value if bn else 0.0)
    return _val(c, "debt_to_equity", debt / eq.value, [_inp(v.line_item, v) for v in (bc, bn, eq) if v])


@metric("current_ratio", "x", "current assets / current liabilities")
def current_ratio(c: Ctx):
    a, l = c.instant("current_assets"), c.instant("current_liabilities")
    if not a or not l:
        return _na("current_ratio", *(["current_assets"] if not a else []), *(["current_liabilities"] if not l else []))
    if l.value <= 0:
        return Undefined("current_ratio", "current liabilities <= 0")
    return _val(c, "current_ratio", a.value / l.value, [_inp("current_assets", a), _inp("current_liabilities", l)])


@metric("interest_coverage", "x", "ebit / finance costs")
def interest_coverage(c: Ctx):
    e, f = ebit(c), c.ttm("finance_costs")
    if isinstance(e, NotAvailable) or not f:
        return _na("interest_coverage", "ebit", "finance_costs")
    if f[0] <= 0:
        return Undefined("interest_coverage", "no finance costs")
    return _val(c, "interest_coverage", e.value / f[0], list(e.inputs), e.warnings)


@metric("interest_coverage_ebitda", "x", "ebitda / finance costs")
def interest_coverage_ebitda(c: Ctx):
    e, f = ebitda(c), c.ttm("finance_costs")
    if isinstance(e, NotAvailable) or not f:
        return _na("interest_coverage_ebitda", "ebitda", "finance_costs")
    if f[0] <= 0:
        return Undefined("interest_coverage_ebitda", "no finance costs")
    return _val(c, "interest_coverage_ebitda", e.value / f[0], list(e.inputs), e.warnings)


@metric("net_debt_ebitda", "x", "net debt / ebitda")
def net_debt_ebitda(c: Ctx):
    n, e = net_debt(c), ebitda(c)
    if isinstance(n, NotAvailable) or isinstance(e, NotAvailable):
        return _na("net_debt_ebitda", *{*(n.missing if isinstance(n, NotAvailable) else ()), *(e.missing if isinstance(e, NotAvailable) else ())})
    if e.value <= 0:
        return Undefined("net_debt_ebitda", "ebitda <= 0")
    return _val(c, "net_debt_ebitda", n.value / e.value, [*n.inputs, *e.inputs], e.warnings)


@metric("roe", "ratio", "trailing profit attributable to owners / closing equity attributable to owners")
def roe(c: Ctx):
    p = pat_ttm(c)
    eq = c.instant("equity_owners") or c.instant("total_equity")
    if isinstance(p, NotAvailable) or not eq:
        return _na("roe", *(["pat_ttm"] if isinstance(p, NotAvailable) else []), *(["equity"] if not eq else []))
    if eq.value <= 0:
        return Undefined("roe", "equity <= 0")
    return _val(c, "roe", p.value / eq.value, [*p.inputs, _inp(eq.line_item, eq)])


@metric("roa", "ratio", "trailing profit attributable to owners / total assets")
def roa(c: Ctx):
    p, a = pat_ttm(c), c.instant("total_assets")
    if isinstance(p, NotAvailable) or not a:
        return _na("roa", *(["pat_ttm"] if isinstance(p, NotAvailable) else []), *(["total_assets"] if not a else []))
    if a.value <= 0:
        return Undefined("roa", "assets <= 0")
    return _val(c, "roa", p.value / a.value, [*p.inputs, _inp("total_assets", a)])


@metric("roce", "ratio", "ebit / (total assets - current liabilities)")
def roce(c: Ctx):
    e, a, l = ebit(c), c.instant("total_assets"), c.instant("current_liabilities")
    if isinstance(e, NotAvailable) or not a or not l:
        return _na("roce", *(["ebit"] if isinstance(e, NotAvailable) else []), *(["total_assets"] if not a else []), *(["current_liabilities"] if not l else []))
    cap = a.value - l.value
    if cap <= 0:
        return Undefined("roce", "capital employed <= 0")
    return _val(c, "roce", e.value / cap, [*e.inputs, _inp("total_assets", a), _inp("current_liabilities", l)], e.warnings)


def _days(c: Ctx, mid: str, bs: str, base_name: str, base):
    b = c.instant(bs)
    if not b or isinstance(base, NotAvailable):
        return _na(mid, *(([bs]) if not b else []), *((base.missing) if isinstance(base, NotAvailable) else []))
    if base.value <= 0:
        return Undefined(mid, f"{base_name} <= 0")
    return _val(c, mid, b.value / base.value * 365.0, [_inp(bs, b), *base.inputs])


def _cogs(c: Ctx):
    m, p, ch = c.ttm("cost_of_materials"), c.ttm("purchases_of_traded_goods"), c.ttm("change_in_inventories")
    if not m and not p:
        return _na("cogs", "cost_of_materials|purchases_of_traded_goods")
    used = [*(m[1] if m else []), *(p[1] if p else []), *(ch[1] if ch else [])]
    val = (m[0] if m else 0.0) + (p[0] if p else 0.0) + (ch[0] if ch else 0.0)
    return Value("cogs", val, "INR", c.as_of.ts, tuple(_inp(v.line_item, v) for v in used), c.basis)


@metric("receivable_days", "days", "trade receivables / revenue from operations x 365")
def receivable_days(c: Ctx):
    r = revenue_ttm(c)
    return _days(c, "receivable_days", "trade_receivables_current", "revenue", r)


@metric("inventory_days", "days", "inventories / cost of goods (materials + traded purchases + change in inventories) x 365")
def inventory_days(c: Ctx):
    return _days(c, "inventory_days", "inventories", "cost of goods", _cogs(c))


@metric("payable_days", "days", "trade payables / cost of goods x 365")
def payable_days(c: Ctx):
    return _days(c, "payable_days", "trade_payables_current", "cost of goods", _cogs(c))


@metric("cash_conversion_cycle", "days", "receivable days + inventory days - payable days")
def cash_conversion_cycle(c: Ctx):
    parts = [receivable_days(c), inventory_days(c), payable_days(c)]
    miss = [m for p in parts if isinstance(p, NotAvailable) for m in p.missing]
    if miss:
        return _na("cash_conversion_cycle", *dict.fromkeys(miss))
    if any(isinstance(p, Undefined) for p in parts):
        return Undefined("cash_conversion_cycle", "a component is not meaningful")
    r, i, p = parts
    return _val(c, "cash_conversion_cycle", r.value + i.value - p.value, [*r.inputs, *i.inputs, *p.inputs])


@metric("altman_z", "score", "Altman Z'' for emerging-market non-financials: 3.25 + 6.56 WC/TA + 3.26 RE/TA + 6.72 EBIT/TA + 1.05 BookEquity/TL (reserves = other equity)")
def altman_z(c: Ctx):
    e, ta, ca, cl = ebit(c), c.instant("total_assets"), c.instant("current_assets"), c.instant("current_liabilities")
    oe, eq, tl = c.instant("other_equity"), c.instant("total_equity"), c.instant("total_liabilities")
    need = {"ebit": e if not isinstance(e, NotAvailable) else None, "total_assets": ta, "current_assets": ca,
            "current_liabilities": cl, "other_equity": oe, "total_equity": eq, "total_liabilities": tl}
    miss = [k for k, v in need.items() if v is None]
    if miss:
        return _na("altman_z", *miss)
    if ta.value <= 0 or tl.value <= 0:
        return Undefined("altman_z", "assets or liabilities <= 0")
    z = (3.25 + 6.56 * (ca.value - cl.value) / ta.value + 3.26 * oe.value / ta.value
         + 6.72 * e.value / ta.value + 1.05 * eq.value / tl.value)
    return _val(c, "altman_z", z, [*e.inputs, *(_inp(k, v) for k, v in need.items() if k != "ebit")], e.warnings)


@metric("fcf", "INR", "latest 12-month cash flow from operations + purchases of PPE and intangibles (reported as outflows)")
def fcf(c: Ctx):
    cfo = c.latest_period("cash_flow_operations", 12)
    if not cfo:
        return _na("fcf", "cash_flow_operations (12-month)")
    if (c.as_of.date_ist - cfo.period_end).days > STALE_FINANCIALS_DAYS:
        return _na("fcf", "cash_flow_operations", reason="older than 18 months")
    cap = [v for v in (c.latest_period("capex_ppe", 12), c.latest_period("capex_intangibles", 12)) if v and v.period_end == cfo.period_end]
    if not cap:
        return _na("fcf", "capex_ppe (same period)")
    c._note([cfo, *cap])
    return _val(c, "fcf", cfo.value + sum(v.value for v in cap), [_inp("cash_flow_operations", cfo), *(_inp(v.line_item, v) for v in cap)])


# ---- market-based -------------------------------------------------------------------------------------------

@metric("market_cap", "INR", "last close x shares outstanding (paid-up capital / face value, rolled for later splits and bonuses)")
def market_cap(c: Ctx):
    m = c.mcap()
    if not m:
        return _na("market_cap", "price (<=10 days old)", "paid_up_equity_capital", "face_value")
    return _val(c, "market_cap", m[0], m[1])


@metric("ev", "INR", "market cap + net debt + non-controlling interest (book)")
def ev(c: Ctx):
    m, n = market_cap(c), net_debt(c)
    if isinstance(m, NotAvailable) or isinstance(n, NotAvailable):
        return _na("ev", *{*(m.missing if isinstance(m, NotAvailable) else ()), *(n.missing if isinstance(n, NotAvailable) else ())})
    nci = c.instant("non_controlling_interest")
    return _val(c, "ev", m.value + n.value + (nci.value if nci else 0.0), [*m.inputs, *n.inputs, *([_inp("non_controlling_interest", nci)] if nci else [])])


@metric("pe", "x", "market cap / trailing profit attributable to owners (equals price / EPS on the current share count)")
def pe(c: Ctx):
    m, p = market_cap(c), pat_ttm(c)
    if isinstance(m, NotAvailable) or isinstance(p, NotAvailable):
        return _na("pe", *{*(m.missing if isinstance(m, NotAvailable) else ()), *(p.missing if isinstance(p, NotAvailable) else ())})
    if p.value <= 0:
        return Undefined("pe", "trailing profit <= 0: P/E is not meaningful (G1)")
    return _val(c, "pe", m.value / p.value, [*m.inputs, *p.inputs])


@metric("pb", "x", "market cap / equity attributable to owners")
def pb(c: Ctx):
    m = market_cap(c)
    eq = c.instant("equity_owners") or c.instant("total_equity")
    if isinstance(m, NotAvailable) or not eq:
        return _na("pb", *(m.missing if isinstance(m, NotAvailable) else ()), *(["equity"] if not eq else []))
    if eq.value <= 0:
        return Undefined("pb", "book equity <= 0")
    return _val(c, "pb", m.value / eq.value, [*m.inputs, _inp(eq.line_item, eq)])


@metric("ev_ebitda", "x", "enterprise value / ebitda")
def ev_ebitda(c: Ctx):
    v, e = ev(c), ebitda(c)
    if isinstance(v, NotAvailable) or isinstance(e, NotAvailable):
        return _na("ev_ebitda", *{*(v.missing if isinstance(v, NotAvailable) else ()), *(e.missing if isinstance(e, NotAvailable) else ())})
    if e.value <= 0:
        return Undefined("ev_ebitda", "ebitda <= 0: multiple is not meaningful (G1)")
    return _val(c, "ev_ebitda", v.value / e.value, [*v.inputs, *e.inputs], e.warnings)


@metric("ev_sales", "x", "enterprise value / revenue from operations")
def ev_sales(c: Ctx):
    v, r = ev(c), revenue_ttm(c)
    if isinstance(v, NotAvailable) or isinstance(r, NotAvailable):
        return _na("ev_sales", *{*(v.missing if isinstance(v, NotAvailable) else ()), *(r.missing if isinstance(r, NotAvailable) else ())})
    if r.value <= 0:
        return Undefined("ev_sales", "revenue <= 0")
    return _val(c, "ev_sales", v.value / r.value, [*v.inputs, *r.inputs])


@metric("fcf_yield", "ratio", "free cash flow / market cap")
def fcf_yield(c: Ctx):
    f, m = fcf(c), market_cap(c)
    if isinstance(f, NotAvailable) or isinstance(m, NotAvailable):
        return _na("fcf_yield", *{*(f.missing if isinstance(f, NotAvailable) else ()), *(m.missing if isinstance(m, NotAvailable) else ())})
    return _val(c, "fcf_yield", f.value / m.value, [*f.inputs, *m.inputs])


# ---- bank items straight from filings -----------------------------------------------------------------------

def _direct(mid: str, li: str, unit: str, formula: str):
    @metric(mid, unit, formula)
    def _fn(c: Ctx, _li=li, _mid=mid):
        v = c.latest_period(_li, 3) or c.latest_period(_li, 6) or c.latest_period(_li, 12)
        if not v or (c.as_of.date_ist - v.period_end).days > STALE_FINANCIALS_DAYS:
            return _na(_mid, _li)
        c._note([v])
        return _val(c, _mid, v.value, [_inp(_li, v)])
    return _fn


_direct("gross_npa_amount", "gross_npa_amount", "INR", "gross non-performing assets, as reported in the results filing")
_direct("net_npa_amount", "net_npa_amount", "INR", "net non-performing assets, as reported in the results filing (standalone; a reported 0 means not reported and is dropped)")
_direct("gnpa_pct", "gross_npa_pct", "ratio", "gross NPA ratio as reported in the results filing (standalone)")
_direct("nnpa_pct", "net_npa_pct", "ratio", "net NPA ratio as reported in the results filing (standalone)")
_direct("cet1", "cet1_ratio", "ratio", "Common Equity Tier 1 ratio as reported in the results filing (standalone)")


def _pair(c: Ctx, li: str):
    """Latest balance-sheet value and the one about a year earlier (None when the earlier one is not there)."""
    now = c.instant(li)
    return now, (c.instant(li, back_days=365) if now else None)


def _avg(now, then):
    return ((now.value + then.value) / 2, [now, then]) if then else (now.value, [now])


@metric("nii", "INR", "net interest income: interest earned - interest expended, trailing twelve months")
def nii(c: Ctx):
    a, b = c.ttm("interest_earned"), c.ttm("interest_expended")
    if not a or not b:
        return _na("nii", *(["interest_earned"] if not a else []), *(["interest_expended"] if not b else []))
    return _val(c, "nii", a[0] - b[0], [_inp(v.line_item, v) for v in [*a[1], *b[1]]])


@metric("nii_to_assets", "ratio", "NII / average total assets. A proxy: reported NIM divides by average interest-earning assets, which filings do not give")
def nii_to_assets(c: Ctx):
    n = nii(c)
    now, then = _pair(c, "total_assets")
    if isinstance(n, NotAvailable) or not now:
        return _na("nii_to_assets", *(n.missing if isinstance(n, NotAvailable) else ()), *(["total_assets"] if not now else []))
    base, used = _avg(now, then)
    if base <= 0:
        return Undefined("nii_to_assets", "assets <= 0")
    return _val(c, "nii_to_assets", n.value / base, [*n.inputs, *(_inp("total_assets", v) for v in used)],
                () if then else ("single_balance_sheet_date",))


@metric("cost_to_income", "ratio", "operating expenses / (NII + other income), trailing twelve months")
def cost_to_income(c: Ctx):
    n, ox, oi = nii(c), c.ttm("bank_operating_expenses"), c.ttm("other_income")
    if isinstance(n, NotAvailable) or not ox or not oi:
        return _na("cost_to_income", *(n.missing if isinstance(n, NotAvailable) else ()),
                   *(["bank_operating_expenses"] if not ox else []), *(["other_income"] if not oi else []))
    inc = n.value + oi[0]
    if inc <= 0:
        return Undefined("cost_to_income", "net operating income <= 0")
    return _val(c, "cost_to_income", ox[0] / inc, [*n.inputs, *(_inp(v.line_item, v) for v in [*ox[1], *oi[1]])])


@metric("ldr", "ratio", "loan-to-deposit ratio: advances / deposits (latest balance sheet)")
def ldr(c: Ctx):
    adv, dep = c.instant("bank_advances"), c.instant("bank_deposits")
    if not adv or not dep:
        return _na("ldr", *(["bank_advances"] if not adv else []), *(["bank_deposits"] if not dep else []))
    if dep.value <= 0:
        return Undefined("ldr", "deposits <= 0")
    return _val(c, "ldr", adv.value / dep.value, [_inp("bank_advances", adv), _inp("bank_deposits", dep)])


@metric("credit_cost", "ratio", "provisions (other than tax and contingencies), trailing twelve months / average advances")
def credit_cost(c: Ctx):
    pr = c.ttm("bank_provisions")
    now, then = _pair(c, "bank_advances")
    if not pr or not now:
        return _na("credit_cost", *(["bank_provisions"] if not pr else []), *(["bank_advances"] if not now else []))
    base, used = _avg(now, then)
    if base <= 0:
        return Undefined("credit_cost", "advances <= 0")
    return _val(c, "credit_cost", pr[0] / base, [*(_inp(v.line_item, v) for v in pr[1]), *(_inp("bank_advances", v) for v in used)],
                () if then else ("single_balance_sheet_date",))


@metric("leverage_assets_to_equity", "x", "total assets / equity attributable to owners (latest balance sheet)")
def leverage_assets_to_equity(c: Ctx):
    a, eq = c.instant("total_assets"), c.instant("equity_owners") or c.instant("total_equity")
    if not a or not eq:
        return _na("leverage_assets_to_equity", *(["total_assets"] if not a else []), *(["equity"] if not eq else []))
    if eq.value <= 0:
        return Undefined("leverage_assets_to_equity", "equity <= 0")
    return _val(c, "leverage_assets_to_equity", a.value / eq.value, [_inp("total_assets", a), _inp(eq.line_item, eq)])


def _external(mid: str, unit: str):
    REGISTRY[mid] = MetricSpec(mid, unit, "needs an external source (see playbook.requires)", lambda c: None, external="playbook.requires")


# Sector metrics TRIKAL cannot derive from the results filings yet (they come from concalls / annual reports /
# regulators in M5-M6). They exist so the engine answers "NotAvailable: needs X" instead of KeyError or a guess.
for _m, _u in (("nim", "ratio"), ("casa_ratio", "ratio"), ("pcr", "ratio"), ("slippage_ratio", "ratio"),
               ("car", "ratio"), ("vnb", "INR"), ("vnb_margin", "ratio"),
               ("embedded_value", "INR"), ("combined_ratio", "ratio"), ("arpob", "INR"), ("sssg", "ratio"),
               ("order_book", "INR"), ("book_to_bill", "x"), ("arpu", "INR"), ("load_factor", "ratio")):
    _external(_m, _u)


class Engine:
    def __init__(self, reader: PitReader, registry: pbmod.Registry | None = None) -> None:
        self.r = reader
        self.reg = registry or pbmod.load()

    def resolution(self, security_id: str, as_of: AsOf, basis: str = "auto") -> pbmod.Resolution:
        prof = self.r.profile(security_id, as_of)
        c = Ctx(self.r, security_id, as_of, basis)
        profitable = None
        p = pat_ttm(c)
        if isinstance(p, Value):
            profitable = p.value > 0
        return self.reg.resolve(security_id, prof["name"], prof["sector"], prof["family"], profitable)

    def compute(self, metric_id: str, security_id: str, as_of: AsOf, basis: str = "auto"):
        if metric_id not in REGISTRY:
            raise KeyError(f"unknown metric {metric_id!r}")
        res = self.resolution(security_id, as_of, basis)
        res.playbook.check_metric(metric_id)          # raises ForbiddenMetric: no number is ever produced
        spec = REGISTRY[metric_id]
        if spec.external:
            src = res.playbook.requires.get(metric_id, "an external source not yet ingested")
            return NotAvailable(metric_id, (metric_id,), f"needs {src}")
        c = Ctx(self.r, security_id, as_of, basis)
        out = spec.fn(c)
        if isinstance(out, Value):
            extra = []
            if res.playbook.caution_for(metric_id):
                extra.append("caution: " + res.playbook.caution_for(metric_id))
            if res.confidence < 0.7:
                extra.append(f"playbook_confidence:{res.confidence} ({res.how})")
            if extra:
                out = Value(out.metric, out.value, out.unit, out.as_of, out.inputs, out.basis, (*out.warnings, *extra), out.formula)
        return out

    def compute_many(self, metric_ids: list[str], security_id: str, as_of: AsOf, basis: str = "auto") -> dict:
        """Every metric the playbook allows; forbidden ones are reported (not raised) so a screen can show why."""
        res = self.resolution(security_id, as_of, basis)
        out: dict = {}
        for m in metric_ids:
            f = res.playbook.explain(m)
            out[m] = f if f else self.compute(m, security_id, as_of, basis)
        return out
