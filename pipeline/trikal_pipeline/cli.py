"""`trikal` command line. Every command is idempotent and safe to re-run."""

from __future__ import annotations

import datetime as dt
import sys
import time

import typer

from trikal_pipeline.http import Fetcher
from trikal_pipeline.raw import RawStore

app = typer.Typer(no_args_is_help=True, add_completion=False)

EARLIEST = {"NSE": dt.date(1994, 11, 1), "BSE": dt.date(2007, 1, 1)}


def _d(s: str | None, default: dt.date) -> dt.date:
    return dt.date.fromisoformat(s) if s else default


@app.command("fetch-prices")
def fetch_prices(
    exchange: str = typer.Argument(..., help="NSE or BSE"),
    start: str = typer.Option(None, help="YYYY-MM-DD (default: earliest known file)"),
    end: str = typer.Option(None, help="YYYY-MM-DD (default: today)"),
    newest_first: bool = typer.Option(True, help="Fetch recent days first"),
    retry_errors: bool = typer.Option(True),
) -> None:
    """Download daily bhavcopies into the raw zone. Skips days already answered (ok / not_found)."""
    from trikal_pipeline.sources import bhav

    exchange = exchange.upper()
    s, e = _d(start, EARLIEST[exchange]), _d(end, dt.date.today())
    raw, fetcher = RawStore(), Fetcher()
    done = raw.done_partitions(bhav.SOURCE_KEY[exchange])
    days = [d for d in bhav.daterange(s, e) if d.isoformat() not in done]
    if newest_first:
        days.reverse()
    typer.echo(f"{exchange}: {len(days)} days to fetch ({s} .. {e}); {len(done)} already answered")
    stats = {"ok": 0, "not_found": 0, "error": 0}
    t0 = time.monotonic()
    for i, d in enumerate(days, 1):
        stats[bhav.fetch_day(fetcher, raw, exchange, d)] += 1
        if i % 100 == 0 or i == len(days):
            rate = i / max(1e-9, time.monotonic() - t0)
            typer.echo(f"  {exchange} {i}/{len(days)} at {d} {stats} ({rate:.2f} d/s)")
            sys.stdout.flush()
    fetcher.close()


@app.command("init")
def init() -> None:
    """Create/upgrade the canonical schema."""
    from trikal_core.db import connect, db_path, init_schema

    con = connect()
    init_schema(con)
    typer.echo(f"schema ready at {db_path()}")


@app.command("load-prices")
def load_prices(exchange: str = typer.Argument(..., help="NSE or BSE")) -> None:
    """Stage every fetched bhavcopy and rebuild price_eod for the exchange."""
    from trikal_core.db import connect, init_schema
    from trikal_pipeline.load_prices import load_exchange
    from trikal_pipeline.sources import bhav

    exchange = exchange.upper()
    staged = bhav.stage_all(RawStore(), exchange)
    typer.echo(f"staged: {staged}")
    con = connect()
    init_schema(con)
    t0 = time.monotonic()
    typer.echo(f"loaded rows by format: {load_exchange(con, exchange)} in {time.monotonic() - t0:.1f}s")


@app.command("fetch-masters")
def fetch_masters() -> None:
    """Fetch NSE symbol-change, name-change, delisted and equity-list files (dated raw snapshots)."""
    from trikal_pipeline.sources import nse_ref

    typer.echo(nse_ref.fetch_masters(Fetcher(), RawStore()))


@app.command("fetch-corp-actions")
def fetch_corp_actions(start: str = typer.Option("1995-01-01"), end: str = typer.Option(None)) -> None:
    """Fetch the NSE corporate-actions feed month by month (recent months always refreshed)."""
    from trikal_pipeline.sources import nse_ref

    typer.echo(nse_ref.fetch_corp_actions(Fetcher(), RawStore(), _d(start, dt.date(1995, 1, 1)),
                                          _d(end, dt.date.today())))


@app.command("load-ref")
def load_ref() -> None:
    """Load NSE master files and corporate actions into canonical tables."""
    from trikal_core.db import connect, init_schema
    from trikal_pipeline.sources import nse_ref

    con, raw = connect(), RawStore()
    init_schema(con)
    typer.echo(f"masters: {nse_ref.load_masters(con, raw)}")
    typer.echo(f"corp actions: {nse_ref.load_corp_actions(con, raw)}")


