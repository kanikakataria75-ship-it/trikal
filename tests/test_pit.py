"""Point-in-time / look-ahead tests (ARCHITECTURE §2.2). Each one fails if the future leaks into the past."""

from __future__ import annotations

import datetime as dt

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from conftest import D, add_prices, add_sessions, eod
from trikal_core.db import insert_many
from trikal_core.pit import PitReader
from trikal_core.timeutil import IST, AsOf, at_ist, end_of_day_ist
from trikal_pipeline import adjustments, security_master

ISIN = "INE000X01015"  # fixture ISIN (not a real security)
SID = "S:INE000X01"


def test_asof_requires_timezone():
    with pytest.raises(ValueError):
        AsOf(dt.datetime(2020, 1, 1))


def _simple_listing(con, code="FIX", start=D(2020, 1, 1), end=D(2020, 12, 31)):
    insert_many(con, "INSERT INTO listing VALUES (?,?,?,?,?,?,?)", [(SID, "NSE", code, start, end, "isin", 1.0)])


def test_canary_price_known_later_is_invisible(con):
    _simple_listing(con)
    d = D(2020, 3, 2)
    add_prices(con, [("NSE", d, "FIX", "EQ", ISIN, 100.0, 99.0)])
    # same trade date, but this sentinel row only becomes known one second after the as-of instant
    as_of = AsOf(eod(D(2020, 3, 3)))
    add_prices(con, [("NSE", D(2020, 3, 3), "FIX", "EQ", ISIN, 666.0, 100.0, as_of.ts + dt.timedelta(seconds=1))])
    bars = PitReader(con).prices(SID, as_of)
    assert [b.close for b in bars] == [100.0]


def test_eod_price_not_visible_before_close(con):
    _simple_listing(con)
    d = D(2020, 3, 2)
    add_prices(con, [("NSE", d, "FIX", "EQ", ISIN, 100.0, 99.0)])
    assert PitReader(con).prices(SID, AsOf(at_ist(d, dt.time(11, 0)))) == []
    assert len(PitReader(con).prices(SID, AsOf(at_ist(d, dt.time(16, 0))))) == 1


def test_split_after_asof_does_not_adjust_history(con):
    _simple_listing(con)
    add_prices(con, [("NSE", D(2020, 3, 2), "FIX", "EQ", ISIN, 1000.0, 990.0),
                     ("NSE", D(2020, 3, 3), "FIX", "EQ", ISIN, 101.0, 1000.0)])
    insert_many(con, """INSERT INTO adj_event (security_id, exchange, code, ex_date, factor, method, agreement, applied,
                        known_at, known_precision) VALUES (?,?,?,?,?,?,?,?,?,?)""",
                [(SID, "NSE", "FIX", D(2020, 3, 3), 0.1, "announcement", "parsed_confirmed", True,
                  at_ist(D(2020, 3, 3), dt.time(9, 0)), "convention")])
    r = PitReader(con)
    before = r.prices(SID, AsOf.end_of(D(2020, 3, 2)))
    assert before[0].close == 1000.0 and before[0].factor == 1.0  # a 2-Mar terminal never saw the split
    after = r.prices(SID, AsOf.end_of(D(2020, 3, 3)))
    assert after[0].close == pytest.approx(100.0) and after[1].close == 101.0
    assert r.prices(SID, AsOf.end_of(D(2020, 3, 3)), adjusted=False)[0].close == 1000.0


def test_index_membership_is_bitemporal(con):
    # included effective 1-Apr (announced 15-Mar); exclusion announced 20-Aug, effective 1-Sep
    insert_many(con, "INSERT INTO index_membership VALUES (?,?,?,?,?,?,?,?,?)", [
        ("NIFTY500", SID, "FIX", D(2020, 4, 1), D(9999, 12, 31), end_of_day_ist(D(2020, 3, 15)), "reconstructed", 1.0, ""),
        ("NIFTY500", SID, "FIX", D(2020, 4, 1), D(2020, 9, 1), end_of_day_ist(D(2020, 8, 20)), "reconstructed", 1.0, ""),
    ])
    r = PitReader(con)
    members = lambda d: {m[0] for m in r.index_members("NIFTY500", AsOf.end_of(d))}  # noqa: E731
    assert SID not in members(D(2020, 3, 31))        # announced, not yet effective
    assert SID in members(D(2020, 4, 1))
    assert SID in members(D(2020, 8, 25))            # exit announced but not yet effective
    assert SID not in members(D(2020, 9, 1))
    # as of 10-Aug nobody knew the exit; a query for a past date must not use later knowledge
    known_then = r.con.execute(
        """SELECT valid_to FROM index_membership WHERE known_at <= ? ORDER BY known_at DESC LIMIT 1""",
        [end_of_day_ist(D(2020, 8, 10))]).fetchone()[0]
    assert known_then == D(9999, 12, 31)


