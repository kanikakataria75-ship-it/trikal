"""Load parsed results filings (XBRL now, HTML for 2008-2017) into `filing` and `fact_financial_all`,
then derive the PIT table `fact_financial` (value-change rows only).

Incremental: a document already present in `filing` is not parsed again.
"""

from __future__ import annotations

import csv
import datetime as dt
import json
from pathlib import Path

import duckdb

from trikal_core.db import data_dir, insert_many
from trikal_core.timeutil import IST, utcnow
from trikal_pipeline.html_results import parse_results_html
from trikal_pipeline.raw import RawStore
from trikal_pipeline.xbrl_results import family_from_url, months_between, parse_results_xbrl

LIST_KEYS = ("nse.results.quarterly", "nse.results.annual", "nse.results.integrated")
CSV_COLS = ["filing_id", "security_id", "basis", "concept", "dims", "col", "period_start", "period_end",
            "is_instant", "period_months", "value", "unit", "known_at", "known_precision", "source_sha"]
STATUTORY_DAYS = {"Fourth Quarter": 60, "Annual": 60, "Yearly": 60}  # LODR Reg 33: 60 days for Q4/annual, else 45


def _ts(s: str | None) -> dt.datetime | None:
    if not s:
        return None
    for f in ("%d-%b-%Y %H:%M:%S", "%d-%b-%Y %H:%M", "%d-%b-%Y"):
        try:
            return dt.datetime.strptime(s.strip().title() if f.startswith("%d-%b") else s.strip(), f).replace(tzinfo=IST)
        except ValueError:
            continue
    return None


def _date(s: str | None) -> dt.date | None:
    t = _ts(s)
    return t.date() if t else None


def symbol_security_map(con: duckdb.DuckDBPyConnection) -> dict[str, str]:
    rows = con.execute("""
        SELECT code, arg_max(security_id, valid_to) FROM listing WHERE exchange = 'NSE' GROUP BY code""").fetchall()
    return {c: s for c, s in rows}


def list_rows(raw: RawStore):
    """Yield (symbol, row dict) for every filing row of every fetched results list."""
    for key in LIST_KEYS:
        for sym, sha in raw.latest_ok(key).items():
            try:
                rows = json.loads(raw.read(sha))
            except Exception:
                continue
            if isinstance(rows, dict):
                rows = rows.get("data") or []
            for row in rows if isinstance(rows, list) else []:
                yield sym, key, row


def filing_index(raw: RawStore) -> dict[str, dict]:
    """url -> metadata from the exchange lists (document url is the xbrl link or the html detail link)."""
    idx: dict[str, dict] = {}
    for sym, key, row in list_rows(raw):
        integrated = key.endswith("integrated")
        if row.get("type") and "financials" not in row["type"].lower():
            continue  # Integrated Filing- Governance documents are not financial statements
        x = (row.get("xbrl") or "").strip()
        h = (row.get("resultDetailedDataLink") or "").strip()
        if x.lower().endswith(".xml") and x.lower().startswith("http"):
            url, kind = x, "results_xbrl"
        elif h.lower().startswith("http"):
            url, kind = h, "results_html"
        else:
            continue
        bc = _ts(row.get("broadcast_Date") if integrated else row.get("broadCastDate"))
        prec = "exact"
        if bc is None:
            bc = _ts(row.get("creation_Date") if integrated else row.get("filingDate"))
        meta = dict(
            symbol=sym, kind=kind, known_at=bc, known_precision=prec if bc else "imputed",
            basis={"Consolidated": "consolidated"}.get(row.get("consolidated"), "standalone"),
            to=_date(row.get("qe_Date") if integrated else row.get("toDate")),
            frm=_date(row.get("fromDate")),
            label=row.get("relatingTo") or row.get("period"),
            audited=row.get("audited"),
            flag="|".join(str(row.get(k)) for k in ("reInd", "type_Sub", "revised_Date") if row.get(k) not in (None, "", "-")),
        )
        prev = idx.get(url)
        if prev is None or (bc and (prev["known_at"] is None or bc < prev["known_at"])):
            idx[url] = meta  # same document listed twice: keep the earliest broadcast
    return idx


def _iso(t: dt.datetime | None) -> str:
    return t.isoformat() if t else ""


