"""Rule-based reading of results decks: accepted only with a header-matched table row or a sentence naming the period."""

from __future__ import annotations

import datetime as dt

import pytest

from trikal_pipeline import deck_metrics as DM

D = dt.date

ICICI_LIKE = """Financial summary
Q1-FY26 Q2-FY26 Q3-FY26 Q4-FY26 Q1-FY27
Net interest margin 4.36 4.32 4.32 4.34 4.53
Provision coverage ratio 74.7 75.3 75.8 76.2 80.3
Total capital adequacy 16.84 16.31 17.18 16.55 16.33
CASA ratio 38.0 38.4 38.8 39.1 39.5
"""


def test_reporting_quarter_is_the_latest_quarter_ended_before_the_announcement():
    assert DM.reporting_quarter(D(2026, 7, 22)) == D(2026, 6, 30)
    assert DM.reporting_quarter(D(2025, 4, 19)) == D(2025, 3, 31)
    assert DM.reporting_quarter(D(2026, 1, 17)) == D(2025, 12, 31)
    assert DM.reporting_quarter(D(2026, 7, 2)) == D(2026, 3, 31)                           # two days after June 30: results cannot be out yet
    assert DM.reporting_quarter(D(2026, 12, 20)) == D(2026, 9, 30) and DM.reporting_quarter(D(2026, 11, 20)) == D(2026, 9, 30)


def test_period_tokens_in_the_common_deck_spellings():
    q = lambda s: [d for _, d, _ in DM.period_tokens(s)]    # noqa: E731
    assert q("Q1-FY27 Q4FY26 Q3 FY'26") == [D(2026, 6, 30), D(2026, 3, 31), D(2025, 12, 31)]
    assert q("Q1FY27") == [D(2026, 6, 30)] and q("Q4 FY26") == [D(2026, 3, 31)] and q("Q2-FY26") == [D(2025, 9, 30)]
    assert q("Jun-26 Mar-26") == [D(2026, 6, 30), D(2026, 3, 31)] and q("as at June 30, 2026") == [D(2026, 6, 30)]
    assert q("Sep'25  Dec 2025") == [D(2025, 9, 30), D(2025, 12, 31)]
    assert DM.period_tokens("FY26")[0][1:] == (D(2026, 3, 31), "fy")


def test_table_row_value_is_taken_from_the_reporting_quarters_column_not_the_first_number():
    hits = DM.scan_page(ICICI_LIKE, 17, D(2026, 6, 30))
    got = {h.concept: h.value for h in hits}
    assert got["nim"] == pytest.approx(0.0453) and got["pcr"] == pytest.approx(0.803) and got["car"] == pytest.approx(0.1633) and got["casa_ratio"] == pytest.approx(0.395)
    old = {h.concept: h.value for h in DM.scan_page(ICICI_LIKE, 17, D(2025, 6, 30))}
    assert old["nim"] == pytest.approx(0.0436)                                                              # the same row, another period: another column


def test_row_without_a_matching_header_is_not_guessed():
    text = "Net interest margin 4.36 4.32 4.32 4.34 4.53"                                  # five numbers, no header
    assert DM.scan_page(text, 3, D(2026, 6, 30)) == []
    text = "Q1-FY27 Q2-FY27\nNet interest margin 4.36 4.32 4.32"                           # header and row disagree on the count
    assert DM.scan_page(text, 3, D(2026, 6, 30)) == []


def test_sentences_count_only_when_they_name_the_period():
    assert DM.scan_page("CASA ratio stood at 39.5% as of June 30, 2026", 9, D(2026, 6, 30))[0].value == pytest.approx(0.395)
    assert DM.scan_page("CASA ratio stood at 39.5%", 9, D(2026, 6, 30)) == []                # which period? unknown: not accepted
    assert DM.scan_page("NIM remained healthy at 4.3% in FY2026", 7, D(2026, 6, 30)) == []    # a different period


def test_implausible_values_and_domestic_rows_are_rejected():
    assert DM.scan_page("Q1FY27 Q4FY26\nNet interest margin 45.0 4.3", 1, D(2026, 6, 30)) == []
    assert DM.scan_page("Q1FY27 Q4FY26\nNIM (Domestic) 4.5 4.3", 1, D(2026, 6, 30)) == []


