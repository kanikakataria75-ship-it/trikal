"""Fixture database for point-in-time tests. All rows here are TEST FIXTURES, never real market data."""

from __future__ import annotations

import datetime as dt

import pytest

from trikal_core.db import connect, init_schema, insert_many
from trikal_core.timeutil import at_ist

D = dt.date


def eod(d: dt.date):
    return at_ist(d, dt.time(16, 0))


@pytest.fixture
def con(tmp_path):
    c = connect(tmp_path / "fixture.duckdb")
    init_schema(c)
    yield c
    c.close()


def add_prices(con, rows):
    """rows: (exchange, date, code, series, isin, close, prev_close[, known_at])"""
    out = []
    for r in rows:
        x, d, code, series, isin, close, prev = r[:7]
        known = r[7] if len(r) > 7 else eod(d)
        out.append((x, d, code, series, isin, None, "STK", close, close, close, close, close, prev,
                    1000.0, close * 1000, 10, known, "convention", known, "fixture"))
    insert_many(con, "INSERT INTO price_eod VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)", out)


def add_sessions(con, exchange, days, status="session"):
    insert_many(con, "INSERT INTO exchange_day VALUES (?,?,?)", [(exchange, d, status) for d in days])
