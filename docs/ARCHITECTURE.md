# TRIKAL — Architecture (M0 draft)

Status: **DRAFT for review**. Nothing here is built yet. Decisions marked `ADR-n` are recorded in [DECISIONS.md](DECISIONS.md); items marked **[Q]** are waiting on the owner (see [RISKS.md](RISKS.md) § Open questions).

---

## 1. System at a glance

```
             ┌──────────────────────────── SOURCES ─────────────────────────────┐
             │ NSE/BSE archives+JSON · AMFI/AMC files · RBI · MOSPI · FRED ·    │
             │ GDELT · World Bank/IMF · PIB/DGTR/SEBI/CEA/PPAC · rating agencies │
             └───────────────┬──────────────────────────────────────────────────┘
                             │  fetchers (rate-limited, cached, robots-aware)
                             ▼
  /pipeline   RAW zone  ──►  STAGING  ──►  CANONICAL (bitemporal Postgres)  ──►  Parquet snapshots
  (Dagster)   immutable      parsed,       entity-resolved, PIT, lineage          (DuckDB, backtests)
              content-hash   validated
                             │
  /analytics  metric registry · playbook rule engine · valuation · forensics · sensitivities · backtest
  /kasauti    scoring · report card · LLM extraction · chat/debate agents (read-only tool layer)
                             │
  /api        FastAPI — every endpoint takes `as_of`; REST + WebSocket (live ticks / alerts)
                             │
  /web        Next.js terminal — dockview workspace, command bar, Time Spine, R3F scenes
```

### Repository layout (monorepo)

```
/pipeline      Python package `trikal_pipeline`   (Dagster definitions, fetchers, parsers, loaders)
/analytics     Python package `trikal_analytics`  (pure functions over PIT frames; no I/O)
/kasauti       Python package `trikal_kasauti`
/core          Python package `trikal_core`       (shared: PIT data-access layer, types, ids, lineage)  ← added, ADR-004
/api           FastAPI app
/web           Next.js app
/config        playbooks/*.yaml · scores/kasauti_vN.yaml (frozen) · sources.yaml (source registry)
/docs          ARCHITECTURE · DATA_SOURCES · FORMULAS · SECTOR_PLAYBOOKS · UI_SPEC · DECISIONS · RISKS
/data          (git-ignored) raw/ staging/ parquet/ — mount point, configurable
/tests         cross-package PIT / look-ahead / golden-file suites
```

Python tooling: `uv` workspace, Python 3.12, `ruff`, `mypy --strict` on `core` and `analytics`, `pytest` + `hypothesis`. JS tooling: `pnpm`, TypeScript strict, `vitest`, Playwright (visual regression).

---

## 2. The time model — the core of the whole product

TRIKAL tracks **three** timestamps per fact, not two. The third is what makes results reproducible.

| Column | Meaning | Example (TCS Q3 FY25 revenue) |
|---|---|---|
| `valid_from` / `valid_to` (or `period_start` / `period_end`) | The period or interval the fact describes | 2024-10-01 → 2024-12-31 |
| `known_at` | When it became **public** (exchange broadcast timestamp, IST, tz-aware) | 2025-01-09 21:39:43 IST |
| `recorded_at` | When **TRIKAL** ingested it (system/transaction time) | 2026-10-12 03:10 UTC |

- `as_of` queries filter `known_at <= as_of`. This is the PIT guarantee.
- `recorded_at` lets us answer "what did TRIKAL's database say on date X" — needed to reproduce a past KASAUTI run exactly and to audit late-arriving or corrected source data. Backfilled history has `recorded_at` ≫ `known_at`; that is expected and is *not* look-ahead, because the query key is `known_at`.
- **Restatements / revisions** never update in place. A restated figure is a new row with the same `(entity, metric, period, basis)` and a later `known_at`; `as_of` picks the latest row known at that time. The earlier row stays.
- **Unknown publication time.** If a source gives only a date, `known_at` = that date at 23:59:59 IST and `known_at_precision = 'day'`. If a source gives *no* publication date (e.g. some old PDFs), we use a documented, conservative lag rule (e.g. the statutory deadline for that filing type) and set `known_at_precision = 'imputed'`. Imputed rows are shown with a marker in the UI and can be excluded from backtests with one flag.

