"""Valuation maths against closed-form identities (no data, no database)."""

import pytest

from trikal_analytics import valuation as V


def test_constant_growth_dcf_equals_gordon_closed_form():
    f0, r, g, n = 100.0, 0.12, 0.05, 10
    res = V.dcf_fcff(f0, r, g_start=g, g_terminal=g, years=n, net_debt=0.0)
    gordon_ev = f0 * (1 + g) / (r - g)
    assert res.enterprise_value == pytest.approx(gordon_ev, rel=1e-12)
    assert res.equity_value == pytest.approx(gordon_ev, rel=1e-12)


def test_dcf_subtracts_net_debt_and_minorities_and_divides_by_shares():
    res = V.dcf_fcff(100.0, 0.12, 0.05, 0.05, 10, net_debt=300.0, minorities=50.0, shares=10.0)
    assert res.equity_value == pytest.approx(res.enterprise_value - 350.0)
    assert res.per_share == pytest.approx(res.equity_value / 10.0)
    assert 0 < res.terminal_share < 1


def test_growth_fades_linearly_to_terminal():
    assert V.growth_path(0.20, 0.05, 4) == pytest.approx([0.20, 0.15, 0.10, 0.05])
    assert V.growth_path(0.10, 0.05, 1) == [0.10]


def test_rate_must_exceed_terminal_growth():
    with pytest.raises(V.ValuationError):
        V.dcf_fcff(100.0, 0.05, 0.05, 0.05, 5, 0.0)
    with pytest.raises(V.ValuationError):
        V.justified_pb(0.15, 0.06, 0.06)


def test_non_positive_base_cash_flow_is_rejected_not_modelled():
    with pytest.raises(V.ValuationError):
        V.dcf_fcff(-5.0, 0.12, 0.05, 0.05, 10, 0.0)


def test_reverse_dcf_inverts_the_forward_model():
    kw = dict(fcff0=100.0, wacc=0.12, g_terminal=0.05, years=10, net_debt=200.0, minorities=0.0)
    market = V.dcf_fcff(kw["fcff0"], kw["wacc"], 0.18, kw["g_terminal"], kw["years"], kw["net_debt"]).equity_value
    g = V.reverse_dcf_growth(market, **kw)
    assert g == pytest.approx(0.18, abs=1e-6)


def test_reverse_dcf_says_no_solution_instead_of_clamping():
    kw = dict(fcff0=100.0, wacc=0.12, g_terminal=0.05, years=10, net_debt=0.0)
    with pytest.raises(V.ValuationError, match="no solution"):
        V.reverse_dcf_growth(1e12, **kw)
    with pytest.raises(V.ValuationError, match="no solution"):
        V.reverse_dcf_growth(1.0, **kw)


def test_justified_multiples_closed_form():
    assert V.justified_pb(0.15, 0.12, 0.05) == pytest.approx(0.10 / 0.07)
    assert V.justified_pe(0.4, 0.12, 0.05) == pytest.approx(0.4 * 1.05 / 0.07)
    assert V.justified_pb(0.12, 0.12, 0.05) == pytest.approx(1.0)       # ROE = Ke -> trades at book


def test_residual_income_equals_book_when_roe_equals_cost_of_equity():
    r = V.residual_income(1000.0, [0.13] * 5, 0.13, 0.05)
    assert r.equity_value == pytest.approx(1000.0)


def test_residual_income_rewards_returns_above_cost_of_equity():
    hi = V.residual_income(1000.0, [0.20] * 5, 0.13, 0.05).equity_value
    lo = V.residual_income(1000.0, [0.08] * 5, 0.13, 0.05).equity_value
    assert hi > 1000.0 > lo


def test_ddm_flat_dividends_match_perpetuity():
    r = V.ddm(10.0, 0.10, 0.0, 0.0, 8)
    assert r.per_share == pytest.approx(10.0 / 0.10, rel=1e-9)


def test_sotp_applies_stakes_net_debt_and_holdco_discount():
    parts = [V.SotpPart("ListedSub", 1000.0, 0.60, "market"), V.SotpPart("Unlisted", 400.0, 1.0, "assumed")]
    r = V.sotp(parts, holdco_net_debt=100.0, holdco_discount=0.25, shares=10.0)
    assert r.equity_value == pytest.approx((600 + 400 - 100) * 0.75)
    assert r.per_share == pytest.approx(r.equity_value / 10)
    with pytest.raises(V.ValuationError):
        V.sotp(parts, 0.0, 1.0)


def test_nav_and_per_unit():
    assert V.nav_per_share({"land": 1000.0, "inventory": 500.0}, {"land": 0.2}, 300.0, 10.0) == pytest.approx((800 + 500 - 300) / 10)
    assert V.per_unit(1200.0, 400.0) == 3.0
    with pytest.raises(V.ValuationError):
        V.per_unit(1.0, 0.0)


def test_scenarios_must_sum_to_one_and_give_a_range_not_a_point():
    sc = [V.Scenario("bear", 0.25, {"g": 0.0}), V.Scenario("base", 0.5, {"g": 0.05}), V.Scenario("bull", 0.25, {"g": 0.10})]
    rng = V.scenario_range(sc, lambda a: 100 * (1 + a["g"]))
    assert rng.low == pytest.approx(100.0) and rng.high == pytest.approx(110.0) and rng.expected == pytest.approx(105.0)
    with pytest.raises(V.ValuationError):
        V.scenario_range([V.Scenario("a", 0.5, {}), V.Scenario("b", 0.4, {})], lambda a: 1.0)


def test_sensitivity_grid_marks_invalid_cells_none():
    grid = V.sensitivity(lambda wacc, g: V.dcf_fcff(100.0, wacc, g, g, 5, 0.0).equity_value,
                         "wacc", [0.04, 0.10], "g", [0.05])
    assert grid[0] == [None] and grid[1][0] is not None


def test_percentile_rank():
    assert V.percentile_rank(5, [1, 2, 3, 4]) == 1.0
    assert V.percentile_rank(0, [1, 2, 3, 4]) == 0.0
    assert V.percentile_rank(2, [1, 2, 3]) == pytest.approx((1 + 0.5) / 3)
    assert V.percentile_rank(1, []) is None
