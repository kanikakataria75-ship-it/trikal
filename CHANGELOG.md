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

## M4: Sector playbook engine + Valuation Lab (CODE COMPLETE for review, 2026-10-12)

Built ahead of the UI milestone because it needs no UI; it runs on the M2 data as it arrives.

**Sector rules (enforced in the engine, not the UI)**
- 30 playbooks + 4 overlays as YAML (`config/playbooks/`): the 27 sectors of the spec, global rules and metric
  groups, parents, overlays (holdco, PSU, cyclical, loss-making). Union-only restrictions; validated at load.
- Company -> playbook by explicit override, filing family, name rule or NSE sector, with `how` and a confidence.
  Checked against the real universe: banks 34 (SBI, PNB, Axis ...), NBFC/HFC 42, capital markets 12, insurers 10,
  hospitals 4, ... ; the review found and fixed four rule bugs (see tests).
- `Engine.compute` raises `ForbiddenMetric` before any computation (EBITDA, EV, leverage, working capital,
  Altman for financials); `Lab.run` raises `ForbiddenMethod` (FCFF DCF for banks) before reading any input.
  Three distinct "no number" states: Forbidden (policy), Undefined (data condition, e.g. P/E for a loss), NotAvailable
  (inputs or an external source missing, named).

**Metrics** (`metrics.py`): revenue/PAT/EBITDA/EBIT/margins, net debt, EV, market cap (shares rolled forward for
later splits/bonuses), P/E, P/B, EV/EBITDA, EV/sales, ROE, ROA, ROCE, coverage, working-capital days, Altman Z'',
FCF and yield, growth. Every value carries its inputs with filing and `known_at`, plus warnings (old-page input,
post-Ind-AS-116 EBITDA, low playbook confidence, caution text). Sector metrics that need concalls or regulators
(NIM, CASA, ARPOB, order book ...) answer "needs <source>".

**Valuation Lab** (`valuation.py` + `lab.py`): FCFF/FCFE DCF, reverse DCF ("what growth is priced in", with a
true "no solution"), DDM, justified P/B, residual income, SOTP with holdco discount, NAV, EV/tonne, EV/MW,
bear/base/bull ranges with probabilities, sensitivity grids, multiples vs own history and sector peers (G4,
cyclical-peak-trap warning). No hidden defaults: assumptions are `user`, `pit` or `template`, and the output says which.

**Tests:** 115 in total (60 new): closed-form identities for every model, hand-checkable synthetic company for the
metrics, enforcement mutation-checked (removing the checks fails 2 tests), point-in-time visibility, basis never mixed.
`trikal analyze <CODE>` shows playbook, allowed/blocked items and metrics with reasons.

**Honest limits:** values for most companies read "missing X" until the M2 download finishes; the name rules are
heuristics to review (RISKS R-31); sector operating metrics wait for M5/M6 (R-32); no UI yet.

## M3: Terminal and home page (CODE COMPLETE for review, 2026-10-13)

**Terminal** (`web/`, Next.js + React Three Fiber; API in `api/`)
- dockview workspace with 11 function panels: DES (identity, playbook, 3D touchstone of the price history), GP (prices with
  gold verticals for every applied split/bonus), FA (statements with lineage, restated and pre-2018 marks), DUP, CR (Cash
  River), RV (peers), WC (what changed), OWN, DCF (Valuation Lab: methods the sector allows, labelled assumptions), EVT, HELP.
- Command bar (`/`, Ctrl+K): `TCS FA`, `ASOF 2008-10-24`, `ASOF -5Y`, history; delisted names searchable.
- Kaal-Rekha time spine bound to the global as-of; per-panel pinning (then vs now); rewound frame; lineage/dense/CB modes.
- Read API: every endpoint requires `as_of`, refuses the future, keeps value states (value / n.m. / n/a / forbidden).

**Home page**
- Touchstone hero: real adjusted price histories drawn as a gold streak on a 3D basalt stone; live NSE tape; command search.
- Time Machine: any session since 1994 as a 3D city of that day's Nifty 500 members (area = turnover, rising/sinking by the
  move), open/close morph, breadth gauge, closing prints with today's-share equivalents, the weeks before, labelled hindsight,
  a news lower-third built from that day's data and exchange announcements, the world and India that week (Wikipedia, CC BY-SA,
  context only), era TV frames, tour and full-screen modes.
- Survivorship: every Nifty 500 cohort since 1999 and one cell per real company of a chosen year.

**Data fixes found while building the UI**
- `last_price` could return an institutional-lot (IL) print instead of the EQ close (e.g. SBIN 24-Oct-2008 ₹1,245 vs ₹1,164.75);
  this also fed market cap. Fixed with series priority + test.
- Splits on crash days were rejected (JINDALSTEL 21-Jan-2008: 5:1 split and −27%); a downside-only wide band now applies pure
  splits/bonuses (`parsed_confirmed_wide`, DQ-logged). Parser now reads "Spl-Rs10 To Rs2" and spelled-out face values.
- Index survivorship counts separated old index names never matched to a security (`unresolved`) from vanished companies.
- 134 tests (19 new in M3).

**Pending** run `trikal adjust` once more (≈ 19 min, API stopped) to apply the narrowed wide band (1 event affected).

## M5: Macro, policy & geopolitics (IN PROGRESS, started 2026-10-13)