def _xbrl_adapter(url, sha, m, raw):
    p = parse_results_xbrl(raw.read(sha))
    basis = {"Consolidated": "consolidated", "Standalone": "standalone"}.get(
        p.meta.get("NatureOfReportStandaloneConsolidated"), m["basis"])
    pe = max((f.period_end for f in p.facts), default=m["to"])
    fy = p.meta.get("DateOfStartOfFinancialYear")
    return dict(facts=p.facts, basis=basis, family=family_from_url(url), period_end=pe,
                period_start=min((f.period_start for f in p.facts if f.period_start), default=None),
                fy_start=dt.date.fromisoformat(fy) if fy else None,
                label=p.meta.get("ReportingQuarter") or m["label"],
                audited=p.meta.get("WhetherResultsAreAuditedOrUnaudited") or m["audited"],
                rounding=p.meta.get("LevelOfRoundingUsedInFinancialStatements"),
                skipped=sum(p.skipped_columns.values()))


def _html_adapter(url, sha, m, raw):
    p = parse_results_html(raw.read(sha))
    if p.period_end is None:
        raise ValueError("; ".join(p.problems) or "no period")
    cons = (p.meta.get("consolidated") or "").lower()
    basis = "consolidated" if cons == "consolidated" else ("standalone" if cons else m["basis"])
    return dict(facts=p.facts, basis=basis, family="HTML", period_end=p.period_end, period_start=p.period_start,
                fy_start=p.fy_start, label=p.meta.get("relating_to") or m["label"],
                audited=p.meta.get("audited") or m["audited"], rounding="Lakhs", skipped=0)


KINDS = {
    "results_xbrl": ("nse.xbrl.results", _xbrl_adapter),
    "results_html": ("nse.results.html", _html_adapter),
}


def load_results(con: duckdb.DuckDBPyConnection, raw: RawStore, kind: str, batch_docs: int = 400,
                 limit: int | None = None) -> dict[str, int]:
    source_key, adapter = KINDS[kind]
    idx = {u: m for u, m in filing_index(raw).items() if m["kind"] == kind}
    sec = symbol_security_map(con)
    # Purge anything that is no longer a recognised financial-results document (rules changed since load).
    known = [r[0] for r in con.execute("SELECT filing_id FROM filing WHERE kind = ?", [kind]).fetchall()]
    stale = [u for u in known if u not in idx]
    for i in range(0, len(stale), 500):
        part = stale[i:i + 500]
        ph = ",".join("?" * len(part))
        con.execute(f"DELETE FROM fact_financial_all WHERE filing_id IN ({ph})", part)
        con.execute(f"DELETE FROM filing WHERE filing_id IN ({ph})", part)
    done = {r[0] for r in con.execute("SELECT filing_id FROM filing WHERE kind = ?", [kind]).fetchall()}
    fetched = raw.db.execute(
        "SELECT partition_key, sha256 FROM fetch_log WHERE source_key = ? AND status = 'ok' "
        "GROUP BY partition_key", (source_key,)).fetchall()
    todo = [(u, s) for u, s in fetched if u not in done and u in idx]
    if limit:
        todo = todo[:limit]
    stats = {"purged_stale": len(stale), "docs": 0, "facts": 0, "parse_errors": 0, "not_in_lists": 0,
             "skipped_columns": 0}
    stats["not_in_lists"] = sum(1 for u, _ in fetched if u not in idx)
    stage = data_dir() / "staging" / "fin"
    stage.mkdir(parents=True, exist_ok=True)
    now = utcnow()
    filings, dq = [], []
    out_path, w, fh = None, None, None

    def flush() -> None:
        nonlocal out_path, w, fh, filings, dq
        if fh:
            fh.close()
            con.execute(f"COPY fact_financial_all FROM '{out_path.as_posix()}' (HEADER, DELIMITER ',', FORCE_NOT_NULL (dims))")
            out_path.unlink()
            fh = w = None
        if filings:
            insert_many(con, "INSERT INTO filing VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)", filings)
        if dq:
            insert_many(con, "INSERT INTO dq_issue VALUES (?,?,?,?,?,?,?)", dq)
        filings, dq = [], []

    for i, (url, sha) in enumerate(todo, 1):
        m = idx[url]
        try:
            d = adapter(url, sha, m, raw)
        except Exception as exc:
            stats["parse_errors"] += 1
            dq.append((f"{kind}_parse_error", "NSE", m["symbol"], m["to"], f"{url}: {type(exc).__name__}: {exc}"[:300],
                       "medium", now))
            continue
        security_id = sec.get(m["symbol"])
        known_at, prec = m["known_at"], m["known_precision"]
        pe = d["period_end"]
        if known_at is None:  # no broadcast time: statutory deadline, flagged as imputed
            days = STATUTORY_DAYS.get(m["label"], 45)
            known_at = dt.datetime.combine(pe + dt.timedelta(days=days), dt.time(23, 59, 59), tzinfo=IST)
            prec = "imputed"
        if security_id is None:
            dq.append(("filing_no_security", "NSE", m["symbol"], pe, url, "medium", now))
        filings.append((url, kind, m["symbol"], security_id, d["family"], d["basis"], d["period_start"], pe,
                        d["fy_start"], d["label"], d["audited"], d["rounding"], known_at, prec, m["flag"], sha, now))
        stats["skipped_columns"] += d["skipped"]
        if fh is None:
            out_path = stage / f"facts_{dt.datetime.now():%H%M%S%f}.csv"
            fh = open(out_path, "w", newline="", encoding="utf-8")
            w = csv.writer(fh)
            w.writerow(CSV_COLS)
        for f in d["facts"]:
            w.writerow([url, security_id or "", d["basis"], f.concept, f.dims, f.col, f.period_start or "",
                        f.period_end, "true" if f.is_instant else "false",
                        months_between(f.period_start, f.period_end) or "", repr(f.value), f.unit,
                        _iso(known_at), prec, sha])
        stats["docs"] += 1
        stats["facts"] += len(d["facts"])
        if i % batch_docs == 0:
            flush()
    flush()
    return stats


