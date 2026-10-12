"""TRIKAL read API for the terminal UI (M3).

Rules (PROMPT invariants, ARCHITECTURE §2.2):
  * every endpoint takes a required `as_of` (YYYY-MM-DD or NOW); a future date is refused
  * data only through `PitReader` (a test forbids importing the database module here)
  * metric results keep their state (value / n.m. / n/a / forbidden); nothing is zero-filled
  * no fabricated data: `DEMO_MODE` exists only as a flag the UI watermarks; this API never invents values

Run:  python -m uvicorn trikal_api.app:app --app-dir api --port 8000
"""

from __future__ import annotations

import datetime as dt
import json
import os
import threading
import time
from contextlib import contextmanager
from pathlib import Path

from fastapi import Body, FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from trikal_analytics import metrics as M
from trikal_analytics import valuation as V
from trikal_analytics.lab import REQUIRED, Lab, template_assumptions
from trikal_analytics.result import ForbiddenError, NotAvailable, Value
from trikal_core.pit import PitReader, load_line_items, open_reader
from trikal_core.timeutil import AsOf

from trikal_api.serialize import plain, result

DEMO_MODE = os.environ.get("DEMO_MODE", "0").lower() in ("1", "true", "yes")
DISCLAIMER = "Research tool. Not investment advice. No ratings or target prices."
ROOT = Path(__file__).resolve().parents[2]
CACHE = ROOT / "data" / "cache"

app = FastAPI(title="TRIKAL API", version="0.3.0")
app.add_middleware(CORSMiddleware, allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],
                   allow_methods=["GET", "POST"], allow_headers=["*"])


# ---- database access: one read-only connection, released when idle so the pipeline can write -------------------
class _Db:
    IDLE_SECONDS = 90

    def __init__(self) -> None:
        self.lock = threading.Lock()
        self.reader: PitReader | None = None
        self.last = 0.0
        self.users = 0
        threading.Thread(target=self._reaper, daemon=True).start()

    @contextmanager
    def reader_ctx(self):
        with self.lock:
            if self.reader is None:
                try:
                    self.reader = open_reader(read_only=True)
                except Exception as e:  # the pipeline holds the write lock (e.g. refresh-m2)
                    raise HTTPException(503, f"database busy (pipeline writing?): {e}") from e
            self.users += 1
            base = self.reader
        try:
            yield PitReader(base.con.cursor())
        finally:
            with self.lock:
                self.users -= 1
                self.last = time.monotonic()

    def _reaper(self) -> None:
        while True:
            time.sleep(15)
            with self.lock:
                if self.reader is not None and self.users == 0 and time.monotonic() - self.last > self.IDLE_SECONDS:
                    self.reader.con.close()
                    self.reader = None


DB = _Db()


def asof(s: str) -> AsOf:
    try:
        a = AsOf.parse(s)
    except Exception as e:
        raise HTTPException(422, f"as_of must be YYYY-MM-DD or NOW: {e}") from e
    if a.date_ist > AsOf.now().date_ist:
        raise HTTPException(422, "as_of cannot be in the future (Bhavishya shows scenarios, not data)")
    return a


AS_OF = Query(..., description="YYYY-MM-DD or NOW (required on every endpoint)")


def ok(payload: dict, a: AsOf | None = None) -> JSONResponse:
    body = {"as_of": a.ts.isoformat() if a else None, "demo": DEMO_MODE, **plain(payload)}
    return JSONResponse(body, headers={"X-Trikal-Demo": "1" if DEMO_MODE else "0"})


def _sid(r: PitReader, code: str, a: AsOf, exchange: str) -> str:
    sid = code if code.startswith(("S:", "X:")) else r.resolve(code, a, exchange)
    if not sid and exchange == "NSE":
        sid = r.resolve(code, a, "BSE")
    if not sid:
        raise HTTPException(404, f"{code} is not listed on {exchange} as of {a.date_ist}")
    return sid


# ---- meta / search -----------------------------------------------------------------------------------------------
@app.get("/api/meta")
def meta(as_of: str = AS_OF):
    a = asof(as_of)
    with DB.reader_ctx() as r:
        return ok({"watermark": r.watermark(a), "stats": r.stats(a), "disclaimer": DISCLAIMER,
                   "now": AsOf.now().ts.isoformat()}, a)