def test_symbol_resolves_to_the_company_that_used_it_then(con):
    insert_many(con, "INSERT INTO listing VALUES (?,?,?,?,?,?,?)", [
        ("S:INE000A01", "NSE", "OLDSYM", D(2010, 1, 1), D(2015, 6, 30), "isin", 1.0),
        ("S:INE000B01", "NSE", "OLDSYM", D(2018, 1, 1), D(2020, 12, 31), "isin", 1.0),  # symbol reused
    ])
    r = PitReader(con)
    assert r.resolve("OLDSYM", AsOf.end_of(D(2012, 1, 1))) == "S:INE000A01"
    assert r.resolve("OLDSYM", AsOf.end_of(D(2019, 1, 1))) == "S:INE000B01"
    assert r.resolve("OLDSYM", AsOf.end_of(D(2009, 1, 1))) is None  # did not exist yet


@settings(max_examples=40, deadline=None)
@given(st.lists(st.tuples(st.integers(0, 60), st.integers(-3, 3)), min_size=1, max_size=30),
       st.integers(0, 70))
def test_property_no_bar_known_after_asof(tmp_path_factory, rows, asof_day):
    from trikal_core.db import connect, init_schema

    c = connect(tmp_path_factory.mktemp("p") / "p.duckdb")
    init_schema(c)
    _simple_listing(c, start=D(2020, 1, 1), end=D(2020, 12, 31))
    base = D(2020, 1, 1)
    seen = set()
    data = []
    for day, lag in rows:
        d = base + dt.timedelta(days=day)
        if d in seen:
            continue
        seen.add(d)
        data.append(("NSE", d, "FIX", "EQ", ISIN, 100.0 + day, 100.0, eod(d) + dt.timedelta(days=lag)))
    add_prices(c, data)
    as_of = AsOf.end_of(base + dt.timedelta(days=asof_day))
    got = {b.trade_date for b in PitReader(c).prices(SID, as_of)}
    expected = {r[1] for r in data if r[7] <= as_of.ts}
    assert got == expected
    c.close()


# --- regression: adjustment builder (bugs found 2026-10-09/10) -------------------------------------

def _build_master(con):
    security_master.build(con)
    return adjustments.build(con)


def test_bonus_with_unadjusted_prevclose_is_confirmed_by_price(con):
    # legacy NSE files do not adjust PREVCLOSE: the ex-date row shows the old close (real case: TCS 2018)
    days = [D(2018, 5, 29), D(2018, 5, 30), D(2018, 5, 31)]
    add_sessions(con, "NSE", days)
    add_prices(con, [("NSE", days[0], "FIX", "EQ", ISIN, 3523.5, 3502.0),
                     ("NSE", days[1], "FIX", "EQ", ISIN, 3514.1, 3523.5),
                     ("NSE", days[2], "FIX", "EQ", ISIN, 1741.05, 3514.1)])
    con.execute("""INSERT INTO corp_action VALUES ('NSE','FIX','EQ',?, 'Fixture Ltd','Bonus 1:1', ?, NULL, 1,
                   'bonus', 1, 1, NULL, ?, 'imputed', now(), 'fixture')""", [ISIN, days[2], at_ist(days[2], dt.time(9))])
    _build_master(con)
    ev = con.execute("SELECT factor, agreement, applied FROM adj_event").fetchall()
    assert ev == [(0.5, "parsed_confirmed", True)]


