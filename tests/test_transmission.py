"""Transmission Engine / SHOCK on the synthetic universe (Alpha truly loads 0.5 on Brent; the equal-weight market carries 0.25)."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from conftest import D
from test_sensitivity import make_universe
from trikal_analytics import sensitivity as S
from trikal_core.pit import PitReader
from trikal_core.timeutil import AsOf


@pytest.fixture
def world(con, monkeypatch):
    from trikal_pipeline import sensitivity as B

    monkeypatch.setattr(B, "MIN_MARKET_MEMBERS", 10)
    make_universe(con)
    B.build(con)
    import trikal_api.app as appmod

    monkeypatch.setattr(appmod, "open_reader", lambda read_only=True: PitReader(con))
    monkeypatch.setattr(appmod.DB, "reader", None)
    return TestClient(appmod.app), PitReader(con)


def test_shock_total_is_relative_plus_market_and_matches_the_true_beta(world):
    _, r = world
    from trikal_api import transmission as T

    a = AsOf.end_of(D(2018, 6, 30))
    t = T.shock_table(r, a, "BRENT +20")
    rows = {x["sector"]: x for x in t["rows"]}
    expected = 0.5 * S.parse_shocks("BRENT +20")[0].delta                         # Alpha: true beta 0.5 x ln(1.2)
    assert rows["Alpha"]["total"] == pytest.approx(expected, abs=0.03)
    assert abs(rows["Beta"]["total"]) < 0.03
    assert rows["Alpha"]["total"] == pytest.approx(rows["Alpha"]["relative"] + rows["Alpha"]["market"])
    assert t["rows"][0]["sector"] == "Beta" and t["market"]["total"] == pytest.approx(0.25 * 0.1823, abs=0.03)   # sorted worst first
    assert "high" in {c["confidence"] for row in t["rows"] for c in row["cells"].values()}


def test_combined_shock_adds_and_warns_about_double_counting(world):
    _, r = world
    from trikal_api import transmission as T

    t = T.shock_table(r, AsOf.end_of(D(2018, 6, 30)), "BRENT +10 & BRENT +10")
    assert len(t["shocks"]) == 2 and any("double" in n for n in t["notes"])


def test_a_shock_far_outside_the_sample_is_flagged_as_extrapolation(world):
    _, r = world
    from trikal_api import transmission as T

    a = AsOf.end_of(D(2018, 6, 30))
    assert any("Far outside" in n for n in T.shock_table(r, a, "BRENT +400")["notes"])
    assert not any("Far outside" in n for n in T.shock_table(r, a, "BRENT +1")["notes"])


def test_nothing_is_estimated_before_enough_history_exists(world):
    _, r = world
    from trikal_api import transmission as T

    t = T.shock_table(r, AsOf.end_of(D(2013, 6, 30)), "BRENT +20")
    assert t["rows"] == [] and t["market"]["total"] == 0


def test_endpoints_validate_input_and_require_as_of(world):
    client, _ = world
    assert client.get("/api/shock?q=BRENT%20%2B20").status_code == 422                      # as_of is required
    assert client.get("/api/shock?q=NOPE%20%2B1&as_of=2018-06-30").status_code == 422        # unknown driver: a message, not a crash
    ok = client.get("/api/shock?q=BRENT%20%2B20&as_of=2018-06-30")
    assert ok.status_code == 200 and ok.json()["rows"]
    ov = client.get("/api/transmission?as_of=2018-06-30").json()
    assert {s["sector"] for s in ov["sectors"]} == {"Alpha", "Beta"} and ov["market"]["brent"]["confidence"] in ("high", "medium")
    assert ov["drivers"][0]["id"] == "brent" and ov["drivers"][0]["latest"]["value"] > 0
