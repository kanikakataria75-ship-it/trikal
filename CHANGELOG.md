# Changelog

## M0 — Plan (2026-10-09)
- Added `PROMPT.md` (build prompt, source of truth).
- Added planning docs: `docs/ARCHITECTURE.md`, `docs/DATA_SOURCES.md` (endpoints probed live on 2026-10-09), `docs/SECTOR_PLAYBOOKS.md` (draft), `docs/UI_SPEC.md`, `docs/RISKS.md` (risks + open questions), `docs/DECISIONS.md` (ADR-001…009, all proposed).
- No application code. Waiting for owner review of the open questions in `docs/RISKS.md` §5.

## M1: Security master & prices (DONE for review, 2026-10-10)

**Data** (full numbers: `docs/reports/coverage.md`)
- NSE daily prices from 03-Nov-1994 and BSE from 02-Jan-2007 to today: 28.1M unadjusted rows, every
  trading day accounted for (NSE 0 unknown days; BSE 33 unknown days, logged).
- Security master: 9,859 securities including delisted and merged ones. Identity methods: ISIN 2,722 · code
  continuity 3,744 · symbol chain 204 · cross-exchange price match 78 · synthetic (pre-2011, no ISIN
  reachable) 3,111. Each listing carries a method and a confidence.
- Corporate actions: 43,794 NSE announcements (1995 to now). 2,785 adjustment events are applied, all
  confirmed by announcement + observed price move (e.g. TCS bonuses 2006/2009/2018). Exchange-only signals
  are recorded for review and never applied (ADR-012).
- Nifty 500 point-in-time membership rebuilt from 850 NSE Indices press releases (1998 to now) plus cited
  overrides. The count is **exactly 500 on every effective date from 06-Dec-2011 to today**; 2010: 501.
  Pre-2010 is lower confidence (2005: 512 incl. 16 unresolved names). 1,443 securities were ever members.
- Pilot universe for M2: 1,326 ever-members with an NSE symbol (977 still trading).

**Code**
- `core/`: time model (`AsOf`, known_at precision), ids, DuckDB schema, `PitReader` (the only data door).
- `pipeline/`: raw zone, polite fetcher, bhavcopy (5 formats), NSE reference files, corporate-action
  parser, trading calendar, security master, adjustments, index reconstruction, coverage report, CLI.
- 41 tests: look-ahead canaries, property test, bitemporal membership, and a regression test for every
  bug found.

**Known limitations** (RISKS R-3, R-4, R-11, R-24, R-25)
- BSE-only companies' corporate actions are not applied (no announcement feed reachable).
- Index history before Dec-2011 is approximate (names only, some unresolved); flagged per row.
- Sector classification history is not built yet (M2).
- DuckDB stand-in instead of Postgres (ADR-010); ADRs 001-013 are still "proposed" pending your review.

**Started for M2 (overnight, raw only):** per-company results lists (including SEBI "Integrated Filing"
results from Dec-2024 on, a separate endpoint), shareholding, pledge, annual-report lists, then
XBRL result documents since FY2012 for the pilot universe. Run: `run_m2_overnight.cmd` (resumable).

## M2: Fundamentals & ownership (CODE COMPLETE for review, 2026-10-12; raw download still running)

**What exists**
- Results parsers for every era: XBRL (`INDAS`, `BANKING`, `NBFC_INDAS`, `NONINDAS`, SEBI Integrated Filing
  "Financials") and the pre-2018 HTML pages (FY2008-FY2017). Bitemporal `filing`, `fact_financial_all`,
  `fact_financial` (value-change PIT table), restatement-aware, `known_at` = exact exchange broadcast time.
- `config/line_items.yaml`: 76 canonical line items (income statement, bank items incl. NPA amounts, balance
  sheet, cash flow, ownership) with source-concept priority; `PitReader.financials(as_of, basis='auto')`
  returns value, source concept, rank, filing and `known_at`.
- Shareholding: promoter/public for every filing since 2015, category detail (MF, insurance, FPI, retail, ...)
  from SHP XBRL; pledge snapshots; `PitReader.ownership` / `.pledge`.
- Sector classification with method and confidence on every row; `PitReader.classification(min_confidence=)`.
- Accounting-identity checks (`trikal check-financials`); coverage report extended with download progress,
  pass rates, ownership and classification; `trikal refresh-m2` does it all in one go.
- 55 tests (14 new): the year-to-date period rule (mutation-checked), unit scaling, `-` is not zero, Part II
  arithmetic guard, percentage-scale normalisation, restatement and revision visibility by as-of date,
  line-item fallback lineage, classification confidence.

**Findings that changed the design** (details: DATA_SOURCES §10, ADR-014..017)
- The XBRL year-to-date column carries the quarter's dates; periods are derived from the column.
- Results XBRL exists only from Jun-2017; FY2008-17 comes from HTML pages (income statement only).
- SEBI Integrated Filing (from Dec-2024) is a separate endpoint and half of its rows are governance, not financials.
- Pledge history and shareholding before Sep-2021 are not served by the exchange (RISKS R-26, R-27).

**Validated on a spread sample of 255 real documents** (180 XBRL documents across all four families and 75 old pages): 0 parse
errors; the XBRL identities hold on 138/138 (income statement), 42/42 (balance sheet), 44/44 (cash flow);
old-page profit reconciles on 59% of the sampled pages (company-typed template, RISKS R-28).
The full-universe pass rates will be published in `docs/reports/coverage.md` as the download completes.

**Not done / deferred**
- The raw download is incomplete (about 1.5-2 days of wall-clock); until it finishes, coverage is partial and
  the report says so.
- Scheme-level mutual fund holdings (AMC files) deferred; category totals per quarter are in (RISKS R-13).
- Annual-report PDFs and concalls are M6.
