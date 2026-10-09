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
