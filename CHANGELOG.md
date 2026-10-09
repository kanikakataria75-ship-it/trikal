# Changelog

## M0 — Plan (2026-10-09)
- Added `PROMPT.md` (build prompt, source of truth).
- Added planning docs: `docs/ARCHITECTURE.md`, `docs/DATA_SOURCES.md` (endpoints probed live on 2026-10-09), `docs/SECTOR_PLAYBOOKS.md` (draft), `docs/UI_SPEC.md`, `docs/RISKS.md` (risks + open questions), `docs/DECISIONS.md` (ADR-001…009, all proposed).
- No application code. Waiting for owner review of the open questions in `docs/RISKS.md` §5.

## M1: Security master & prices (IN PROGRESS, 2026-10-09; not yet reviewed)
- Owner answers to Q1–Q9 recorded (free sources only, personal use, Nifty 500 ever-members pilot, next-open execution, 50 bps baseline costs). Still open: machine specs, LLM cap, path to earlier backtest data.
- Private GitHub remote created; work on branch `m1-security-master`.
- Built: raw zone (content-addressed + SQLite fetch log), polite fetcher, NSE/BSE bhavcopy fetch/stage/load (all 5 formats), NSE reference files, corporate-actions feed + subject parser (18 golden tests), Nifty snapshots + press-release crawler, security master, adjustment-event builder, PitReader, `trikal show`.
- Not done yet: full price backfill (partial), index-membership reconstruction from press-release PDFs, PIT/look-ahead test suite, FORMULAS.md, source_coverage report.
- KNOWN BUG (found at wrap-up): on the partial backfill the adjustment builder *applies* spurious events, e.g. TCS NSE 2025-01-20 factor 0.986 and BSE 2025-10-20 factor 0.738, both `implied_only`. Cause: the "gap" is measured against the calendar of days loaded so far, so missing days look like consecutive sessions. Fix before review: measure gaps against the full exchange calendar (fetch log ok + not_found), and apply `implied_only` events only when the previous session is truly adjacent. Adjusted prices are NOT trustworthy until this is fixed.
