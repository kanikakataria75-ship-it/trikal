"""Read the downloaded earnings-call transcripts into `concall` and `concall_promise` (rule-based, see call_parse.py)."""

from __future__ import annotations

import json

import duckdb

from trikal_core.db import insert_many
from trikal_core.timeutil import utcnow
from trikal_pipeline import call_parse as CP
from trikal_pipeline import deck_metrics as DM
from trikal_pipeline.load_financials import symbol_security_map
from trikal_pipeline.raw import RawStore
from trikal_pipeline.sources import nse_calls as NC
from trikal_pipeline.sources.nse_decks import announced


def build_calls(con: duckdb.DuckDBPyConnection, raw: RawStore, symbols: list[str] | None = None, limit: int | None = None,
                log=print) -> dict[str, int]:
    sec = symbol_security_map(con)
    pdfs = raw.latest_ok(NC.PDF_KEY)
    done = {r[0] for r in con.execute("SELECT source_url FROM concall").fetchall()}
    todo = [(s, r) for s, r in NC.call_rows(raw, symbols) if r["attchmntFile"].strip() in pdfs and r["attchmntFile"].strip() not in done]
    if limit:
        todo = todo[:limit]
    log(f"{len(todo)} transcripts to read")
    stats = {"calls": 0, "promises": 0, "no_period": 0, "too_short": 0, "errors": 0}
    now = utcnow()
    for i, (sym, row) in enumerate(todo, 1):
        url = row["attchmntFile"].strip()
        at = announced(row)
        sid = sec.get(sym)
        q = DM.reporting_quarter(at.date())
        if sid is None or q is None:
            stats["no_period"] += 1
            insert_many(con, "INSERT INTO concall VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                        [(url, sid, sym, at, None, 0, 0, "no security or reporting quarter", None, None, now)])
            continue
        try:
            res = CP.parse_pdf(raw.read(pdfs[url]), at.date(), q)
        except Exception as exc:
            stats["errors"] += 1
            insert_many(con, "INSERT INTO concall VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                        [(url, sid, sym, at, q, 0, 0, f"error: {type(exc).__name__}", None, None, now)])
            continue
        con.execute("BEGIN")
        insert_many(con, "INSERT INTO concall VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                    [(url, sid, sym, at, q, res.pages, res.words, res.status, json.dumps(res.tone), json.dumps(res.examples), now)])
        if res.promises:
            insert_many(con, "INSERT INTO concall_promise VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                        [(url, sid, at, q, p.metric, p.op, p.low, p.high, p.horizon_end, p.horizon_kind, p.quote, p.page) for p in res.promises])
        con.execute("COMMIT")
        stats["calls"] += 1
        stats["promises"] += len(res.promises)
        stats["too_short"] += res.status != "ok"
        if i % 50 == 0:
            log(f"calls {i}/{len(todo)} {stats}")
    return stats
