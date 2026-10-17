"""Metric engine and Valuation Lab on a synthetic company whose numbers can be checked by hand.

Company: 4 quarters of revenue 1000, expenses 800 (finance 20, depreciation 30), profit 100, tax 30, PBT 130.
  TTM revenue 4000; EBITDA = 4000 - (3200 - 80 - 120) = 1000; PAT 400.
  100 shares (paid-up 1000 / face value 10) at price 50 -> market cap 5000.
  Equity 2000; borrowings 200 + 300; cash 100 + other bank 50 -> net debt 350; EV 5350.
"""

import datetime as dt

import pytest

from conftest import D, QUARTER_ENDS, add_balance, add_fact_row, add_quarters, known_after, seed_company, seed_standard
from trikal_analytics import valuation as V
from trikal_analytics.lab import Lab, template_assumptions
from trikal_analytics.metrics import Engine
from trikal_analytics.result import ForbiddenMetric, ForbiddenMethod, NotAvailable, Undefined, Value
from trikal_core.db import insert_many
from trikal_core.pit import PitReader
from trikal_core.timeutil import AsOf, at_ist

NOW = AsOf.end_of(D(2025, 3, 31))


def engine(con):
    return Engine(PitReader(con))


def test_core_metrics_match_hand_calculation(con):
    sid = seed_standard(con)
    e = engine(con)
    g = lambda m: e.compute(m, sid, NOW)  # noqa: E731
    assert g("revenue_ttm").value == 4000 and g("pat_ttm").value == 400
    assert g("ebitda").value == 1000 and g("ebitda_margin").value == pytest.approx(0.25)
    assert g("ebit").value == pytest.approx(880) and g("interest_coverage").value == pytest.approx(880 / 80)
    assert g("market_cap").value == 5000 and g("pe").value == pytest.approx(12.5)
    assert g("net_debt").value == 350 and g("ev").value == 5350
    assert g("ev_ebitda").value == pytest.approx(5.35) and g("ev_sales").value == pytest.approx(5350 / 4000)
    assert g("pb").value == pytest.approx(2.5) and g("roe").value == pytest.approx(0.2)
    assert g("debt_to_equity").value == pytest.approx(0.25) and g("current_ratio").value == pytest.approx(1.5)
    v = g("pe")
    assert {i.name for i in v.inputs} >= {"share_price", "paid_up_equity_capital", "face_value"}
    assert all(i.filing_id for i in v.inputs if i.name != "share_price")      # lineage on every input
    assert v.basis == "consolidated" and "post_ind_as_116" in " ".join(g("ebitda").warnings)


def test_loss_makes_pe_undefined_not_negative(con):
    sid = seed_standard(con)
    con.execute("DELETE FROM fact_financial WHERE concept = 'ProfitLossForPeriod'")
    add_quarters(con, sid, "ProfitLossForPeriod", [-50, -20, -10, 20])
    e = engine(con)
    out = e.compute("pe", sid, NOW)                                   # a data condition: explained, not raised
    assert isinstance(out, Undefined) and "not meaningful" in out.reason
    res = e.resolution(sid, NOW)
    assert "loss_making" in res.playbook.overlays and not res.playbook.is_primary_allowed("pe")


def test_non_positive_denominators_are_undefined(con):
    sid = seed_standard(con)
    add_balance(con, sid, "Equity", -100.0, pe=D(2025, 3, 31))
    assert isinstance(engine(con).compute("pb", sid, AsOf.end_of(D(2025, 6, 1))), (Undefined, NotAvailable))
    con.execute("DELETE FROM fact_financial WHERE concept = 'Expenses'")
    add_quarters(con, sid, "Expenses", [1200] * 4)                    # expenses above revenue -> negative EBITDA
    out = engine(con).compute("ev_ebitda", sid, NOW)
    assert isinstance(out, Undefined) and "G1" in out.reason


def test_missing_inputs_are_named_never_guessed(con):
    sid = seed_company(con)
    add_quarters(con, sid, "RevenueFromOperations", [1000] * 4)
    out = engine(con).compute("ebitda", sid, NOW)
    assert isinstance(out, NotAvailable) and set(out.missing) == {"total_expenses", "finance_costs", "depreciation_amortisation"}


