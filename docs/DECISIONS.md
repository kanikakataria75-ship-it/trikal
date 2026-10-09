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
