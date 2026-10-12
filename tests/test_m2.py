"""M2 tests: results XBRL/HTML parsing, shareholding, point-in-time financials, classification.
All inputs are small synthetic fixtures modelled on real filings (never real market data)."""

from __future__ import annotations

import datetime as dt

import pytest

from conftest import D
from trikal_core.db import insert_many
from trikal_core.pit import PitReader
from trikal_core.timeutil import IST, AsOf, at_ist
from trikal_pipeline import shp
from trikal_pipeline.html_results import parse_number, parse_results_html, slug
from trikal_pipeline.xbrl_results import family_from_url, months_between, parse_results_xbrl

SID = "S:INE000X01"


def xbrl(contexts: str, facts: str) -> bytes:
    return (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<xbrli:xbrl xmlns:xbrli="http://www.xbrl.org/2003/instance" xmlns:link="http://www.xbrl.org/2003/linkbase" '
        'xmlns:xbrldi="http://xbrl.org/2006/xbrldi" xmlns:in-bse-fin="http://www.bseindia.com/xbrl/fin/2020-03-31/in-bse-fin">'
        f"{contexts}{facts}</xbrli:xbrl>").encode()


def ctx(cid: str, start: str, end: str) -> str:
    return (f'<xbrli:context id="{cid}"><xbrli:entity><xbrli:identifier scheme="x">T</xbrli:identifier></xbrli:entity>'
            f"<xbrli:period><xbrli:startDate>{start}</xbrli:startDate><xbrli:endDate>{end}</xbrli:endDate></xbrli:period></xbrli:context>")


def inst(cid: str, day: str) -> str:
    return (f'<xbrli:context id="{cid}"><xbrli:entity><xbrli:identifier scheme="x">T</xbrli:identifier></xbrli:entity>'
            f"<xbrli:period><xbrli:instant>{day}</xbrli:instant></xbrli:period></xbrli:context>")


def fact(name: str, cref: str, val: str, unit: str = "INR") -> str:
    return f'<in-bse-fin:{name} contextRef="{cref}" unitRef="{unit}" decimals="-5">{val}</in-bse-fin:{name}>'


def text(name: str, val: str) -> str:
    return f'<in-bse-fin:{name} contextRef="OneD">{val}</in-bse-fin:{name}>'


# ---- results XBRL --------------------------------------------------------------------------------------

def test_four_column_period_comes_from_the_column_not_the_context_dates():
    """Regression (TCS FY24): the year-to-date context repeats the quarter's dates in the XML."""
    body = xbrl(
        ctx("OneD", "2024-01-01", "2024-03-31") + ctx("FourD", "2024-01-01", "2024-03-31") + inst("OneI", "2024-03-31"),
        text("DateOfStartOfFinancialYear", "2023-04-01") + text("DateOfEndOfReportingPeriod", "2024-03-31")
        + fact("RevenueFromOperations", "OneD", "612370000000.00")
        + fact("RevenueFromOperations", "FourD", "2408930000000.00")
        + fact("Assets", "OneI", "1464490000000.00"))
    p = parse_results_xbrl(body)
    by = {(f.concept, f.col): f for f in p.facts}
    q, y, a = by[("RevenueFromOperations", "One")], by[("RevenueFromOperations", "Four")], by[("Assets", "One")]
    assert (q.period_start, q.period_end, months_between(q.period_start, q.period_end)) == (D(2024, 1, 1), D(2024, 3, 31), 3)
    assert (y.period_start, y.period_end, months_between(y.period_start, y.period_end)) == (D(2023, 4, 1), D(2024, 3, 31), 12)
    assert y.value > 3 * q.value
    assert a.is_instant and a.period_start is None and a.period_end == D(2024, 3, 31)


def test_nine_month_ytd_and_unknown_columns_are_not_guessed():
    body = xbrl(ctx("OneD", "2024-10-01", "2024-12-31") + ctx("FourD", "2024-10-01", "2024-12-31") + ctx("TwoD", "2024-07-01", "2024-09-30"),
                text("DateOfStartOfFinancialYear", "2024-04-01") + text("DateOfEndOfReportingPeriod", "2024-12-31")
                + fact("ProfitBeforeTax", "FourD", "-1292300000.00") + fact("ProfitBeforeTax", "TwoD", "5.00"))
    p = parse_results_xbrl(body)
    assert [(f.col, months_between(f.period_start, f.period_end)) for f in p.facts] == [("Four", 9)]
    assert p.skipped_columns == {"Two": 1}


