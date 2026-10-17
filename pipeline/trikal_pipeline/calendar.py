"""Exchange trading calendar derived from the bhavcopy fetch log (no external holiday list needed).

status per (exchange, day):
  session     a valid bhavcopy exists
  no_session  the exchange has no file for the day (NSE: HTTP 404; BSE: placeholder page) - and,
              for BSE, NSE did not trade that day either (BSE placeholders are not trusted alone)
Days absent from the table are UNKNOWN (not fetched yet, fetch error, or untrusted answer).
Consumers must treat unknown days as "cannot judge", never as holidays.
"""

from __future__ import annotations

import duckdb

from trikal_core.db import insert_many
from trikal_pipeline.raw import RawStore
from trikal_pipeline.sources.bhav import SOURCE_KEY


def build(con: duckdb.DuckDBPyConnection, raw: RawStore) -> dict[str, int]:
    status: dict[str, dict[str, str]] = {}
    for exchange, key in SOURCE_KEY.items():
        rows = raw.db.execute(
            """SELECT partition_key,
                      MAX(CASE WHEN status = 'ok' THEN 2 WHEN status = 'not_found' THEN 1 ELSE 0 END)
               FROM fetch_log WHERE source_key = ? GROUP BY 1""",
            (key,),
        ).fetchall()
        status[exchange] = {d: ("session" if s == 2 else "no_session") for d, s in rows if s > 0}
    nse = status.get("NSE", {})
    for d, s in list(status.get("BSE", {}).items()):
        if s == "no_session" and nse.get(d) == "session":
            del status["BSE"][d]  # BSE said "no file" on a day NSE traded: unknown, not a holiday
    out_rows = [(x, d, s) for x, days in status.items() for d, s in days.items()]
    con.execute("BEGIN")
    con.execute("DELETE FROM exchange_day")
    insert_many(con, "INSERT INTO exchange_day VALUES (?, CAST(? AS DATE), ?)", out_rows, chunk=2000)
    con.execute("COMMIT")
    counts = con.execute("SELECT exchange, status, count(*) FROM exchange_day GROUP BY 1, 2").fetchall()
    return {f"{x}_{s}": n for x, s, n in counts}
