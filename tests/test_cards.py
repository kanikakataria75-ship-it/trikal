"""Results card, score history and heatmap: point in time, comparisons against the right quarter, missing data stays missing."""

from __future__ import annotations

import json

from fastapi.testclient import TestClient

from conftest import D, QUARTER_ENDS, add_quarters, seed_company
from trikal_api import cards
from trikal_core.db import insert_many
from trikal_core.pit import PitReader
from trikal_core.timeutil import AsOf, utcnow


def seeded(con):
    sid = seed_company(con)
    add_quarters(con, sid, "RevenueFromOperations", [100e7, 110e7, 121e7, 133.1e7])
    add_quarters(con, sid, "ProfitBeforeExceptionalItemsAndTax", [20e7, 22e7, 24e7, 26e7])
    add_quarters(con, sid, "FinanceCosts", [1e7, 1e7, 1e7, 1e7])
    add_quarters(con, sid, "DepreciationDepletionAndAmortisationExpense", [2e7, 2e7, 2e7, 2e7])
    add_quarters(con, sid, "ProfitLossForPeriod", [15e7, 16e7, 18e7, 20e7])
    return sid


def test_the_card_compares_the_latest_quarter_with_the_one_before_and_hides_what_is_missing(con):
    sid = seeded(con)
    c = cards.results_card(PitReader(con), sid, AsOf.now(), [])
    assert c["available"] and c["period_end"] == QUARTER_ENDS[-1] and c["prev_end"] == QUARTER_ENDS[-2]
    assert c["yago_end"] is None                                                     # only four quarters stored: no year-ago column, no invented one
    rev = next(r for r in c["rows"] if r["label"] == "Revenue")
    assert abs(rev["qoq"] - 0.10) < 1e-9 and rev["yoy"] is None
    assert not any(r["label"].startswith("EPS") for r in c["rows"])                  # EPS was never stored
    ebitda = next(r for r in c["rows"] if r["label"].startswith("EBITDA"))
    assert ebitda["now"] == 26e7 + 1e7 + 2e7                                         # profit before tax + interest + depreciation (no other income stored)


def test_the_card_of_an_earlier_date_shows_only_what_was_public_then(con):
    sid = seeded(con)
    c = cards.results_card(PitReader(con), sid, AsOf.end_of(D(2024, 9, 1)), [])
    assert c["period_end"] == QUARTER_ENDS[1]                                        # the September-quarter results were not out on 1 Sep 2024


def test_history_and_heatmap_endpoints(con, tmp_path, monkeypatch):
    import trikal_api.app as appmod

    sid = seeded(con)
    pil = {"quality": {"score": 0.8, "coverage": 1.0, "metrics": {}}, "growth": {"score": None, "coverage": 0.2, "metrics": {}}}
    detail = json.dumps({"profile": "industrial", "peer_fallback": False, "dropped": {}, "skipped": {}, "drivers": [], "pillars": pil})
    for day, score in ((D(2024, 6, 28), 55.0), (D(2024, 9, 30), 61.0)):
        insert_many(con, "INSERT INTO kasauti_score VALUES (?,?,?,?,?,?,?,?,?,?,?)", [(1, day, sid, score, 0.9, "ok", "it_services", "it_services", 12, detail, utcnow())])
    monkeypatch.setattr(appmod, "open_reader", lambda read_only=True: PitReader(con))
    monkeypatch.setattr(appmod.DB, "reader", None)
    monkeypatch.setenv("TRIKAL_DATA", str(tmp_path))
    c = TestClient(appmod.app)
    h = c.get("/api/company/TEST/kasauti/history?as_of=2024-08-15").json()
    assert h["available"] and [p["score"] for p in h["points"]] == [55.0]            # the September score does not exist yet
    assert h["points"][0]["pillars"]["growth"] is None and h["points"][0]["reconstructed"] is True
    assert c.get("/api/company/TEST/kasauti/history?as_of=2024-03-01").json()["available"] is False
    assert c.get("/api/company/TEST/results-card?as_of=2024-12-31").json()["available"] is True
