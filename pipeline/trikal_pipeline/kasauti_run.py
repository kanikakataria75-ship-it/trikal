"""Run KASAUTI: score the Nifty 500 of each date, store the scores, and build the report card. Writes the database, so stop the API."""

from __future__ import annotations

import datetime as dt
import json
from pathlib import Path

import duckdb

from trikal_analytics import metrics as M
from trikal_core.db import data_dir, insert_many
from trikal_core.pit import PitReader
from trikal_core.timeutil import AsOf, utcnow
from trikal_kasauti import backtest as BT
from trikal_kasauti.config import ScoreConfig
from trikal_kasauti.factors import PriceBook
from trikal_kasauti.scoring import raw_metrics, score_panel

INDEX = "NIFTY500"


def rebalance_dates(con: duckdb.DuckDBPyConnection, start: dt.date, end: dt.date) -> list[dt.date]:
    """Last NSE session of March, June, September and December in [start, end]."""
    rows = con.execute(
        """SELECT max(trade_date) FROM (SELECT DISTINCT trade_date FROM price_eod WHERE exchange = 'NSE' AND trade_date BETWEEN ? AND ?)
           GROUP BY year(trade_date), month(trade_date) HAVING month(trade_date) IN (3, 6, 9, 12) ORDER BY 1""", [start, end]).fetchall()
    return [r[0] for r in rows]


def _json(o):
    if isinstance(o, (dt.date, dt.datetime)):
        return o.isoformat()
    raise TypeError(type(o))


def score_date(con: duckdb.DuckDBPyConnection, cfg: ScoreConfig, day: dt.date, book: PriceBook | None = None) -> dict:
    """Score the index members of `day` and replace that date's stored rows."""
    as_of = AsOf.end_of(day)
    reader = PitReader(con)
    members = [m[0] for m in reader.index_members(INDEX, as_of)]
    if not members:
        return {"date": day, "members": 0, "scored": 0}
    book = book or PriceBook(reader, members, AsOf.end_of(day))
    engine = M.Engine(reader)
    rows = []
    for sid in members:
        try:
            rows.append(raw_metrics(engine, reader, book, sid, as_of, cfg))
        except Exception:                                                     # one broken company must not stop the date
            continue
    scored = score_panel(rows, cfg, day)
    now = utcnow()
    con.execute("BEGIN")
    con.execute("DELETE FROM kasauti_score WHERE version = ? AND as_of = ?", [cfg.version, day])
    insert_many(con, "INSERT INTO kasauti_score VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                [(cfg.version, day, s["security_id"], s["score"], s["confidence"], s["status"], s["playbook"], s["peer_group"], s["n_peers"],
                  json.dumps({k: s[k] for k in ("profile", "peer_fallback", "pillars", "dropped", "skipped", "drivers")}, default=_json), now)
                 for s in scored])
    con.execute("COMMIT")
    return {"date": day, "members": len(members), "scored": sum(1 for s in scored if s["score"] is not None)}


def report_path(version: int) -> Path:
    from trikal_kasauti.config import report_file

    p = report_file(version)
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


def run_backtest(con: duckdb.DuckDBPyConnection, cfg: ScoreConfig, limit: int | None = None, log=print) -> dict:
    bt = cfg.backtest
    start = bt["start"] if isinstance(bt["start"], dt.date) else dt.date.fromisoformat(str(bt["start"]))
    last = con.execute("SELECT max(trade_date) FROM price_eod WHERE exchange = 'NSE'").fetchone()[0]
    dates = rebalance_dates(con, start, last)
    done = {r[0] for r in con.execute("SELECT DISTINCT as_of FROM kasauti_score WHERE version = ?", [cfg.version]).fetchall()}
    todo = [d for d in dates if d not in done][: limit or None]
    reader = PitReader(con)
    log(f"{len(dates)} rebalance dates, {len(done & set(dates))} already scored, {len(todo)} to do")
    book = None
    if todo:
        ever = sorted({m[0] for d in dates for m in reader.index_members(INDEX, AsOf.end_of(d))})
        log(f"loading prices for {len(ever)} securities")
        book = PriceBook(reader, ever, AsOf.end_of(last))
    for d in todo:
        log(f"scored {score_date(con, cfg, d, book)}")
    scores: dict[dt.date, dict[str, float]] = {}
    for d in dates:
        sc = {r["security_id"]: r["score"] for r in reader.kasauti_scores(cfg.version, d) if r["score"] is not None}
        if sc:
            scores[d] = sc
    if not scores:
        return {"error": "no scores"}
    if book is None:
        book = PriceBook(reader, sorted({s for v in scores.values() for s in v}), AsOf.end_of(last))
    rep = BT.evaluate(scores, book, [int(h) for h in bt["horizons_months"]], last, float(bt["top_fraction"]), float(bt["cost_per_side"]))
    rep.update({"version": cfg.version, "config_sha256": cfg.sha256, "generated_at": utcnow().isoformat(), "data_end": last.isoformat(),
                "label": "in-sample backtest (the score definition was written before looking at these returns, but the history is what "
                         "it is: short, one COVID cycle, price returns without dividends)",
                "conventions": {k: bt[k] for k in ("entry", "cost_per_side", "top_fraction", "benchmark", "returns")}})
    report_path(cfg.version).write_text(json.dumps(rep, default=_json, indent=1), encoding="utf-8")
    return rep
