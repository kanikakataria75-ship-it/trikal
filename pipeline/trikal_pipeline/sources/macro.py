"""Macro series (M5): fetch into the raw zone, parse, load as bitemporal observations.

Sources (DATA_SOURCES §12): FRED (graph CSV without a key; ALFRED vintages with FRED_API_KEY), MOSPI eSankhyiki
CPI API, World Bank commodity "Pink Sheet". Series are declared in config/macro_series.yaml.

known_at (ADR-020): with FRED vintages, the exact first-release date of each value (precision 'vintage').
Otherwise a conservative rule from the registry: period end + lag_days, or the release calendar day, at a fixed
IST time (precision 'imputed'). Never earlier than the real release; the UI marks imputed times with "≈".
"""

from __future__ import annotations

import csv
import datetime as dt
import io
import json
import os
import ssl
from pathlib import Path

import httpx
import yaml

from trikal_core.db import insert_many
from trikal_core.timeutil import IST, utcnow
from trikal_pipeline.raw import RawStore

ROOT = Path(__file__).resolve().parents[3]
UA = "TRIKAL-research/0.3 (personal, non-commercial research terminal; contact: kanikakataria75@gmail.com)"
PINKSHEET_URL = ("https://thedocs.worldbank.org/en/doc/5d903e848db1d1b83e0ec8f744e55570-0350012021/related/"
                 "CMO-Historical-Data-Monthly.xlsx")
MOSPI_CPI = "https://api.mospi.gov.in/api/cpi/getCPIIndex"


def registry() -> dict:
    return yaml.safe_load((ROOT / "config" / "macro_series.yaml").read_text(encoding="utf-8"))["series"]


def _client(legacy_tls: bool = False) -> httpx.Client:
    if legacy_tls:  # api.mospi.gov.in still needs legacy TLS renegotiation; scoped to that host only
        ctx = ssl.create_default_context()
        ctx.options |= getattr(ssl, "OP_LEGACY_SERVER_CONNECT", 0x4)
        return httpx.Client(verify=ctx, timeout=90, headers={"User-Agent": UA}, follow_redirects=True)
    return httpx.Client(timeout=90, headers={"User-Agent": UA}, follow_redirects=True)


def _store(raw: RawStore, key: str, part: str, url: str, r: httpx.Response, ext: str) -> str:
    if r.status_code != 200 or not r.content:
        raw.log(key, part, url, "error" if r.status_code != 404 else "not_found", r.status_code, None)
        return "error"
    sha = raw.put(key, url, r.content, r.headers.get("content-type"), ext)
    raw.log(key, part, url, "ok", 200, sha)
    return "ok"


# ---------------------------------------------------------------------------------------------- fetch
def fetch(raw: RawStore, only: list[str] | None = None) -> dict[str, int]:
    reg = registry()
    out: dict[str, int] = {}

    def bump(k):
        out[k] = out.get(k, 0) + 1

    api_key = os.environ.get("FRED_API_KEY") or _dotenv("FRED_API_KEY")
    with _client() as c:
        for sid, s in reg.items():
            if only and sid not in only or s["source"]["kind"] != "fred":
                continue
            fid = s["source"]["id"]
            if api_key:  # ALFRED: every vintage, with its real-time window
                url = (f"https://api.stlouisfed.org/fred/series/observations?series_id={fid}&api_key={api_key}"
                       f"&file_type=json&realtime_start=1776-07-04&realtime_end=9999-12-31")
                try:
                    r = c.get(url)
                    bump("fred_vintage:" + _store(raw, "fred.vintage", fid, url.replace(api_key, "KEY"), r, "json"))
                    continue
                except httpx.HTTPError:
                    bump("fred_vintage:error")
            url = f"https://fred.stlouisfed.org/graph/fredgraph.csv?id={fid}"
            try:
                bump("fred_csv:" + _store(raw, "fred.csv", fid, url, c.get(url), "csv"))
            except httpx.HTTPError as e:
                raw.log("fred.csv", fid, url, "error", None, None, type(e).__name__)
                bump("fred_csv:error")
        if not only or any(reg[k]["source"]["kind"] == "pinksheet" for k in only if k in reg):
            url = _pinksheet_url(c)
            try:
                bump("pinksheet:" + _store(raw, "wb.pinksheet", "monthly", url, c.get(url), "xlsx"))
            except httpx.HTTPError:
                bump("pinksheet:error")
    if not only or any(reg[k]["source"]["kind"] == "mospi_cpi" for k in only if k in reg):
        with _client(legacy_tls=True) as c:
            for year in range(2011, dt.date.today().year + 1):
                base = f"{MOSPI_CPI}?base_year=2012&series=Current&year={year}&state_code=99&sector_code=3&format=json&limit=200"
                try:
                    rows, page, pages = [], 1, 1
                    while page <= pages:                       # the API caps pages at 200 rows
                        j = c.get(f"{base}&page={page}").json()
                        rows += j.get("data") or []
                        pages = (j.get("meta_data") or {}).get("totalPages", 1)
                        page += 1
                    if not rows:
                        raw.log("mospi.cpi", str(year), base, "not_found", 200, None)
                        bump("mospi_cpi:not_found")
                        continue
                    body = json.dumps({"data": rows}).encode()
                    sha = raw.put("mospi.cpi", base, body, "application/json", "json")
                    raw.log("mospi.cpi", str(year), base, "ok", 200, sha)
                    bump("mospi_cpi:ok")
                except (httpx.HTTPError, ValueError):
                    bump("mospi_cpi:error")
    return out