def test_financial_company_cannot_get_ebitda_or_leverage(con):
    sid = seed_standard(con, sector="Financial Services", family="BANKING", name="Test Bank Ltd")
    e = engine(con)
    assert e.resolution(sid, NOW).playbook.id == "banks"
    for m in ("ebitda", "ev_ebitda", "debt_to_equity", "net_debt_ebitda", "current_ratio"):
        with pytest.raises(ForbiddenMetric):
            e.compute(m, sid, NOW)
    assert isinstance(e.compute("pb", sid, NOW), Value)
    na = e.compute("nim", sid, NOW)
    assert isinstance(na, NotAvailable) and "investor presentation" in na.reason   # names the missing source
    many = e.compute_many(["ebitda", "pb"], sid, NOW)
    assert many["ebitda"].playbook == "banks" and isinstance(many["pb"], Value)       # explainable, not raised


def test_point_in_time_hides_filings_published_after_as_of(con):
    sid = seed_standard(con)
    e = engine(con)
    early = AsOf.end_of(known_after(QUARTER_ENDS[-1]).date() - dt.timedelta(days=1))   # last quarter not yet public
    assert isinstance(e.compute("revenue_ttm", sid, early), NotAvailable)               # only 3 quarters known
    assert e.compute("revenue_ttm", sid, AsOf.end_of(known_after(QUARTER_ENDS[-1]).date())).value == 4000


def test_basis_is_never_mixed_inside_one_ttm(con):
    sid = seed_standard(con)
    con.execute("DELETE FROM fact_financial WHERE concept = 'RevenueFromOperations'")
    add_quarters(con, sid, "RevenueFromOperations", [1000] * 4, basis="standalone")
    for pe in QUARTER_ENDS[-2:]:
        add_fact_row(con, sid, "RevenueFromOperations", 2000, pe, 3, basis="consolidated")
    out = engine(con).compute("revenue_ttm", sid, NOW)
    # consolidated is "recent", so it is chosen; with only 2 consolidated quarters the answer is missing, not 1000+1000+2000+2000
    assert isinstance(out, NotAvailable)


def test_shares_are_rolled_forward_for_a_bonus_after_the_filing(con):
    sid = seed_standard(con)
    insert_many(con, """INSERT INTO adj_event (security_id, exchange, code, ex_date, factor, method, agreement, applied, known_at, known_precision)
                        VALUES (?,?,?,?,?,?,?,?,?,?)""",
                [(sid, "NSE", "TEST", D(2025, 3, 10), 0.5, "announcement", "parsed_confirmed", True,
                  at_ist(D(2025, 3, 10), dt.time(9)), "convention")])
    # price after the 1:1 bonus is 25; paid-up capital in the last filing still reflects 100 shares
    con.execute("DELETE FROM price_eod")
    from conftest import add_prices
    add_prices(con, [("NSE", D(2025, 3, 28), "TEST", "EQ", "INE000X01029", 25.0, 25.0)])
    assert engine(con).compute("market_cap", sid, NOW).value == pytest.approx(25.0 * 200)


def test_stale_price_is_not_used(con):
    sid = seed_standard(con, price_date=D(2024, 12, 1))
    out = engine(con).compute("market_cap", sid, NOW)
    assert isinstance(out, NotAvailable) and "price" in out.missing[0]


def test_old_page_inputs_carry_a_warning(con):
    sid = seed_company(con)
    for pe in QUARTER_ENDS:
        add_fact_row(con, sid, "html:total_income_from_operations", 1000, pe, 3)
    out = engine(con).compute("revenue_ttm", sid, NOW)
    assert any(w.startswith("old_page_input") for w in out.warnings)


def test_growth_needs_a_positive_base(con):
    sid = seed_standard(con)
    add_fact_row(con, sid, "RevenueFromOperations", 900, D(2023, 12, 31), 3, known=known_after(D(2023, 12, 31)))
    assert engine(con).compute("revenue_growth", sid, NOW).value == pytest.approx(1000 / 900 - 1)
    con.execute("DELETE FROM fact_financial WHERE concept='RevenueFromOperations' AND period_end = '2023-12-31'")
    add_fact_row(con, sid, "RevenueFromOperations", -5, D(2023, 12, 31), 3, known=known_after(D(2023, 12, 31)))
    assert isinstance(engine(con).compute("revenue_growth", sid, NOW), Undefined)


# ---- valuation lab ------------------------------------------------------------------------------------------------

def seed_cashflow(con, sid):
    add_fact_row(con, sid, "CashFlowsFromUsedInOperatingActivities", 600.0, D(2024, 12, 31), 12)
    add_fact_row(con, sid, "PurchaseOfPropertyPlantAndEquipmentClassifiedAsInvestingActivities", -200.0, D(2024, 12, 31), 12)


