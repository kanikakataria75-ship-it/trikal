"""Coverage & data-quality report (Markdown). Metadata about the data only: counts, ranges, rates."""

from __future__ import annotations

import datetime as dt

import duckdb


def _table(rows, headers) -> str:
    out = ["| " + " | ".join(headers) + " |", "|" + "---|" * len(headers)]
    for r in rows:
        out.append("| " + " | ".join("" if v is None else (f"{v:,}" if isinstance(v, int) else str(v)) for v in r) + " |")
    return "\n".join(out)


TARGET_START = {"NSE": dt.date(1994, 11, 1), "BSE": dt.date(2007, 1, 1)}


def report(con: duckdb.DuckDBPyConnection) -> str:
    q = lambda sql, p=None: con.execute(sql, p or []).fetchall()  # noqa: E731
    parts = [f"# TRIKAL data coverage — generated {dt.datetime.now():%Y-%m-%d %H:%M} IST", ""]

    parts += ["## Trading calendar (from the fetch log)",
              "Target range = earliest file we try to fetch -> today. Unknown = not answered yet "
              "(not fetched / fetch error / untrusted placeholder).", ""]
    rows = []
    today = dt.date.today()
    for x, start in TARGET_START.items():
        ses, nos = q("""SELECT count(*) FILTER (WHERE status = 'session')::INT,
                               count(*) FILTER (WHERE status = 'no_session')::INT
                        FROM exchange_day WHERE exchange = ? AND d BETWEEN ? AND ?""", [x, start, today])[0]
        rows.append((x, start, today, ses, nos, (today - start).days + 1 - ses - nos))
    parts += [_table(rows, ["exchange", "target from", "to", "sessions", "no session", "unknown days"]), ""]

    parts += ["## Prices (unadjusted, as published)", ""]
    rows = q("""SELECT exchange, min(trade_date), max(trade_date), count(*)::BIGINT, count(isin)::BIGINT,
                       count(DISTINCT code)::INT FROM price_eod GROUP BY 1 ORDER BY 1""")
    parts += [_table([(a, b, c, int(d), int(e), f) for a, b, c, d, e, f in rows],
                     ["exchange", "from", "to", "rows", "rows with ISIN", "distinct codes"]), ""]

    parts += ["## Security master", ""]
    rows = q("SELECT id_method, count(*)::INT, round(avg(confidence), 2) FROM security GROUP BY 1 ORDER BY 2 DESC")
    parts += [_table(rows, ["identity method (weakest listing)", "securities", "avg confidence"]), ""]

    parts += ["## Price adjustments", ""]
    rows = q("""SELECT exchange, agreement, applied, count(*)::INT FROM adj_event GROUP BY ALL ORDER BY 1, 4 DESC""")
    parts += [_table(rows, ["exchange", "agreement", "applied", "events"]), ""]

    parts += ["## Index membership reconstruction", ""]
    rows = q("""SELECT index_code, count(*)::INT, count(*) FILTER (WHERE ok)::INT, min(effective_date), max(effective_date)
                FROM index_count_check GROUP BY 1""")
    parts += [_table(rows, ["index", "count checks", "passing", "earliest", "latest"]), ""]
    rows = q("""WITH c AS (SELECT effective_date, ok, sum(CASE WHEN NOT ok THEN 1 ELSE 0 END)
                           OVER (ORDER BY effective_date DESC) AS fails_so_far FROM index_count_check)
                SELECT min(effective_date) FROM c WHERE fails_so_far = 0""")
    parts += [f"Contiguous passing window (from today backwards) starts at **{rows[0][0]}**.", ""]
    rows = q("""SELECT index_code, count(DISTINCT security_id)::INT,
                       count(DISTINCT security_id) FILTER (WHERE security_id LIKE 'U:%')::INT,
                       count(DISTINCT security_id) FILTER (WHERE method = 'pre_coverage')::INT
                FROM index_membership GROUP BY 1""")
    parts += [_table(rows, ["index", "securities ever", "unresolved placeholders", "pre-coverage start"]), ""]
    rows = q("""SELECT extract(year FROM effective_date)::VARCHAR y, count(*)::INT,
                       count(*) FILTER (WHERE security_id LIKE 'U:%')::INT,
                       count(*) FILTER (WHERE symbol IS NOT NULL)::INT,
                       count(*) FILTER (WHERE parse_confidence = 0 AND security_id NOT LIKE 'U:%')::INT
                FROM index_event GROUP BY 1 ORDER BY 1""")
    parts += ["Events by year (unresolved = name not matched to a security; superseded = revised/voided):", "",
              _table(rows, ["year", "events", "unresolved", "with symbol", "superseded"]), ""]

    parts += ["## Open data-quality issues", ""]
    rows = q("SELECT kind, severity, count(*)::INT FROM dq_issue GROUP BY ALL ORDER BY 3 DESC")
    parts += [_table(rows, ["kind", "severity", "count"]), ""]
    return "\n".join(parts)