def test_missing_row_in_source_file_is_not_an_adjustment(con):
    # BSE 15-Jul-2022 file omits the security; PREVCLOSE on the 18th refers to the 15th's close.
    days = [D(2022, 7, 14), D(2022, 7, 15), D(2022, 7, 18)]
    add_sessions(con, "BSE", days)
    add_sessions(con, "BSE", [D(2022, 7, 16), D(2022, 7, 17)], "no_session")
    add_prices(con, [("BSE", days[0], "500000", "A", ISIN, 2998.70, 3038.55),
                     ("BSE", days[2], "500000", "A", ISIN, 3060.35, 2993.55)])
    _build_master(con)
    ev = con.execute("SELECT agreement, applied FROM adj_event").fetchall()
    assert ev == [("unverifiable", False)]


def test_unknown_days_block_implied_factor(con):
    # 2-Mar was never fetched (unknown): a gap of unknown size must not produce an applied factor
    add_sessions(con, "NSE", [D(2020, 3, 1), D(2020, 3, 3)])
    add_prices(con, [("NSE", D(2020, 3, 1), "FIX", "EQ", ISIN, 100.0, 100.0),
                     ("NSE", D(2020, 3, 3), "FIX", "EQ", ISIN, 51.0, 50.0)])
    _build_master(con)
    assert con.execute("SELECT count(*) FROM adj_event WHERE applied").fetchone()[0] == 0


def test_only_core_and_pipeline_touch_the_database_directly():
    """ADR-004/010: analytics, kasauti and api read data only through trikal_core.pit.PitReader."""
    import pathlib

    root = pathlib.Path(__file__).resolve().parents[1]
    offenders = []
    for pkg in ("analytics", "kasauti", "api"):
        for f in (root / pkg).rglob("*.py") if (root / pkg).exists() else []:
            text = f.read_text(encoding="utf-8")
            if "trikal_core.db" in text or "import duckdb" in text:
                offenders.append(str(f.relative_to(root)))
    assert offenders == []


def test_small_exchange_only_discrepancy_is_not_applied(con):
    # PREVCLOSE differs by 3% with no announcement: noise in old files, not a corporate action
    days = [D(2001, 10, 16), D(2001, 10, 17)]
    add_sessions(con, "NSE", days)
    add_prices(con, [("NSE", days[0], "FIX", "EQ", None, 100.0, 100.0),
                     ("NSE", days[1], "FIX", "EQ", None, 98.0, 97.0)])
    _build_master(con)
    assert con.execute("SELECT agreement, applied FROM adj_event").fetchall() == [("implied_only", False)]


def test_large_exchange_only_change_goes_to_review_not_applied(con):
    # could be a BSE-only company's 1:5 split - or a base-price reset; without an announcement we do not guess
    days = [D(2019, 3, 1), D(2019, 3, 4)]
    add_sessions(con, "BSE", days)
    add_sessions(con, "BSE", [D(2019, 3, 2), D(2019, 3, 3)], "no_session")
    add_prices(con, [("BSE", days[0], "500001", "B", ISIN, 500.0, 495.0),
                     ("BSE", days[1], "500001", "B", ISIN, 101.0, 100.0)])
    _build_master(con)
    ev = con.execute("SELECT round(factor, 3), agreement, applied FROM adj_event").fetchall()
    assert ev == [(0.2, "implied_confirmed", False)]
    assert con.execute("SELECT count(*) FROM dq_issue WHERE kind = 'adj_implied_confirmed'").fetchone()[0] == 1


def test_pre_coverage_member_excluded_before_first_effective_date_is_not_a_member_today(con, tmp_path):
    # regression: open version stamped with the first *effective* date outranked an earlier-published exit
    from trikal_core.timeutil import end_of_day_ist as eod_ist

    insert_many(con, "INSERT INTO index_membership VALUES (?,?,?,?,?,?,?,?,?)", [
        ("NIFTY500", "X:OLD", "OLD", D(1990, 1, 1), D(9999, 12, 31), eod_ist(D(1998, 9, 2)), "pre_coverage", 1.0, ""),
        ("NIFTY500", "X:OLD", "OLD", D(1990, 1, 1), D(1999, 2, 3), eod_ist(D(1998, 12, 28)), "pre_coverage", 1.0, ""),
    ])
    r = PitReader(con)
    assert "X:OLD" in {m[0] for m in r.index_members("NIFTY500", AsOf.end_of(D(1999, 1, 15)))}
    assert "X:OLD" not in {m[0] for m in r.index_members("NIFTY500", AsOf.end_of(D(2026, 1, 1)))}