@app.command("fetch-index")
def fetch_index() -> None:
    """Fetch Nifty constituent snapshots and every relevant NSE Indices press release (PDF)."""
    from trikal_core.db import connect, init_schema
    from trikal_pipeline.sources import nifty

    con, raw, fetcher = connect(), RawStore(), Fetcher()
    init_schema(con)
    typer.echo(f"snapshots: {list(nifty.fetch_snapshots(fetcher, raw))}")
    typer.echo(f"loaded snapshot rows: {nifty.load_snapshots(con, raw)}")
    con.close()  # do not hold the DuckDB write lock during the long PDF crawl
    typer.echo(f"press releases: {nifty.fetch_press_pdfs(fetcher, raw)}")


@app.command("build")
def build() -> None:
    """Rebuild the security master and adjustment events from canonical inputs."""
    from trikal_core.db import connect, init_schema
    from trikal_pipeline import adjustments, calendar, security_master

    con = connect()
    init_schema(con)
    typer.echo(f"calendar: {calendar.build(con, RawStore())}")
    t0 = time.monotonic()
    typer.echo(f"security master: {security_master.build(con)} ({time.monotonic() - t0:.0f}s)")
    t0 = time.monotonic()
    typer.echo(f"adjustment events: {adjustments.build(con)} ({time.monotonic() - t0:.0f}s)")


@app.command("adjust")
def adjust() -> None:
    """Rebuild only the adjustment events (after a parser or rule change); the security master is untouched."""
    from trikal_core.db import connect
    from trikal_pipeline import adjustments

    con = connect()
    t0 = time.monotonic()
    typer.echo(f"adjustment events: {adjustments.build(con)} ({time.monotonic() - t0:.0f}s)")


@app.command("fetch-context")
def fetch_context(
    days: str = typer.Option("events", help="'events' (the Time Machine's historic days +/- 3), 'all', or YYYY-MM-DD:YYYY-MM-DD"),
) -> None:
    """Fetch the Wikipedia context layer (world + India events by day) into the raw zone, then load it."""
    import datetime as dt

    from trikal_core.db import connect, init_schema
    from trikal_pipeline.http import Fetcher
    from trikal_pipeline.sources import wiki_context

    today = dt.date.today()
    if days == "all":
        start, end = dt.date(1994, 11, 3), today
    elif ":" in days:
        a, b = days.split(":")
        start, end = dt.date.fromisoformat(a), dt.date.fromisoformat(b)
    else:
        start = end = None
    span = [start + dt.timedelta(n) for n in range((end - start).days + 1)] if start else []
    if not span:  # the Time Machine's built-in days (keep in sync with TM_EVENTS in api/trikal_api/app.py)
        events = ["1994-11-03", "1998-05-12", "2000-02-29", "2004-05-17", "2006-05-22", "2008-01-21", "2008-10-24",
                  "2009-05-18", "2013-08-28", "2014-05-16", "2016-06-24", "2016-11-09", "2019-09-20", "2020-03-23",
                  "2021-02-01", "2023-01-27", "2024-06-04"]
        span = sorted({dt.date.fromisoformat(e) + dt.timedelta(k) for e in events for k in range(-3, 2)})
    years = sorted({d.year for d in span} | set(range(1994, today.year + 1)))
    raw = RawStore()
    f = Fetcher(timeout=30, retries=2)
    try:
        typer.echo(f"fetched: {wiki_context.fetch(f, raw, span, years)}")
    finally:
        f.close()
    con = connect()
    init_schema(con)
    typer.echo(f"loaded: {wiki_context.load(con, raw)}")


@app.command("fetch-macro")
def fetch_macro(only: str = typer.Option("", help="comma-separated series ids (default: all in config/macro_series.yaml)")) -> None:
    """Fetch macro series (FRED, MOSPI, World Bank Pink Sheet) into the raw zone, then load macro_obs."""
    from trikal_core.db import connect, init_schema
    from trikal_pipeline.sources import macro

    raw = RawStore()
    typer.echo(f"fetched: {macro.fetch(raw, [x for x in only.split(',') if x] or None)}")
    con = connect()
    init_schema(con)
    typer.echo(f"loaded: {macro.load(con, raw)}")


