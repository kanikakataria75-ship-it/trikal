"""Storage: embedded DuckDB stand-in for the canonical store (ADR-010).

Schema mirrors ARCHITECTURE §3.2 for the M1 subset. Lineage: every fact row carries `source_sha`,
the SHA-256 of the immutable raw object it was parsed from (see trikal_pipeline.raw).
"""

from __future__ import annotations

import os
from pathlib import Path

import duckdb

SCHEMA_VERSION = 1


def data_dir() -> Path:
    p = Path(os.environ.get("TRIKAL_DATA", Path(__file__).resolve().parents[2] / "data"))
    p.mkdir(parents=True, exist_ok=True)
    return p


def db_path() -> Path:
    return Path(os.environ.get("TRIKAL_DB", data_dir() / "trikal.duckdb"))


def connect(path: Path | str | None = None, read_only: bool = False) -> duckdb.DuckDBPyConnection:
    p = str(path or db_path())
    con = duckdb.connect(p, read_only=read_only)
    con.execute("SET TimeZone = 'Asia/Kolkata'")
    return con


DDL = r"""
CREATE TABLE IF NOT EXISTS meta (key VARCHAR PRIMARY KEY, value VARCHAR);

-- The RAW zone index (raw_object, fetch_log) lives in data/raw/index.sqlite; see trikal_pipeline.raw.

-- Daily end-of-day prices, UNADJUSTED, exactly as the exchange published them.
CREATE TABLE IF NOT EXISTS price_eod (
    exchange      VARCHAR NOT NULL,      -- NSE | BSE
    trade_date    DATE NOT NULL,
    code          VARCHAR NOT NULL,      -- NSE symbol | BSE scrip code
    series        VARCHAR NOT NULL,      -- NSE series | BSE group ('' if absent)
    isin          VARCHAR,               -- NULL in files that do not carry it
    name          VARCHAR,
    instr_type    VARCHAR,               -- UDiFF FinInstrmTp / BSE SC_TYPE, if given
    open DOUBLE, high DOUBLE, low DOUBLE, close DOUBLE, last DOUBLE, prev_close DOUBLE,
    volume        DOUBLE,
    turnover      DOUBLE,                -- rupees
    trades        BIGINT,
    known_at      TIMESTAMPTZ NOT NULL,
    known_precision VARCHAR NOT NULL,
    recorded_at   TIMESTAMPTZ NOT NULL,
    source_sha    VARCHAR NOT NULL
    -- uniqueness of (exchange, trade_date, code, series) is enforced by the loader + a DQ test;
    -- no PK index so that bulk rebuilds of ~30M rows stay fast.
);

-- Trading calendar derived from the fetch log; absent days are UNKNOWN (trikal_pipeline.calendar).
CREATE TABLE IF NOT EXISTS exchange_day (exchange VARCHAR, d DATE, status VARCHAR);

-- NSE master files (each load is a dated snapshot; history accumulates from first fetch).
CREATE TABLE IF NOT EXISTS nse_symbol_change (
    company_name VARCHAR, old_symbol VARCHAR, new_symbol VARCHAR, change_date DATE,
    known_at TIMESTAMPTZ, known_precision VARCHAR, recorded_at TIMESTAMPTZ, source_sha VARCHAR
);
CREATE TABLE IF NOT EXISTS nse_name_change (
    symbol VARCHAR, prev_name VARCHAR, new_name VARCHAR, change_date DATE,
    known_at TIMESTAMPTZ, known_precision VARCHAR, recorded_at TIMESTAMPTZ, source_sha VARCHAR
);
CREATE TABLE IF NOT EXISTS nse_delisted (
    symbol VARCHAR, company VARCHAR, delisted_date DATE, delisting_type VARCHAR,
    known_at TIMESTAMPTZ, known_precision VARCHAR, recorded_at TIMESTAMPTZ, source_sha VARCHAR
);
CREATE TABLE IF NOT EXISTS nse_equity_list (
    snapshot_date DATE, symbol VARCHAR, name VARCHAR, series VARCHAR, listing_date DATE,
    paid_up_value DOUBLE, market_lot INTEGER, isin VARCHAR, face_value DOUBLE,
    recorded_at TIMESTAMPTZ, source_sha VARCHAR
);

-- Corporate actions as announced (NSE corporate-actions feed).
CREATE TABLE IF NOT EXISTS corp_action (
    exchange VARCHAR, code VARCHAR, series VARCHAR, isin VARCHAR, company VARCHAR,
    subject VARCHAR, ex_date DATE, record_date DATE, face_value DOUBLE,
    kind VARCHAR,            -- split | consolidation | bonus | rights | dividend | demerger | ... | other
    ratio_num DOUBLE, ratio_den DOUBLE, amount DOUBLE,
    known_at TIMESTAMPTZ, known_precision VARCHAR, recorded_at TIMESTAMPTZ, source_sha VARCHAR
);

-- Securities (ADR-011): one row per equity line of an issuer.
CREATE TABLE IF NOT EXISTS security (
    security_id VARCHAR PRIMARY KEY,
    isin_stem VARCHAR, latest_isin VARCHAR, latest_name VARCHAR,
    first_trade DATE, last_trade DATE,
    id_method VARCHAR,       -- isin | symbol_chain | synthetic
    confidence DOUBLE
);
CREATE TABLE IF NOT EXISTS security_isin (security_id VARCHAR, isin VARCHAR, first_seen DATE, last_seen DATE);

-- Maps exchange rows to securities over time; the join key for every price query.
CREATE TABLE IF NOT EXISTS listing (
    security_id VARCHAR NOT NULL, exchange VARCHAR NOT NULL, code VARCHAR NOT NULL,
    valid_from DATE NOT NULL, valid_to DATE NOT NULL,       -- inclusive trading-date range
    method VARCHAR, confidence DOUBLE
);

-- Price adjustment events (ADR-009): factor multiplies prices strictly before ex_date.
CREATE TABLE IF NOT EXISTS adj_event (
    security_id VARCHAR, exchange VARCHAR, code VARCHAR, ex_date DATE,
    factor DOUBLE, method VARCHAR,          -- exchange_base_price | announcement
    implied_factor DOUBLE, parsed_factor DOUBLE, parsed_kind VARCHAR, subject VARCHAR,
    agreement VARCHAR,                      -- match | mismatch | implied_only | parsed_only
    applied BOOLEAN,                        -- false = recorded for review, not used in adjusted series
    known_at TIMESTAMPTZ, known_precision VARCHAR
);

-- Index constituents: official snapshots and announced changes.
CREATE TABLE IF NOT EXISTS index_snapshot (
    index_code VARCHAR, snapshot_date DATE, symbol VARCHAR, isin VARCHAR, name VARCHAR, industry VARCHAR,
    recorded_at TIMESTAMPTZ, source_sha VARCHAR
);
CREATE TABLE IF NOT EXISTS press_release (
    url VARCHAR PRIMARY KEY, published_date DATE, title VARCHAR, sha256 VARCHAR, parse_status VARCHAR
);
CREATE TABLE IF NOT EXISTS index_event (
    index_code VARCHAR, effective_date DATE, announced_date DATE, action VARCHAR,   -- in | out
    symbol VARCHAR, company VARCHAR, security_id VARCHAR,
    source_url VARCHAR, source_sha VARCHAR, section_title VARCHAR, parse_confidence DOUBLE
);
CREATE TABLE IF NOT EXISTS index_membership (
    index_code VARCHAR, security_id VARCHAR, symbol VARCHAR,
    valid_from DATE, valid_to DATE,          -- [valid_from, valid_to) ; valid_to = 9999-12-31 if open
    known_at TIMESTAMPTZ, method VARCHAR, confidence DOUBLE, note VARCHAR
);
CREATE TABLE IF NOT EXISTS index_count_check (
    index_code VARCHAR, effective_date DATE, expected INTEGER, reconstructed INTEGER, ok BOOLEAN, note VARCHAR
);

-- Data-quality issues: anything we could not resolve is recorded, never patched silently.
CREATE TABLE IF NOT EXISTS dq_issue (
    kind VARCHAR, exchange VARCHAR, code VARCHAR, d DATE, detail VARCHAR, severity VARCHAR,
    created_at TIMESTAMPTZ
);
"""


