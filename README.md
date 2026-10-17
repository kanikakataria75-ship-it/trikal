# TRIKAL

Point-in-time equity research terminal for Indian equities (NSE + BSE). Personal research use only. It
is not investment advice and gives no ratings or target prices.

- Build spec: [PROMPT.md](PROMPT.md)
- Design docs: [docs/](docs/). Start with [ARCHITECTURE](docs/ARCHITECTURE.md), [FORMULAS](docs/FORMULAS.md) and [DECISIONS](docs/DECISIONS.md).
- Progress: [CHANGELOG.md](CHANGELOG.md). Latest data coverage: run `trikal coverage`, which writes `docs/reports/coverage.md`.

## Setup (Windows, no Docker needed for M1)

```bash
py -m venv .venv
.venv/Scripts/python -m pip install -e ".[dev]"
.venv/Scripts/trikal init
```

Data lives in `data/` (git-ignored):
- `raw/`: immutable downloads plus `index.sqlite`, the fetch log
- `staging/`: extracted CSVs and PDF text
- `trikal.duckdb`: the canonical store

## Pipeline (each command is idempotent)

```bash
.venv/Scripts/trikal fetch-prices NSE        # daily bhavcopies 1994 -> today (~3 h first time, polite rate)
.venv/Scripts/trikal fetch-prices BSE        # 2007 -> today
.venv/Scripts/trikal fetch-masters           # symbol/name changes, delistings, equity list
.venv/Scripts/trikal fetch-corp-actions      # NSE corporate actions 1995 -> today
.venv/Scripts/trikal fetch-index             # Nifty constituent files + all NSE Indices press releases
.venv/Scripts/trikal load-prices NSE
.venv/Scripts/trikal load-prices BSE
.venv/Scripts/trikal load-ref
.venv/Scripts/trikal build                   # calendar, security master, adjustment events
.venv/Scripts/trikal build-index NIFTY500    # point-in-time membership reconstruction
.venv/Scripts/trikal coverage                # data coverage & quality report
```

## Fundamentals & ownership (M2)

The raw download is long (about 140,000 documents for the pilot universe at one request per second, 1.5–2 days).
It is resumable and runs detached:

```bash
run_m2_overnight.cmd                           # double-click (or run in a terminal). Keep the laptop plugged in.
```
```bash
.venv/Scripts/trikal refresh-m2                # parse whatever has arrived, run identity checks, rewrite the coverage report
```

`refresh-m2` can be run at any time, including while the download is still going. Individual steps are
`parse-financials`, `parse-ownership` and `check-financials`. The progress and pass rates are at the end of
`docs/reports/coverage.md`.

## Look at a stock as of any date

```bash
.venv/Scripts/trikal show TCS --as-of 2018-05-30
.venv/Scripts/trikal show TCS --as-of 2018-06-01
```

## Terminal and home page (M3)

Two processes: the read API (every endpoint requires `as_of`) and the web app.

```
.venv\Scripts\python.exe -m uvicorn trikal_api.app:app --app-dir api --port 8000
npm --prefix web install      # first time only
npm --prefix web run dev       # http://localhost:3000  (terminal: /terminal)
```

The home page's Time Machine also reads the Wikipedia context layer: `trikal fetch-context` (see DATA_SOURCES §11).
Stop the API before any pipeline command that writes the database (`build`, `adjust`, `refresh-m2`, `fetch-context`).

## Tests

```bash
.venv/Scripts/python -m pytest -q
```

They include look-ahead (point-in-time) tests that fail if any future information leaks into a past view.