@app.get("/api/search")
def search(q: str, as_of: str = AS_OF, limit: int = 15):
    a = asof(as_of)
    with DB.reader_ctx() as r:
        return ok({"results": r.search(q, a, limit)}, a)


@app.get("/api/market")
def market(as_of: str = AS_OF, hindsight: bool = False):
    """The last session known at as_of. With hindsight=true each name is also marked with whether it still
    trades TODAY — an explicit, labelled look back from the present (home page), never used in a computation."""
    a = asof(as_of)
    with DB.reader_ctx() as r:
        m = r.market_day(a)
        if m is None:
            raise HTTPException(404, f"no NSE session known as of {a.date_ist}")
        if hindsight:
            ids = [x["security_id"] for k in ("gainers", "losers", "most_traded") for x in m[k]]
            alive = r.still_trading(ids, AsOf.now())
            for k in ("gainers", "losers", "most_traded"):
                for x in m[k]:
                    x["trades_today"] = x["security_id"] in alive
        return ok({"market": m, "hindsight": hindsight}, a)


TM_MARQUEE = ["RELIANCE", "TCS", "HDFCBANK", "INFY", "ITC", "SBIN", "HINDUNILVR", "LT"]


TM_EVENTS = ["1994-11-03", "1998-05-12", "2000-02-29", "2004-05-17", "2006-05-22", "2008-01-21",
             "2008-10-24", "2009-05-18", "2013-08-28", "2014-05-16", "2016-06-24", "2016-11-09", "2019-09-20",
             "2020-03-23", "2021-02-01", "2023-01-27", "2024-06-04"]
_TM_CACHE: dict = {}


def _warm_time_machine() -> None:
    """Past sessions never change between data refreshes: precompute the built-in event days in the background."""
    for d in TM_EVENTS:
        try:
            _time_machine(asof(d), True)
        except Exception:
            pass


@app.on_event("startup")
def _startup() -> None:
    threading.Thread(target=_warm_time_machine, daemon=True).start()


@app.get("/api/timemachine")
def timemachine(as_of: str = AS_OF, hindsight: bool = False):
    a = asof(as_of)
    return ok(_time_machine(a, hindsight), a)


def _time_machine(a: AsOf, hindsight: bool, before_days: int = 120) -> dict:
    """One session, rebuilt for the Time Machine: breadth and movers, every index member as a tile (open/close,
    turnover, sector), the equal-weight path of those members in the weeks before, marquee prints of the day.
    hindsight=true adds what happened to the SAME members over the following year — labelled, and computed
    with today's knowledge on purpose; it is never mixed into the as-of numbers."""
    key = (a.date_ist, hindsight)
    if key in _TM_CACHE and a.date_ist < AsOf.now().date_ist:
        return _TM_CACHE[key]
    with DB.reader_ctx() as r:
        m = r.market_day(a)
        if m is None:
            raise HTTPException(404, f"no NSE session known as of {a.date_ist}")
        smap = r.session_map(a)
        d = m["session"]
        ids = [t["security_id"] for t in smap["tiles"]]
        before = r.ew_path(ids, d - dt.timedelta(days=before_days), d, a)
        marquee = []
        for code in TM_MARQUEE:
            sid = r.resolve(code, a, "NSE")
            lp = r.last_price(sid, a) if sid else None
            if lp and lp[0] == d:
                # the same print expressed in today's shares: every split/bonus applied since (known now; hindsight)
                f = 1.0
                for e in r.adjustment_events(sid, AsOf.now(), "NSE"):
                    if e[4] and e[0] > d:
                        f *= e[1]
                marquee.append({"code": code, "close": lp[1], "today_terms": lp[1] * f, "factor": f})
        try:
            ctx = r.context(d)
        except Exception:  # the context table may not exist yet on an older database
            ctx = {"world": [], "india": []}
        out = {"market": m, "map": smap, "before": before, "marquee": marquee, "hindsight": None,
               "tape": r.day_tape(a), "context": {**ctx, "licence": "Wikipedia contributors · CC BY-SA 4.0",
                                                 "note": "editorial summaries written after the fact; context only"}}
        if hindsight:
            now = AsOf.now()
            after = r.ew_path(ids, d + dt.timedelta(days=1), d + dt.timedelta(days=380), now)[:250]
            alive = r.still_trading(ids + [x["security_id"] for k in ("gainers", "losers", "most_traded") for x in m[k]], now)
            for k in ("gainers", "losers", "most_traded"):
                for x in m[k]:
                    x["trades_today"] = x["security_id"] in alive

            def cum(n):
                v = 1.0
                for x in after[:n]:
                    v *= 1 + (x["r"] or 0)
                return v - 1 if after else None

            out["hindsight"] = {"after": after, "m1": cum(21), "m3": cum(63), "y1": cum(250), "sessions": len(after),
                                "still_trading_today": len(alive & set(ids)), "members": len(ids),
                                "note": "computed with today's data; the members are fixed to that day's index"}
    if len(_TM_CACHE) > 200:
        _TM_CACHE.clear()
    _TM_CACHE[key] = out
    return out