def test_governance_filing_family_and_dimensions():
    assert family_from_url("https://x/corporate/xbrl/INTEGRATED_FILING_INDAS_1_2_WEB.xml") == "INTEGRATED"
    assert family_from_url("https://x/corporate/xbrl/NBFC_INDAS_1_2.xml") == "NBFC_INDAS"
    assert family_from_url("https://x/corporate/xbrl/BANKING_1_2.xml") == "BANKING"
    body = xbrl('<xbrli:context id="OneReportableSegmentRevenue01D"><xbrli:entity><xbrli:identifier scheme="x">T</xbrli:identifier>'
                '<xbrli:segment><xbrldi:explicitMember dimension="in-bse-fin:SegmentAxis">in-bse-fin:RetailMember</xbrldi:explicitMember>'
                "</xbrli:segment></xbrli:entity><xbrli:period><xbrli:startDate>2024-01-01</xbrli:startDate><xbrli:endDate>2024-03-31</xbrli:endDate></xbrli:period></xbrli:context>",
                fact("SegmentRevenue", "OneReportableSegmentRevenue01D", "100"))
    (f,) = parse_results_xbrl(body).facts
    assert f.dims == "SegmentAxis=RetailMember" and f.col == "One"


# ---- old HTML pages --------------------------------------------------------------------------------------

HTML = """<html><body><table>
<tr><td>Symbol</td><td>TEST</td></tr><tr><td>Company</td><td>Test Ltd</td></tr><tr><td>Industry</td><td>-</td></tr>
<tr><td>Audited / Un-Audited</td><td>Unaudited</td></tr><tr><td>Cumulative / Non-Cumulative</td><td>Non-Cumulative</td></tr>
<tr><td>Consolidated / Non-Consolidated</td><td>Non-Consolidated</td></tr><tr><td>Period</td><td>Quarterly</td></tr>
<tr><td>Relating to</td><td>Third Quarter</td></tr><tr><td>Financial Year</td><td>01-Apr-2015 To 31-Mar-2016</td></tr>
<tr><td>Period Ended</td><td>31-Dec-2015</td></tr>
<tr><td>Description</td><td>Amount(Rs. in lakhs)</td></tr><tr><td>Part I</td></tr>
<tr><td>(a) Net sales/income from operations (Net of excise duty)</td></tr><tr><td>2345.00</td></tr>
<tr><td>Total income from operations (net) ( a + b)</td></tr><tr><td>2637.00</td></tr>
<tr><td>Other income</td></tr><tr><td>-</td></tr>
<tr><td>Tax expense</td></tr><tr><td>(12.50)</td></tr>
<tr><td>Earnings per share (before extraordinary items) (not annualised):</td></tr>
<tr><td>(a) Basic</td></tr><tr><td>0.09</td></tr>
<tr><td>Segment Reporting</td></tr><tr><td>Total</td></tr><tr><td>999.00</td></tr>
<tr><td>Search for another company</td></tr></table></body></html>""".encode()


def test_html_period_units_and_not_reported_dash():
    p = parse_results_html(HTML)
    assert (p.period_start, p.period_end) == (D(2015, 10, 1), D(2015, 12, 31))
    by = {f.concept: f for f in p.facts}
    assert by["html:total_income_from_operations"].value == 2637.0 * 1e5       # lakhs -> INR
    assert "html:other_income" not in by                                      # '-' is "not reported", not zero
    assert by["html:tax_expense"].value == -12.5 * 1e5                        # parentheses = negative
    assert by["html:earnings_per_share_basic"].value == 0.09                  # per-share data is not scaled
    assert not any("total" == f.concept.split(":")[1] for f in p.facts)       # segment-table noise ignored


def test_html_part_two_only_accepted_when_arithmetic_holds():
    good = HTML.replace(b"<tr><td>Search for", (
        b"<tr><td>- Number of shares</td></tr><tr><td>400.00</td></tr><tr><td>- Percentage of shareholding</td></tr><tr><td>40.00</td></tr>"
        b"<tr><td>- Number of shares</td></tr><tr><td>100</td></tr><tr><td>Promoters and Promoter Group Shareholding</td></tr>"
        b"<tr><td>a) Pledged / Encumbered</td></tr>"
        b"<tr><td>- Percentage of shares (as a % of the total shareholding of promoter and promoter group)</td></tr><tr><td>16.67</td></tr>"
        b"<tr><td>- Percentage of shares (as a % of the total share capital of the company)</td></tr><tr><td>10.00</td></tr>"
        b"<tr><td>- Number of shares</td></tr><tr><td>500</td></tr><tr><td>b) Non - encumbered</td></tr>"
        b"<tr><td>- Percentage of shares (as a % of the total shareholding of the promoter and promoter group)</td></tr><tr><td>83.33</td></tr>"
        b"<tr><td>- Percentage of shares (as a % of the total share capital of the company)</td></tr><tr><td>50.00</td></tr>"
        b"<tr><td>Search for"))
    names = {f.concept: f.value for f in parse_results_html(good).facts}
    assert names["html:public_shares"] == 400 and names["html:promoter_pledged_shares"] == 100
    assert names["html:promoter_nonencumbered_shares"] == 500
    bad = good.replace(b"<tr><td>83.33</td></tr>", b"<tr><td>12.00</td></tr>")  # contradicts the share counts
    assert not any(f.concept == "html:promoter_pledged_shares" for f in parse_results_html(bad).facts)