### 2.1 Tradability convention (backtests)

Knowing a fact and being able to trade on it are different things. A result broadcast at 21:39 on day D can only be acted on at the open of D+1. The backtest engine uses `tradable_from = next_session_open(known_at)` and executes at the open (or VWAP proxy) of that session, never at the close of D. This convention is fixed in ADR-003 and applies to every signal.

### 2.2 Enforcing PIT in code, not by discipline

- **One door.** Analytics and KASAUTI code cannot query tables directly. They go through `trikal_core.pit.PitReader`, whose every method needs an `AsOf` value (a tz-aware timestamp newtype). There is no default `as_of=now`; the API layer supplies `now()` explicitly for live views.
- **Canonical tables are not granted to the analytics DB role.** Only views/functions that take `as_of` are. A raw `SELECT` from analytics code fails at the database level.
- **Look-ahead test suite** (runs in CI on every commit):
  1. *Canary facts.* Fixtures insert sentinel facts with `known_at` = as_of + 1 second; any query result that contains a sentinel fails the test.
  2. *Property tests* (hypothesis): for random entities and random `as_of`, every row returned satisfies `known_at <= as_of`, recursively through derived metrics. Derived values carry the max `known_at` of their inputs.
  3. *Replay test.* Recompute a KASAUTI snapshot for date D twice: once from the full database with `as_of=D`, once from a database truncated to `known_at <= D`. The outputs must match bit-for-bit.
  4. *Corporate-action leak test.* An adjusted price series as of D must not reflect a split whose announcement was after D (see §4.3).

---

## 3. Storage

### 3.1 Zones

| Zone | Store | Rule |
|---|---|---|
| **raw** | Content-addressed files on disk (`/data/raw/<source>/<yyyy>/<mm>/<sha256>.<ext>`) + `raw_object` table (url, fetched_at, http headers, sha256, size) | Immutable. Never edited, never deleted. Re-fetches that produce identical bytes are de-duplicated by hash. |
| **staging** | Postgres schema `stg` | Parsed 1:1 from a raw object, typed, validated. Re-buildable from raw at any time. |
| **canonical** | Postgres schema `pit` (bitemporal) + TimescaleDB hypertables for prices | Entity-resolved to ISIN/company id; the only zone the app reads. |
| **analytics** | Parquet (partitioned by date/entity) read by DuckDB | Derived snapshots for backtests and the screener. Always regenerated from canonical; tagged with the `recorded_at` watermark they were built from. |

### 3.2 Canonical model (core tables, abridged)

```
security           (security_id PK, isin, instrument_type, face_value, listing_date, status)  -- ISIN is the key; security_id is surrogate to survive ISIN changes on corp actions
company            (company_id PK, cin, legal_name, incorporation_date)
security_company   (security_id, company_id, valid_from, valid_to, known_at)
listing            (security_id, exchange, symbol_or_code, series, valid_from, valid_to, known_at, source)   -- symbol/code history
company_name_hist  (company_id, name, valid_from, valid_to, known_at, source)
lineage_event      (event_id, type: merger|demerger|amalgamation|name_change|isin_change|delisting|relisting|suspension,
                    from_ids[], to_ids[], ratio, record_date, effective_date, known_at, source_doc_id)
price_eod          (security_id, exchange, trade_date, o,h,l,c,last,prev_close, volume, turnover, trades, delivery_qty, source_doc_id)   -- UNADJUSTED only, hypertable
corp_action        (security_id, type, ex_date, record_date, ratio_num, ratio_den, cash_amount, announced_at (=known_at), source_doc_id)
index_membership   (index_code, security_id, valid_from, valid_to, known_at, weight?, source_doc_id, confidence)
classification     (company_id, scheme: NSE_IIC|BSE|TRIKAL_PLAYBOOK, level, code, valid_from, valid_to, known_at, method: official|reconstructed, confidence)
fact_financial     (company_id, statement, line_item_id, basis: standalone|consolidated, period_type: Q|H|9M|FY,
                    period_end, value, unit, currency, known_at, recorded_at, is_restated, source_doc_id, source_locator, xbrl_concept)
shareholding       (company_id, period_end, category, sub_category, holder_name?, shares, pct, pledged_shares, known_at, source_doc_id)
mf_holding         (scheme_id, isin, period_end, qty, mkt_value, pct_nav, known_at, source_doc_id)
event              (event_id, kind, entity refs[], event_time, known_at, payload jsonb, source_doc_id)   -- announcements, ratings, policy, geo
extracted_fact     (id, source_doc_id, page, char_start, char_end, quote, schema_name, payload jsonb, model, prompt_hash,
                    confidence, review_status, known_at = source_doc.known_at)
source_doc         (source_doc_id, raw_object_sha256, source_key, doc_type, url, published_at, known_at, known_at_precision)
```