@app.get("/api/survivors")
def survivors(on: dt.date, as_of: str = AS_OF):
    """Nifty 500 members on `on`, each marked with whether it still trades at as_of (hindsight on purpose)."""
    a = asof(as_of)
    if on > a.date_ist:
        raise HTTPException(422, "`on` must not be after as_of")
    with DB.reader_ctx() as r:
        m = r.members_fate("NIFTY500", on, a)
        return ok({"on": on, "members": m, **{k: sum(1 for x in m if x["fate"] == k) for k in ("alive", "gone", "unresolved")}}, a)


# ---- company -------------------------------------------------------------------------------------------------------
HEADLINE = ["market_cap", "revenue_ttm", "pat_ttm", "ebitda_margin", "net_margin", "roe", "roce", "pe", "pb",
            "ev_ebitda", "debt_to_equity", "revenue_growth", "profit_growth"]


@app.get("/api/company/{code}")
def company(code: str, as_of: str = AS_OF, exchange: str = "NSE"):
    a = asof(as_of)
    with DB.reader_ctx() as r:
        sid = _sid(r, code, a, exchange)
        eng = M.Engine(r)
        prof = r.profile(sid, a)
        res = eng.resolution(sid, a)
        pb = res.playbook
        last = r.last_price(sid, a, max_age_days=100000)
        listings = [dict(zip(["exchange", "code", "valid_from", "valid_to", "method", "confidence"], x)) for x in r.listings(sid, a)]
        nse = [x for x in listings if x["exchange"] == "NSE"]
        active = bool(last) and (a.date_ist - last[0]).days <= 10
        members = {x[0] for x in r.index_members("NIFTY500", a)}
        return ok({
            "security_id": sid, "code": (nse[-1]["code"] if nse else code.upper()),
            "name": r.display_name(sid, prof["name"]),
            "sector": prof["sector"], "sector_method": prof["sector_method"], "sector_confidence": prof["sector_confidence"],
            "family": prof["family"], "listings": listings, "active": active,
            "last_price": {"date": last[0], "close": last[1]} if last else None,
            "nifty500_member": sid in members,
            "playbook": {"id": pb.id, "label": pb.label, "chain": pb.chain, "overlays": pb.overlays, "how": res.how,
                         "confidence": res.confidence, "why": res.why, "key_metrics": pb.key_metrics,
                         "primary": pb.primary, "secondary": pb.secondary, "not_primary": pb.not_primary,
                         "forbidden_metrics": pb.forbidden_metrics, "forbidden_methods": pb.forbidden_methods,
                         "forbidden_reason": pb.forbidden_reason, "cautions": pb.caution, "red_flags": pb.red_flags,
                         "requires": pb.requires, "cyclical": pb.cyclical, "sources": pb.sources},
            "metrics": {k: result(v) for k, v in eng.compute_many(HEADLINE, sid, a).items()},
        }, a)