def build_financials(con: duckdb.DuckDBPyConnection) -> int:
    """fact_financial = fact_financial_all reduced to value-change rows per (key, known order)."""
    con.execute("BEGIN")
    con.execute("DELETE FROM fact_financial")
    con.execute("""
        INSERT INTO fact_financial
        WITH r AS (
            SELECT *, lag(value) OVER w AS prev_value
            FROM fact_financial_all
            WHERE security_id <> ''
            WINDOW w AS (PARTITION BY security_id, basis, concept, dims, unit, period_start, period_end
                         ORDER BY known_at, filing_id))
        SELECT security_id, basis, concept, dims, period_start, period_end, is_instant, period_months, value, unit,
               known_at, known_precision, filing_id, source_sha, prev_value IS NOT NULL AS is_restated
        FROM r
        WHERE prev_value IS NULL OR abs(value - prev_value) > greatest(1e-9 * abs(prev_value), 1e-6)""")
    n = con.execute("SELECT count(*) FROM fact_financial").fetchone()[0]
    con.execute("COMMIT")
    return n


def relabel_dims(con: duckdb.DuckDBPyConnection, raw: RawStore, batch_docs: int = 500) -> dict[str, int]:
    """One-off: filings loaded before the parser named segment / other-expense members. Re-reads each XBRL filing that has
    dimensional facts and replaces only those facts (the consolidated lines are untouched)."""
    rows = con.execute("""
        SELECT f.filing_id, f.security_id, f.basis, f.known_at, f.known_precision, f.source_sha
        FROM filing f
        WHERE f.kind = 'results_xbrl'
          AND f.filing_id IN (SELECT DISTINCT filing_id FROM fact_financial_all WHERE dims <> '')""").fetchall()
    stage = data_dir() / "staging" / "fin"
    stage.mkdir(parents=True, exist_ok=True)
    stats = {"filings": len(rows), "relabelled_facts": 0, "errors": 0}
    for i in range(0, len(rows), batch_docs):
        part = rows[i:i + batch_docs]
        out_path = stage / f"relabel_{dt.datetime.now():%H%M%S%f}.csv"
        n = 0
        with open(out_path, "w", newline="", encoding="utf-8") as fh:
            w = csv.writer(fh)
            w.writerow(CSV_COLS)
            for url, security_id, basis, known_at, prec, sha in part:
                try:
                    p = parse_results_xbrl(raw.read(sha))
                except Exception:
                    stats["errors"] += 1
                    continue
                for f in p.facts:
                    if not f.dims:
                        continue
                    w.writerow([url, security_id or "", basis, f.concept, f.dims, f.col, f.period_start or "",
                                f.period_end, "true" if f.is_instant else "false",
                                months_between(f.period_start, f.period_end) or "", repr(f.value), f.unit,
                                _iso(known_at), prec, sha])
                    n += 1
        ids = [r[0] for r in part]
        ph = ",".join("?" * len(ids))
        con.execute("BEGIN")
        con.execute(f"DELETE FROM fact_financial_all WHERE dims <> '' AND filing_id IN ({ph})", ids)
        con.execute(f"COPY fact_financial_all FROM '{out_path.as_posix()}' (HEADER, DELIMITER ',', FORCE_NOT_NULL (dims))")
        con.execute("COMMIT")
        out_path.unlink()
        stats["relabelled_facts"] += n
    return stats
