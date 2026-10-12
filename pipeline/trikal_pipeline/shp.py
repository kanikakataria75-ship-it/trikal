"""Shareholding pattern (SHP) and promoter-pledge loaders.

Three sources, all point-in-time:
  * list API summary  : promoter % / public % per quarter for every filing, 2015 -> (no category detail)
  * SHP XBRL          : category totals (MF, FPI, insurance, retail, ...) per quarter, ~Sep-2021 -> via the list API
  * pledge endpoint   : latest quarter only; history accumulates forward from the first fetch (RISKS R-26)

The filed percentage is stored (it is the company's declared figure), after normalising its scale, which
changed between filings (fraction 0.7177 vs percent 71.77). Where it disagrees with the share-count based
percentage by more than 0.05 pp (e.g. a base that includes depository receipts) a data-quality row is logged.

Revised filings: the exchange list keeps only the revised record, whose broadcast time is the revision's.
`known_at` is that time (flag 'Revised'); the original values are not retained, so between the original
submission and the revision the quarter is simply absent from point-in-time views (never look-ahead).
"""

from __future__ import annotations

import csv
import datetime as dt
import json
import re
import xml.etree.ElementTree as ET

import duckdb

from trikal_core.db import data_dir, insert_many
from trikal_core.timeutil import IST, utcnow
from trikal_pipeline.raw import RawStore

XBRLI = "{http://www.xbrl.org/2003/instance}"

_FIX = [("Catergory", "Category"), ("Goverments", "Governments"), ("Rbi", "RBI"), ("Uti", "UTI"), ("Sme", "SME"),
        ("Isis", "Is")]


def norm_category(name: str) -> str:
    n = name.strip()
    if n.endswith("_ContextI"):
        n = n[: -len("_ContextI")]
    elif n.endswith("Member"):
        n = n[: -len("Member")]
    elif n.endswith("I") and not n.endswith(("RBI", "UTI")):
        pass
    n = n.replace("_", "")
    for a, b in _FIX:
        n = n.replace(a, b)
    return n


def parse_shp(body: bytes) -> dict:
    root = ET.fromstring(body)
    cat_of: dict[str, str] = {}
    for c in root.findall(XBRLI + "context"):
        cid = c.attrib["id"]
        name = None
        for m in c.iter():
            if m.tag.endswith("explicitMember") and m.attrib.get("dimension", "").endswith("CategoryOfShareholdersAxis"):
                name = (m.text or "").split(":")[-1]
        if name is None and cid.endswith("_ContextI"):
            name = cid
        if name:
            cat_of[cid] = norm_category(name)
    vals: dict[str, dict] = {}
    meta: dict[str, str] = {}
    for el in root:
        n = el.tag.split("}")[-1]
        cref = el.attrib.get("contextRef")
        if not cref:
            continue
        if cref in cat_of and n in ("NumberOfShareholders", "NumberOfFullyPaidUpEquityShares",
                                    "ShareholdingAsAPercentageOfTotalNumberOfShares"):
            try:
                vals.setdefault(cat_of[cref], {})[n] = float((el.text or "").strip())
            except ValueError:
                pass
        elif n in ("Symbol", "ISIN", "ScripCode", "DateOfReport", "NameOfTheCompany") and n not in meta and el.text:
            meta[n] = el.text.strip()
    total = vals.get("ShareholdingPattern", {}).get("NumberOfFullyPaidUpEquityShares")
    # scale of the reported percentage: the whole pattern is 100 (percent) or 1 (fraction) in the same file
    rep_total = vals.get("ShareholdingPattern", {}).get("ShareholdingAsAPercentageOfTotalNumberOfShares")
    scale = 100.0 if (rep_total is not None and 0 < rep_total <= 1.5) else 1.0
    rows, problems = [], []
    for cat, v in vals.items():
        shares = v.get("NumberOfFullyPaidUpEquityShares")
        if shares is None:
            continue
        computed = 100.0 * shares / total if total else None
        rep = v.get("ShareholdingAsAPercentageOfTotalNumberOfShares")
        rep = rep * scale if rep is not None else None
        pct = rep if rep is not None else computed
        if computed is not None and rep is not None and abs(rep - computed) > 0.05:
            problems.append(f"{cat}: reported {rep:.4f} vs share-count {computed:.4f}")
        rows.append((cat, v.get("NumberOfShareholders"), shares, pct))
    return {"meta": meta, "rows": rows, "total": total, "problems": problems}


def _ts(s: str | None) -> dt.datetime | None:
    if not s:
        return None
    for f in ("%d-%b-%Y %H:%M:%S", "%d-%b-%Y"):
        try:
            return dt.datetime.strptime(s.strip().title(), f).replace(tzinfo=IST)
        except ValueError:
            continue
    return None


def _sym_sec(con) -> dict[str, str]:
    return {c: s for c, s in con.execute(
        "SELECT code, arg_max(security_id, valid_to) FROM listing WHERE exchange = 'NSE' GROUP BY code").fetchall()}


def shp_list_rows(raw: RawStore):
    for sym, sha in raw.latest_ok("nse.shareholding").items():
        try:
            rows = json.loads(raw.read(sha))
        except Exception:
            continue
        for row in rows if isinstance(rows, list) else []:
            yield sym, row