def _pinksheet_url(c: httpx.Client) -> str:
    """The monthly file's document id changes with every release: read the current link from the landing page."""
    import re

    try:
        page = c.get("https://www.worldbank.org/en/research/commodity-markets").text
        m = re.search(r"https://thedocs\.worldbank\.org/[^\"']*CMO-Historical-Data-Monthly\.xlsx", page)
        if m:
            return m.group(0)
    except httpx.HTTPError:
        pass
    return PINKSHEET_URL


def _dotenv(name: str) -> str | None:
    p = ROOT / ".env"
    if not p.exists():
        return None
    for line in p.read_text(encoding="utf-8").splitlines():
        if line.strip().startswith(name + "="):
            return line.split("=", 1)[1].strip().strip('"') or None
    return None


# ---------------------------------------------------------------------------------------------- known_at
def _month_end(d: dt.date) -> dt.date:
    return (d.replace(day=28) + dt.timedelta(days=4)).replace(day=1) - dt.timedelta(days=1)


def period_of(d: dt.date, freq: str) -> tuple[dt.date, dt.date]:
    if freq == "M":
        return d.replace(day=1), _month_end(d)
    return d, d


def imputed_known_at(period_end: dt.date, rule: dict) -> dt.datetime:
    if "release_day" in rule:
        nxt = period_end + dt.timedelta(days=1)
        day = nxt.replace(day=min(rule["release_day"], 28))
        return dt.datetime.combine(day, dt.time(17, 30), IST)
    return dt.datetime.combine(period_end + dt.timedelta(days=rule.get("lag_days", 0)), dt.time(18, 0), IST)


# ---------------------------------------------------------------------------------------------- parse
def parse_fred_csv(text: str) -> list[tuple[dt.date, float]]:
    rows = []
    rd = csv.reader(io.StringIO(text))
    next(rd, None)
    for r in rd:
        if len(r) < 2 or r[1] in ("", "."):
            continue  # FRED marks missing days with '.': absent, never zero
        rows.append((dt.date.fromisoformat(r[0]), float(r[1])))
    return rows


def parse_fred_vintages(text: str) -> list[tuple[dt.date, float, dt.date]]:
    """ALFRED observations: one row per (date, vintage window). Returns (date, value, realtime_start)."""
    out = []
    for o in json.loads(text).get("observations", []):
        if o["value"] in ("", "."):
            continue
        out.append((dt.date.fromisoformat(o["date"]), float(o["value"]), dt.date.fromisoformat(o["realtime_start"])))
    return out


_MONTHS = {m: i for i, m in enumerate(["January", "February", "March", "April", "May", "June", "July", "August",
                                         "September", "October", "November", "December"], start=1)}


def parse_mospi_cpi(text: str, subgroup: str) -> list[tuple[dt.date, float, str]]:
    out = []
    for r in json.loads(text).get("data", []):
        if r.get("state") != "All India" or r.get("sector") != "Combined" or r.get("subgroup") != subgroup:
            continue
        try:
            out.append((dt.date(int(r["year"]), _MONTHS[r["month"]], 1), float(r["index"]), r.get("status") or ""))
        except (KeyError, ValueError, TypeError):
            continue
    return out


