"""Read the downloaded results decks and load the figures they state into `fact_reported` (rule-based, see deck_metrics.py)."""

from __future__ import annotations

import datetime as dt
import json

import duckdb

from trikal_analytics import metrics as M
from trikal_core.db import insert_many
from trikal_core.pit import PitReader
from trikal_core.timeutil import AsOf, utcnow
from trikal_pipeline import deck_metrics as DM
from trikal_pipeline.load_financials import symbol_security_map
from trikal_pipeline.raw import RawStore
from trikal_pipeline.sources import nse_decks as ND

# A figure that contradicts what the results filing itself implies is a misread, not a finding.
NIM_VS_NII_ASSETS_TOLERANCE = 0.025


def _gate(con: duckdb.DuckDBPyConnection, security_id: str, announced: dt.datetime, hits: dict) -> dict[str, str]:
    """Cross-checks against the XBRL numbers known at the announcement. Returns concept -> reason for every value to reject."""
    reasons: dict[str, str] = {}
    if not any(c in hits for c in ("nim", "car")):
        return reasons
    eng = M.Engine(PitReader(con))
    a = AsOf(announced)
    if "nim" in hits:
        proxy = eng.compute("nii_to_assets", security_id, a)
        if hasattr(proxy, "value") and abs(hits["nim"].value - proxy.value) > NIM_VS_NII_ASSETS_TOLERANCE:
            reasons["nim"] = f"NIM {hits['nim'].value:.4f} is far from net interest income / assets {proxy.value:.4f} in the filing"
    if "car" in hits:
        cet1 = eng.compute("cet1", security_id, a)
        if hasattr(cet1, "value") and hits["car"].value < cet1.value - 0.002:
            reasons["car"] = f"capital adequacy {hits['car'].value:.4f} is below the filing's CET1 {cet1.value:.4f}"
    return reasons


def drop_outliers(con: duckdb.DuckDBPyConnection, rel: float = 0.5, min_values: int = 4) -> int:
    """A company's quarterly ratios do not jump by half: a value far from the median of its own series for that metric is a misread,
    removed (the metric is then n/a for that quarter, never replaced)."""
    rows = con.execute("SELECT security_id, concept, period_end, value, source_url FROM fact_reported").fetchall()
    by: dict[tuple, list] = {}
    for sid, c, pe, v, url in rows:
        by.setdefault((sid, c), []).append((pe, v, url))
    bad = []
    for (sid, c), vs in by.items():
        if len(vs) < min_values:
            continue
        med = sorted(v for _, v, _ in vs)[len(vs) // 2]
        bad += [(sid, c, pe, url) for pe, v, url in vs if med and abs(v - med) > rel * abs(med)]
    for sid, c, pe, url in bad:
        con.execute("DELETE FROM fact_reported WHERE security_id = ? AND concept = ? AND period_end = ? AND source_url = ?", [sid, c, pe, url])
    return len(bad)


def build_reported(con: duckdb.DuckDBPyConnection, raw: RawStore, symbols: list[str] | None = None, limit: int | None = None,
                   log=print) -> dict[str, int]:
    sec = symbol_security_map(con)
    pdfs = raw.latest_ok(ND.PDF_KEY)
    done = {r[0] for r in con.execute("SELECT source_url FROM deck_parsed").fetchall()}
    todo = [(s, row) for s, row in ND.deck_rows(raw, symbols) if row["attchmntFile"].strip() in pdfs and row["attchmntFile"].strip() not in done]
    if limit:
        todo = todo[:limit]
    stats = {"decks": 0, "values": 0, "no_security": 0, "gate_rejected": 0, "no_period": 0, "nothing_matched": 0, "errors": 0}
    log(f"{len(todo)} decks to read")
    now = utcnow()
    for i, (sym, row) in enumerate(todo, 1):
        url = row["attchmntFile"].strip()
        at = ND.announced(row)
        sid = sec.get(sym)
        if sid is None:
            stats["no_security"] += 1
            continue
        try:
            res = DM.parse_deck(raw.read(pdfs[url]), at.date())
        except Exception as exc:
            stats["errors"] += 1
            insert_many(con, "INSERT INTO deck_parsed VALUES (?,?,?,?,?,?,?,?)",
                        [(url, sym, at, None, f"error: {type(exc).__name__}", 0, str(exc)[:300], now)])
            continue
        values = res["values"]
        rejected = _gate(con, sid, at, values) if values else {}
        keep = {c: h for c, h in values.items() if c not in rejected}
        stats["gate_rejected"] += len(rejected)
        rows = [(sid, c, h.period_end, h.value, "ratio", f"deck_rule:{h.kind}", 0.9 if h.kind == "table" else 0.7, url, pdfs[url], h.page,
                 h.line, at, "exact" if row.get("exchdisstime") else "day", now) for c, h in keep.items()]
        con.execute("BEGIN")
        if rows:
            con.execute("DELETE FROM fact_reported WHERE source_url = ?", [url])
            insert_many(con, "INSERT INTO fact_reported VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)", rows)
        status = res["status"] if not (values and not keep) else "gate_rejected"
        insert_many(con, "INSERT INTO deck_parsed VALUES (?,?,?,?,?,?,?,?)",
                    [(url, sym, at, res.get("period_end"), status, len(rows),
                      json.dumps({"dropped": res.get("dropped"), "rejected": rejected}, default=str)[:900], now)])
        con.execute("COMMIT")
        stats["decks"] += 1
        stats["values"] += len(rows)
        stats["no_period"] += status.startswith(("the deck never", "no reporting"))
        stats["nothing_matched"] += status == "nothing matched"
        if i % 25 == 0:
            log(f"decks {i}/{len(todo)} {stats}")
    stats["outliers_removed"] = drop_outliers(con)
    return stats
