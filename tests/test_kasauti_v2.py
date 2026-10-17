"""KASAUTI v2: v1 stays frozen and unchanged, the new pillars behave, credibility is ranked among everyone and shrunk toward 50%."""

from __future__ import annotations

import datetime as dt

import pytest

from conftest import add_fact_row, add_quarters, seed_company
from test_kasauti import D, full
from trikal_analytics import metrics as M
from trikal_core.pit import PitReader
from trikal_core.timeutil import AsOf
from trikal_kasauti import config as KC
from trikal_kasauti import scoring as SC


def test_v2_config_is_valid_and_v1_is_still_the_frozen_file():
    c = KC.load(2)
    for prof in c.profiles.values():
        assert sum(p.weight for p in prof) == pytest.approx(1.0)
    assert {p.name for p in c.profiles["industrial"]} >= {"earnings_quality", "credibility"}
    assert "earnings_quality" not in {p.name for p in c.profiles["financial"]}          # cash-flow ratios mean nothing for a bank
    assert "credibility" not in c.not_in_v1 and "macro_fit" in c.not_in_v1
    fz = KC.frozen()
    assert fz["version"] == 1 and fz["sha256"] == KC.load(1).sha256                       # v2 did not touch the frozen v1


def with_eq(i, q, kept=None):
    r = full(i, q)
    r["values"].update(cfo_to_profit=q, accruals_ratio=-q, other_income_share=-q, promise_kept=kept)
    return r


def test_credibility_is_ranked_among_all_companies_not_one_sector_and_dropped_when_missing():
    rows = [with_eq(i, i + 1, kept=(i + 1) / 20 if i < 10 else None) for i in range(12)]
    for i, r in enumerate(rows):
        r["playbook"] = "it_services" if i % 2 else "cement"                              # five of the ten with a value sit in each sector
    out = {r["security_id"]: r for r in SC.score_panel(rows, KC.load(2), D(2026, 9, 30))}
    top = out["S:009"]["pillars"]["credibility"]
    assert top["metrics"]["promise_kept"]["percentile"] > 0.9                               # best of ten across both sectors
    assert "credibility" not in out["S:011"]["pillars"] and "credibility" in out["S:011"]["dropped"]
    assert out["S:011"]["score"] is not None                                                # no data costs the pillar, not the score


def test_promise_kept_is_shrunk_and_needs_two_judged_statements(monkeypatch):
    verdicts = iter(["delivered"])
    monkeypatch.setattr(SC.PR, "dedupe", lambda p: p)
    monkeypatch.setattr(SC.PR, "judge", lambda *a: {"verdict": next(verdicts)})
    class R:
        def concall_promises(self, sid, a):
            return [1]
    assert SC.promise_kept(None, R(), "S:1", None) is None                                  # one statement is not enough
    verdicts = iter(["delivered", "delivered", "missed", "pending", "not judged"])
    class R3:
        def concall_promises(self, sid, a):
            return [1, 2, 3, 4, 5]
    assert SC.promise_kept(None, R3(), "S:1", None) == pytest.approx((2.0 + 1.0) / (3 + 2))   # two kept, one missed, shrunk toward 0.5


def test_earnings_quality_metrics_use_the_same_twelve_months_and_are_not_defined_for_losses(con):
    sid = seed_company(con)
    pe = dt.date(2024, 12, 31)
    for li, v in (("CashFlowsFromUsedInOperatingActivities", 90e7), ("ProfitLossForPeriod", 100e7), ("Assets", 1000e7)):
        add_fact_row(con, sid, li, v, pe, 12 if li != "Assets" else None)
    add_quarters(con, sid, "OtherIncome", [5e7] * 4)
    add_quarters(con, sid, "ProfitBeforeTax", [30e7] * 4)
    r = PitReader(con)
    eng = M.Engine(r)
    a = AsOf.end_of(dt.date(2025, 3, 20))
    got = eng.compute_many(["cfo_to_profit", "accruals_ratio", "other_income_share"], sid, a)
    assert got["cfo_to_profit"].value == pytest.approx(0.9)
    assert got["accruals_ratio"].value == pytest.approx(0.01)                               # (100 - 90) / 1000
    assert got["other_income_share"].value == pytest.approx(20e7 / 120e7)