@app.get("/api/company/{code}/prices")
def prices(code: str, as_of: str = AS_OF, exchange: str = "NSE", adjusted: bool = True, start: dt.date | None = None):
    a = asof(as_of)
    with DB.reader_ctx() as r:
        sid = _sid(r, code, a, exchange)
        bars = r.prices(sid, a, exchange, start=start, adjusted=adjusted)
        if not bars and exchange == "NSE":
            exchange = "BSE"
            bars = r.prices(sid, a, exchange, start=start, adjusted=adjusted)
        cols = {"t": [], "o": [], "h": [], "l": [], "c": [], "v": [], "f": []}
        for b in bars:
            if b.close is None:
                continue
            cols["t"].append(b.trade_date.isoformat()); cols["o"].append(b.open); cols["h"].append(b.high)
            cols["l"].append(b.low); cols["c"].append(b.close); cols["v"].append(b.volume); cols["f"].append(b.factor)
        events = [dict(zip(["ex_date", "factor", "method", "agreement", "applied", "kind", "subject"], e))
                  for e in r.adjustment_events(sid, a, exchange)]
        return ok({"security_id": sid, "exchange": exchange, "adjusted": adjusted, "bars": cols,
                   "adjustments": events, "source": f"{exchange} bhavcopy (unadjusted), adjusted with confirmed events only"}, a)


@app.get("/api/company/{code}/timeline")
def timeline(code: str, as_of: str = AS_OF, exchange: str = "NSE"):
    a = asof(as_of)
    with DB.reader_ctx() as r:
        sid = _sid(r, code, a, exchange)
        return ok({"security_id": sid, "events": r.timeline(sid, a)}, a)


@app.get("/api/company/{code}/financials")
def financials(code: str, as_of: str = AS_OF, exchange: str = "NSE", period: str = "Q", basis: str = "auto"):
    a = asof(as_of)
    months = 3 if period.upper() == "Q" else 12
    cfg = load_line_items()
    with DB.reader_ctx() as r:
        sid = _sid(r, code, a, exchange)
        vals = r.financials(sid, a, basis=basis)
        rows: dict[str, dict] = {}
        periods: set = set()
        for v in vals:
            spec = cfg.get(v.line_item, {})
            if spec.get("kind") == "flow" and v.months != months:
                continue
            if spec.get("statement") == "ownership":
                continue
            row = rows.setdefault(v.line_item, {"line_item": v.line_item, "statement": spec.get("statement"),
                                                "kind": spec.get("kind"), "cells": {}})
            key = v.period_end.isoformat()
            periods.add(key)
            row["cells"][key] = {"value": v.value, "concept": v.concept, "source_rank": v.source_rank,
                                 "filing_id": v.filing_id, "known_at": v.known_at, "restated": v.is_restated,
                                 "basis": v.basis, "low_confidence": v.concept.startswith("html:")}
        order = list(cfg)
        ordered = sorted(rows.values(), key=lambda x: order.index(x["line_item"]) if x["line_item"] in order else 999)
        return ok({"security_id": sid, "period": period.upper(), "periods": sorted(periods, reverse=True)[:16],
                   "rows": ordered, "note": "INR; consolidated where reported, else standalone; latest-known version of each value"}, a)


@app.get("/api/company/{code}/ownership")
def ownership(code: str, as_of: str = AS_OF, exchange: str = "NSE"):
    a = asof(as_of)
    with DB.reader_ctx() as r:
        sid = _sid(r, code, a, exchange)
        return ok({"security_id": sid, "quarters": r.ownership(sid, a, 16),
                   "pledge": [dict(zip(["as_on", "promoter_pct", "pledged_pct_of_promoter", "pledged_pct_of_total",
                                        "shares_pledged", "known_at"], p)) for p in r.pledge(sid, a)[:12]],
                   "note": "category detail before Sep-2021 and pledge history before the first snapshot are not served by the exchange"}, a)


@app.get("/api/company/{code}/dupont")
def dupont(code: str, as_of: str = AS_OF, exchange: str = "NSE"):
    a = asof(as_of)
    with DB.reader_ctx() as r:
        sid = _sid(r, code, a, exchange)
        m = M.Engine(r).compute_many(["roe", "roa", "net_margin", "revenue_ttm", "pat_ttm"], sid, a)
        out = {k: result(v) for k, v in m.items()}
        roe, roa, nm = m["roe"], m["roa"], m["net_margin"]
        if all(isinstance(x, Value) for x in (roe, roa, nm)) and nm.value and roa.value:
            out["asset_turnover"] = {"state": "value", "value": roa.value / nm.value, "unit": "x",
                                     "formula": "ROA / net margin = revenue / assets"}
            out["equity_multiplier"] = {"state": "value", "value": roe.value / roa.value, "unit": "x",
                                        "formula": "ROE / ROA = assets / equity"}
        else:
            for k, f in (("asset_turnover", "revenue / assets"), ("equity_multiplier", "assets / equity")):
                out[k] = {"state": "na", "missing": [x for x in ("roe", "roa", "net_margin") if not isinstance(m[x], Value)],
                          "reason": f"{f}: needs ROE, ROA and net margin"}
        return ok({"security_id": sid, "tree": out}, a)


