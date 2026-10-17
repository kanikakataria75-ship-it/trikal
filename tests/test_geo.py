"""Policy/geo markers and chokepoint intensity from dated context items (hand-written fixtures)."""

from __future__ import annotations

import datetime as dt

import pytest
from fastapi.testclient import TestClient

from conftest import D
from trikal_core.db import insert_many
from trikal_core.pit import PitReader
from trikal_core.timeutil import AsOf, at_ist


def ctx(con, rows):
    now = at_ist(D(2026, 1, 1), dt.time(0))
    insert_many(con, "INSERT INTO context_event VALUES (?,?,?,?,?,?,?,?,?,?)",
                [(d, sc, None, None, t, "Reuters", "https://example.org/x", "Portal:Current_events/x", "sha", now) for d, sc, t in rows])


def test_markers_are_tagged_dated_and_never_after_as_of(con):
    ctx(con, [(D(2020, 3, 23), "world", "The Reserve Bank of India cuts the repo rate by 75 basis points."),
              (D(2020, 3, 24), "india", "Prime Minister announces a nationwide lockdown to curb the COVID-19 pandemic."),
              (D(2020, 3, 25), "world", "A random sports result with nothing relevant."),
              (D(2022, 2, 24), "world", "Russia launches an invasion of Ukraine; sanctions follow."),
              (D(2024, 2, 1), "india", "The Union Budget is presented in Parliament by the Finance Minister.")])
    r = PitReader(con)
    m = r.context_markers(AsOf.end_of(D(2022, 12, 31)))
    tags = {(x["day"], x["tag"]) for x in m}
    assert (D(2020, 3, 23), "rbi") in tags and (D(2020, 3, 24), "pandemic") in tags
    assert (D(2022, 2, 24), "conflict") in tags and (D(2022, 2, 24), "sanctions") in tags
    assert all(x["day"] <= D(2022, 12, 31) for x in m)                       # the 2024 Budget does not exist yet at this as-of
    assert not any("sports" in x["text"] for x in m)
    assert all(x["source_name"] and x["source_url"] for x in m)               # every marker keeps its source


def test_budget_tag_only_applies_to_india_scope(con):
    ctx(con, [(D(2021, 2, 1), "world", "Another country's Union Budget is presented in Parliament by the Finance Minister."),
              (D(2021, 2, 1), "india", "The Union Budget is presented in Parliament by the Finance Minister.")])
    m = PitReader(con).context_markers(AsOf.end_of(D(2021, 12, 31)))
    assert [x["scope"] for x in m if x["tag"] == "budget"] == ["india"]


def test_chokepoint_intensity_is_a_percentile_of_its_own_history_up_to_as_of(con):
    quiet = [(D(2019, m, 10), "world", "Ships transit the Strait of Hormuz as usual.") for m in range(1, 13)]
    hot = [(D(2020, 1, 5 + i), "world", f"Tanker seized near the Strait of Hormuz, incident {i}.") for i in range(8)]
    later = [(D(2025, 6, 5), "world", "Strait of Hormuz closure threatened.")]
    ctx(con, quiet + hot + later)
    r = PitReader(con)
    h = next(c for c in r.chokepoint_pulse(AsOf.end_of(D(2020, 2, 15))) if c["id"] == "hormuz")
    assert h["last_90d"] == 9 and h["intensity"] == pytest.approx(13 / 14)    # Dec+Jan+Feb; only the Nov-Jan window (10) was busier
    assert all(x["day"] <= D(2020, 2, 15) for x in h["recent"])               # the 2025 item is invisible at this as-of
    assert h["sectors"] and h["source"]
    q = next(c for c in r.chokepoint_pulse(AsOf.end_of(D(2019, 12, 31))) if c["id"] == "hormuz")
    assert q["intensity"] <= 1.0 and q["last_90d"] == 3


def test_endpoints_require_as_of_and_return_corridors(con, monkeypatch):
    import trikal_api.app as appmod

    monkeypatch.setattr(appmod, "open_reader", lambda read_only=True: PitReader(con))
    monkeypatch.setattr(appmod.DB, "reader", None)
    c = TestClient(appmod.app)
    assert c.get("/api/geo").status_code == 422 and c.get("/api/context/markers").status_code == 422
    j = c.get("/api/geo?as_of=2020-02-15").json()
    assert {x["id"] for x in j["corridors"]} >= {"gulf_crude", "europe", "east_asia"} and len(j["chokepoints"]) == 4