**Step 1 — macro data layer (done)**
- `macro_series` / `macro_obs` (bitemporal, ADR-020), registry `config/macro_series.yaml`, `trikal fetch-macro`.
- 27 series: USD/INR (1973–), Brent (1987–), US 10Y (1962–), Fed funds, broad dollar, VIX, India 10Y, India interbank,
  India CPI (OECD 1957–; MOSPI 2013–2025), 17 Pink Sheet commodities (1960–). ~150k observations.
- `PitReader.macro / macro_latest / macro_series`; API `/api/macro`, `/api/macro/{id}`; terminal `MACRO` desk
  (tiles by category with y/y and ≈ for imputed release times, full-history chart). Rewind works (24-Oct-2008: INR 49.25, +24.7% y/y).
- 5 tests (missing ≠ zero, vintages, MOSPI filtering, imputed rules, revisions invisible until released).

**Next:** sector sensitivities (PIT regressions) → Transmission Engine (3D) + `SHOCK` → policy/event calendar → Exposure Theatre.

**Interface modes (2026-10-13):** `◆ CINEMA | ▮ PRO` switch (remembered; `MODE PRO`). PRO = flat dense workstation that opens
straight into the terminal, six-group layout, F-key bar, 2D sparkline instead of the 3D stone, and the new `MAP` heatmap panel
(shared treemap layout with the 3D city). Home page redirects PRO users to `/terminal`. See UI_SPEC §10.

**Step 2 — sector sensitivities, Transmission Engine, SHOCK, Time Spine context, Exposure Theatre (2026-10-13)**
- `trikal build-sensitivity`: monthly OLS per sector, trailing 60 months (min 36): sector return = a + b·Δdriver + m·market return,
  against 10 drivers (Brent, USD/INR, call-money rate as the REPO proxy, India 10Y, US 10Y, copper, iron ore, coal, gold, VIX).
  Relative beta + the market's own beta = total. `usable_from` keeps every window point-in-time. 19 sectors, 51,591 estimates
  (200 at the latest as-of); confidence high/medium/low from n, |t| and the share of back-projected sector labels.
- API `/api/transmission`, `/api/shock?q=CRUDE +20 & INR 90`, `/api/shock/companies`, `/api/context/markers`, `/api/geo`
  (all need `as_of`; future refused). A shock far outside the history (> 3× the driver's typical monthly move) now carries an
  explicit "straight-line extension" warning (found on real data: USD/INR +5% is a 5σ month).
- Terminal: `TX` (3D drivers → sectors → companies planes; flat driver × sector matrix in PRO) with the SHOCK box; `GEO`
  Exposure Theatre (dot-globe centred on India, trade arteries as arcs with moving light, chokepoint rings sized by dated-news
  intensity vs the area's own history, detail with sparkline, linked sectors, measured crude response, sourced items; flat map
  twin in PRO); Time Spine now carries policy / geopolitical / market markers (thinned to one per ~5 px, hover shows text and source).
  TX and GEO open full-window (Esc or any other function returns).
- Real-data check (12-Oct-2026): market beta to USD/INR −2.39 (t −3.8, high); Brent −0.11 (t −2.1); sector-level cells are
  mostly low confidence (160 of 190 sector×driver cells). Reported as is: no sector shows a sign-stable, high-confidence response
  to crude yet, so the table is a hint, not a forecast.
- Performance: `peers` took 20–33 s (DuckDB retried `import pandas` on every query; metrics re-read the same company inputs for
  each metric). Marker for pandas as absent + inputs shared per company/as-of inside an Engine: 6 s. 167 tests.
- Fixes: `PanelState` never renders children without data (it crashed DES/RV when a fetch failed and retried); drei `<Html>` labels
  (crash when the docking layout moves a panel) replaced by `components/three/Label.tsx` in TX/GEO.
- Holding pattern: after the refresh, 16 quarters of category detail (MF / insurance / FPI / promoter / public, pledge) for the
  companies already downloaded; the downloader continues (detailed history, then ~39k XBRL results, each phase followed by a refresh).

## Free-data upgrades instead of LLM extraction (2026-10-16)

No LLM budget, so the M6 gaps are filled from what the exchange already files in structured form, and the rest is rule-based.
- **Segments (`SEG`)**: the XBRL carries each segment's real name as a text fact in the member's context ("Oil to Chemicals (O2C)",
  "Banking, Financial Services and Insurance"); the parser now uses it as the dimension value, so a business has the same key across filings
  (`trikal relabel-dims` re-read the 52,921 filings that had dimensional facts: 680k facts). `PitReader.segments`, `/api/company/{code}/segments`,
  terminal panel `SEG`: stacked revenue by year/quarter plus the latest period's revenue, share, result, margin, assets. Works for
  Reliance, TCS, L&T, ITC, HDFC Bank and ~630 other Ind AS filers from ~FY2019. Plug lines (unallocated / eliminations) get no margin.
- **Other-expense breakdown** members are labelled the same way (Power, Fuel and Water ...), ready for a cost-structure view.
- **Reported coverage ratios**: `dscr` / `iscr` as the company states them (`FA` group "Ratios as reported"), ~670 companies from 2019;
  definitions differ between companies, so they are shown as reported, never recomputed.
- Peers endpoint cache (pinned as-of forever, NOW for 10 min). 171 tests.