Every canonical row has `source_doc_id` (and, for extracted text, a page/char span). That single foreign key is what powers the lineage hover in the UI (invariant 4).

### 3.3 Why these engines (ADR-001)
- **Postgres + TimescaleDB:** one boring, transactional home for bitemporal facts; Timescale only for `price_eod` and macro series (compression and continuous aggregates). ~5,500 securities × ~30 years × ~250 days ≈ 40M price rows: comfortably single-node.
- **DuckDB over Parquet:** cross-sectional scans for the screener and backtests (all stocks × all dates) run far faster than row-store Postgres and need no server.
- **No vector database in v1.** Concall/annual report retrieval uses Postgres full-text plus `pgvector` if needed — one fewer system.

---

## 4. Pipeline (`/pipeline`)

### 4.1 Orchestration — Dagster (ADR-002)
Dagster's software-defined assets with **daily partitions** match the domain (one bhavcopy per trading day, one shareholding filing per quarter). Built-in asset checks cover data quality; backfills are first-class. Prefect is fine too, but asset lineage in Dagster directly mirrors TRIKAL's own lineage idea.

Each source = `fetch` asset (→ raw) → `parse` asset (→ staging) → `load` asset (→ canonical) → asset checks. All idempotent: re-running a partition is a no-op if the raw hash is unchanged.

### 4.2 Fetcher rules
- A per-host token bucket (default ≤ 1 request/second for exchange sites, lower for small government sites) and exponential backoff.
- Conditional GET / content-hash to avoid re-downloading.
- `robots.txt` honoured, checked at start-up and cached daily.
- Every request logs to `raw_object` even when it fails (status code, size), so gaps are visible, not silent.
- **No fabricated fill.** A missing trading-day file is recorded as `missing` in a `source_coverage` table and surfaces in a coverage dashboard. Nothing is interpolated in canonical.

### 4.3 Corporate-action adjustment (invariant 7)
- Store **only unadjusted** prices plus `corp_action` events.
- Adjusted series computed on read: `adj_factor(t | as_of) = Π factors of actions with ex_date > t AND announced_at <= as_of`. So a rewind to 2020 shows prices adjusted for splits known by 2020 only, exactly what a 2020 terminal would show. (Corporate-action leak test, §2.2.)
- Factors: split/consolidation (FV ratio), bonus (`(a+b)/a`), rights (theoretical ex-rights price method), special dividends above a threshold (configurable, off by default; ordinary dividends are tracked for total-return series only), demerger (price-ratio method from the first post-demerger session of parent + spun-off entity, documented in FORMULAS.md).
- Per-share fundamentals (EPS, BVPS, DPS) adjusted by the same factor function.
- Total-return index per security (dividends reinvested at ex-date close) for backtests.

### 4.4 Entity resolution
- ISIN is the master key, but ISINs change (e.g. face-value change creates a new ISIN). `security_id` is a surrogate that persists across such changes via `lineage_event(isin_change)`.
- Pre-ISIN-era NSE bhavcopies (the old `cm*bhav` format lacks an ISIN column in early years) are joined via the symbol history built from NSE's symbol-change file + the delisted list + listing dates. Unresolvable rows are parked in `stg.unresolved` and reported. They are never guessed.
- NSE symbol ↔ BSE scrip code linkage via ISIN, in both bhavcopies (the current UDiFF format carries ISIN for both exchanges; verified, see DATA_SOURCES).