CASH_RIVER = {
    "income": ["revenue_from_operations", "other_income"],
    "costs": ["cost_of_materials", "purchases_of_traded_goods", "change_in_inventories", "employee_expense",
              "other_expenses", "depreciation_amortisation", "finance_costs", "exceptional_items"],
    "below": ["profit_before_tax", "tax_expense", "profit_after_tax"],
    "bank": ["interest_earned", "interest_expended", "bank_provisions"],
}


@app.get("/api/company/{code}/cashriver")
def cashriver(code: str, as_of: str = AS_OF, exchange: str = "NSE"):
    """The latest full year's income statement as flows. Missing lines are returned as null, never as zero."""
    a = asof(as_of)
    items = [x for v in CASH_RIVER.values() for x in v]
    with DB.reader_ctx() as r:
        sid = _sid(r, code, a, exchange)
        vals = [v for v in r.financials(sid, a, items) if v.months == 12]
        years = sorted({v.period_end for v in vals}, reverse=True)
        out = []
        for y in years[:6]:
            row = {v.line_item: {"value": v.value, "concept": v.concept, "filing_id": v.filing_id, "known_at": v.known_at}
                   for v in vals if v.period_end == y}
            out.append({"period_end": y, "items": {k: row.get(k) for k in items}})
        return ok({"security_id": sid, "years": out, "groups": CASH_RIVER}, a)


@app.get("/api/company/{code}/peers")
def peers(code: str, as_of: str = AS_OF, exchange: str = "NSE", limit: int = 24):
    a = asof(as_of)
    cols = ["market_cap", "pe", "pb", "roe", "ebitda_margin", "revenue_growth"]
    with DB.reader_ctx() as r:
        sid = _sid(r, code, a, exchange)
        eng = M.Engine(r)
        me = eng.resolution(sid, a).playbook.id
        prof = r.profile(sid, a)
        ids = [sid] + [p for p in (r.sector_peers(prof["sector"], a, 300) if prof["sector"] else []) if p != sid]
        rows = []
        for p in ids:
            if len(rows) >= limit:
                break
            res = eng.resolution(p, a)
            if res.playbook.id != me:
                continue
            m = eng.compute_many(cols, p, a)
            if p != sid and not any(isinstance(v, Value) for v in m.values()):
                continue
            rows.append({"security_id": p, "name": r.display_name(p, r.profile(p, a)["name"]), "self": p == sid,
                         "metrics": {k: result(v) for k, v in m.items()}})
        return ok({"security_id": sid, "playbook": me, "sector": prof["sector"], "columns": cols, "rows": rows,
                   "note": "peers = same sector label and same resolved playbook, evaluated at the same as-of"}, a)


@app.get("/api/company/{code}/changes")
def changes(code: str, as_of: str = AS_OF, exchange: str = "NSE", days: int = 91):
    """What changed between as_of - days and as_of: metric moves and the events that became public in between."""
    a = asof(as_of)
    before = AsOf.end_of(a.date_ist - dt.timedelta(days=days))
    with DB.reader_ctx() as r:
        sid = _sid(r, code, a, exchange)
        eng = M.Engine(r)
        now, then = eng.compute_many(HEADLINE, sid, a), eng.compute_many(HEADLINE, sid, before)
        moves = []
        for k in HEADLINE:
            n, t = now[k], then[k]
            moves.append({"metric": k, "now": result(n), "then": result(t),
                          "delta": (n.value - t.value) if isinstance(n, Value) and isinstance(t, Value) else None})
        ev = [e for e in r.timeline(sid, a) if e["known_at"] and e["known_at"] > before.ts]
        return ok({"security_id": sid, "since": before.ts, "metrics": moves, "events": ev}, a)


