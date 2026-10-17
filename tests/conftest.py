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


# ---- synthetic company for analytics tests --------------------------------------------------------------------

import datetime as _dt  # noqa: E402

QUARTER_ENDS = [D(2024, 3, 31), D(2024, 6, 30), D(2024, 9, 30), D(2024, 12, 31)]


def known_after(pe: _dt.date, days: int = 45) -> _dt.datetime:
    return at_ist(pe + _dt.timedelta(days=days), _dt.time(18, 0))


def seed_company(con, sid="S:INE000X01", name="Test Industries Ltd", sector="Information Technology",
                 family="INDAS", code="TEST", price=50.0, price_date=D(2025, 3, 28)):
    """Listing, security, classification, one filing per quarter and a price. Facts are added with add_quarters."""
    insert_many(con, "INSERT INTO security VALUES (?,?,?,?,?,?,?,?)", [(sid, sid[2:], sid[2:] + "029", name, D(2000, 1, 1), D(2026, 1, 1), "isin", 1.0)])
    insert_many(con, "INSERT INTO listing VALUES (?,?,?,?,?,?,?)", [(sid, "NSE", code, D(2000, 1, 1), D(2026, 1, 1), "isin", 1.0)])
    insert_many(con, "INSERT INTO classification VALUES (?,?,?,?,?,?,?,?,?)",
                [(sid, "NSE_INDUSTRY", sector, D(1990, 1, 1), D(9999, 12, 31), at_ist(D(1990, 1, 1), _dt.time(0)), "official_snapshot", 1.0, "")])
    add_prices(con, [("NSE", price_date, code, "EQ", sid[2:] + "029", price, price)])
    for pe in QUARTER_ENDS:
        insert_many(con, "INSERT INTO filing VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                    [(f"f-{sid}-{pe}", "results_xbrl", code, sid, family, "consolidated", pe - _dt.timedelta(days=89), pe, None, "q", "Audited",
                      "Lakhs", known_after(pe), "exact", "", "sha", known_after(pe))])
    return sid


def add_fact_row(con, sid, concept, value, pe, months, basis="consolidated", unit="INR", known=None, fid=None):
    start = None if months is None else pe - _dt.timedelta(days=months * 30 - 1)
    insert_many(con, "INSERT INTO fact_financial VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                [(sid, basis, concept, "", start, pe, months is None, months, value, unit, known or known_after(pe), "exact",
                  fid or f"f-{sid}-{pe}", "sha", False)])


def add_quarters(con, sid, concept, values, basis="consolidated", unit="INR"):
    """One value per quarter in QUARTER_ENDS order."""
    for pe, v in zip(QUARTER_ENDS, values):
        add_fact_row(con, sid, concept, v, pe, 3, basis, unit)


def add_balance(con, sid, concept, value, pe=D(2024, 12, 31), basis="consolidated", unit="INR"):
    add_fact_row(con, sid, concept, value, pe, None, basis, unit)


def seed_standard(con, **kw):
    """TTM revenue 4000, expenses 3200 (finance 80, depreciation 120) -> EBITDA 1000; PAT 400; 100 shares at 50."""
    sid = seed_company(con, **kw)
    add_quarters(con, sid, "RevenueFromOperations", [1000] * 4)
    add_quarters(con, sid, "Expenses", [800] * 4)
    add_quarters(con, sid, "FinanceCosts", [20] * 4)
    add_quarters(con, sid, "DepreciationDepletionAndAmortisationExpense", [30] * 4)
    add_quarters(con, sid, "ProfitLossForPeriod", [100] * 4)
    add_quarters(con, sid, "TaxExpense", [30] * 4)
    add_quarters(con, sid, "ProfitBeforeTax", [130] * 4)
    add_balance(con, sid, "PaidUpValueOfEquityShareCapital", 1000.0)
    add_balance(con, sid, "FaceValueOfEquityShareCapital", 10.0, unit="INRPerShare")
    for k, v in (("Equity", 2000.0), ("BorrowingsCurrent", 200.0), ("BorrowingsNoncurrent", 300.0),
                 ("CashAndCashEquivalents", 100.0), ("BankBalanceOtherThanCashAndCashEquivalents", 50.0),
                 ("CurrentAssets", 900.0), ("CurrentLiabilities", 600.0), ("Assets", 5000.0)):
        add_balance(con, sid, k, v)
    return sid
