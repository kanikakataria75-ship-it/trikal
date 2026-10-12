"""Valuation Lab: runs valuation methods on point-in-time inputs under the company's sector rules.

Principles (PROMPT §4.7, FORMULAS.md §Valuation):
  * The sector playbook decides which methods exist. A forbidden method raises ForbiddenMethod before any input is
    read; a method that is allowed but not primary for the sector is returned with a caution.
  * No hidden defaults. Every rate and growth assumption must be passed in (`user`) or explicitly requested from
    `template_assumptions` (labelled `template`: conventional starting values that the user must confirm).
    Missing assumptions raise ValuationError naming them.
  * Inputs taken from filings are labelled `pit` with their lineage. Output is a value, or a RANGE across
    explicit scenarios, never a rating or a target price. `value_to_price` is a ratio, not a recommendation.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field

from trikal_analytics import valuation as V
from trikal_analytics.metrics import REGISTRY, Ctx, Engine, ebitda, fcf, market_cap, net_debt, pat_ttm
from trikal_analytics.result import Input, NotAvailable, Undefined, Value
from trikal_core.pit import PitReader
from trikal_core.timeutil import IST, AsOf

REQUIRED = {
    "dcf_fcff": ["wacc", "g_start", "g_terminal", "years"],
    "dcf_fcfe": ["cost_of_equity", "g_start", "g_terminal", "years"],
    "reverse_dcf_fcff": ["wacc", "g_terminal", "years"],
    "ddm": ["cost_of_equity", "g_start", "g_terminal", "years", "dps0"],
    "justified_pb": ["cost_of_equity", "g_terminal", "roe"],
    "residual_income": ["cost_of_equity", "g_terminal", "roe_path"],
    "sotp": ["parts", "holdco_discount"],
    "nav": ["asset_values", "haircuts"],
    "ev_per_tonne": ["capacity"],
    "ev_per_mw": ["capacity"],
}


@dataclass(frozen=True)
class Assumption:
    name: str
    value: object
    source: str            # pit:<line item(s)> | user | template


@dataclass(frozen=True)
class Valuation:
    method: str
    playbook: str
    as_of: dt.datetime
    equity_value: float | None
    per_share: float | None
    enterprise_value: float | None
    price: float | None
    value_to_price: float | None
    assumptions: tuple[Assumption, ...]
    inputs: tuple[Input, ...] = ()
    terminal_share: float | None = None
    implied: dict = field(default_factory=dict)       # e.g. reverse DCF: implied growth
    warnings: tuple[str, ...] = ()


@dataclass(frozen=True)
class Relative:
    metric: str
    value: float
    own_percentile: float | None
    own_points: int
    peer_percentile: float | None
    peer_median: float | None
    peers: int
    warnings: tuple[str, ...] = ()


def template_assumptions(method: str, playbook_id: str) -> dict:
    """Conventional starting values, labelled 'template'. They are NOT recommendations: the user confirms or edits."""
    fin = playbook_id in ("banks", "nbfc_hfc", "insurance_life", "insurance_general", "financials", "capital_markets")
    base = {"years": 10, "g_terminal": 0.05}
    if method in ("dcf_fcff", "reverse_dcf_fcff"):
        base |= {"wacc": 0.12, "g_start": 0.12}
    if method in ("dcf_fcfe", "ddm", "justified_pb", "residual_income"):
        base |= {"cost_of_equity": 0.14 if fin else 0.13, "g_start": 0.10}
    if method == "justified_pb":
        base["g_terminal"] = 0.06
    return {k: Assumption(k, v, "template") for k, v in base.items()}


class Lab:
    def __init__(self, engine: Engine) -> None:
        self.e = engine
        self.r: PitReader = engine.r

    # ---- what is allowed ------------------------------------------------------------------------------
    def methods(self, security_id: str, as_of: AsOf) -> dict:
        pb = self.e.resolution(security_id, as_of).playbook
        every = set(REQUIRED) | {"multiples"}
        return {
            "playbook": pb.id,
            "primary": list(pb.primary), "secondary": list(pb.secondary),
            "forbidden": sorted(m for m in every | set(REQUIRED) if m in pb.forbidden_methods or m in pb.forbidden_metrics),
            "not_primary": sorted(pb.not_primary),
            "reason": pb.forbidden_reason,
        }

    # ---- run -----------------------------------------------------------------------------------------------
    def run(self, method: str, security_id: str, as_of: AsOf, assumptions: dict, basis: str = "auto") -> Valuation:
        if method not in REQUIRED:
            raise KeyError(f"unknown valuation method {method!r}")
        res = self.e.resolution(security_id, as_of, basis)
        pb = res.playbook
        pb.check_method(method)                                   # ForbiddenMethod: nothing below runs
        a = {k: (v if isinstance(v, Assumption) else Assumption(k, v, "user")) for k, v in assumptions.items()}
        missing = [k for k in REQUIRED[method] if k not in a]
        if missing:
            raise V.ValuationError(f"{method}: missing assumptions {missing} (use template_assumptions() to start, then confirm)")
        c = Ctx(self.r, security_id, as_of, basis)
        warn: list[str] = []
        if res.confidence < 0.7:
            warn.append(f"playbook_confidence:{res.confidence} ({res.how}: {res.why})")
        if method in pb.not_primary or (pb.primary and method not in pb.primary and method not in pb.secondary):
            warn.append(f"{method} is not a primary method for {pb.id}")
        px = c.price()
        shares = c.shares()
        sh = shares[0] if shares else None
        inputs: list[Input] = []
        used: list[Assumption] = list(a.values())

        def pit(name: str, value: float, source: str, ins: list[Input]) -> float:
            used.append(Assumption(name, value, source))
            inputs.extend(ins)
            return value

        out: dict = {}
        nd = None
        if method in ("dcf_fcff", "reverse_dcf_fcff"):
            f = fcf(c)
            if isinstance(f, NotAvailable):
                raise V.ValuationError(f"{method}: free cash flow not available ({', '.join(f.missing)})")
            fin = c.ttm("finance_costs")
            tax, pbt = c.ttm("tax_expense"), c.ttm("profit_before_tax")
            t = min(max(tax[0] / pbt[0], 0.0), 0.40) if tax and pbt and pbt[0] > 0 else 0.0
            fcff0 = a["fcff0"].value if "fcff0" in a else pit("fcff0", f.value + (fin[0] * (1 - t) if fin else 0.0),
                                                              "pit:cash_flow_operations+capex+finance_costs*(1-tax)", list(f.inputs))
            n = net_debt(c)
            if isinstance(n, NotAvailable):
                raise V.ValuationError(f"{method}: net debt not available ({', '.join(n.missing)})")
            nci = c.instant("non_controlling_interest")
            nd = pit("net_debt", n.value, "pit:borrowings-cash", list(n.inputs))
            nc = nci.value if nci else 0.0
            if method == "dcf_fcff":
                r = V.dcf_fcff(fcff0, a["wacc"].value, a["g_start"].value, a["g_terminal"].value, a["years"].value, nd, nc, sh)
                out = dict(equity_value=r.equity_value, per_share=r.per_share, enterprise_value=r.enterprise_value,
                           terminal_share=r.terminal_share)
            else:
                m = market_cap(c)
                if isinstance(m, NotAvailable):
                    raise V.ValuationError(f"reverse DCF needs market cap ({', '.join(m.missing)})")
                inputs.extend(m.inputs)
                g = V.reverse_dcf_growth(m.value, fcff0, a["wacc"].value, a["g_terminal"].value, a["years"].value, nd, nc)
                out = dict(equity_value=m.value, per_share=px[1] if px else None, implied={"implied_year1_growth": g})
        elif method == "dcf_fcfe":
            p = pat_ttm(c)
            f = fcf(c)
            base = a["fcfe0"].value if "fcfe0" in a else (f.value if isinstance(f, Value) else None)
            if base is None:
                raise V.ValuationError("dcf_fcfe: free cash flow to equity not available; pass fcfe0")
            r = V.dcf_fcfe(base, a["cost_of_equity"].value, a["g_start"].value, a["g_terminal"].value, a["years"].value, sh)
            out = dict(equity_value=r.equity_value, per_share=r.per_share, terminal_share=r.terminal_share)
        elif method == "ddm":
            r = V.ddm(a["dps0"].value, a["cost_of_equity"].value, a["g_start"].value, a["g_terminal"].value, a["years"].value)
            out = dict(equity_value=r.equity_value * sh if sh else None, per_share=r.per_share, terminal_share=r.terminal_share)
        elif method == "justified_pb":
            multiple = V.justified_pb(a["roe"].value, a["cost_of_equity"].value, a["g_terminal"].value)
            eq = c.instant("equity_owners") or c.instant("total_equity")
            if not eq:
                raise V.ValuationError("justified_pb: book equity not available")
            book = pit("book_equity", eq.value, "pit:equity", [Input(eq.line_item, eq.value, eq.period_end, eq.concept, eq.filing_id, eq.known_at)])
            out = dict(equity_value=multiple * book, per_share=multiple * book / sh if sh else None, implied={"justified_pb": multiple})
        elif method == "residual_income":
            eq = c.instant("equity_owners") or c.instant("total_equity")
            if not eq:
                raise V.ValuationError("residual_income: book equity not available")
            book = pit("book_equity", eq.value, "pit:equity", [Input(eq.line_item, eq.value, eq.period_end, eq.concept, eq.filing_id, eq.known_at)])
            r = V.residual_income(book, a["roe_path"].value, a["cost_of_equity"].value, a["g_terminal"].value,
                                  a["payout"].value if "payout" in a else 0.0,
                                  a["persistence"].value if "persistence" in a else 1.0, sh)
            out = dict(equity_value=r.equity_value, per_share=r.per_share, terminal_share=r.terminal_share)
        elif method == "sotp":
            parts = a["parts"].value
            n = net_debt(c)
            hnd = a["holdco_net_debt"].value if "holdco_net_debt" in a else (n.value if isinstance(n, Value) else None)
            if hnd is None:
                raise V.ValuationError("sotp: holdco net debt not available; pass holdco_net_debt")
            r = V.sotp(parts, hnd, a["holdco_discount"].value, sh)
            out = dict(equity_value=r.equity_value, per_share=r.per_share, enterprise_value=r.enterprise_value)
            if any(p.basis == "assumed" for p in parts):
                warn.append("sotp includes unlisted parts valued on user-assumed multiples")
        elif method == "nav":
            if not sh:
                raise V.ValuationError("nav: shares outstanding not available")
            liab = a["liabilities"].value if "liabilities" in a else None
            if liab is None:
                tl = c.instant("total_liabilities")
                if not tl:
                    raise V.ValuationError("nav: pass liabilities or have total liabilities in the filings")
                liab = pit("liabilities", tl.value, "pit:total_liabilities", [Input("total_liabilities", tl.value, tl.period_end, tl.concept, tl.filing_id, tl.known_at)])
            ps = V.nav_per_share(a["asset_values"].value, a["haircuts"].value, liab, sh)
            out = dict(equity_value=ps * sh, per_share=ps)
        else:  # ev_per_tonne / ev_per_mw
            from trikal_analytics.metrics import ev as ev_metric

            e = ev_metric(c)
            if isinstance(e, NotAvailable):
                raise V.ValuationError(f"{method}: EV not available ({', '.join(e.missing)})")
            inputs.extend(e.inputs)
            out = dict(enterprise_value=e.value, implied={method: V.per_unit(e.value, a["capacity"].value)})
        price = px[1] if px else None
        ps = out.get("per_share")
        return Valuation(method, pb.id, as_of.ts, out.get("equity_value"), ps, out.get("enterprise_value"), price,
                         (ps / price) if (ps and price) else None, tuple(used), tuple(inputs),
                         out.get("terminal_share"), out.get("implied", {}), tuple([*c.warnings, *warn]))

    # ---- scenarios ----------------------------------------------------------------------------------------------
    def scenario_range(self, method: str, security_id: str, as_of: AsOf, scenarios: list[V.Scenario], common: dict | None = None):
        """Fair-value range per share across explicit bear/base/bull scenarios (probabilities must sum to 1)."""
        def fn(ass: dict) -> float:
            v = self.run(method, security_id, as_of, {**(common or {}), **ass})
            if v.per_share is None:
                raise V.ValuationError("per-share value not available (shares outstanding missing)")
            return v.per_share
        return V.scenario_range(scenarios, fn)

    # ---- multiples versus own history and peers (G4) ------------------------------------------------------------------
    def relative(self, metric: str, security_id: str, as_of: AsOf, history_years: int = 5, peer_cap: int = 120):
        """A multiple is never reported alone: its percentile in the company's own history and among sector peers."""
        res = self.e.resolution(security_id, as_of)
        res.playbook.check_metric(metric)
        now = self.e.compute(metric, security_id, as_of)
        if not isinstance(now, Value):
            return now
        warn: list[str] = []
        # own history: month-ends going back, each computed strictly as of that date
        hist: list[float] = []
        d = as_of.date_ist.replace(day=1)
        for _ in range(history_years * 12):
            d = (d - dt.timedelta(days=1)).replace(day=1)
            end = (d.replace(day=28) + dt.timedelta(days=4)).replace(day=1) - dt.timedelta(days=1)
            v = self.e.compute(metric, security_id, AsOf.end_of(end))
            if isinstance(v, Value):
                hist.append(v.value)
        own = V.percentile_rank(now.value, hist) if len(hist) >= 8 else None
        if own is None:
            warn.append("own history shorter than 8 observations: percentile not reported")
        # peers: same sector label AND same resolved playbook, evaluated as of the same date
        prof = self.r.profile(security_id, as_of)
        peers: list[float] = []
        if prof["sector"]:
            for pid in self.r.sector_peers(prof["sector"], as_of, limit=peer_cap * 3):
                if pid == security_id:
                    continue
                if self.e.resolution(pid, as_of).playbook.id != res.playbook.id:
                    continue
                v = self.e.compute(metric, pid, as_of)
                if isinstance(v, Value):
                    peers.append(v.value)
                if len(peers) >= peer_cap:
                    break
        peer_pct = V.percentile_rank(now.value, peers) if len(peers) >= pb_min(res.playbook) else None
        if peer_pct is None:
            warn.append(f"fewer than {pb_min(res.playbook)} comparable peers with data: peer percentile not reported")
        if res.playbook.cyclical and metric == "pe" and "ebitda_margin" in REGISTRY:
            mnow = self.e.compute("ebitda_margin", security_id, as_of) if "ebitda_margin" not in res.playbook.forbidden_metrics else None
            mh = []
            if isinstance(mnow, Value):
                dd = as_of.date_ist.replace(day=1)
                for _ in range(history_years * 12):
                    dd = (dd - dt.timedelta(days=1)).replace(day=1)
                    end = (dd.replace(day=28) + dt.timedelta(days=4)).replace(day=1) - dt.timedelta(days=1)
                    mv = self.e.compute("ebitda_margin", security_id, AsOf.end_of(end))
                    if isinstance(mv, Value):
                        mh.append(mv.value)
                mp = V.percentile_rank(mnow.value, mh) if len(mh) >= 8 else None
                if mp is not None and mp >= 0.8 and (own is None or own <= 0.5):
                    warn.append("cyclical_peak_trap: low P/E at margins in the top 20% of their own history")
        return Relative(metric, now.value, own, len(hist), peer_pct, (sorted(peers)[len(peers) // 2] if peers else None),
                        len(peers), tuple(warn))


def pb_min(pb) -> int:
    return pb.min_peers
