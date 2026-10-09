"""Golden tests for the NSE Indices press-release parser (snippets adapted from real releases)."""

import datetime as dt

from trikal_pipeline.index_history import index_code_for, norm_company, parse_events

D = dt.date


def test_index_aliases_and_lookalikes():
    for name in ["S&P CNX 500", "CNX 500 Index", "NIFTY 500", "Nifty 500", "(4) S&P CNX 500 Index"[4:]]:
        assert index_code_for(name) == "NIFTY500", name
    for name in ["Nifty500 Multicap 50:25:25", "Nifty 500 Equal Weight", "Nifty500 Momentum 50", "NIFTY Midcap 150"]:
        assert index_code_for(name) is None, name


def test_company_named_inclusion_is_a_row_not_an_action():
    text = """1) NIFTY 500
The following companies are being excluded:
Sr. No. Company Name Symbol
1 Bharat Financial Inclusion Ltd. BHARATFIN
2 Capital First Ltd. CAPF
The following companies are being included:
Sr. No. Company Name Symbol
1 Adani Green Energy Ltd. ADANIGREEN
2) NIFTY Midcap 150
The following company is being excluded:
Sr. No. Company Name Symbol
1 IIFL Holdings Ltd. IIFL"""
    ev = parse_events("Change in Indices w.e.f. December 28, 2018", text, D(2018, 12, 14))
    got = [(e["action"], e["symbol"]) for e in ev if e["index_code"] == "NIFTY500"]
    assert got == [("out", "BHARATFIN"), ("out", "CAPF"), ("in", "ADANIGREEN")]
    assert all(e["effective_date"] == D(2018, 12, 28) for e in ev)


def test_reason_mentioning_nifty500_does_not_switch_section():
    text = """4) Nifty Microcap 250
The following company is being excluded on account of inclusion in Nifty 500:
Sr. No. Company Name Symbol
1 Shoppers Stop Ltd. SHOPERSTOP
The following company is being included:
Sr. No. Company Name Symbol
1 Safari Industries (India) Ltd. SAFARI"""
    assert parse_events("Replacements in indices w.e.f. September 30, 2022", text, D(2022, 9, 16)) == []


def test_inline_index_in_sentence_old_layout():
    text = """(1) S&P CNX 500
The following companies are being excluded from S&P CNX 500 w.e.f. January 21, 2003
Sr. No. Company Name Industry Name
1 J. K. Corp Ltd. Diversified
(2) CNX Midcap 200
The following companies are being excluded from the CNX Midcap 200 w.e.f. February 27, 2003:
Sr. No. Company Name Industry Name
1 Aksh Optifibre Ltd Cables"""
    ev = parse_events("Changes in indices w.e.f. Jan. 21 and Feb. 27, 2003", text, D(2003, 1, 16))
    assert [(e["index_code"], e["action"], e["effective_date"]) for e in ev] == [("NIFTY500", "out", D(2003, 1, 21))]
    assert norm_company(ev[0]["company"]) == "j k"


def test_industry_suffix_is_dropped_for_matching():
    assert norm_company("Mahavir Spinning Mills Ltd. Textiles Cotton") == "mahavir spinning mills"


def test_1999_layout_with_are():
    text = """The companies being excluded from S&P CNX 500 are:
S. No. Company Name Industry Name
1 Precision Fasteners Limited Fasteners
The companies being included in the S&P CNX 500 are:
S. No. Company Name Industry Name
1 Moser Baer Ltd. Computers - Hardware
The companies being excluded from the CNX MidCap 200 are:
Sr. No. Company Name Industry Name
1. HDFC Bank Ltd. Banks"""
    ev = parse_events("Change in S&P CNX 500 index w.e.f. March 17, 1999", text, D(1999, 2, 25))
    assert [(e["action"], e["company"][:12]) for e in ev] == [("out", "Precision Fa"), ("in", "Moser Baer L")]
    assert {e["effective_date"] for e in ev} == {D(1999, 3, 17)}


def test_single_index_release_takes_index_from_title():
    text = """The Index Maintenance Sub-Committee has decided to make the following change.
The following company is being included:
Sr. No. Company Name Symbol
1 Marico LLiimmiitteedd MARICO"""
    ev = parse_events("Change in CNX 500 Index w.e.f May 12, 2014", text, D(2014, 4, 25))
    assert [(e["index_code"], e["action"], e["symbol"], e["company"]) for e in ev] == \
        [("NIFTY500", "in", "MARICO", "Marico Limited")]
    # multi-index titles must not set a default section
    assert parse_events("Change in CNX Alpha, CNX High Beta & CNX 500 Index w.e.f July 1, 2014", text, D(2014, 7, 1)) == []


def test_undouble_glyphs():
    from trikal_pipeline.index_history import _undouble

    assert _undouble("LLiimmiitteedd") == "Limited"
    assert _undouble("eexxcclluuddeedd:") == "excluded:"
    assert _undouble("JJJSSSWWW") == "JSW"
    assert _undouble("&&") == "&"
    for keep in ("TCS", "SBIN", "AAPL", "Ltd.", "3IINFOTECH", "M&M", "1:1"):
        assert _undouble(keep) == keep


def test_symbol_found_before_wrapped_date_text():
    text = """1) CNX 500 Index
The following company is being included:
Sr. No. Company Name Symbol
1 United Breweries (Holdings) Limited UBHOLDINGS April 9,"""
    ev = parse_events("Change in indices w.e.f. April 9, 2012", text, D(2012, 4, 4))
    assert [(e["symbol"], e["company"]) for e in ev] == [("UBHOLDINGS", "United Breweries (Holdings) Limited")]
