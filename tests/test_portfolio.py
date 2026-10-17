"""Watchlist alerts and portfolio valuation (pure parts), and the endpoints on a tiny fixture."""

from __future__ import annotations

import datetime as dt

import pytest
from fastapi.testclient import TestClient

from conftest import D, add_prices, seed_company
from trikal_api import portfolio as PF
from trikal_core.pit import PitReader

KA = dt.datetime(2026, 5, 20, 18, 0, tzinfo=dt.timezone.utc)


def snap(**kw):
    base = {"code": "XYZ", "security_id": "S:1", "name": "Xyz", "sector": "IT", "price": 100.0, "change_1d": 0.01, "high_52w": 110.0, "low_52w": 80.0, "pos_52w": 0.6,
            "score": 60.0, "score_prev": 58.0, "last_results": None, "upcoming": []}
    base.update(kw)
    return base


def test_alerts_fire_on_results_score_price_extremes_and_actions():
    assert PF.alerts_for(snap(), D(2026, 5, 1)) == []                                   # a quiet day says nothing
    a = PF.alerts_for(snap(last_results={"period": D(2026, 3, 31), "known_at": KA}), D(2026, 5, 1))
    assert [x["type"] for x in a] == ["results"]
    assert PF.alerts_for(snap(last_results={"period": D(2026, 3, 31), "known_at": KA}), D(2026, 6, 1)) == []   # already seen
    assert [x["type"] for x in PF.alerts_for(snap(score=52.0, score_prev=60.0), None)] == ["score"]
    assert PF.alerts_for(snap(score=52.0, score_prev=None), None) == []                  # no earlier score to compare with
    assert [x["type"] for x in PF.alerts_for(snap(change_1d=-0.07), None)] == ["price"]
    assert [x["type"] for x in PF.alerts_for(snap(pos_52w=1.0), None)] == ["high"]
    assert [x["type"] for x in PF.alerts_for(snap(pos_52w=0.0), None)] == ["low"]
    up = PF.alerts_for(snap(upcoming=[{"kind": "dividend", "ex_date": D(2026, 6, 5), "subject": "Dividend - Rs 5 Per Share"}]), None)
    assert up[0]["type"] == "action" and "05 Jun" in up[0]["text"]


def test_holdings_parse_and_errors():
    assert PF.parse_holdings("tcs:10:3200, infy:5") == [{"code": "TCS", "qty": 10.0, "avg": 3200.0}, {"code": "INFY", "qty": 5.0, "avg": None}]
    for bad in ("TCS", "TCS:abc", "TCS:5:x"):
        with pytest.raises(ValueError, match="bad holding"):
            PF.parse_holdings(bad)


def test_valuation_totals_weights_and_sector_mix():
    rows = [{"value": 600.0, "cost": 500.0, "day_pnl": 6.0, "sector": "IT", "score": 70.0}, {"value": 400.0, "cost": None, "day_pnl": -4.0, "sector": "Banks", "score": 40.0},
            {"value": None, "cost": None, "day_pnl": None, "sector": "IT", "score": None}]
    t = PF.valuation(rows)
    assert t["value"] == 1000 and t["cost"] == 500 and t["pnl"] == 500 and t["pnl_pct"] == pytest.approx(1.0)   # only holdings with a cost count in P&L
    assert [s["sector"] for s in t["sectors"]] == ["IT", "Banks"] and t["sectors"][0]["weight"] == pytest.approx(0.6)
    assert rows[0]["weight"] == pytest.approx(0.6) and rows[2]["weight"] is None
    assert t["weighted_score"] == pytest.approx(58.0)


def test_endpoints_value_holdings_and_refuse_bad_input(con, monkeypatch):
    import trikal_api.app as appmod

    sid = seed_company(con, sid="S:INE000P01", code="PORTX", name="Port X Ltd", price=250.0, price_date=D(2025, 3, 28))
    add_prices(con, [("NSE", D(2025, 3, 27), "PORTX", "EQ", sid[2:] + "029", 240.0, 240.0)])
    monkeypatch.setattr(appmod, "open_reader", lambda read_only=True: PitReader(con))
    monkeypatch.setattr(appmod.DB, "reader", None)
    c = TestClient(appmod.app)
    j = c.get("/api/portfolio?as_of=2025-03-29&holdings=PORTX:10:200,NOPE:1").json()
    h = {x["code"]: x for x in j["holdings"]}
    assert h["PORTX"]["value"] == 2500 and h["PORTX"]["pnl"] == 500 and h["PORTX"]["pnl_pct"] == pytest.approx(0.25)
    assert h["PORTX"]["day_pnl"] is not None and h["PORTX"]["day_pnl"] > 0                  # 240 -> 250 on the last session
    assert "error" in h["NOPE"] and j["totals"]["value"] == 2500                          # an unknown code is reported, not guessed
    assert c.get("/api/portfolio?as_of=2025-03-29&holdings=PORTX").status_code == 422
    w = c.get("/api/watch?as_of=2025-03-29&codes=PORTX,NOPE").json()
    assert w["items"][0]["price"] == 250.0 and "error" in w["items"][1]
    assert c.get("/api/watch?codes=PORTX").status_code == 422
