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


@app.command("raw-status")
def raw_status() -> None:
    """Summarise the raw zone fetch log."""
    for row in RawStore().status_counts():
        typer.echo("  ".join(str(x) for x in row))


if __name__ == "__main__":
    app()
