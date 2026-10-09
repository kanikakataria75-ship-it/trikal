# TRIKAL — Risks & Open Questions (M0)

Severity: **H** can invalidate results or block a milestone · **M** degrades a feature · **L** nuisance.

## 1. Data gaps

| ID | Risk | Sev | Mitigation |
|---|---|---|---|
| R-2 | **BSE-only companies** (a large share of the 5,000+ universe): BSE's JSON API returns 403 to scripts, so filings and shareholding for BSE-only names are harder to get than NSE's. | H | Prices are fine (BSE UDiFF bhavcopy ✅). For filings, use the BSE public attachment archive + XBRL where linked; measure coverage per company in a `source_coverage` table and show it in the UI. Licensed feed if coverage stays poor **[Q1]**. |
| R-3 | **Sector classification before 31-Mar-2022 is not officially point-in-time.** This is the exact failure from the owner's previous study. | H | Reconstruct from the legacy NSE industry field + revenue mix, store `method='reconstructed'` + confidence, and show a "classification confidence" line in every backtest report. Offer a sensitivity run that excludes low-confidence periods. Licensed PIT classification is the real fix **[Q1]**. |
| R-4 | **Index membership history** has no consolidated official file; it must be rebuilt from press-release PDFs (2008+ verified) and circulars. Errors propagate into "Nifty 500 universe as of date" backtests. | H | Parse every release, reconcile forward against today's constituent files and periodic snapshots, and cross-check index counts (Nifty 500 must have 500 members on each date). Any mismatch day is flagged, not patched. |
| R-5 | **Fundamentals depth:** XBRL coverage is good only for roughly the last decade. The "10–15 years" target needs PDF extraction for older years, which is lower quality. Balance-sheet data is half-yearly only since FY20 and annual before that; the cash-flow statement in results only since FY20. | H | Extraction ladder (ARCHITECTURE §4.5) with confidence + review queue; older years shown with a confidence marker; scoring excludes unreviewed low-confidence values. |
| R-6 | **Concall transcripts** are systematically available only from ~mid-2021 (LODR Reg 46(2)(oa)). Management Credibility therefore has ~5 years of history at most, and much less for small caps. | M | KASAUTI v1 Report Card reports pillar-level coverage by year; the pillar is dropped (not imputed) where history is missing, and the in-sample backtest is also run *without* that pillar for comparability. |
| R-8 | **Old filings lack a broadcast timestamp** (seen: NSE results rows from 2005 have no `broadCastDate`). | M | Imputed `known_at` using the statutory deadline (conservative: the latest legal filing date), `known_at_precision='imputed'`, excludable from backtests with one flag. |
| R-10 | **Macro data revisions** (GDP, IIP, CPI base changes). Using final values in a backtest is look-ahead. | M | Store every vintage with its release `known_at`; ALFRED for US series; base-year changes linked as lineage events. |
| R-11 | **Corporate-action parsing**: purpose text is free-form; demergers/schemes have complex ratios. A wrong factor corrupts adjusted prices and per-share data. | H | Golden-file tests for every pattern seen; a price-continuity check (unexplained > 35% gap on ex-date flags a missing/incorrect action); manual override table with reason + source. |
| R-12 | **Commodity and PMI series are mostly proprietary**; free proxies are monthly and coarse, which weakens the Transmission Engine's sensitivities. | M | Use free proxies, label method + frequency; estimate sensitivities with appropriately wide confidence bands; licensed data if approved **[Q1]**. |
| R-13 | **MF scheme portfolios** come from about 45 AMC websites in different Excel layouts. | M | Top AMCs by AUM first; parser-per-AMC with golden files; coverage % shown. |

## 2. Methodology / honesty risks

| ID | Risk | Sev | Mitigation |
|---|---|---|---|
| R-7 | **LLM training-data contamination = hidden look-ahead.** An LLM reading a 2021 transcript may "know" what happened in 2023, so its tone/credibility judgements can leak the future into backtests. | H | LLMs only *extract* (verbatim quote + span + structured fields). Delivered/missed judgement is deterministic code against PIT financials. Tone features use lexicon/statistical methods (e.g. Loughran-McDonald-style hedging counts) for backtested versions; LLM-judged tone is allowed only for *live* use and is excluded from in-sample Report Card numbers, with the exclusion stated. |
| R-14 | **Data snooping across KASAUTI versions.** Freezing versions stops silent tuning, but trying 20 versions and publishing the best one is the same sin. | H | The Report Card shows **every** version ever frozen (including abandoned ones), the count of versions tried, and a deflated Sharpe / multiple-testing-adjusted IC. The live record starts at freeze and is the headline. |
| R-15 | **Short history + regime dependence.** India's 2008–2026 sample has few full cycles; decile results may be driven by one regime (e.g. 2020–24 small-cap rally). | M | Sub-period and size-bucket breakdowns are mandatory sections of the Report Card; null results are published. |
| R-16 | **Illiquidity / stale prices** in small caps inflate backtest returns. | M | ADV/impact-cost filters, next-open execution, circuit-limit handling (no fill on locked limit days), costs on. |
| R-17 | **"Advice" perception.** Scores and fair-value ranges could be read as recommendations (SEBI Research Analyst Regulations apply if published to others). | M | Personal-use scope; persistent disclaimer; no ratings/targets; ranges with assumptions. Legal review before any sharing **[Q2]**. |

