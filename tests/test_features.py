"""Calendar (as announced), the PDF report, and the new endpoints' contracts."""

from __future__ import annotations

import datetime as dt

from fastapi.testclient import TestClient

from conftest import D, seed_company
from trikal_core.db import insert_many
from trikal_core.pit import PitReader
from trikal_core.timeutil import AsOf, at_ist, utcnow


def meetings(con):
    ka1, ka2 = at_ist(D(2026, 10, 1), dt.time(10)), at_ist(D(2026, 10, 12), dt.time(10))
    insert_many(con, "INSERT INTO board_meeting VALUES (?,?,?,?,?,?,?,?)", [
        ("AAA", "S:1", D(2026, 10, 20), "Financial Results", "to approve results", ka1, "sha", utcnow()),
        ("BBB", "S:2", D(2026, 10, 25), "Financial Results/Dividend", "results and dividend", ka2, "sha", utcnow()),
        ("AAA", "S:1", D(2026, 9, 1), "Financial Results", "old", at_ist(D(2026, 8, 1), dt.time(10)), "sha", utcnow())])


def test_calendar_shows_only_meetings_already_announced_and_inside_the_window(con):
    meetings(con)
    r = PitReader(con)
    early = r.board_meetings(AsOf.end_of(D(2026, 10, 5)), D(2026, 10, 5), D(2026, 11, 5))
    assert [m["symbol"] for m in early] == ["AAA"]                                   # BBB's meeting was announced on the 12th
    later = r.board_meetings(AsOf.end_of(D(2026, 10, 13)), D(2026, 10, 13), D(2026, 11, 13))
    assert [m["symbol"] for m in later] == ["AAA", "BBB"]
    assert [m["symbol"] for m in r.board_meetings(AsOf.end_of(D(2026, 10, 13)), D(2026, 10, 13), D(2026, 11, 13), ["BBB"])] == ["BBB"]


def test_calendar_endpoint_classifies_and_filters(con, monkeypatch):
    import trikal_api.app as appmod

    meetings(con)
    monkeypatch.setattr(appmod, "open_reader", lambda read_only=True: PitReader(con))
    monkeypatch.setattr(appmod.DB, "reader", None)
    c = TestClient(appmod.app)
    j = c.get("/api/calendar?as_of=2026-10-13&days=30").json()
    kinds = {e["code"]: e["kind"] for e in j["events"]}
    assert kinds == {"AAA": "results", "BBB": "results"} or kinds["BBB"] in ("results", "dividend")
    assert [e["code"] for e in c.get("/api/calendar?as_of=2026-10-13&scope=list&codes=BBB").json()["events"]] == ["BBB"]
    assert c.get("/api/calendar?as_of=2026-10-13&scope=list").json()["events"] == []        # an empty list shows nothing, not everything
    assert c.get("/api/calendar").status_code == 422


def test_pdf_report_builds_with_gaps_and_says_not_scored():
    from trikal_api import report as RP

    data = {"name": "Gap Ltd", "code": "GAP", "sector": None, "playbook": None, "as_of_label": "01 Jan 2025", "metrics": {"roe": {"state": "value", "value": 0.2, "unit": "ratio"}, "pe": {"state": "n/a"}},
            "price": None, "price_date": None, "financials": None, "ownership": None, "segments": None, "concalls": None, "kasauti": {"available": False, "reason": "not a Nifty 500 member"}}
    pdf = RP.build(data)
    assert pdf[:4] == b"%PDF" and len(pdf) > 1500


def test_report_endpoint_404_for_unknown_company(con, monkeypatch):
    import trikal_api.app as appmod

    seed_company(con, sid="S:INE000R01", code="RPTCO", name="Report Co", sector="Information Technology")
    monkeypatch.setattr(appmod, "open_reader", lambda read_only=True: PitReader(con))
    monkeypatch.setattr(appmod.DB, "reader", None)
    c = TestClient(appmod.app)
    assert c.get("/api/company/NOPE/report.pdf?as_of=2025-03-28").status_code == 404
    r = c.get("/api/company/RPTCO/report.pdf?as_of=2025-03-28")
    assert r.status_code == 200 and r.content[:4] == b"%PDF" and r.headers["content-type"] == "application/pdf"
    assert c.get("/api/company/RPTCO/report.pdf").status_code == 422