def init_schema(con: duckdb.DuckDBPyConnection) -> None:
    con.execute(DDL)
    # additive migrations for databases created by earlier builds
    con.execute("ALTER TABLE adj_event ADD COLUMN IF NOT EXISTS applied BOOLEAN")
    con.execute(
        "INSERT OR REPLACE INTO meta VALUES ('schema_version', ?)", [str(SCHEMA_VERSION)]
    )


def insert_many(con: duckdb.DuckDBPyConnection, sql: str, rows: list, chunk: int = 500) -> int:
    """Fast bulk insert: repeats the statement's single `VALUES (...)` group per row in chunks.

    DuckDB's executemany runs one statement per row (very slow for thousands of rows) and rejects
    empty batches; this does neither.
    """
    if not rows:
        return 0
    head, sep, tail = sql.partition("VALUES")
    if not sep:
        raise ValueError("insert_many needs an INSERT ... VALUES (...) statement")
    tail = tail.strip()
    depth, end = 0, None
    for i, ch in enumerate(tail):
        depth += ch == "("
        depth -= ch == ")"
        if depth == 0:
            end = i + 1
            break
    group, rest = tail[:end], tail[end:]
    for i in range(0, len(rows), chunk):
        part = rows[i:i + chunk]
        con.execute(f"{head}VALUES " + ", ".join([group] * len(part)) + rest,
                    [v for r in part for v in r])
    return len(rows)