def test_forbidden_method_stops_before_any_input_is_read(con):
    sid = seed_standard(con, sector="Financial Services", family="BANKING", name="Test Bank Ltd")
    lab = Lab(engine(con))
    for method in ("dcf_fcff", "reverse_dcf_fcff"):
        with pytest.raises(ForbiddenMethod):
            lab.run(method, sid, NOW, {})                       # no assumptions needed: it never gets that far
    assert "dcf_fcff" in lab.methods(sid, NOW)["forbidden"]
    assert lab.methods(sid, NOW)["primary"] == ["p_abv", "justified_pb"]


def test_no_hidden_defaults_missing_assumptions_are_named(con):
    sid = seed_standard(con)
    seed_cashflow(con, sid)
    with pytest.raises(V.ValuationError, match="missing assumptions"):
        Lab(engine(con)).run("dcf_fcff", sid, NOW, {"wacc": 0.12})


def test_dcf_matches_the_pure_model_and_labels_every_assumption(con):
    sid = seed_standard(con)
    seed_cashflow(con, sid)
    lab = Lab(engine(con))
    ass = {"wacc": 0.12, "g_start": 0.10, "g_terminal": 0.05, "years": 10}
    v = lab.run("dcf_fcff", sid, NOW, ass)
    fcff0 = (600 - 200) + 80 * (1 - 30 / 130)                     # CFO + capex + after-tax interest
    expect = V.dcf_fcff(fcff0, 0.12, 0.10, 0.05, 10, net_debt=350.0, minorities=0.0, shares=100.0)
    assert v.equity_value == pytest.approx(expect.equity_value) and v.per_share == pytest.approx(expect.per_share)
    assert v.value_to_price == pytest.approx(expect.per_share / 50.0) and v.terminal_share == pytest.approx(expect.terminal_share)
    src = {a.name: a.source for a in v.assumptions}
    assert src["wacc"] == "user" and src["fcff0"].startswith("pit:") and src["net_debt"].startswith("pit:")


def test_reverse_dcf_recovers_the_growth_baked_into_the_price(con):
    sid = seed_standard(con)
    seed_cashflow(con, sid)
    lab = Lab(engine(con))
    base = {"wacc": 0.12, "g_terminal": 0.05, "years": 10}
    implied = lab.run("reverse_dcf_fcff", sid, NOW, base).implied["implied_year1_growth"]
    back = lab.run("dcf_fcff", sid, NOW, {**base, "g_start": implied})
    assert back.equity_value == pytest.approx(5000.0, rel=1e-6)       # DCF at the implied growth reproduces the market cap


def test_scenario_range_is_a_range_with_probabilities(con):
    sid = seed_standard(con)
    seed_cashflow(con, sid)
    sc = [V.Scenario("bear", 0.3, {"g_start": 0.02}), V.Scenario("base", 0.5, {"g_start": 0.08}), V.Scenario("bull", 0.2, {"g_start": 0.15})]
    rng = Lab(engine(con)).scenario_range("dcf_fcff", sid, NOW, sc, {"wacc": 0.12, "g_terminal": 0.05, "years": 10})
    assert rng.low < rng.values["base"] < rng.high and rng.low == rng.values["bear"] and rng.high == rng.values["bull"]
    assert rng.expected == pytest.approx(sum(rng.values[n] * rng.probabilities[n] for n in rng.values))


def test_template_assumptions_are_labelled_and_never_applied_silently(con):
    t = template_assumptions("dcf_fcff", "it_services")
    assert all(a.source == "template" for a in t.values())
    sid = seed_standard(con)
    seed_cashflow(con, sid)
    v = Lab(engine(con)).run("dcf_fcff", sid, NOW, t)
    assert {a.source for a in v.assumptions if a.name in t} == {"template"}      # the output says they were templates


def test_valuation_rejects_a_rate_below_growth(con):
    sid = seed_standard(con)
    seed_cashflow(con, sid)
    with pytest.raises(V.ValuationError):
        Lab(engine(con)).run("dcf_fcff", sid, NOW, {"wacc": 0.04, "g_start": 0.10, "g_terminal": 0.05, "years": 10})


def test_justified_pb_uses_book_equity_from_filings(con):
    sid = seed_standard(con, sector="Financial Services", family="BANKING", name="Test Bank Ltd")
    v = Lab(engine(con)).run("justified_pb", sid, NOW, {"cost_of_equity": 0.12, "g_terminal": 0.05, "roe": 0.15})
    assert v.equity_value == pytest.approx(2000 * 0.10 / 0.07) and v.implied["justified_pb"] == pytest.approx(0.10 / 0.07)
    assert v.playbook == "banks"
