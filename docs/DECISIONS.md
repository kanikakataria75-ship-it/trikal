# TRIKAL — Decision Log (ADRs)

Format: ID · date · status (`proposed` → `accepted` / `rejected` / `superseded by ADR-n`) · context · decision · consequences.
All ADRs below are **proposed** at M0 and become accepted when the owner signs off on M0.

---

### ADR-001 · 2026-10-09 · proposed: Storage engines
**Context:** We need a bitemporal store for facts, efficient time series, and fast cross-sectional scans for backtests and screening.
**Decision:** PostgreSQL 16 + TimescaleDB (prices, macro series) as the canonical store; Parquet snapshots queried by DuckDB for analytics/backtests. pgvector only if retrieval needs it. No separate vector DB or OLAP server in v1.
**Consequences:** One operational database; analytics snapshots must be regenerated from canonical and stamped with a `recorded_at` watermark.

### ADR-002 · 2026-10-09 · proposed: Orchestrator = Dagster
**Context:** The prompt allows Dagster or Prefect.
**Decision:** Dagster. Software-defined assets with daily/quarterly partitions mirror the data (one bhavcopy per day, one filing per quarter); asset checks give data-quality gates; asset lineage matches TRIKAL's lineage concept.
**Consequences:** Dagster webserver + daemon in Docker; pipeline code is organised as assets, not ad-hoc flows.

### ADR-003 · 2026-10-09 · proposed: Three-timestamp model and tradability convention
**Context:** Invariant 2 asks for valid_time and known_time. Reproducing past runs and auditing backfills also needs system time. Backtests must not trade on information before it is actionable.
**Decision:** Every canonical fact has `valid_*`/`period_*`, `known_at` (public time, IST-aware, with precision: exact|day|imputed) and `recorded_at` (ingest time). `as_of` filters on `known_at`. Backtests trade at the open of the first session strictly after `known_at`.
**Consequences:** Slightly larger tables; imputed timestamps are visible and excludable; a replay test guarantees reproducibility.

### ADR-004 · 2026-10-09 · proposed: Add a shared `/core` package (deviation from §7 layout)
**Context:** The PIT data-access layer, identifiers, lineage types and the `AsOf` type are needed by pipeline, analytics, kasauti and api. Putting them in any one of those creates circular dependencies.
**Decision:** Add `/core` (`trikal_core`). Analytics/kasauti may access data **only** through `trikal_core.pit.PitReader`; the analytics DB role has no grants on base tables.
**Consequences:** This is a small deviation from the prompt's folder list, so it needs owner approval.

### ADR-005 · 2026-10-09 · proposed: Frontend library choices
**Decision:** dockview (over react-grid-layout: real docking, tabs, popouts, serialisable layouts), ECharts (single 2D chart lib incl. Sankey/heatmap/treemap; visx not added), TradingView Lightweight Charts (price), R3F + drei + postprocessing (3D), cmdk, TanStack Table/Virtual/Query, Zustand, Framer Motion. Fonts: Inter Tight + JetBrains Mono (both OFL, self-hosted).
**Consequences:** A single charting idiom; 3D code split and lazy-loaded.

### ADR-006 · 2026-10-09 · proposed: Source-access stance (personal use)
**Context:** NSE/BSE terms restrict aggregation/redistribution and automated collection; many useful datasets are only on their website JSON endpoints. See DATA_SOURCES §7.
**Decision:** Personal, non-commercial use only. Prefer files offered for download; use JSON endpoints only where no download exists, at ≤ 1 req/s per host, with full caching so nothing is fetched twice. Every source carries `licence_status`. No public deployment until licensing is resolved.
**Consequences:** Requires owner acceptance (RISKS Q2). A future `PUBLIC_MODE` gate refuses to serve restricted sources.

### ADR-007 · 2026-10-09 · proposed: Metric results are a tagged union
**Decision:** Every metric returns `Value | Undefined | NotAvailable | Forbidden` (plus confidence/restated flags). Forbidden metrics raise inside the engine and are never computed (invariant 5). The UI renders each state distinctly (UI_SPEC §6).

### ADR-008 · 2026-10-09 · proposed: LLMs extract, code judges
**Context:** Look-ahead via LLM training-data contamination (RISKS R-7).
**Decision:** LLMs produce verbatim-quoted, span-referenced structured extractions only. Promise outcome judgement is deterministic code against PIT data. LLM-judged soft features (tone) are excluded from in-sample backtests.

### ADR-009 · 2026-10-09 · proposed: Unadjusted prices stored, adjustment on read, PIT-aware
**Decision:** Only unadjusted prices + corporate actions are stored; adjustment factors are applied on read using actions with `announced_at <= as_of`.

### ADR-010 · 2026-10-09 · proposed: DuckDB stand-in for Postgres during M1 (temporary deviation)
**Context:** No Docker/Postgres on the dev machine.
**Decision:** Canonical store = embedded DuckDB file (`data/trikal.duckdb`); raw-zone index = SQLite WAL (`data/raw/index.sqlite`) so fetchers can run as separate processes. All reads go through `trikal_core.pit.PitReader`, so a Postgres adapter can replace it later.
**Consequences:** No DB-role enforcement yet (a test will guard imports instead). Revisit once Docker is available.

### ADR-011 · 2026-10-09 · proposed: Security identity = ISIN stem
**Decision:** `security_id = 'S:' + ISIN[:9]` (issuer + security type), so face-value changes (new ISIN serial) stay one security. Pre-ISIN rows inherit identity through same-code trading episodes or NSE symbol-change chains; otherwise a flagged synthetic id. Each listing row carries method + confidence.

### ADR-012 · 2026-10-09, revised 2026-10-10 · proposed: Adjustment factors: announcements confirmed by prices
**Context:** The first version assumed the bhavcopy PREVCLOSE carries the exchange's adjustment. The data disproved it: legacy NSE files do not adjust PREVCLOSE (TCS bonus, 31-May-2018). Gaps in partially downloaded data and holes in source files (BSE 15-Jul-2022 omits TCS) also produced spurious factors.
**Decision:** Announced actions (NSE feed + subject parser) are the primary source. Each is confirmed against the observed close/previous-close move. The exchange-implied factor is used only where present and only across adjacent sessions on the true calendar (`exchange_day`, unknown days are never holidays). Contradicted announcements and gap-contaminated factors are logged and **not applied**; unexplained jumps are logged with a suggested factor. Adjusted-as-of-D uses only events with ex_date <= D. Full rules: FORMULAS.md.

### ADR-013 · 2026-10-10 · proposed: Index membership reconstructed from press releases + cited overrides
**Context:** No official membership history exists (RISKS R-4).
**Decision:** Rebuild backwards from the official constituent file using every NSE Indices press release, with a fixed-size count check at every effective date. Free-text cancellations and revocations (e.g. the voided 27-Mar-2020 rebalance, the 2024 Vodafone Idea revocation) are handled by a human-reviewed `config/index_overrides.yaml`, where each entry cites its source release. Unresolvable names stay in the walk as zero-confidence placeholders, never dropped.
**Consequences:** Accuracy is measurable (share of dates passing the count check), and every membership row traces to a PDF.
