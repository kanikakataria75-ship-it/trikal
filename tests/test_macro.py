"""M5 macro layer: parsers, imputed release times, point-in-time reads. All rows are test fixtures."""

from __future__ import annotations

import datetime as dt
import json

from trikal_core.db import insert_many
from trikal_core.pit import PitReader
from trikal_core.timeutil import IST, AsOf

from conftest import D
from trikal_pipeline.sources.macro import imputed_known_at, parse_fred_csv, parse_fred_vintages, parse_mospi_cpi, period_of


def test_fred_csv_missing_days_are_absent_not_zero():
    rows = parse_fred_csv("observation_date,DEXINUS\n2008-10-23,49.10\n2008-10-24,.\n2008-10-27,49.95\n")
    assert rows == [(D(2008, 10, 23), 49.10), (D(2008, 10, 27), 49.95)]


def test_fred_vintages_keep_first_release_dates():
    body = json.dumps({"observations": [
        {"date": "2008-09-01", "value": "8.1", "realtime_start": "2008-10-31", "realtime_end": "2008-11-29"},
        {"date": "2008-09-01", "value": "8.4", "realtime_start": "2008-11-30", "realtime_end": "9999-12-31"}]})
    assert parse_fred_vintages(body) == [(D(2008, 9, 1), 8.1, D(2008, 10, 31)), (D(2008, 9, 1), 8.4, D(2008, 11, 30))]


def test_mospi_rows_are_filtered_to_all_india_combined_subgroup():
    body = json.dumps({"data": [
        {"year": 2024, "month": "December", "state": "All India", "sector": "Combined", "subgroup": "General-Overall", "index": "195.4"},
        {"year": 2024, "month": "December", "state": "All India", "sector": "Rural", "subgroup": "General-Overall", "index": "196.0"},
        {"year": 2024, "month": "November", "state": "All India", "sector": "Combined", "subgroup": "General-Overall", "index": "-"}]})
    assert parse_mospi_cpi(body, "General-Overall") == [(D(2024, 12, 1), 195.4, "")]


def test_imputed_release_is_after_the_period_and_follows_the_rule():
    ps, pe = period_of(D(2024, 12, 15), "M")
    assert (ps, pe) == (D(2024, 12, 1), D(2024, 12, 31))
    assert imputed_known_at(pe, {"release_day": 12}) == dt.datetime(2025, 1, 12, 17, 30, tzinfo=IST)
    assert imputed_known_at(D(2008, 10, 24), {"lag_days": 2}) == dt.datetime(2008, 10, 26, 18, 0, tzinfo=IST)


def test_macro_read_is_point_in_time_including_revisions(con):
    r = PitReader(con)
    k = lambda d: dt.datetime(d.year, d.month, d.day, 18, tzinfo=IST)  # noqa: E731
    insert_many(con, "INSERT INTO macro_obs VALUES (?,?,?,?,?,?,?,?,?)", [
        ("cpi", D(2008, 9, 1), D(2008, 9, 30), 8.1, k(D(2008, 10, 31)), "vintage", D(2008, 10, 31), "s", k(D(2026, 1, 1))),
        ("cpi", D(2008, 9, 1), D(2008, 9, 30), 8.4, k(D(2008, 11, 30)), "vintage", D(2008, 11, 30), "s", k(D(2026, 1, 1))),
        ("cpi", D(2008, 10, 1), D(2008, 10, 31), 9.0, k(D(2008, 11, 30)), "vintage", D(2008, 11, 30), "s", k(D(2026, 1, 1)))])
    assert [o["value"] for o in r.macro("cpi", AsOf.end_of(D(2008, 10, 15)))] == []          # nothing published yet
    assert [o["value"] for o in r.macro("cpi", AsOf.end_of(D(2008, 11, 5)))] == [8.1]        # first release only
    assert [o["value"] for o in r.macro("cpi", AsOf.end_of(D(2008, 12, 5)))] == [8.4, 9.0]   # revision + next month
