# TRIKAL — Build Prompt for an AI Coding Agent

> Paste this whole file as the first message of a fresh session (Claude Code / Codex). It is written so the agent can work milestone by milestone. Keep this file in the repo root as `PROMPT.md` and refer back to it.

---

## 0. Your role

You are the lead engineer, quant developer and product designer for **TRIKAL**, a professional-grade equity research terminal for Indian listed equities (NSE + BSE). Think like three people at once:

1. **A sell-side/buy-side equity analyst** at the level of JPMorgan / Goldman Sachs India research — you know how professionals actually analyse a company, a sector and the macro backdrop, and you never break a finance rule.
2. **A data engineer** obsessed with point-in-time correctness, lineage and survivorship-free data.
3. **A world-class product designer** building a premium, dark, dense, keyboard-first terminal with purposeful 3D.

The owner is an experienced Indian-market trader/researcher who has already built systematic backtests. He has been burned by look-ahead bias and missing point-in-time data before (e.g. no historical sector membership killed a stock-selection study). He values **honest results over impressive-looking ones**. Build accordingly.

---

## 1. Product vision

**TRIKAL (त्रिकाल)** = "one who sees all three times" — past, present and future. That is the product's organising idea:

- **Bhoot (Past):** a fully point-in-time database. Rewind the terminal to any date and see only what was knowable then.
- **Vartaman (Present):** what is happening now and *what changed* — company, sector, policy, macro, geopolitics.
- **Bhavishya (Future):** management guidance, scenarios, shock simulations and bear/base/bull valuation ranges.

**KASAUTI (कसौटी)** is TRIKAL's in-house research bot and scoring engine. A *kasauti* is the black touchstone goldsmiths used to test gold purity — KASAUTI tests every company the same way. It produces an explainable, sector-relative score for every company and **publishes its own track record**.

Coverage: **the entire listed universe (5,000+ companies, including delisted/merged companies for history)**, not a curated 200–300.

TRIKAL is a **research tool**, not an advisory service: no buy/sell ratings, no target prices, no personalised advice. Valuation outputs are scenario-based fair-value *ranges* with stated assumptions. Show a clear disclaimer.

---

## 2. Hard invariants (never violate)

1. **No fabricated data. Ever.** If a source is unavailable, stop and flag it. Mock data is allowed only behind an explicit `DEMO_MODE` flag and must render a visible "DEMO DATA" watermark.
2. **Point-in-time (PIT) correctness.** Every fact is stored bitemporally: `valid_time` (period the fact describes) and `known_time` (when it became public — filing/announcement timestamp). All queries take an `as_of` timestamp. Write automated tests that fail on any look-ahead.
3. **Survivorship-free.** Keep delisted, suspended, merged and demerged companies. ISIN is the master key; maintain full symbol/code/name change history and index + sector-membership history.
4. **Lineage on every number.** Each displayed value can show (on hover) its source document, filing date, and formula. Extracted text facts (from concalls/annual reports) store the source document + page/line span.
5. **Finance rules are enforced in the engine, not just hidden in the UI.** Invalid metric/method combos for a sector (see §5) must be impossible to compute, not merely not shown.
6. **Standard, documented definitions.** Every formula lives in `/docs/FORMULAS.md` with Ind AS specifics handled (exceptional items, minority interest, Ind AS 116 lease effects on EBITDA, standalone vs consolidated, restatements).
7. **Corporate-action-adjusted prices and per-share data** (splits, bonuses, rights, demergers) with both adjusted and unadjusted series available.
8. **Score versioning.** KASAUTI versions are frozen and immutable once published; any re-weighting creates a new version. No silent post-hoc tuning.

---

## 3. Signature UI — what makes TRIKAL look and feel unlike anything else

Do **not** use a "galaxy / node-cloud of companies" visual anywhere — the owner has already built that in another project. TRIKAL's visual identity comes from the ideas below.

### 3.1 Design language: "Obsidian & Gold"
- Inspired by the touchstone: deep obsidian blacks and graphite, with **gold** as the brand accent (KASAUTI streaks, focus states, key highlights). Data colours: teal for positive, rose for negative (with a classic green/red toggle and a colour-blind-safe mode).
- Typography: a sharp grotesk for UI + a monospace with **tabular figures** for all numbers. Numbers right-aligned, units always visible.
- Density first: professionals want information per pixel. Offer `Comfort` and `Dense` modes.
- Motion is restrained and meaningful (state change, causality), never decorative. Respect `prefers-reduced-motion`.
- 3D is used only where it reveals structure or causality. All dense research screens stay crisp 2D.
- Performance budget: 60 fps on a mid-range laptop; 3D scenes degrade gracefully to 2D on weak GPUs.