# ---- valuation lab -------------------------------------------------------------------------------------------------
@app.get("/api/company/{code}/valuation")
def valuation_methods(code: str, as_of: str = AS_OF, exchange: str = "NSE"):
    a = asof(as_of)
    with DB.reader_ctx() as r:
        sid = _sid(r, code, a, exchange)
        lab = Lab(M.Engine(r))
        m = lab.methods(sid, a)
        templates = {meth: {k: plain(v.value) for k, v in template_assumptions(meth, m["playbook"]).items()}
                     for meth in REQUIRED if meth not in m["forbidden"]}
        return ok({"security_id": sid, **m, "required": REQUIRED, "templates": templates,
                   "note": "template values are conventional starting points, not recommendations; confirm or edit"}, a)


@app.post("/api/company/{code}/valuation/run")
def valuation_run(code: str, as_of: str = AS_OF, exchange: str = "NSE", body: dict = Body(...)):
    a = asof(as_of)
    method = body.get("method")
    assumptions = body.get("assumptions") or {}
    with DB.reader_ctx() as r:
        sid = _sid(r, code, a, exchange)
        lab = Lab(M.Engine(r))
        try:
            v = lab.run(method, sid, a, assumptions)
        except ForbiddenError as e:
            return ok({"state": "forbidden", "method": method, "playbook": e.playbook, "rule": e.rule, "reason": e.why}, a)
        except (V.ValuationError, KeyError) as e:
            return ok({"state": "na", "method": method, "reason": str(e)}, a)
        return ok({"state": "value", "valuation": v}, a)


# ---- showcase (home page): real numbers from the database, cached per as-of day ------------------------------------
MARQUEE = ["RELIANCE", "TCS", "HDFCBANK", "INFY", "ITC", "LT"]


def _streak(r: PitReader, code: str, a: AsOf, points: int = 360) -> dict | None:
    sid = r.resolve(code, a, "NSE")
    if not sid:
        return None
    bars = [b for b in r.prices(sid, a, "NSE") if b.close]
    if len(bars) < 50:
        return None
    step = max(1, len(bars) // points)
    pick = bars[::step] + ([bars[-1]] if (len(bars) - 1) % step else [])
    return {"code": code, "name": r.display_name(sid, r.profile(sid, a)["name"]), "security_id": sid,
            "from": bars[0].trade_date, "to": bars[-1].trade_date, "sessions": len(bars),
            "first": bars[0].close, "last": bars[-1].close,
            "t": [b.trade_date for b in pick], "c": [b.close for b in pick],
            "source": "NSE bhavcopy, adjusted for confirmed splits/bonuses only"}


@app.get("/api/showcase")
def showcase(as_of: str = AS_OF, refresh: bool = False):
    a = asof(as_of)
    CACHE.mkdir(parents=True, exist_ok=True)
    f = CACHE / f"showcase_{a.date_ist.isoformat()}.json"
    if f.exists() and not refresh:
        return JSONResponse(json.loads(f.read_text(encoding="utf-8")))
    with DB.reader_ctx() as r:
        eng = M.Engine(r)
        years = [dt.date(y, 6, 30) for y in range(1999, a.date_ist.year + 1)]
        demo_rules = []
        for code in ("HDFCBANK", "ULTRACEMCO", "INFY"):
            sid = r.resolve(code, a, "NSE")
            if not sid:
                continue
            res = eng.resolution(sid, a)
            m = eng.compute_many(["ev_ebitda", "ebitda_margin", "pe", "pb", "roe", "debt_to_equity"], sid, a)
            demo_rules.append({"code": code, "name": r.display_name(sid, r.profile(sid, a)["name"]),
                               "playbook": res.playbook.id, "label": res.playbook.label,
                               "metrics": {k: result(v) for k, v in m.items()}})
        ghosts_on = dt.date(2008, 1, 1)
        payload = {
            "as_of": a.ts.isoformat(), "demo": DEMO_MODE, "disclaimer": DISCLAIMER,
            "stats": r.stats(a), "watermark": r.watermark(a),
            "strata": r.index_strata("NIFTY500", a, years),
            "ghosts": {"on": ghosts_on, "members": r.gone_members("NIFTY500", ghosts_on, a, 60)},
            "streaks": [s for s in (_streak(r, c, a) for c in MARQUEE) if s],
            "rules": demo_rules,
        }
    body = plain(payload)
    f.write_text(json.dumps(body), encoding="utf-8")
    return JSONResponse(body)


@app.get("/api/health")
def health():
    return {"ok": True, "demo": DEMO_MODE}