def parse_pinksheet(blob: bytes) -> dict[str, list[tuple[dt.date, float]]]:
    """'Monthly Prices' sheet: a header row of commodity names, then rows 'YYYYMmm' with values ('..' = missing)."""
    import openpyxl

    wb = openpyxl.load_workbook(io.BytesIO(blob), read_only=True, data_only=True)
    ws = wb["Monthly Prices"]
    rows = list(ws.iter_rows(values_only=True))
    hdr_i = next(i for i, r in enumerate(rows) if r and r[0] is None and any(isinstance(x, str) and "Crude oil" in x for x in r if x))
    header = [str(x).strip() if x is not None else "" for x in rows[hdr_i]]
    out: dict[str, list[tuple[dt.date, float]]] = {h: [] for h in header if h}
    for r in rows[hdr_i + 1:]:
        if not r or not isinstance(r[0], str) or "M" not in r[0]:
            continue
        y, m = r[0].split("M")
        try:
            d = dt.date(int(y), int(m), 1)
        except ValueError:
            continue
        for h, v in zip(header, r):
            if h and isinstance(v, (int, float)):
                out[h].append((d, float(v)))
    return out


# ---------------------------------------------------------------------------------------------- load
def load(con, raw: RawStore) -> dict[str, int]:
    reg = registry()
    now = utcnow()
    obs: list[tuple] = []
    meta: list[tuple] = []
    fred_csv, fred_v = raw.latest_ok("fred.csv"), raw.latest_ok("fred.vintage")
    pink_sha = raw.latest_ok("wb.pinksheet").get("monthly")
    pink = parse_pinksheet(raw.read(pink_sha)) if pink_sha else {}
    cpi_years = raw.latest_ok("mospi.cpi")
    counts: dict[str, int] = {}
    for sid, s in reg.items():
        src, rule, freq = s["source"], s["known"], s["freq"]
        rows: list[tuple] = []
        if src["kind"] == "fred" and src["id"] in fred_v:
            for d, v, rt in parse_fred_vintages(raw.read(fred_v[src["id"]]).decode()):
                ps, pe = period_of(d, freq)
                rows.append((ps, pe, v, dt.datetime.combine(rt, dt.time(18, 0), IST), "vintage", rt, fred_v[src["id"]]))
        elif src["kind"] == "fred" and src["id"] in fred_csv:
            sha = fred_csv[src["id"]]
            for d, v in parse_fred_csv(raw.read(sha).decode()):
                ps, pe = period_of(d, freq)
                rows.append((ps, pe, v, imputed_known_at(pe, rule), "imputed", None, sha))
        elif src["kind"] == "pinksheet" and pink:
            col = next((h for h in pink if h.strip().lower() == src["column"].strip().lower()), None)
            for d, v in pink.get(col, []) if col else []:
                ps, pe = period_of(d, "M")
                rows.append((ps, pe, v, imputed_known_at(pe, rule), "imputed", None, pink_sha))
        elif src["kind"] == "mospi_cpi":
            sub = "General-Overall" if src["group"] == "General Index" else f"{src['group']}-Overall"
            for year, sha in cpi_years.items():
                for d, v, status in parse_mospi_cpi(raw.read(sha).decode(), sub):
                    ps, pe = period_of(d, "M")
                    rows.append((ps, pe, v, imputed_known_at(pe, rule), "imputed", None, sha))
        obs += [(sid, *r, now) for r in rows]
        counts[sid] = len(rows)
        meta.append((sid, s["name"], s["unit"], freq, s["category"], json.dumps(src), json.dumps(rule), s.get("note"),
                     len(rows), min((r[0] for r in rows), default=None), max((r[1] for r in rows), default=None)))
    # ~150k rows: a temporary CSV + COPY is seconds; parameterised inserts take many minutes
    import tempfile

    with tempfile.NamedTemporaryFile("w", suffix=".csv", delete=False, newline="", encoding="utf-8") as tmp:
        w = csv.writer(tmp)
        for r in obs:
            w.writerow([r[0], r[1], r[2], repr(r[3]), r[4].isoformat(), r[5], r[6] or "", r[7], r[8].isoformat()])
        path = tmp.name
    try:
        con.execute("BEGIN")
        con.execute("DELETE FROM macro_series")
        con.execute("DELETE FROM macro_obs")
        insert_many(con, "INSERT INTO macro_series VALUES (?,?,?,?,?,?,?,?,?,?,?)", meta)
        con.execute(f"""INSERT INTO macro_obs SELECT * FROM read_csv('{Path(path).as_posix()}', header = false,
                        columns = {{'series_id': 'VARCHAR', 'period_start': 'DATE', 'period_end': 'DATE', 'value': 'DOUBLE',
                                   'known_at': 'TIMESTAMPTZ', 'known_precision': 'VARCHAR', 'vintage': 'DATE',
                                   'source_sha': 'VARCHAR', 'recorded_at': 'TIMESTAMPTZ'}}, nullstr = '')""")
        con.execute("COMMIT")
    finally:
        os.unlink(path)
    return counts