### 4.5 Fundamentals extraction ladder
1. **XBRL** (NSE/BSE filings, Ind AS and pre-Ind AS taxonomies). Preferred. Deterministic mapping from XBRL concept → TRIKAL `line_item_id`, kept in `/config/xbrl_map/`.
2. **Structured exchange JSON** (results detail endpoints), where XBRL is absent.
3. **PDF tables** (older results, annual reports) → table extraction + LLM-assisted mapping. Every value gets a page locator and `confidence`. Low-confidence values go to the human-review queue and are **excluded** from scoring until reviewed.
4. **Licensed vendor feed** (if the owner approves one, **[Q1]**) for deep history and full annual statements.

Results are filed in parts. Quarterly filings carry the P&L; half-yearly filings add the balance sheet and (since FY20) the cash-flow statement; full notes, segment detail and related-party data come from the annual report. The `fact_financial.period_type` + `basis` + `known_at` combination handles this without special cases.

---

## 5. Analytics (`/analytics`)

- **Pure functions over PIT frames.** No I/O. Inputs come from `PitReader`; outputs carry lineage (input fact ids + formula id) and `known_at = max(inputs.known_at)`.
- **Metric registry.** Every metric is declared once:
  ```python
  @metric(id="ev_ebitda", formula="FORMULAS.md#ev-ebitda", applies_to=Not(Financials), unit="x",
          undefined_when=[EbitdaNonPositive])
  ```
  Calling a metric for a company whose playbook forbids it raises `ForbiddenMetric`. The engine never returns a number for it (invariant 5). Results are a tagged union:
  - `Value(x, lineage)`
  - `Undefined(reason)`, e.g. P/E for a loss-maker. **Not** a negative number.
  - `NotAvailable(missing_inputs)`: data gap, shown as "n/a" with the missing input named.
  - `Forbidden(rule_id)`: the playbook disallows it; the UI shows the rule and why.
- **Playbook engine.** YAML playbooks in `/config/playbooks/`, schema-validated (pydantic) at start-up. A company maps to a playbook via `classification` (TRIKAL_PLAYBOOK scheme), PIT. Overlays (PSU, holdco, cyclical) stack on a base playbook. The resolution rules are in SECTOR_PLAYBOOKS.md.
- **Valuation Lab.** DCF (FCFF/FCFE), reverse DCF (solve for implied growth with a bracketed root-finder; report "no solution" honestly), multiples bands (own history + peers, both always), SOTP with listed-subsidiary look-through (market values PIT), residual income / justified P/B, DDM, NAV. Scenario objects carry explicit assumptions + probabilities. Output is always a **range**.
- **Backtest engine.** Event-driven over DuckDB snapshots; uses the tradability convention (§2.1); costs = STT + exchange txn + SEBI fee + stamp duty + GST on brokerage + brokerage + an impact model from ADV (parameters in config, documented); liquidity filter; survivorship-free universe from `listing` as of each rebalance; delisting returns handled (last traded price, or the cash/share consideration from the lineage event when known; never silently dropped).

---

## 6. KASAUTI (`/kasauti`)