def load_shareholding(con: duckdb.DuckDBPyConnection, raw: RawStore, limit: int | None = None) -> dict[str, int]:
    """(1) summary rows from the list API, (2) category rows from downloaded SHP XBRL documents."""
    sec = _sym_sec(con)
    now = utcnow()
    stats = {"summary_rows": 0, "xbrl_docs": 0, "category_rows": 0, "parse_errors": 0, "pct_mismatch_docs": 0}
    con.execute("BEGIN")
    con.execute("DELETE FROM shareholding")
    con.execute("DELETE FROM filing WHERE kind = 'shp_xbrl'")
    summary, filings, index = [], [], {}
    for sym, row in shp_list_rows(raw):
        sid = sec.get(sym)
        pe = _ts(row.get("date"))
        known = _ts(row.get("broadcastDate")) or _ts(row.get("systemDate"))
        if not (sid and pe and known):
            continue
        flag = "Revised" if str(row.get("revisedData")).lower() == "revised" else ""
        url = (row.get("xbrl") or "").strip()
        index[url] = (sym, sid, pe.date(), known, flag)
        for cat, key in (("ShareholdingOfPromoterAndPromoterGroup", "pr_and_prgrp"), ("PublicShareholding", "public_val")):
            try:
                pct = float(row[key])
            except (KeyError, TypeError, ValueError):
                continue
            summary.append((sid, pe.date(), cat, None, None, pct, known, "exact", flag, f"list:{row.get('recordId')}", ""))
    stats["summary_rows"] = insert_many(con, "INSERT INTO shareholding VALUES (?,?,?,?,?,?,?,?,?,?,?)", summary)

    fetched = raw.db.execute("SELECT partition_key, sha256 FROM fetch_log WHERE source_key = 'nse.xbrl.shp' "
                             "AND status = 'ok' GROUP BY partition_key").fetchall()
    if limit:
        fetched = fetched[:limit]
    out_rows, dq = [], []
    for url, sha in fetched:
        meta = index.get(url)
        if not meta:
            continue
        sym, sid, pe, known, flag = meta
        try:
            d = parse_shp(raw.read(sha))
        except Exception as exc:
            stats["parse_errors"] += 1
            dq.append(("shp_parse_error", "NSE", sym, pe, f"{url}: {type(exc).__name__}: {exc}"[:300], "medium", now))
            continue
        if d["problems"]:
            stats["pct_mismatch_docs"] += 1
            dq.append(("shp_pct_mismatch", "NSE", sym, pe, f"{url}: {d['problems'][:3]}", "low", now))
        filings.append((url, "shp_xbrl", sym, sid, "SHP", None, None, pe, None, None, None, None, known, "exact",
                        flag, sha, now))
        for cat, holders, shares, pct in d["rows"]:
            out_rows.append((sid, pe, cat, holders, shares, pct, known, "exact", flag, url, sha))
        stats["xbrl_docs"] += 1
    stats["category_rows"] = insert_many(con, "INSERT INTO shareholding VALUES (?,?,?,?,?,?,?,?,?,?,?)", out_rows)
    insert_many(con, "INSERT INTO filing VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)", filings)
    insert_many(con, "INSERT INTO dq_issue VALUES (?,?,?,?,?,?,?)", dq)
    con.execute("COMMIT")
    return stats


def load_pledge(con: duckdb.DuckDBPyConnection, raw: RawStore) -> dict[str, int]:
    """Every pledge payload ever fetched (the endpoint returns only the latest quarter, so we keep them all)."""
    sec = _sym_sec(con)
    rows = raw.db.execute("SELECT partition_key, sha256, attempted_at FROM fetch_log WHERE source_key = 'nse.pledge' "
                          "AND status = 'ok' AND sha256 IS NOT NULL").fetchall()
    out, seen = [], set()
    for sym, sha, fetched_at in rows:
        sid = sec.get(sym)
        if not sid or (sym, sha) in seen:
            continue
        seen.add((sym, sha))
        try:
            payload = json.loads(raw.read(sha))
        except Exception:
            continue
        for x in payload.get("data", []) if isinstance(payload, dict) else []:
            as_on = _ts(x.get("shp"))
            known = _ts(x.get("broadcastDt"))
            if not (as_on and known):
                continue

            def num(k):
                try:
                    return float(str(x.get(k)).strip())
                except (TypeError, ValueError):
                    return None
            out.append((sid, as_on.date(), num("percPromoterHolding"), num("percPromoterShares"), num("percTotShares"),
                        num("totPromoterShares"), num("totPromoterHolding"), num("totIssuedShares"), known, "exact",
                        dt.datetime.fromisoformat(fetched_at), sha))
    con.execute("BEGIN")
    con.execute("DELETE FROM pledge_snapshot")
    n = insert_many(con, "INSERT INTO pledge_snapshot VALUES (?,?,?,?,?,?,?,?,?,?,?,?)", out)
    con.execute("COMMIT")
    return {"pledge_snapshots": n}


# Groupings used by analytics (raw categories stay in `shareholding`).
GROUPS = {
    "promoter": ["ShareholdingOfPromoterAndPromoterGroup"],
    "mutual_funds": ["MutualFundsOrUTI"],
    "insurance": ["InsuranceCompanies"],
    "fpi": ["InstitutionsForeignPortfolioInvestorCategoryOne", "InstitutionsForeignPortfolioInvestorCategoryTwo"],
    "foreign_institutions": ["InstitutionsForeign"],
    "domestic_institutions": ["InstitutionsDomestic"],
    "retail": ["ResidentIndividualShareholdersHoldingNominalShareCapitalUpToRsTwoLakh",
               "ResidentIndividualShareholdersHoldingNominalShareCapitalInExcessOfRsTwoLakh"],
    "public": ["PublicShareholding"],
}
