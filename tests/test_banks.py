"""Bank metrics on a synthetic bank whose numbers can be checked by hand. Regression tests for the real defects found on
HDFC Bank: consolidated placeholder zeros shown as real NPA, and no equity line (so no ROE / P/B)."""

from __future__ import annotations

import pytest

from conftest import D, QUARTER_ENDS, add_balance, add_fact_row, add_quarters, seed_company
from trikal_analytics.metrics import Engine
from trikal_analytics.result import NotAvailable, Undefined, Value
from trikal_core.pit import PitReader
from trikal_core.timeutil import AsOf

NOW = AsOf.end_of(D(2025, 3, 31))


@pytest.fixture
def bank(con):
    sid = seed_company(con, sid="S:INE111B01", name="Test Bank Ltd", sector="Financial Services", family="BANKING", code="TBANK", price=50.0)
    add_quarters(con, sid, "InterestEarned", [300] * 4)
    add_quarters(con, sid, "InterestExpended", [180] * 4)
    add_quarters(con, sid, "OtherIncome", [40] * 4)
    add_quarters(con, sid, "OperatingExpenses", [90] * 4)
    add_quarters(con, sid, "ProvisionsOtherThanTaxAndContingencies", [10] * 4)
    add_quarters(con, sid, "ProfitLossForThePeriod", [50] * 4)
    add_balance(con, sid, "PaidUpValueOfEquityShareCapital", 1000.0)
    add_balance(con, sid, "FaceValueOfEquityShareCapital", 10.0, unit="INRPerShare")
    # a bank balance sheet has no "equity": share capital + reserves
    add_balance(con, sid, "Capital", 100.0)
    add_balance(con, sid, "ReservesAndSurplus", 900.0)
    add_balance(con, sid, "Advances", 8000.0)
    add_balance(con, sid, "Deposits", 10000.0)
    add_balance(con, sid, "Assets", 12000.0)
    return sid


def eng(con):
    return Engine(PitReader(con))


def test_equity_is_capital_plus_reserves_so_roe_and_pb_work(con, bank):
    e = eng(con)
    roe = e.compute("roe", bank, NOW)
    assert isinstance(roe, Value) and roe.value == pytest.approx(200 / 1000)          # PAT 200 / (100 + 900)
    assert any(i.concept == "sum:Capital+ReservesAndSurplus" for i in roe.inputs)    # the lineage says it is derived
    pb = e.compute("pb", bank, NOW)
    assert isinstance(pb, Value) and pb.value == pytest.approx(5000 / 1000)          # market cap 100 shares x 50 = 5000


def test_consolidated_zero_asset_quality_is_not_a_real_zero(con, bank):
    # consolidated block carries the placeholder 0.0; the standalone block has the real numbers
    for q in QUARTER_ENDS:
        add_fact_row(con, bank, "PercentageOfGrossNpa", 0.0, q, 3, basis="consolidated", unit="pure")
        add_fact_row(con, bank, "CET1Ratio", 0.0, q, 3, basis="consolidated", unit="pure")
    add_fact_row(con, bank, "PercentageOfGrossNpa", 0.0117, QUARTER_ENDS[-1], 3, basis="standalone", unit="pure")
    add_fact_row(con, bank, "CET1Ratio", 0.1957, QUARTER_ENDS[-1], 3, basis="standalone", unit="pure")
    e = eng(con)
    assert e.compute("gnpa_pct", bank, NOW).value == pytest.approx(0.0117)
    assert e.compute("cet1", bank, NOW).value == pytest.approx(0.1957)


def test_only_placeholder_zeros_means_not_available_never_zero(con, bank):
    for q in QUARTER_ENDS:
        add_fact_row(con, bank, "PercentageOfGrossNpa", 0.0, q, 3, basis="consolidated", unit="pure")
    r = eng(con).compute("gnpa_pct", bank, NOW)
    assert isinstance(r, NotAvailable)


def test_bank_metrics_match_hand_calculation(con, bank):
    e = eng(con)
    assert e.compute("nii", bank, NOW).value == pytest.approx(4 * (300 - 180))
    assert e.compute("ldr", bank, NOW).value == pytest.approx(0.8)
    assert e.compute("cost_to_income", bank, NOW).value == pytest.approx(360 / (480 + 160))   # opex / (NII + other income)
    cc = e.compute("credit_cost", bank, NOW)
    assert cc.value == pytest.approx(40 / 8000) and "single_balance_sheet_date" in cc.warnings   # one balance sheet date only
    assert e.compute("nii_to_assets", bank, NOW).value == pytest.approx(480 / 12000)


def test_non_positive_denominators_are_undefined(con, bank):
    add_balance(con, bank, "Deposits", 0.0, pe=D(2025, 3, 31))
    assert isinstance(eng(con).compute("ldr", bank, AsOf.end_of(D(2025, 5, 31))), (Undefined, Value))


def test_non_banks_still_get_equity_from_the_ordinary_concept(con):
    sid = seed_company(con, sid="S:INE222C01", name="Plain Co", sector="Information Technology", code="PLAIN")
    add_quarters(con, sid, "ProfitLossForPeriod", [100] * 4)
    add_balance(con, sid, "EquityAttributableToOwnersOfParent", 1500.0)
    add_balance(con, sid, "Capital", 1.0)                 # must not override the real equity line
    add_balance(con, sid, "ReservesAndSurplus", 1.0)
    r = eng(con).compute("roe", sid, NOW)
    assert r.value == pytest.approx(400 / 1500)
