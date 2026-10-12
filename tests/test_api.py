"""M3 read API and the PIT views behind it. All rows are test fixtures."""

from __future__ import annotations

import datetime as dt

import pytest
from fastapi.testclient import TestClient

from trikal_core.db import insert_many
from trikal_core.pit import PitReader
from trikal_core.timeutil import AsOf

from conftest import D, add_prices, seed_standard


@pytest.fixture
def client(con, monkeypatch):
    import trikal_api.app as appmod

    monkeypatch.setattr(appmod, "open_reader", lambda read_only=True: PitReader(con))
    monkeypatch.setattr(appmod.DB, "reader", None)
    return TestClient(appmod.app)


def test_every_endpoint_requires_as_of(client, con):
    seed_standard(con)
    for path in ["/api/meta", "/api/search?q=TEST", "/api/company/TEST", "/api/company/TEST/prices",
                 "/api/company/TEST/financials", "/api/company/TEST/timeline", "/api/market"]:
        assert client.get(path).status_code == 422, path


def test_future_as_of_is_refused(client, con):
    seed_standard(con)
    future = (dt.date.today() + dt.timedelta(days=30)).isoformat()
    r = client.get(f"/api/company/TEST?as_of={future}")
    assert r.status_code == 422 and "future" in r.json()["detail"]


def test_not_listed_yet_is_404_not_empty(client, con):
    seed_standard(con)  # listed from 2000-01-01
    assert client.get("/api/company/TEST?as_of=1999-06-30").status_code == 404


def test_metrics_keep_their_state_and_lineage(client, con):
    seed_standard(con)
    body = client.get("/api/company/TEST?as_of=2025-03-31").json()
    m = body["metrics"]
    assert m["revenue_ttm"]["state"] == "value" and m["revenue_ttm"]["inputs"], "values carry lineage"
    assert all(v["state"] in ("value", "undefined", "na", "forbidden") for v in m.values())
    assert all(v.get("value") != 0 or v["state"] == "value" for v in m.values()), "no zero-fill"


def test_search_finds_delisted_and_hides_not_yet_listed(con):
    r = PitReader(con)
    insert_many(con, "INSERT INTO security VALUES (?,?,?,?,?,?,?,?)",
                [("S:OLD", "OLD", "OLD029", "Old Mills Ltd", D(1995, 1, 1), D(2005, 1, 1), "isin", 1.0),
                 ("S:NEW", "NEW", "NEW029", "New Mills Ltd", D(2020, 1, 1), D(2026, 1, 1), "isin", 1.0)])
    insert_many(con, "INSERT INTO listing VALUES (?,?,?,?,?,?,?)",
                [("S:OLD", "NSE", "OLDMILL", D(1995, 1, 1), D(2005, 1, 1), "isin", 1.0),
                 ("S:NEW", "NSE", "NEWMILL", D(2020, 1, 1), D(2026, 1, 1), "isin", 1.0)])
    hits = r.search("mills", AsOf.end_of(D(2010, 1, 1)))
    assert [h["code"] for h in hits] == ["OLDMILL"]          # the 2020 listing did not exist in 2010
    assert hits[0]["active"] is False                        # delisted, still findable


def test_market_day_uses_only_that_session_and_skips_ex_dates(con):
    r = PitReader(con)
    d0, d1, d2 = D(2008, 10, 23), D(2008, 10, 24), D(2008, 10, 27)
    insert_many(con, "INSERT INTO listing VALUES (?,?,?,?,?,?,?)",
                [(f"S:{c}", "NSE", c, D(2000, 1, 1), D(2026, 1, 1), "isin", 1.0) for c in ("AAA", "BBB", "SPL")])
    add_prices(con, [("NSE", d1, "AAA", "EQ", None, 90.0, 100.0), ("NSE", d1, "BBB", "EQ", None, 110.0, 100.0),
                     ("NSE", d1, "SPL", "EQ", None, 50.0, 100.0),          # split day: prev close not comparable
                     ("NSE", d2, "AAA", "EQ", None, 999.0, 90.0)])         # a later session must not leak
    insert_many(con, "INSERT INTO adj_event VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                [("S:SPL", "NSE", "SPL", d1, 0.5, "announcement", 0.5, 0.5, "split", "split 2:1", "match", True,
                  dt.datetime(2008, 10, 1, tzinfo=dt.timezone.utc), "date")])
    m = r.market_day(AsOf.end_of(d1))
    assert m["session"] == d1
    assert m["securities"] == 2 and m["advances"] == 1 and m["declines"] == 1
    assert d0 < m["session"] < d2


def test_unmatched_index_member_is_unresolved_not_alive(con):
    """least() skips NULLs: a member with no listing must not come out as 'still trading' (regression)."""
    r = PitReader(con)
    ka = dt.datetime(2006, 6, 1, tzinfo=dt.timezone.utc)
    insert_many(con, "INSERT INTO index_membership VALUES (?,?,?,?,?,?,?,?,?)",
                [("NIFTY500", "U:old_name", "Old Name Ltd.", D(2005, 1, 1), D(9999, 12, 31), ka, "press_release", 0.5, ""),
                 ("NIFTY500", "S:LIVE", "LIVE", D(2005, 1, 1), D(9999, 12, 31), ka, "press_release", 1.0, ""),
                 ("NIFTY500", "S:DEAD", "DEAD", D(2005, 1, 1), D(2009, 1, 1), ka, "press_release", 1.0, "")])
    insert_many(con, "INSERT INTO listing VALUES (?,?,?,?,?,?,?)",
                [("S:LIVE", "NSE", "LIVE", D(2000, 1, 1), D(2026, 1, 1), "isin", 1.0),
                 ("S:DEAD", "NSE", "DEAD", D(2000, 1, 1), D(2010, 5, 5), "isin", 1.0)])
    ref = AsOf.end_of(D(2026, 1, 2))
    fate = {x["security_id"]: x["fate"] for x in r.members_fate("NIFTY500", D(2006, 6, 30), ref)}
    assert fate == {"U:old_name": "unresolved", "S:LIVE": "alive", "S:DEAD": "gone"}
    st = r.index_strata("NIFTY500", ref, [D(2006, 6, 30)])[0]
    assert (st["members"], st["still_trading"], st["gone"], st["unresolved"]) == (3, 1, 1, 1)