def test_last_price_prefers_the_equity_series(con):
    """Regression: an institutional-lot (IL) print on the same day must not replace the EQ close."""
    from trikal_core.pit import PitReader
    from trikal_core.timeutil import AsOf

    insert_many(con, "INSERT INTO listing VALUES (?,?,?,?,?,?,?)", [("S:SBI", "NSE", "SBIX", D(2000, 1, 1), D(2026, 1, 1), "isin", 1.0)])
    add_prices(con, [("NSE", D(2008, 10, 24), "SBIX", "IL", None, 1245.0, 1336.0),
                     ("NSE", D(2008, 10, 24), "SBIX", "EQ", None, 1164.75, 1326.25),
                     ("NSE", D(2008, 10, 24), "SBIX", "N1", None, 99.0, 99.0)])
    assert PitReader(con).last_price("S:SBI", AsOf.end_of(D(2008, 10, 24))) == (D(2008, 10, 24), 1164.75)


def _ca(con, day, subject, kind, fv):
    con.execute("""INSERT INTO corp_action VALUES ('NSE','FIX','EQ',?, 'Fixture Ltd', ?, ?, NULL, ?,
                   ?, NULL, NULL, NULL, ?, 'imputed', now(), 'fixture')""", [ISIN, subject, day, fv, kind, at_ist(day, dt.time(9))])


def test_split_on_a_crash_day_is_still_applied(con):
    """Regression (JINDALSTEL 21-Jan-2008): 5:1 split and a -27% session. Observed 0.146 vs factor 0.2."""
    days = [D(2008, 1, 17), D(2008, 1, 18), D(2008, 1, 21)]
    add_sessions(con, "NSE", days)
    add_sessions(con, "NSE", [D(2008, 1, 19), D(2008, 1, 20)], "no_session")
    add_prices(con, [("NSE", days[0], "FIX", "EQ", ISIN, 15860.45, 15504.75),
                     ("NSE", days[1], "FIX", "EQ", ISIN, 14363.85, 15860.45),
                     ("NSE", days[2], "FIX", "EQ", ISIN, 2104.25, 14363.85)])
    _ca(con, days[2], "Fv Split Rs.5/- To Re.1/-", "split", 1.0)
    _build_master(con)
    assert con.execute("SELECT factor, agreement, applied FROM adj_event").fetchall() == [(0.2, "parsed_confirmed_wide", True)]


def test_bonus_debentures_never_get_the_wide_band(con):
    """'Bonus debentures' are debt, not shares: a flat price on the ex-date must keep them unapplied."""
    days = [D(2010, 3, 4), D(2010, 3, 5), D(2010, 3, 8)]
    add_sessions(con, "NSE", days)
    add_sessions(con, "NSE", [D(2010, 3, 6), D(2010, 3, 7)], "no_session")
    add_prices(con, [("NSE", days[0], "FIX", "EQ", ISIN, 2000.0, 1990.0),
                     ("NSE", days[1], "FIX", "EQ", ISIN, 2010.0, 2000.0),
                     ("NSE", days[2], "FIX", "EQ", ISIN, 1865.0, 2010.0)])
    _ca(con, days[2], "Sch Of Agmt- Bonus Deb1:1", "bonus", 10.0)
    _build_master(con)
    assert con.execute("SELECT agreement, applied FROM adj_event").fetchall() == [("parsed_price_disagrees", False)]


def test_bonus_day_with_no_price_drop_is_not_applied(con):
    """Regression (a 2021 case): 'Bonus 1:2' but the price fell only 7% on the ex-date — likely the wrong date.
    The crash-day widening is downside only, so this stays unapplied for review."""
    days = [D(2021, 8, 3), D(2021, 8, 4), D(2021, 8, 5)]
    add_sessions(con, "NSE", days)
    add_prices(con, [("NSE", days[0], "FIX", "EQ", ISIN, 300.0, 298.0),
                     ("NSE", days[1], "FIX", "EQ", ISIN, 301.0, 300.0),
                     ("NSE", days[2], "FIX", "EQ", ISIN, 281.3, 301.0)])
    _ca(con, days[2], " Bonus 1:2", "bonus", 10.0)
    _build_master(con)
    assert con.execute("SELECT agreement, applied FROM adj_event").fetchall() == [("parsed_price_disagrees", False)]