@app.command("show")
def show(
    code: str,
    as_of: str = typer.Option("NOW", "--as-of", help="YYYY-MM-DD | ISO timestamp | NOW"),
    exchange: str = typer.Option("NSE"),
    days: int = typer.Option(10),
) -> None:
    """Print a security as the terminal would have seen it on a date."""
    from trikal_core.db import connect
    from trikal_core.pit import PitReader
    from trikal_core.timeutil import AsOf

    a = AsOf.parse(as_of)
    r = PitReader(connect(read_only=True))
    sid = r.resolve(code, a, exchange)
    typer.echo(f"AS OF {a}   {exchange}:{code.upper()} -> {sid}")
    if not sid:
        raise typer.Exit(1)
    for row in r.listings(sid, a):
        typer.echo(f"  listing {row}")
    for ev in r.adjustment_events(sid, a, exchange)[-6:]:
        typer.echo(f"  adj {ev}")
    bars = r.prices(sid, a, exchange)
    for b in bars[-days:]:
        typer.echo(f"  {b.trade_date}  close={b.close:.2f}  factor={b.factor:.6f}  vol={b.volume:.0f}")


@app.command("build-index")
def build_index(index_code: str = typer.Argument("NIFTY500")) -> None:
    """Reconstruct point-in-time membership of an index from NSE Indices press releases."""
    from trikal_core.db import connect, init_schema
    from trikal_pipeline import index_history
    from trikal_pipeline.sources import nifty

    con, raw = connect(), RawStore()
    init_schema(con)
    nifty.load_press_index(con, raw)
    typer.echo(index_history.rebuild(con, raw, index_code.upper()))


@app.command("coverage")
def coverage(out: str = typer.Option("docs/reports/coverage.md", help="Markdown output path")) -> None:
    """Write the data coverage & quality report."""
    from pathlib import Path

    from trikal_core.db import connect
    from trikal_pipeline.coverage import report

    text = report(connect(read_only=True))
    Path(out).parent.mkdir(parents=True, exist_ok=True)
    Path(out).write_text(text, encoding="utf-8")
    typer.echo(f"wrote {out}")


@app.command("fetch-m2")
def fetch_m2(symbols_file: str = typer.Option("data/pilot_symbols.txt"),
             since: str = typer.Option("2011-04-01", help="earliest period end for XBRL documents")) -> None:
    """Overnight raw download for M2: per-company filing lists, then XBRL result documents (resumable)."""
    from trikal_pipeline.sources.nse_company import run_overnight

    run_overnight(symbols_file, since)


@app.command("parse-financials")
def parse_financials(limit: int = typer.Option(0, help="parse at most N new documents (0 = all)")) -> None:
    """Parse downloaded results documents into filing / fact_financial_all, then rebuild fact_financial."""
    from trikal_core.db import connect, init_schema
    from trikal_pipeline import load_financials as lf

    con, raw = connect(), RawStore()
    init_schema(con)
    t0 = time.monotonic()
    for kind in lf.KINDS:
        typer.echo(f"{kind}: {lf.load_results(con, raw, kind, limit=limit or None)}  ({time.monotonic() - t0:.0f}s)")
    typer.echo(f"fact_financial rows (value changes only): {lf.build_financials(con):,}")


@app.command("parse-ownership")
def parse_ownership() -> None:
    """Load shareholding patterns (list summary + SHP XBRL), pledge snapshots and sector classification."""
    from trikal_core.db import connect, init_schema
    from trikal_pipeline import classification, shp

    con, raw = connect(), RawStore()
    init_schema(con)
    typer.echo(f"shareholding: {shp.load_shareholding(con, raw)}")
    typer.echo(f"pledge: {shp.load_pledge(con, raw)}")
    typer.echo(f"classification: {classification.build(con)}")


@app.command("check-financials")
def check_financials() -> None:
    """Run accounting-identity checks over parsed financials and report pass rates."""
    from trikal_core.db import connect
    from trikal_pipeline import quality

    for name, n, ok, share in quality.run(connect()):
        typer.echo(f"{name:45s} checked={n:6d} ok={ok:6d} pass={'n/a' if share is None else f'{share:.1%}'}")


