"""Segment disclosures: members are named from the text fact in their context; the PIT reader serves them as known."""

from __future__ import annotations

import datetime as dt

import pytest
from fastapi.testclient import TestClient

from conftest import D
from test_m2 import ctx, fact, inst, text, xbrl
from trikal_core.db import insert_many
from trikal_core.pit import PitReader
from trikal_core.timeutil import AsOf, at_ist
from trikal_pipeline.xbrl_results import parse_results_xbrl

SID = "S:INESEG00001"


def seg_ctx(cid: str, start: str, end: str, axis: str, member: str) -> str:
    return (f'<xbrli:context id="{cid}"><xbrli:entity><xbrli:identifier scheme="x">T</xbrli:identifier></xbrli:entity>'
            f"<xbrli:period><xbrli:startDate>{start}</xbrli:startDate><xbrli:endDate>{end}</xbrli:endDate></xbrli:period>"
            f'<xbrli:scenario><xbrldi:explicitMember dimension="in-bse-fin:{axis}">in-bse-fin:{member}</xbrldi:explicitMember></xbrli:scenario>'
            "</xbrli:context>")


def seg_inst(cid: str, day: str, axis: str, member: str) -> str:
    return (f'<xbrli:context id="{cid}"><xbrli:entity><xbrli:identifier scheme="x">T</xbrli:identifier></xbrli:entity>'
            f"<xbrli:period><xbrli:instant>{day}</xbrli:instant></xbrli:period>"
            f'<xbrli:scenario><xbrldi:explicitMember dimension="in-bse-fin:{axis}">in-bse-fin:{member}</xbrldi:explicitMember></xbrli:scenario>'
            "</xbrli:context>")


def desc(cid: str, name: str) -> str:
    return f'<in-bse-fin:DescriptionOfReportableSegment contextRef="{cid}">{name}</in-bse-fin:DescriptionOfReportableSegment>'


def test_segment_members_take_the_companys_own_label_for_durations_and_balances():
    body = xbrl(
        ctx("OneD", "2024-01-01", "2024-03-31")
        + seg_ctx("OneReportableSegmentRevenue02D", "2024-01-01", "2024-03-31", "ReportableSegmentsAxis", "OneReportableSegmentRevenue02Member")
        + seg_ctx("OneReportableSegmentAssets02D", "2024-01-01", "2024-03-31", "ReportableSegmentAssetsAxis", "OneReportableSegmentAssets02Member")
        + seg_inst("OneReportableSegmentAssets02I", "2024-03-31", "ReportableSegmentAssetsAxis", "OneReportableSegmentAssets02Member"),
        text("DateOfStartOfFinancialYear", "2024-01-01") + text("DateOfEndOfReportingPeriod", "2024-03-31")
        + desc("OneReportableSegmentRevenue02D", "Paper  and Board") + desc("OneReportableSegmentAssets02D", "Paper and Board")
        + fact("SegmentRevenue", "OneReportableSegmentRevenue02D", "1000")
        + fact("SegmentAssets", "OneReportableSegmentAssets02I", "5000")
        + fact("RevenueFromOperations", "OneD", "1100"))
    p = parse_results_xbrl(body)
    got = {(f.concept, f.dims) for f in p.facts}
    assert ("SegmentRevenue", "Segment=Paper and Board") in got            # whitespace tidied
    assert ("SegmentAssets", "Segment=Paper and Board") in got              # instant context finds the label on the duration one
    assert ("RevenueFromOperations", "") in got                             # consolidated lines untouched


def test_a_member_without_a_label_keeps_its_original_key():
    body = xbrl(ctx("OneD", "2024-01-01", "2024-03-31")
                + seg_ctx("OneReportableSegmentRevenue01D", "2024-01-01", "2024-03-31", "ReportableSegmentsAxis", "OneReportableSegmentRevenue01Member"),
                text("DateOfStartOfFinancialYear", "2024-01-01") + text("DateOfEndOfReportingPeriod", "2024-03-31")
                + fact("SegmentRevenue", "OneReportableSegmentRevenue01D", "10"))
    assert [f.dims for f in parse_results_xbrl(body).facts] == ["ReportableSegmentsAxis=OneReportableSegmentRevenue01Member"]


