"""Load staged bhavcopy CSVs into canonical `price_eod` (unadjusted), one bulk SQL per format.

Rebuild semantics: the exchange's rows are replaced wholesale from staging, which is itself a pure
function of the raw zone, so the load is idempotent and reproducible.
"""

from __future__ import annotations

import duckdb

from trikal_core.db import data_dir

# Each SELECT yields the canonical column list. `src` is the read_csv relation over a glob.
_COMMON_TAIL = """
    (trade_date + INTERVAL 16 HOUR)::TIMESTAMP::TIMESTAMPTZ AS known_at,
    'convention' AS known_precision,
    now() AS recorded_at,
    regexp_extract(filename, '__([0-9a-f]{64})\\.csv$', 1) AS source_sha
"""

_DATE = "CAST(regexp_extract(filename, '(\\d{4}-\\d{2}-\\d{2})__', 1) AS DATE) AS trade_date"

SQL = {
    "nse_udiff": f"""
        SELECT 'NSE' AS exchange, {_DATE}, trim(TckrSymb) AS code, coalesce(trim(SctySrs), '') AS series,
               nullif(trim(ISIN), '') AS isin, trim(FinInstrmNm) AS name, trim(FinInstrmTp) AS instr_type,
               TRY_CAST(OpnPric AS DOUBLE) AS open, TRY_CAST(HghPric AS DOUBLE) AS high,
               TRY_CAST(LwPric AS DOUBLE) AS low, TRY_CAST(ClsPric AS DOUBLE) AS close,
               TRY_CAST(LastPric AS DOUBLE) AS last, TRY_CAST(PrvsClsgPric AS DOUBLE) AS prev_close,
               TRY_CAST(TtlTradgVol AS DOUBLE) AS volume, TRY_CAST(TtlTrfVal AS DOUBLE) AS turnover,
               TRY_CAST(TtlNbOfTxsExctd AS BIGINT) AS trades, {_COMMON_TAIL}
        FROM src WHERE Sgmt = 'CM'""",
    "bse_udiff": f"""
        SELECT 'BSE' AS exchange, {_DATE}, trim(FinInstrmId) AS code, coalesce(trim(SctySrs), '') AS series,
               nullif(trim(ISIN), '') AS isin, trim(FinInstrmNm) AS name, trim(FinInstrmTp) AS instr_type,
               TRY_CAST(OpnPric AS DOUBLE), TRY_CAST(HghPric AS DOUBLE), TRY_CAST(LwPric AS DOUBLE),
               TRY_CAST(ClsPric AS DOUBLE), TRY_CAST(LastPric AS DOUBLE), TRY_CAST(PrvsClsgPric AS DOUBLE),
               TRY_CAST(TtlTradgVol AS DOUBLE), TRY_CAST(TtlTrfVal AS DOUBLE),
               TRY_CAST(TtlNbOfTxsExctd AS BIGINT), {_COMMON_TAIL}
        FROM src WHERE Sgmt = 'CM'""",
    "nse_legacy": f"""
        SELECT 'NSE' AS exchange, {_DATE}, trim(SYMBOL) AS code, trim(SERIES) AS series,
               nullif(trim(ISIN), '') AS isin, NULL AS name, NULL AS instr_type,
               TRY_CAST(OPEN AS DOUBLE), TRY_CAST(HIGH AS DOUBLE), TRY_CAST(LOW AS DOUBLE),
               TRY_CAST(CLOSE AS DOUBLE), TRY_CAST(LAST AS DOUBLE), TRY_CAST(PREVCLOSE AS DOUBLE),
               TRY_CAST(TOTTRDQTY AS DOUBLE), TRY_CAST(TOTTRDVAL AS DOUBLE),
               TRY_CAST(TOTALTRADES AS BIGINT), {_COMMON_TAIL}
        FROM src WHERE SYMBOL IS NOT NULL""",
    "bse_legacy": f"""
        SELECT 'BSE' AS exchange, {_DATE}, trim(SC_CODE) AS code, coalesce(trim(SC_GROUP), '') AS series,
               nullif(trim(ISIN_CODE), '') AS isin, trim(SC_NAME) AS name, trim(SC_TYPE) AS instr_type,
               TRY_CAST(OPEN AS DOUBLE), TRY_CAST(HIGH AS DOUBLE), TRY_CAST(LOW AS DOUBLE),
               TRY_CAST(CLOSE AS DOUBLE), TRY_CAST(LAST AS DOUBLE), TRY_CAST(PREVCLOSE AS DOUBLE),
               TRY_CAST(NO_OF_SHRS AS DOUBLE), TRY_CAST(NET_TURNOV AS DOUBLE),
               TRY_CAST(NO_TRADES AS BIGINT), {_COMMON_TAIL}
        FROM src WHERE SC_CODE IS NOT NULL""",
}
SQL["bse_isin"] = SQL["bse_legacy"]

FORMATS = {"NSE": ["nse_legacy", "nse_udiff"], "BSE": ["bse_legacy", "bse_isin", "bse_udiff"]}

# Columns optional in older files of a format; created as NULL when absent so one SQL fits all.
_OPTIONAL = {"nse_legacy": ["ISIN", "TOTALTRADES"], "bse_legacy": ["ISIN_CODE"], "bse_isin": ["ISIN_CODE"]}


def _src_relation(con: duckdb.DuckDBPyConnection, fmt: str) -> bool:
    files = sorted((data_dir() / "staging" / fmt).glob("*.csv"))
    if not files:
        return False
    # Views cannot take bound parameters; paths are ours (data dir + sha names), quoted defensively.
    plist = "[" + ", ".join("'" + f.as_posix().replace("'", "''") + "'" for f in files) + "]"
    con.execute(
        f"CREATE OR REPLACE TEMP VIEW src_raw AS SELECT * FROM read_csv({plist}, all_varchar = true, header = true, "
        "union_by_name = true, filename = true, ignore_errors = false, null_padding = true, strict_mode = false)"
    )
    cols = {r[0].upper(): r[0] for r in con.execute("DESCRIBE src_raw").fetchall()}
    extra = ", ".join(f"NULL::VARCHAR AS {c}" for c in _OPTIONAL.get(fmt, []) if c not in cols)
    con.execute(f"CREATE OR REPLACE TEMP VIEW src AS SELECT *{', ' + extra if extra else ''} FROM src_raw")
    return True


def load_exchange(con: duckdb.DuckDBPyConnection, exchange: str) -> dict[str, int]:
    out: dict[str, int] = {}
    con.execute("BEGIN")
    con.execute("DELETE FROM price_eod WHERE exchange = ?", [exchange])
    for fmt in FORMATS[exchange]:
        if not _src_relation(con, fmt):
            continue
        before = con.execute("SELECT count(*) FROM price_eod WHERE exchange = ?", [exchange]).fetchone()[0]
        con.execute(f"""
            INSERT INTO price_eod
            SELECT * FROM ({SQL[fmt]}) q
            QUALIFY row_number() OVER (PARTITION BY exchange, trade_date, code, series ORDER BY source_sha) = 1
        """)
        out[fmt] = con.execute(
            "SELECT count(*) FROM price_eod WHERE exchange = ?", [exchange]).fetchone()[0] - before
    con.execute("COMMIT")
    return out