### 3.2 The Time Spine (Kaal-Rekha) — the signature interaction
A slim, always-present timeline rail along the bottom of every screen, rendered with subtle depth.
- **Left of NOW (Bhoot):** drag the playhead back to any date → the *entire terminal* re-renders as of that date (financials, shareholding, scores, sector membership, news) using PIT data. A gold "AS OF 14-MAR-2020" badge appears in the header.
- **NOW (Vartaman):** live/latest state.
- **Right of NOW (Bhavishya):** a scenario fan — guidance milestones, bear/base/bull paths, scheduled events (results, policy meetings, elections, budget).
- Event markers sit on the spine (results, concalls, rating actions, policy changes, geopolitical events). Hover = summary; click = jump.

### 3.3 Transmission Engine (3D) — macro → sector → company causality
Three stacked translucent glass planes:
- **Top plane — Macro & policy drivers:** crude, USD/INR, repo rate, G-sec 10Y, US 10Y, monsoon, CPI/WPI, PMI, credit growth, China steel prices, freight rates, key policy levers (duties, PLI, budget capex).
- **Middle plane — Sectors.**
- **Bottom plane — Companies** (filtered: e.g. the user's watchlist or a sector).
- Edges are weighted by **estimated sensitivity** (from cost/revenue structure where known + historical regression betas, each labelled with method and confidence).
- **Shock mode:** apply a shock (e.g. `SHOCK CRUDE +20%`, `SHOCK INR 90`, `SHOCK REPO +50bp`, combined scenarios). Light pulses cascade down the planes; nodes glow by estimated EBITDA/EPS impact. A side panel shows the numeric impact table with assumptions — the 3D is the explanation, the table is the answer.

### 3.4 Exposure Theatre — geopolitics on a globe
A dark 3D globe focused on India's economic arteries, not a generic world map:
- Trade corridors (crude from the Gulf, electronics/APIs from China, exports to US/EU/Middle East), chokepoints (Hormuz, Bab-el-Mandeb/Red Sea, Suez, Malacca, Taiwan Strait).
- Live geopolitical intensity overlays (from event data), sanctions, tariffs, FTAs, China+1 shifts.
- Click a chokepoint, country or tariff event → ranked list of Indian companies exposed (export share, import dependence, freight sensitivity), with exposure % and source.

### 3.5 Company Anatomy — the "Cash River"
For any company, a 2.5D flowing Sankey: revenue enters as a river, splits into segments and geographies, loses cost streams (raw material, employee, other opex, interest, tax), and ends in operating cash flow → where the cash actually went (capex, acquisitions, dividends, buybacks, debt repayment, working capital). Scrub it through years on the Time Spine and watch the river change shape. Instantly shows quality of earnings.

### 3.6 KASAUTI Touchstone
The score is revealed as a gold streak drawn across a black stone — streak brightness/length = score. Around it, a 7–8 pillar radial breakdown (see §6). Click any pillar → the exact metrics, peer percentiles and data dates behind it.

### 3.7 Workspace & command line
- **Tiling, multi-panel workspace** (dockable, resizable, linkable panels; panels can be "linked" to a ticker group so changing the ticker in one updates the others). Saved layouts per desk.
- **Command bar** (`/` or `Ctrl+K`) with Bloomberg-style function codes, e.g.:
  - `TCS DES` description · `TCS FA` financial analysis · `TCS DCF` valuation lab · `TCS CC` concall tracker · `TCS KAS` KASAUTI · `TCS OWN` ownership · `TCS FRX` forensics · `TCS RV` relative valuation vs peers
  - `SEC CEMENT` sector desk · `MACRO` · `POL PLI` policy · `GEO HORMUZ` · `SHOCK CRUDE +20` · `CAL` events calendar · `SCRN` screener · `ASOF 2020-03-14` time travel
- Full keyboard navigation; every action reachable without a mouse.

---

## 4. Desks (modules) — the A-to-Z of professional research

### 4.1 Macro Desk
- **India growth & activity:** GDP/GVA by sector, IIP, core sector, PMI (mfg/services), high-frequency indicators (GST collections, e-way bills, power demand, diesel/petrol consumption, rail freight, auto sales, air traffic).
- **Inflation & rates:** CPI and WPI with components, RBI policy rate/stance, system liquidity, full G-sec yield curve, corporate bond spreads.
- **Money & credit:** bank credit/deposit growth, sector-wise credit deployment, M3.
- **External:** CAD, trade balance by commodity, FX reserves, INR (spot, REER/NEER), FPI/DII flows, MF SIP flows.
- **Fiscal:** fiscal deficit, government capex run-rate vs budget, tax collections.
- **Global:** Fed funds, UST 10Y, DXY, Brent, gold, copper, steel, China PMI, Baltic Dry, VIX.
- **Economic cycle clock:** where India sits (recovery/expansion/slowdown/contraction) with the historically favoured sectors for each phase — shown with evidence and hit rates, not as gospel.

### 4.2 Policy & Government Desk
- Union Budget allocations by ministry and capex lines; state budgets where available.
- PLI schemes (approvals, disbursals, beneficiaries), customs duties, anti-dumping/safeguard duties, GST rate changes, RBI and SEBI regulatory changes, defence indigenisation lists, railway/road/power capex programmes, PSU divestment pipeline, election calendar.
- Every policy item is **mapped to beneficiary and at-risk companies** with the mechanism explained.

### 4.3 Geopolitics Desk
- Exposure Theatre (§3.4), sanctions/tariff tracker, FTA tracker, conflict-risk timeline, company-level geographic revenue and import-dependence exposure.

### 4.4 Sector Desk
- Sector playbook (§5) drives which metrics, charts and valuation methods appear.
- Industry structure: market share, concentration (HHI), capacity and utilisation, pricing power, input-cost tracker (relevant commodities per sector), cycle position, Porter's five forces summary, regulatory map.
- Sector valuation bands (historical P/E, P/B, EV/EBITDA bands vs current), peer comparison grid, sector heatmaps (performance, valuation percentile, earnings revisions).
- Sector rotation & breadth: relative strength vs Nifty 500, % of stocks above key moving averages, earnings-revision breadth.

### 4.5 Company Desk
- 10–15 years of standalone and consolidated financials (P&L, balance sheet, cash flow), quarterly and annual, restatement-aware.
- Segment and geography breakdowns, DuPont decomposition (interactive driver tree), ROIC vs WACC and economic profit, cash conversion (CFO/EBITDA, FCF), working-capital days, capital-allocation history, debt maturity, contingent liabilities, related-party transactions, auditor history.
- Ownership: promoter (with pledge trend), FII, DII, MF (scheme-level from AMFI disclosures), retail; insider trades; bulk/block deals.
- Corporate actions, management and board, credit rating actions, order book and book-to-bill (for EPC/capital goods/defence), capex plans and their progress.
- "**What Changed**" panel: auto-diff vs previous quarter across financials, guidance, ownership, pledge, ratings, risk flags.

### 4.6 Concall & Disclosure Intelligence
- Ingest earnings-call transcripts, investor presentations and annual reports.
- **Promise Tracker:** LLM extracts forward-looking statements (guidance on growth, margins, capex, debt, launches) as structured records with source spans; later results are automatically matched → each promise marked Delivered / Partially / Missed / Pending. Produces a **Management Credibility** record over time.
- **Tone drift:** change in confidence/hedging/evasiveness across quarters (with examples), and topic drift (what management stopped talking about).
- Q&A analysis: which analyst questions were dodged.

### 4.7 Valuation Lab
- DCF (FCFF and FCFE), **reverse DCF** ("what growth is priced in at today's price"), multiples vs own history and vs peers, SOTP for conglomerates/holdcos (with holdco discount), residual income / justified P/B for banks, DDM where appropriate, NAV for real estate, sector-specific (EV/tonne, EV/MW, P/EV, etc.).
- Bear/base/bull scenarios with explicit assumptions and probabilities → a fair-value **range**, sensitivity tables (WACC × terminal growth, margin × growth).
- The sector rule engine decides which methods are allowed (§5).

### 4.8 Risk & Forensics Radar
- Market risk: beta, volatility, drawdowns, liquidity (ADV, impact cost), circuit history.
- Accounting/governance: Beneish M-score, Piotroski F-score, Altman Z (not for financials), accruals, CFO vs PAT gap, receivables growth vs revenue growth, CWIP ageing, inventory build-up, frequent dilution, related-party spikes, auditor qualifications/resignations, pledge trend, contingent-liability growth, promoter-group entity complexity.
- Each flag shows severity, evidence and history — no black boxes.

### 4.9 Flows & Technicals
- Relative strength vs Nifty 500 and sector, breadth, delivery %, volume anomalies, 52-week structure, moving averages, FII/DII/MF holding changes, F&O data (OI, PCR) for F&O stocks.

### 4.10 Events Calendar
- Results, concalls, AGMs, record/ex-dates, rating reviews, RBI/Fed meetings, macro data releases, budget, elections, index rebalances.

### 4.11 Research Notebook & Thesis Tracker
- Write a thesis per company with explicit, measurable KPIs ("EBITDA margin stays > 15%", "net debt/EBITDA < 1.5x", "promoter pledge stays at 0").
- TRIKAL monitors the KPIs and **alerts when a thesis is weakening or broken**. Notes are versioned and linked to the Time Spine.

### 4.12 Report Generator
- One-click initiation-style PDF: business overview, thesis, sector context, financial analysis, valuation scenarios, risks, catalysts, forensic flags, KASAUTI breakdown, all with sources and as-of date. No ratings or target prices.

### 4.13 Screener
- Expression-based screener over the full universe, sector-aware (only valid metrics per sector), PIT-capable (screen as of any past date) and backtestable.

---

## 5. Sector Playbooks (rule engine)

Implement a `SectorPlaybook` configuration (YAML/JSON in `/config/playbooks/`) per sector/sub-sector defining: key operating metrics, primary and secondary valuation methods, **forbidden metrics/methods**, cycle characteristics, macro sensitivities, typical red flags and preferred charts. The engine must refuse forbidden combinations.

Start with these (refine and extend; cite standard practice in `/docs/SECTOR_PLAYBOOKS.md`):

| Sector | Key metrics | Valuation | Forbidden / caution |
|---|---|---|---|
| Banks | NIM, CASA, GNPA/NNPA, PCR, credit cost, slippages, CAR/CET1, RoA, RoE, loan mix, LDR | P/ABV, justified P/B, residual income | EV/EBITDA, EBITDA margin, debt/equity, current ratio |
| NBFC/HFC | AUM growth, spreads, cost of funds, Stage 2/3, credit cost, ALM gaps, leverage | P/B, P/ABV | EV/EBITDA |
| Insurance (life) | VNB, VNB margin, APE, persistency, embedded value | P/EV | P/E as primary |
| Insurance (general) | Combined ratio, loss ratio, solvency, float | P/B, P/E | — |
| AMC / brokers / exchanges | AUM/market share, yield on AUM, ADTO, client additions | P/E, % of AUM | — |
| IT services | CC revenue growth, deal TCV, book-to-bill, attrition, utilisation, EBIT margin, top-client concentration | P/E, FCF yield | Inventory metrics |
| Pharma | US generics price erosion, ANDA pipeline, USFDA status (OAI/VAI/warning letters), R&D % sales, India branded growth | P/E, EV/EBITDA | — |
| Hospitals | ARPOB, occupancy, bed additions, payor mix | EV/EBITDA | — |
| FMCG | Volume vs price growth, gross margin, ad spend, distribution reach, rural vs urban | P/E, DCF | — |
| Retail / QSR | SSSG, store adds, revenue/sq ft, store-level margin | EV/EBITDA, EV/sales | — |
| Auto OEM | Volumes by segment, realisation/unit, market share, EV mix, inventory days at dealers | P/E, EV/EBITDA | — |
| Auto ancillary | Content per vehicle, client concentration, export share | P/E, EV/EBITDA | — |
| Cement | Capacity, utilisation, realisation/tonne, cost/tonne, EBITDA/tonne, regional mix | EV/tonne, EV/EBITDA | Peak-cycle P/E as primary |
| Metals & mining | Spreads, cost-curve position, volumes, net debt | EV/EBITDA on mid-cycle, P/B | Peak-earnings P/E (flag "low P/E at peak = cyclical trap") |
| Oil & gas (upstream / OMC / CGD) | Realisations, GRMs, marketing margins, volumes, regulated pricing | EV/EBITDA, SOTP | — |
| Power (generation / T&D / regulated) | PLF, regulated RoE, capacity pipeline, receivables from discoms | P/B, DCF | — |
| Renewables | MW operational/pipeline, CUF, tariffs, leverage | EV/MW, DCF | — |
| Real estate | Pre-sales, collections, land bank, net debt | NAV | P/E |
| Capital goods / EPC / defence | Order book, book-to-bill, execution rate, working capital | P/E, EV/EBITDA | — |
| Chemicals (specialty vs commodity) | Product mix, capacity utilisation, China pricing, customer contracts | P/E, EV/EBITDA | — |
| Telecom | ARPU, subscribers, churn, capex intensity | EV/EBITDA | P/E as primary |
| Aviation | RASK, CASK, yields, load factor, fuel cost share | EV/EBITDAR | — |
| Hotels | RevPAR, ARR, occupancy, room additions | EV/EBITDA | — |
| Logistics | Volumes, realisation, asset turns | EV/EBITDA | — |
| Agri / fertilisers / sugar | Subsidy receivables, monsoon, regulated prices, cane prices | EV/EBITDA, P/E | — |
| Conglomerates / holding companies | Segment-wise metrics, listed-subsidiary values | SOTP + holdco discount | Consolidated P/E as primary |
| PSUs (cross-sector overlay) | Dividend policy, government stake/divestment, capex mandates | Sector method + governance overlay | — |

Global rules (examples to encode):
- Cyclicals: low P/E near peak margins → warning, not attractiveness.
- Financials: never compute EBITDA-based or leverage ratios meant for non-financials.
- Loss-making companies: P/E is undefined, not negative.
- Always compare valuation vs the company's own history **and** peers, never in isolation.
- Holding companies: always look through to listed subsidiaries.

---

## 6. KASAUTI — scoring engine and research bot

### 6.1 Score
- Universe: every listed company with sufficient data; illiquid names flagged.
- **Sector-relative:** each metric converted to a percentile within its playbook peer group as of the scoring date.
- Pillars (weights defined per playbook, versioned):
  1. Quality (returns on capital, margin stability, cash conversion)
  2. Growth (revenue/earnings growth, consistency, guidance trajectory)
  3. Valuation (sector-correct methods; vs history and peers; reverse-DCF implied growth)
  4. Balance sheet & Forensics (leverage appropriate to sector, forensic flags)
  5. Management Credibility (from the Promise Tracker)
  6. Ownership Flow (promoter, pledge, FII/DII/MF accumulation or distribution)
  7. Momentum & Sector Regime (relative strength, sector regime)
  8. Macro Fit (sensitivity to current macro regime and active shocks)
- Output: 0–100 score, pillar breakdown, top positive and negative drivers, data as-of date, and confidence (data completeness).

### 6.2 Report Card (the differentiator)
- Compute historical scores strictly point-in-time and publish: decile returns, information coefficient, hit rate, turnover, drawdowns, with transaction costs — for every frozen version.
- Maintain a **live forward record** starting from each version's freeze date.
- Show failures honestly. A null result is a valid result.

### 6.3 Research bot
- KASAUTI chat answers questions using tools over TRIKAL's database (safe, read-only, parameterised query layer — not free-form SQL against production), and **cites every number** with its source and date. If data is missing, it says so; it never guesses figures.
- **Bull vs Bear debate mode:** two agents argue a company using only TRIKAL data; KASAUTI summarises where the evidence is stronger and what would change the view.
- Natural-language screening, e.g. "companies where management beat guidance 3 quarters in a row and MF holding is rising".
- Uses an LLM provider abstraction so models can be swapped.

---

## 7. Architecture

```
/pipeline   Python — ingestion, parsing, PIT storage, corporate-action adjustment, scheduling
/analytics  Python — metrics, playbook rule engine, valuation, forensics, sensitivities, backtests
/kasauti    Python — scoring, report card, LLM extraction (concalls), chat/debate agents
/api        FastAPI — typed REST/WebSocket API, as_of on every endpoint
/web        Next.js (App Router) + TypeScript — the terminal
/config     Sector playbooks, score versions, source registry
/docs       ARCHITECTURE, DATA_SOURCES, FORMULAS, SECTOR_PLAYBOOKS, UI_SPEC, DECISIONS (ADR log)
```

- **Storage:** PostgreSQL (+ TimescaleDB for time series) as the canonical bitemporal store; Parquet + DuckDB for analytics and backtests. Data zones: raw (immutable source files) → staging → canonical.
- **Orchestration:** Dagster or Prefect; idempotent, incremental, retryable jobs with data-quality checks.
- **Identifiers:** ISIN master with NSE symbol / BSE code / name history; corporate-action and merger/demerger lineage.
- **LLM extraction:** structured outputs with schema validation, source-span references, confidence, and human-review queue for low-confidence extractions. Cache results; track cost.
- **Frontend:** React Three Fiber + drei + postprocessing (3D), TradingView Lightweight Charts (price), ECharts or visx (heatmaps, treemaps, Sankey, bands), TanStack Table with virtualisation (dense grids), cmdk (command bar), dockview or react-grid-layout (tiling), Zustand + TanStack Query, Framer Motion.
- **Testing:** unit tests for every formula, PIT/look-ahead tests, golden-file tests for parsers, visual regression for key screens.

### Candidate data sources (verify each one's current availability, format and terms before use; document in `/docs/DATA_SOURCES.md`)
- NSE / BSE: bhavcopies, corporate announcements, financial results (incl. XBRL), shareholding patterns, corporate actions, bulk/block deals, insider-trading disclosures, index constituents history.
- AMFI (MF scheme portfolios), credit-rating agency press releases.
- RBI DBIE, MOSPI, PIB, Union Budget documents, CGA, GST statistics, DGTR notifications, SEBI circulars, PPAC (fuel), CEA (power).
- Global: FRED, World Bank / IMF, public commodity price sources, GDELT (geopolitical events).
- Respect robots.txt and terms of use, rate-limit and cache. The project is personal-use first; licensing for public redistribution will be reviewed before any public launch — keep the source registry ready for that.

---

## 8. Build plan (milestones)

Work strictly in this order. At the end of each milestone: run tests, update docs, write a short `CHANGELOG` entry, and **stop for review**.

- **M0 — Plan only (no app code):** read this prompt fully; produce `ARCHITECTURE.md`, `DATA_SOURCES.md` (with verified status of each source), `SECTOR_PLAYBOOKS.md` (draft), `UI_SPEC.md` (screens, panel system, command grammar, design tokens), and a risk list (data gaps, legal, performance). Ask your open questions. Stop.
- **M1 — Security master & prices:** full universe incl. delisted, ISIN mapping history, daily prices, corporate actions, adjusted series, index-membership history. PIT tests.
- **M2 — Fundamentals & ownership:** results (standalone/consolidated, quarterly/annual, restatement-aware), shareholding patterns, sector classification history. PIT tests.
- **M3 — Terminal shell:** design system (Obsidian & Gold), command bar, tiling workspace, Time Spine wired to `as_of`, Company Desk v1 (financials, DuPont tree, Cash River, peers, What Changed).
- **M4 — Sector playbook engine + Valuation Lab** (incl. reverse DCF, scenarios, forbidden-method enforcement).
- **M5 — Macro, Policy & Geopolitics data** + Transmission Engine + Exposure Theatre + shock simulator.
- **M6 — Concall intelligence:** transcript ingestion, Promise Tracker, tone drift, Management Credibility.
- **M7 — KASAUTI v1:** scoring, explainability, PIT backtest, Report Card; freeze v1.
- **M8 — KASAUTI chat + Bull/Bear debate**, thesis tracker + alerts, report generator.
- **M9 — Forensics radar, events calendar, screener, performance pass, deployment.**

---

## 9. Working rules

- Read existing code and docs before changing anything. Keep an ADR log in `/docs/DECISIONS.md` for every significant choice.
- Small, reviewable commits with clear messages. Tests alongside code.
- Ask before deviating from this architecture or adding paid services.
- When a finance question is ambiguous, choose the conventional professional treatment, document it, and flag it.
- Never silently drop data or fill gaps; show "not available" explicitly.
- Prefer boring, reliable infrastructure; spend creativity on the research features and the UI.
- At the start of every session, re-read this file and `/docs/DECISIONS.md`.

**Begin with M0.**