@app.command("refresh-m2")
def refresh_m2() -> None:
    """Parse everything downloaded so far, run the identity checks and rewrite the coverage report."""
    from trikal_core.db import connect, init_schema
    from trikal_pipeline import classification, coverage as cov, quality, shp
    from trikal_pipeline import load_financials as lf

    con, raw = connect(), RawStore()
    init_schema(con)
    for kind in lf.KINDS:
        typer.echo(f"{kind}: {lf.load_results(con, raw, kind)}")
    typer.echo(f"fact_financial rows: {lf.build_financials(con):,}")
    typer.echo(f"shareholding: {shp.load_shareholding(con, raw)}")
    typer.echo(f"pledge: {shp.load_pledge(con, raw)}")
    typer.echo(f"classification: {classification.build(con)}")
    for name, n, ok, share in quality.run(con):
        typer.echo(f"  check {name}: {ok}/{n} ({'n/a' if share is None else f'{share:.1%}'})")
    from pathlib import Path

    Path("docs/reports").mkdir(parents=True, exist_ok=True)
    Path("docs/reports/coverage.md").write_text(cov.report(con), encoding="utf-8")
    typer.echo("wrote docs/reports/coverage.md")


@app.command("analyze")
def analyze(
    code: str,
    as_of: str = typer.Option("NOW", "--as-of", help="YYYY-MM-DD | NOW"),
    exchange: str = typer.Option("NSE"),
) -> None:
    """Show a company's sector playbook, which metrics/methods it allows, and the metrics with their reasons."""
    from trikal_analytics import metrics as M
    from trikal_analytics.lab import Lab
    from trikal_analytics.result import Forbidden, NotAvailable, Undefined, Value
    from trikal_core.db import connect
    from trikal_core.pit import PitReader
    from trikal_core.timeutil import AsOf

    a = AsOf.parse(as_of)
    r = PitReader(connect(read_only=True))
    sid = r.resolve(code, a, exchange)
    if not sid:
        typer.echo(f"{code}: not found on {exchange} as of {a}")
        raise typer.Exit(1)
    eng = M.Engine(r)
    res = eng.resolution(sid, a)
    prof = r.profile(sid, a)
    typer.echo(f"AS OF {a}   {prof['name']}  ({sid})")
    typer.echo(f"sector label: {prof['sector']} [{prof['sector_method']}, {prof['sector_confidence']}]   reporting family: {prof['family']}")
    typer.echo(f"playbook: {res.playbook.id}  via {res.how} (confidence {res.confidence}); overlays {list(res.playbook.overlays) or '-'}")
    m = Lab(eng).methods(sid, a)
    typer.echo(f"valuation primary: {m['primary']}  secondary: {m['secondary']}  not primary: {m['not_primary']}")
    typer.echo(f"forbidden valuation methods ({len(m['forbidden'])}; metrics are checked individually below): {', '.join(m['forbidden'][:12])}{' ...' if len(m['forbidden']) > 12 else ''}")
    if m["reason"]:
        typer.echo(f"  why: {m['reason']}")
    show = ["revenue_ttm", "ebitda_margin", "pat_ttm", "market_cap", "pe", "pb", "ev_ebitda", "roe", "roce", "debt_to_equity", "net_debt_ebitda"]
    for k, v in eng.compute_many(show, sid, a).items():
        if isinstance(v, Value):
            typer.echo(f"  {k:16s} {v.value:>18,.4f} {v.unit}   {'; '.join(v.warnings)[:70]}")
        elif isinstance(v, Forbidden):
            typer.echo(f"  {k:16s} FORBIDDEN by {v.playbook}")
        elif isinstance(v, Undefined):
            typer.echo(f"  {k:16s} not meaningful: {v.reason}")
        elif isinstance(v, NotAvailable):
            typer.echo(f"  {k:16s} n/a: missing {', '.join(v.missing)} {v.reason}")


@app.command("raw-status")
def raw_status() -> None:
    """Summarise the raw zone fetch log."""
    for row in RawStore().status_counts():
        typer.echo("  ".join(str(x) for x in row))


if __name__ == "__main__":
    app()