## 3. Legal / licensing

| ID | Risk | Sev | Mitigation |
|---|---|---|---|
| R-1 | **NSE/BSE terms** restrict aggregation and redistribution; NSE data-portal terms prohibit automated collection without consent; JSON endpoints are a grey zone even for personal use. | H | ADR-006 stance: personal use; prefer published downloads; strict rate limits + caching; `licence_status` per source; no public deployment until licensed. **Owner decision [Q2].** |
| R-18 | Endpoint fragility: NSE/BSE change URLs, formats (e.g. the bhavcopy UDiFF switch) and anti-bot measures without notice. | M | `source_health` daily check, raw zone keeps everything already fetched, parsers versioned by format. |

## 4. Engineering / performance

| ID | Risk | Sev | Mitigation |
|---|---|---|---|
| R-19 | **Scope.** The prompt describes the work of a team over years. Building breadth first risks a terminal that looks impressive but has untrustworthy data. | H | Milestone order is data-first (M1–M2) on purpose. Each desk ships only when its data is PIT-tested. Proposal: run M1–M2 on a **pilot universe** (Nifty 500 + all delisted names that were ever in it), then widen to the full universe once parsers are stable **[Q3]**. |
| R-20 | 3D scenes miss 60 fps on integrated GPUs. | M | Demand-frameloop, instancing, GPU-tier fallback to 2D twins, perf tests in CI (frame-time budget on a reference scene). |
| R-21 | `as_of` changes trigger heavy recomputation across many panels. | M | Server-side PIT snapshots per day for common aggregates; query cache keyed by `as_of`; playhead updates on release. |
| R-22 | LLM cost for extracting ~5,000 companies × 20 quarters of transcripts + annual reports. | M | Cache by doc hash, cheap model for triage + stronger model for extraction, per-month budget cap with a hard stop **[Q5]**. |
| R-23 | Windows host: Postgres/Timescale/Dagster run best on Linux. | L | Docker Desktop with WSL2, or WSL2 natively **[Q4]**. |

---

## 5. Open questions for the owner

| # | Question | Why it matters | My default if you don't mind either way |
|---|---|---|---|
| **Q1** | Is there a **budget for any licensed data** (e.g. a fundamentals vendor such as CMOTS / ACE Equity / Capitaline / Prowess for deep PIT financials + classification history; NSE data licence)? | Decides whether R-3/R-5/R-12 are solved properly or approximated with confidence flags. | Free sources only, with reconstruction + confidence flags; revisit after M2 with measured coverage numbers. |
| **Q2** | Do you accept the **personal-use stance** for NSE/BSE (published downloads first; website JSON endpoints used politely where no download exists)? Any plan to share TRIKAL with others? | Legal risk (R-1, R-17). | Yes for personal use; nothing deployed publicly. |
| **Q3** | **History depth & pilot scope**: prices from 1995 (NSE start) or from 2005? Fundamentals target 2011+ (XBRL era) first, older via PDFs later? Pilot on the Nifty 500 ever-members before the full 5,000+? | Effort and data quality in M1–M2. | Prices: full NSE history from 1995 + BSE from the earliest UDiFF/legacy files available. Fundamentals: XBRL era first. Pilot universe first, then full. |
| **Q4** | **Machine & runtime**: can you run Docker Desktop (WSL2)? RAM / disk / GPU of the main machine? | Local stack and 3D budgets. | Docker Desktop; ≥ 16 GB RAM, ≥ 200 GB free disk. |
| **Q5** | **LLM provider and monthly budget** (I'd default to Anthropic models behind the provider abstraction), and can you register a free **FRED API key**? | M5–M8. | Anthropic API, a monthly cap you set; FRED key in `.env`. |
| **Q6** | Do you have **existing datasets** from your earlier backtests (prices, corporate actions, sector maps) you want cross-checked against TRIKAL? | Great for validation (diffs), *not* as a source unless their lineage is known. | Use only for reconciliation reports. |
| **Q7** | **Backtest conventions**: execute at next-session open after `known_at` (my default) or next-session VWAP? Your realistic cost assumptions (brokerage bp, impact model)? | Report Card realism. | Next open; delivery brokerage 0, statutory charges exact, impact = f(order size / ADV). |
| **Q8** | Single user, local only (no auth), or do you want login from day one? | Scope of M3. | Single user, local, no auth in v1. |
| **Q9** | Version control: I've initialised a local git repo. Do you want a GitHub remote (private)? | Backups, PR-style reviews per milestone. | Local only until you say otherwise. |