def seg_fact(con, concept, label, value, pe, months, known, basis="consolidated", fid="f"):
    start = pe - dt.timedelta(days=months * 30 - 1)
    insert_many(con, "INSERT INTO fact_financial VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                [(SID, basis, concept, f"Segment={label}", start, pe, False, months, value, "INR", known, "exact", fid, "sha", False)])


@pytest.fixture
def seg(con):
    k = lambda y, m, d: at_ist(D(y, m, d), dt.time(20, 0))  # noqa: E731
    pe = D(2024, 3, 31)
    seg_fact(con, "SegmentRevenue", "Cement", 600.0, pe, 12, k(2024, 5, 10))
    seg_fact(con, "SegmentRevenue", "Power", 400.0, pe, 12, k(2024, 5, 10))
    seg_fact(con, "SegmentProfitLossBeforeTaxAndFinanceCosts", "Cement", 120.0, pe, 12, k(2024, 5, 10))
    seg_fact(con, "SegmentRevenue", "Cement", 650.0, pe, 12, k(2025, 5, 12), fid="restated")        # later restatement
    seg_fact(con, "SegmentRevenue", "Cement", 300.0, pe, 12, k(2024, 5, 10), basis="standalone")   # standalone loses to consolidated
    seg_fact(con, "SegmentRevenue", "Cement", 150.0, pe, 3, k(2024, 5, 10))                         # a quarter, not an annual figure
    return PitReader(con)


def test_segments_are_point_in_time_with_shares_and_margins(seg):
    before = seg.segments(SID, AsOf.end_of(D(2024, 5, 9)))
    assert before["periods"] == []                                            # not public yet
    a = seg.segments(SID, AsOf.end_of(D(2024, 12, 31)))["periods"][0]
    assert a["basis"] == "consolidated" and a["total_revenue"] == 1000.0
    cement = next(s for s in a["segments"] if s["label"] == "Cement")
    assert cement["revenue"] == 600.0 and cement["share"] == pytest.approx(0.6) and cement["margin"] == pytest.approx(0.2)
    power = next(s for s in a["segments"] if s["label"] == "Power")
    assert power["margin"] is None and "result" not in power                    # missing is not zero
    later = seg.segments(SID, AsOf.end_of(D(2025, 6, 1)))["periods"][0]
    assert next(s for s in later["segments"] if s["label"] == "Cement")["revenue"] == 650.0
    q = seg.segments(SID, AsOf.end_of(D(2025, 6, 1)), months=3)["periods"][0]
    assert [s["label"] for s in q["segments"]] == ["Cement"] and q["segments"][0]["revenue"] == 150.0


def test_segments_endpoint(con, seg, monkeypatch):
    import trikal_api.app as appmod

    insert_many(con, "INSERT INTO security VALUES (?,?,?,?,?,?,?,?)", [(SID, "INESEG00001", "INESEG000019", "Seg Co", D(2000, 1, 1), D(2030, 1, 1), "isin", 1.0)])
    insert_many(con, "INSERT INTO listing VALUES (?,?,?,?,?,?,?)", [(SID, "NSE", "SEGCO", D(2000, 1, 1), D(2030, 1, 1), "isin", 1.0)])
    monkeypatch.setattr(appmod, "open_reader", lambda read_only=True: PitReader(con))
    monkeypatch.setattr(appmod.DB, "reader", None)
    c = TestClient(appmod.app)
    j = c.get("/api/company/SEGCO/segments?as_of=2024-12-31&period=FY").json()
    assert j["periods"][0]["segments"][0]["label"] == "Cement" and j["period"] == "FY"
    assert c.get("/api/company/SEGCO/segments?as_of=2024-12-31&period=X").status_code == 422
    assert c.get("/api/company/SEGCO/segments").status_code == 422