def test_number_and_slug_helpers():
    assert parse_number("1,234.50") == 1234.5 and parse_number("(5)") == -5 and parse_number("-") is None
    assert slug("(c) Changes in inventories of finished goods, work-in-progress") == "changes_in_inventories_of_finished_goods_work_in_progress"


# ---- shareholding ------------------------------------------------------------------------------------------

def shp_doc(scale: float) -> bytes:
    def cat(cid, member, holders, shares, pct):
        return (f'<xbrli:context id="{cid}"><xbrli:entity><xbrli:identifier scheme="x">T</xbrli:identifier><xbrli:segment>'
                f'<xbrldi:explicitMember dimension="in-bse-fin:CategoryOfShareholdersAxis">in-bse-fin:{member}Member</xbrldi:explicitMember>'
                f"</xbrli:segment></xbrli:entity><xbrli:period><xbrli:instant>2025-06-30</xbrli:instant></xbrli:period></xbrli:context>",
                f'<in-bse-fin:NumberOfShareholders contextRef="{cid}" unitRef="pure">{holders}</in-bse-fin:NumberOfShareholders>'
                f'<in-bse-fin:NumberOfFullyPaidUpEquityShares contextRef="{cid}" unitRef="shares">{shares}</in-bse-fin:NumberOfFullyPaidUpEquityShares>'
                f'<in-bse-fin:ShareholdingAsAPercentageOfTotalNumberOfShares contextRef="{cid}" unitRef="pure">{pct * scale}</in-bse-fin:ShareholdingAsAPercentageOfTotalNumberOfShares>')
    parts = [cat("ShareholdingPatternI", "ShareholdingPattern", 1000, 1000, 100.0),
             cat("PromI", "ShareholdingOfPromoterAndPromoterGroup", 5, 600, 60.0),
             cat("MfI", "MutualFundsOrUti", 40, 100, 10.0)]
    return xbrl("".join(p[0] for p in parts), "".join(p[1] for p in parts))


@pytest.mark.parametrize("scale", [1.0, 0.01])  # percent (71.77) and fraction (0.7177) filings
def test_shp_percentage_scale_is_normalised(scale):
    d = shp.parse_shp(shp_doc(scale))
    pct = {c: p for c, h, s, p in d["rows"]}
    assert pct["ShareholdingOfPromoterAndPromoterGroup"] == pytest.approx(60.0)
    assert pct["MutualFundsOrUTI"] == pytest.approx(10.0)          # 'Uti' spelling normalised across years
    assert d["problems"] == []


def test_shp_filed_percentage_wins_but_disagreement_is_reported():
    doc = shp_doc(1.0).replace(b">10.0<", b">12.5<")
    d = shp.parse_shp(doc)
    assert {c: p for c, h, s, p in d["rows"]}["MutualFundsOrUTI"] == pytest.approx(12.5)
    assert len(d["problems"]) == 1


def test_ownership_reader_is_point_in_time_and_revision_aware(con):
    t = lambda y, m, d: at_ist(D(y, m, d), dt.time(18, 0))  # noqa: E731
    rows = [
        (SID, D(2025, 3, 31), "ShareholdingOfPromoterAndPromoterGroup", None, None, 50.0, t(2025, 4, 20), "exact", "", "f1", ""),
        (SID, D(2025, 3, 31), "ShareholdingOfPromoterAndPromoterGroup", None, None, 52.0, t(2025, 7, 1), "exact", "Revised", "f2", ""),
        (SID, D(2025, 3, 31), "MutualFundsOrUTI", 10, 100, 5.0, t(2025, 4, 20), "exact", "", "f1", ""),
    ]
    insert_many(con, "INSERT INTO shareholding VALUES (?,?,?,?,?,?,?,?,?,?,?)", rows)
    r = PitReader(con)
    assert r.ownership(SID, AsOf.end_of(D(2025, 4, 10))) == []                        # not yet public
    before = r.ownership(SID, AsOf.end_of(D(2025, 5, 1)))[0]
    assert before["promoter"] == 50.0 and before["mutual_funds"] == 5.0 and before["fpi"] is None   # missing != 0
    after = r.ownership(SID, AsOf.end_of(D(2025, 8, 1)))[0]
    assert after["promoter"] == 52.0 and after["revised"] is True