- **Score versions** are YAML files in `/config/scores/kasauti_vN.yaml`, with pillar weights per playbook, metric lists, transforms (winsorise → peer percentile) and minimum-coverage rules. On freeze, the file's SHA-256 is written to `score_version` and the file becomes read-only in CI (a test fails if a frozen file changes). Re-weighting = new file, new version.
- **Peer groups** are the playbook peer group as of the scoring date; minimum peer count (e.g. 8) falls back to the parent group, recorded in output.
- **Confidence** = weighted data completeness; pillars with insufficient inputs are dropped *and reported*, not imputed.
- **Report Card** per version: decile/quintile forward returns (1/3/6/12m), rank IC with Newey-West t-stats, hit rate, turnover, drawdowns, cost-adjusted long-only top-decile vs Nifty 500 TRI; split by period, size bucket and sector. Pre-freeze history is labelled **"in-sample backtest"**; post-freeze is the **"live record"**, never merged into one line.
- **LLM layer.** Provider abstraction (`LLMClient` protocol) with structured-output + JSON-schema validation; every call logged with model, prompt hash, tokens, cost, latency; responses cached by (model, prompt hash, doc hash).
  - *Extraction* (concall promises, guidance) stores verbatim quote + span. **Judging** whether a promise was delivered is deterministic code against PIT financials, not the LLM (see RISKS R-7 on training-data contamination).
  - *Chat/debate* agents get only read-only, parameterised tools (`get_metric(company, metric, as_of)`, `screen(expr, as_of)`, `get_doc_span(...)`). No SQL tool. A post-processor checks that every number in the answer matches a tool-returned value; unverifiable numbers are struck out and flagged.

---

## 7. API (`/api`)

- FastAPI + pydantic v2; OpenAPI → generated TypeScript client for `/web`.
- **`as_of` is a required query parameter on every data endpoint.** The web app sends the Time Spine value; "NOW" is sent explicitly as a timestamp.
- Responses include `as_of`, `data_watermark` (latest `known_at` used) and per-value lineage ids; `GET /lineage/{id}` resolves to source doc, filing time, formula.
- WebSocket channels: `alerts`, `ingest-status`, and (if a live feed is ever licensed) `ticks`.
- `DEMO_MODE` is a server-side flag; when on, every response carries `demo: true` and the web shell renders the watermark. Demo data lives in a separate schema and can never mix with canonical.

---

## 8. Web (`/web`)

Covered in detail in [UI_SPEC.md](UI_SPEC.md). Stack (ADR-005): Next.js App Router (client-heavy; the terminal is one route with a workspace), TypeScript, Zustand (workspace + `as_of` state), TanStack Query (server cache keyed by `as_of`), **dockview** (tiling, popout, serialisable layouts), **cmdk** (command bar), TanStack Table + virtual, TradingView Lightweight Charts, **ECharts** (Sankey/heatmap/treemap/bands; one charting lib for 2D, not two), React Three Fiber + drei + postprocessing for the 3 scenes, Framer Motion for state transitions.

Rendering budget: 3D scenes lazy-loaded, rendered on demand (`frameloop="demand"`), GPU tier detection (`detect-gpu`) → 2D fallback component for each scene. Each 3D scene has a 2D twin that renders the same data (the table is the answer; §3.3 of PROMPT).

---

## 9. Deployment & environments

- **Local first.** Windows 11 host → Docker Desktop (WSL2 backend) for Postgres/Timescale + Dagster; Python and Node run natively or in containers **[Q4]**.
- Environments: `dev` (local), later `prod` (single VM, e.g. 4 vCPU / 16 GB / 500 GB SSD is ample for v1), never a public endpoint until licensing is resolved (RISKS R-1).
- Backups: nightly `pg_dump` + raw zone sync (raw is the ultimate source of truth; canonical can be rebuilt from it).

---

## 10. Milestone → architecture mapping

| Milestone | Builds |
|---|---|
| M1 | `core` (ids, AsOf, PitReader, lineage), raw zone, Dagster skeleton, security master, listing/lineage history, EOD prices (NSE+BSE), corp actions, adjusted series, index membership (official + reconstructed), PIT test suite |
| M2 | fact_financial (XBRL ladder steps 1–2), shareholding, pledge, classification history, MF holdings (top AMCs first) |
| M3 | API skeleton, web shell, design system, Time Spine, Company Desk v1 |
| M4 | metric registry, playbooks, Valuation Lab |
| M5 | macro/policy/geo ingestion, sensitivities, Transmission Engine, Exposure Theatre |
| M6 | document ingestion, LLM extraction, Promise Tracker |
| M7 | KASAUTI scoring + backtest + Report Card; freeze v1 |
| M8 | chat, debate, thesis tracker, reports |
| M9 | forensics, calendar, screener, perf, deploy |