def test_conflicting_candidates_drop_the_metric_and_unqualified_rows_win():
    page = "Q1FY27 Q4FY26\nNet interest margin 4.5 4.3\nQ1FY27 Q4FY26\nNet interest margin - retail 6.1 6.0\nQ1FY27 Q4FY26\nCASA ratio 39 38\nQ1FY27 Q4FY26\nCASA ratio 41 40"
    chosen, dropped = DM.choose(DM.scan_page(page, 2, D(2026, 6, 30)))
    assert chosen["nim"].value == pytest.approx(0.045)                                                      # the retail row is qualified, so it loses
    assert "casa_ratio" in dropped and "casa_ratio" not in chosen                            # two unqualified rows disagree: n/a, not a coin flip


# ---- from the table to the metric engine ----------------------------------------------------------------------

def test_a_deck_figure_reaches_the_metric_with_its_source_and_never_before_it_was_public(con):
    from conftest import add_quarters, seed_company
    from trikal_analytics import metrics as M
    from trikal_analytics.result import NotAvailable, Value
    from trikal_core.db import insert_many
    from trikal_core.pit import PitReader
    from trikal_core.timeutil import AsOf, at_ist

    sid = seed_company(con, sid="S:INE000B01", code="BANKX", name="Bank X Limited", sector="Financial Services", family="BANKING")
    add_quarters(con, sid, "InterestEarned", [100] * 4)
    ka = at_ist(D(2026, 7, 22), dt.time(15, 18))
    insert_many(con, "INSERT INTO fact_reported VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                [(sid, "nim", D(2026, 6, 30), 0.0453, "ratio", "deck_rule:table", 0.9, "https://x/deck.pdf", "sha", 17,
                  "Net interest margin 4.36 4.32 4.32 4.34 4.53", ka, "exact", ka)])
    eng = M.Engine(PitReader(con))
    before = eng.compute("nim", sid, AsOf.end_of(D(2026, 7, 21)))
    assert isinstance(before, NotAvailable)                                           # the deck was not public yet
    v = eng.compute("nim", sid, AsOf.end_of(D(2026, 8, 5)))
    assert isinstance(v, Value) and v.value == pytest.approx(0.0453) and "as_stated_in_results_deck" in v.warnings
    assert v.inputs[0].filing_id == "https://x/deck.pdf" and "page 17" in v.formula
    stale = eng.compute("nim", sid, AsOf.end_of(D(2027, 2, 1)))
    assert isinstance(stale, NotAvailable)                                            # older than about two quarters: not current


def test_prose_rows_year_sentences_and_long_histories_are_not_taken_for_a_quarter():
    hdr = "Q1FY27 Q4FY26 Q3FY26"
    assert DM.scan_page(hdr + "\nTotal CRAR stands at 15.69% and CET-1 at 12.54 across", 31, D(2026, 6, 30)) == []           # prose, not a row
    assert DM.scan_page("NIM for FY27 stands at 5.45% including fees", 28, D(2026, 3, 31)) == []                                 # a year, not the quarter
    long_hdr = " ".join(f"Q{(i % 4) + 1}FY{20 + (i + 3) // 4}" for i in range(12))
    assert DM.scan_page(long_hdr + "\nCRAR (%) " + " ".join(["12.9"] * 11) + " 33.3", 37, D(2026, 6, 30)) == []                # twelve columns: too easy to misalign


def test_outliers_against_the_companys_own_series_are_removed(con):
    from trikal_core.db import insert_many
    from trikal_core.timeutil import at_ist
    from trikal_pipeline.load_reported import drop_outliers

    ka = at_ist(D(2026, 1, 1), dt.time(12, 0))
    vals = [(D(2025, 3, 31), 0.150), (D(2025, 6, 30), 0.152), (D(2025, 9, 30), 0.155), (D(2025, 12, 31), 0.153), (D(2026, 3, 31), 0.333)]
    insert_many(con, "INSERT INTO fact_reported VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                [("S:A", "car", pe, v, "ratio", "deck_rule:table", 0.9, f"u{pe}", "sha", 1, "x", ka, "exact", ka) for pe, v in vals])
    assert drop_outliers(con) == 1
    assert sorted(r[0] for r in con.execute("SELECT value FROM fact_reported").fetchall())[-1] == 0.155