# ---- point-in-time financials ----------------------------------------------------------------------------------

def add_fact(con, concept, value, ps, pe, months, ka, basis="consolidated", fid="f", restated=False, unit="INR"):
    insert_many(con, "INSERT INTO fact_financial VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                [(SID, basis, concept, "", ps, pe, ps is None, months, value, unit, ka, "exact", fid, "sha", restated)])


def test_financials_follow_the_as_of_date_and_restatements(con):
    k = lambda y, m, d: at_ist(D(y, m, d), dt.time(20, 0))  # noqa: E731
    add_fact(con, "RevenueFromOperations", 1000.0, D(2023, 10, 1), D(2023, 12, 31), 3, k(2024, 1, 20), fid="orig")
    add_fact(con, "RevenueFromOperations", 1100.0, D(2023, 10, 1), D(2023, 12, 31), 3, k(2024, 7, 20), fid="comparative", restated=True)
    r = PitReader(con)
    assert r.financials(SID, AsOf.end_of(D(2024, 1, 19)), ["revenue_from_operations"]) == []          # not public yet
    v = r.financials(SID, AsOf.end_of(D(2024, 3, 1)), ["revenue_from_operations"])
    assert [(x.value, x.filing_id, x.is_restated) for x in v] == [(1000.0, "orig", False)]
    v = r.financials(SID, AsOf.end_of(D(2024, 8, 1)), ["revenue_from_operations"])
    assert [(x.value, x.filing_id, x.is_restated) for x in v] == [(1100.0, "comparative", True)]


def test_line_item_fallback_uses_old_page_label_and_reports_lineage(con):
    k = at_ist(D(2012, 2, 1), dt.time(18, 0))
    add_fact(con, "html:total_income_from_operations", 2.637e8, D(2011, 10, 1), D(2011, 12, 31), 3, k, basis="standalone")
    (v,) = PitReader(con).financials(SID, AsOf.end_of(D(2012, 3, 1)), ["revenue_from_operations"])
    assert v.concept == "html:total_income_from_operations" and v.source_rank > 0 and v.basis == "standalone"
    add_fact(con, "RevenueFromOperations", 9e8, D(2011, 10, 1), D(2011, 12, 31), 3, k, basis="standalone", fid="x")
    (v,) = PitReader(con).financials(SID, AsOf.end_of(D(2012, 3, 1)), ["revenue_from_operations"])
    assert v.concept == "RevenueFromOperations" and v.source_rank == 0   # preferred concept wins


def test_basis_auto_prefers_consolidated_and_months_filter(con):
    k = at_ist(D(2024, 5, 1), dt.time(18, 0))
    for basis, val in (("standalone", 1.0), ("consolidated", 2.0)):
        add_fact(con, "ProfitLossForPeriod", val, D(2024, 1, 1), D(2024, 3, 31), 3, k, basis=basis, fid=basis)
    add_fact(con, "ProfitLossForPeriod", 9.0, D(2023, 4, 1), D(2024, 3, 31), 12, k, basis="consolidated", fid="fy")
    r = PitReader(con)
    auto = r.financials(SID, AsOf.now(), ["profit_after_tax"], months=3)
    assert [(x.basis, x.value) for x in auto] == [("consolidated", 2.0)]
    assert [x.value for x in r.financials(SID, AsOf.now(), ["profit_after_tax"], basis="standalone")] == [1.0]
    assert [x.value for x in r.financials(SID, AsOf.now(), ["profit_after_tax"], months=12)] == [9.0]


def test_classification_reports_method_and_confidence(con):
    t = at_ist(D(2026, 10, 9), dt.time(0, 0))
    insert_many(con, "INSERT INTO classification VALUES (?,?,?,?,?,?,?,?,?)", [
        (SID, "NSE_INDUSTRY", "Information Technology", D(1990, 1, 1), D(2026, 10, 9), at_ist(D(1990, 1, 1), dt.time(0, 0)), "assumed_static_backward", 0.5, ""),
        (SID, "NSE_INDUSTRY", "Information Technology", D(2026, 10, 9), D(9999, 12, 31), t, "official_snapshot", 1.0, ""),
    ])
    r = PitReader(con)
    assert r.classification(SID, AsOf.end_of(D(2015, 1, 1))) == ("Information Technology", "assumed_static_backward", 0.5)
    assert r.classification(SID, AsOf.end_of(D(2015, 1, 1)), min_confidence=1.0) is None      # official-only: unknown then
    assert r.classification(SID, AsOf.now())[1] == "official_snapshot"
