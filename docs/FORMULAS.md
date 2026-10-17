# TRIKAL — Formulas & Conventions

Every displayed number links to an entry here. Status: M1 entries (time, identity, prices, index
membership). Financial-statement formulas (Ind AS treatment, EBITDA, ROIC, …) are added in M2/M4.

---

## Time conventions

| Fact | `known_at` | Precision | Rationale |
|---|---|---|---|
| EOD price (bhavcopy row) | trade date 16:00 IST | `convention` | The close is final after the 15:30 close (closing session/VWAP); the bhavcopy is published after that. A query at 11:00 on day D never sees D's close. |
| Price-adjustment event | ex-date 09:00 IST | `convention` | Effective at the pre-open of the first session on/after the ex-date. |
| NSE corporate action | `caBroadcastDate` if present, else ex-date 09:00 IST | `exact` / `imputed` | Imputation is conservative: no later than the moment the price adjusts. |
| Symbol / name change | effective date 00:00 IST | `imputed` | The exchange circular usually precedes it; using the effective date is never early. |
| NSE delisting | delisting date 23:59:59 IST | `day` | |
| Index membership: interval opens | inclusion press-release date 23:59:59 IST | `day` | |
| Index membership: interval closes | exclusion press-release date 23:59:59 IST | `day` | Before that, the interval is stored and returned as open-ended. |

An `AsOf` without a timezone is rejected. `AsOf.end_of(D)` = D 23:59:59 IST.

**Tradability (backtests, ADR-003):** a fact known at `t` is first tradable at the open of the
first session strictly after `t`.

---

## Security identity (ADR-011)

`security_id = "S:" + ISIN[0:9]`, i.e. country + issuer type + 4-char issuer code + 2-char security
type. A face-value change produces a new ISIN serial under the same issuer and type, so the security
keeps one id across splits.

The equity universe is NSE series `EQ, BE, BZ, BT, SM, ST, SZ` and BSE type `Q`/`STK`, restricted to
ISINs `INE…01…` / `IN9…01…` where an ISIN is present. REIT/InvIT units, ETFs and bonds are not in the
equity master. They can still be index constituents; see "Index membership" below.

Rows without an ISIN (NSE before Aug-2011, BSE before ~2017) inherit identity in this order:

| Method | Rule | Confidence |
|---|---|---|
| `isin` | the row carries a valid company-equity ISIN | 1.00 |
| `code_continuity` | same exchange code, same trading *episode*, before the episode's first ISIN-bearing row | 0.95 |
| `symbol_chain` | NSE `symbolchange.csv` links the episode to a later episode that has an ISIN | 0.90 |
| `cross_exchange_price` | an NSE listing with no ISIN closes within ±2% of exactly one BSE scrip code on all of 6 sessions sampled across its life; it takes that BSE code's identity (often ISIN-based, because BSE codes are stable into the ISIN era) | 0.85 |
| `synthetic` | nothing reachable: `X:<exchange>:<code>:<first trade date>` | 0.80 |

A **trading episode** is a run of sessions for one exchange code. A new episode starts after a gap of
more than 250 sessions, or after an NSE delisting record. This stops a reused symbol from inheriting
the previous company's identity.

---

## Corporate actions & adjusted prices (ADR-009, ADR-012)

Prices are stored **unadjusted**. The adjustment `factor` of an event multiplies every price dated
strictly before its ex-date. Volumes are divided by the same factor.

| Action | Factor | Notes |
|---|---|---|
| Split / consolidation, FV `old → new` | `new / old` | e.g. Rs 10 → Re 1: 0.1 |
| Bonus `a:b` (a new for every b held) | `b / (a + b)` | 1:1 → 0.5; 1:2 → 2/3 |
| Rights `a:b` at issue price `P` (cum price `C`) | `TERP / C`, `TERP = (b·C + a·P) / (a + b)` | `P = FV + premium` when the subject gives a premium |
| Ordinary dividend | none (price series) | Recorded for total-return series |
| Demerger, capital reduction | from the price signal only | No reliable text factor; needs the exchange or observed signal |

**Signals and decision rules.** Every comparison requires the previous close to come from the
*immediately previous session* on the true exchange calendar, with no unknown days in between:

- `implied = PREVCLOSE(t) / CLOSE(prev session)`, which is the exchange's own base-price adjustment.
  Verified: NSE legacy bhavcopies do **not** adjust PREVCLOSE. On TCS's 1:1 bonus (ex 31-May-2018),
  PREVCLOSE is 3514.10 while the close is 1741.05. So this signal is rarely present, and
  announcements are the primary source.
- `parsed` = the factor computed from the announced action (table above).
- `observed = CLOSE(t) / CLOSE(prev session)`.

| Agreement | Condition | Applied |
|---|---|---|
| `match` | `|implied/parsed − 1| ≤ 2%` | yes (implied) |
| `mismatch` | both present, disagree | yes (implied), DQ issue |
| `parsed_confirmed` | `0.80 ≤ observed/parsed ≤ 1.25` | yes |
| `parsed_unconfirmed` | no clean observation | yes, DQ issue |
| `parsed_price_disagrees` | observed move contradicts it | **no**, DQ issue |
| `implied_confirmed` | no announcement; implied factor beyond ±25% (split/bonus-sized) **and** the close follows it | **no**, DQ review queue: base-price resets after suspensions look identical (e.g. factors > 1 with no consolidation) |
| `implied_only` | no announcement; small or unconfirmed (PREVCLOSE disagrees with the true previous close on ~1–2% of rows in some eras for reasons unrelated to corporate actions) | **no** |
| `unverifiable` | implied factor across a gap or unknown days | **no**, DQ issue |

**Adjusted price as of D** = `price(t) × Π factor(e)` over applied events `e` with
`t < ex_date(e) ≤ D` and `known_at(e) ≤ D`. A terminal rewound to D therefore shows exactly the
adjustments that had happened by D.

**Unexplained jumps.** A clean session-to-session move outside `[0.60, 1.60]` with no applied event,
and larger than ₹0.10 in absolute terms (so two-tick moves in penny stocks are ignored), is logged as
`unexplained_price_jump` with a suggested factor. It is never applied automatically.

---

## Trading calendar

`exchange_day(exchange, d, status)` is derived from the bhavcopy fetch log:

- `session`: a valid file exists.
- `no_session`: NSE returned 404, or BSE served its placeholder page on a day NSE also did not trade.
- **Absent = unknown**: not fetched, fetch error, or BSE placeholder on an NSE session day.

Unknown is never treated as a holiday.

---

## Index membership (reconstructed, RISKS R-4)

There is no official history file. Membership is rebuilt backwards from the official current
constituent file, using NSE Indices press releases (1998 →):

1. Events are parsed from each release's Nifty 500 sections (old names: Crisil 500, S&P CNX 500,
   CNX 500). Look-alike indices (Nifty500 Multicap, Equal Weight, …) are excluded.
2. Each event is resolved to a security: by symbol where printed (≈2013 →), otherwise by company name
   (fuzzy match ≥ 0.80 against every name source we hold, restricted to securities trading on NSE
   around the effective date). Unresolved names stay in the walk as `U:<name>` placeholders with
   confidence 0, so counts remain correct and the gap remains visible.
3. A later release repeating the same change within 120 days supersedes the earlier one.
   Human-reviewed corrections with citations live in `config/index_overrides.yaml` (voided
   releases, revoked events, events stated in unparseable tables).
4. The walk undoes each effective date's changes and records the member count in
   `index_count_check`. The Nifty 500 must hold 500.
5. Placeholder constituents in the official file (e.g. "Dummy HEG Ltd.", ISIN `DUM…`) are excluded
   and logged.

Membership rows are bitemporal: `[valid_from, valid_to)` with `known_at` as in the time table above.
Members present before the earliest parsed release get `method = pre_coverage` (true start unknown).

---

## Financial statements (M2)

**Sources and eras** (verified on real filings, 2026-10-12)

| Filing period | Document | Content |
|---|---|---|
| FY2008 – FY2017 | NSE "Financial Results Details" HTML page | Part I income statement (quarterly or annual) and Part II shareholding/pledge. **No balance sheet, no cash flow.** Amounts in ₹ lakh. |
| Jun-2017 → Sep-2024 | Results XBRL (`INDAS`, `BANKING`, `NBFC_INDAS`, `NONINDAS`) | Income statement; balance sheet and cash flow in half-yearly and annual filings; segment data |
| Dec-2024 → | SEBI Integrated Filing of type "Financials" (`INTEGRATED_FILING_INDAS…`) | Same content as the Ind AS XBRL. The "Governance" integrated filings are not financial statements and are ignored. |

**Units.** All money is stored in rupees (INR). XBRL values are already in full rupees (the declared "level of
rounding", lakhs or crores, only describes precision). Old HTML amounts are scaled by the unit declared in the
page header. Per-share data (EPS, face value) is ₹ per share and is never scaled. A value shown as `-` on an
old page means "not reported" and is skipped, never stored as zero.

**Periods: the column rule.** XBRL contexts are named by column: `One…` = the current reporting period
(the quarter), `Four…` = year-to-date (the full year in a Q4 filing). The XML dates of the `Four` contexts
repeat the quarter's dates and are **wrong** (TCS FY24: the `FourD` revenue of ₹2.41 lakh cr is dated
Jan–Mar 2024). Therefore:

- `One`, duration: the context's own start and end (a quarter; 6 months in some half-yearly filings)
- `Four`, duration: [financial-year start, reporting-period end] (3, 6, 9 or 12 months)
- instants (balance sheet): the context's date
- any other column (`Two`, `Three`, …): not interpreted; counted and skipped, never guessed

`period_months` records what was assigned, so consumers never assume a quarter. For old HTML pages the period
comes from "Relating to", "Period Ended", "Cumulative" and "Financial Year" in the page header.

**Basis.** `standalone` or `consolidated` as declared in the filing. `PitReader.financials(basis='auto')`
returns consolidated where the company had reported it by the as-of date, else standalone, and says which.

**Bitemporal storage.** `known_at` is the exchange's broadcast time of the filing (exact, to the second).
Every number of every filing is loaded (`fact_financial_all`). The point-in-time table `fact_financial` keeps
a row only when the value differs from the previously known value of the same (company, basis, concept,
dimensions, period). A later filing that repeats a comparative unchanged adds nothing; a changed value is a
restatement (`is_restated`). A query as of D takes, per key, the latest row with `known_at ≤ D`. When the
broadcast time is missing, `known_at` is imputed as period end plus the statutory deadline (45 days; 60 for
Q4 and annual) and marked `imputed`.

**Line items.** `config/line_items.yaml` maps a canonical line item (`revenue_from_operations`,
`profit_before_tax`, `cash_flow_operations`, …) to source concepts in priority order: the Ind AS taxonomy
concept first, then the old-page label. The returned value carries the concept actually used and its priority
rank, so a fallback (for example pre-GST revenue "net of excise duty") is always visible. Segment
(dimensional) facts are stored but not returned by `financials()`.

**Accounting-identity checks** (`trikal check-financials`; pass rates in `docs/reports/coverage.md`):
Income − Expenses = PBT before exceptional items; PBT before exceptional + exceptional = PBT; PBT − tax =
profit from continuing operations; Assets = Equity + Liabilities; operating + investing + financing cash flow =
net change in cash. Tolerance is 0.5% of magnitude or ₹5 lakh. For old pages, PBT must reconcile under at
least one of the template conventions companies use (finance costs inside or outside "total expenses"; other
income separate or already inside income). A failure is a data-quality row with the evidence, not a silent fix.

**Not yet computed (M4):** TTM, EBITDA (Ind AS 116 views), ROIC, working-capital days, DuPont. These belong to
the metric registry with the sector rules.

## Ownership (M2)

- **Shareholding pattern** per quarter. Promoter and public percentages come from the list API for every
  filing (2015 →). The category detail (mutual funds, insurance, FPI, retail, …) comes from each quarter's SHP
  XBRL, which the list API exposes for roughly the last 20 quarters (Sep-2021 →).
- The stored percentage is the **filed** figure after normalising its scale (some filings use fractions such as
  0.7177, others percent such as 71.77, decided per file from the "total shareholding pattern" context). If it
  differs from the share-count based percentage by more than 0.05 pp (for example a base that includes
  depository receipts) a `shp_pct_mismatch` data-quality row is written.
- **Revisions.** The exchange list keeps only the revised record, stamped with the revision's broadcast time.
  `known_at` is that time and the row is flagged. The original values are not retained, so a point-in-time view
  between the original submission and the revision shows the quarter as unavailable instead of leaking the
  revised numbers backwards.
- **Pledge.** The exchange serves only the latest quarter. Every fetch is kept in the raw zone, so history
  accumulates from the first fetch (Oct-2026). Fields: promoter holding %, pledged % of promoter holding,
  pledged % of total shares, number of pledged shares. For 2012–2017, pledge and encumbrance counts also appear
  in Part II of the old result pages; they are accepted only when public + pledged + non-encumbered shares
  reconcile with the stated percentages.
- **Groups** (`PitReader.ownership`): promoter, public, mutual funds, insurance, FPI (categories I + II),
  foreign institutions, domestic institutions, retail. A group missing from a quarter's filing is `None`, never 0.

## Sector classification (M2)

NSE does not publish classification history. `classification` rows carry their provenance:

| scheme / method | confidence | meaning |
|---|---|---|
| `NSE_INDUSTRY` / `official_snapshot` | 1.0 | label in an NSE constituent file (Nifty 50/100/200/500/Total Market/Microcap 250) on that date. Accumulates with every `trikal fetch-index`. |
| `NSE_INDUSTRY` / `assumed_static_backward` | 0.5 | the earliest official label projected backwards. Companies rarely change sector, but this is an assumption; use `min_confidence=1.0` for official-only. |
| `NSE_LEGACY` / `press_release` | ≤ 0.8 | the industry printed beside the company when it joined the S&P CNX 500 (1999 → about 2010), in the old vocabulary. |

The label is NSE's sector level (22 sectors) of the India Industry Classification. The macro-sector, industry
and basic-industry detail is not published per company.

---

## Sector rules and metrics (M4)

**Which playbook applies.** `config/playbooks/mapping.yaml`, evaluated top to bottom, first match wins, and the
answer carries `how` and a confidence: explicit override 1.0 → filing family (`BANKING`, `NBFC_INDAS`) 0.9–0.95 →
name rule inside a sector 0.6–0.8 → NSE sector default 0.4–0.8 → fallback (`generic_nonfinancial`, 0.2). Nothing
is silently defaulted; a low-confidence resolution is attached to every metric as a warning.

**Merge.** global → parent chain → base → overlays. Forbidden sets are unions: an overlay can add restrictions,
never remove them. Loading fails if a playbook forbids something it lists as a key metric or primary valuation,
or uses an unknown valuation id.

**Three different "no number" states** (never confuse them):

| State | Meaning | Example |
|---|---|---|
| `Forbidden` (raised) | sector policy: the computation does not run | EBITDA, EV or debt/equity for a bank |
| `Undefined` | a data condition makes the number meaningless | P/E when trailing profit ≤ 0 (G1); growth from a non-positive base |
| `NotAvailable` | the inputs are missing, named, or need a source we do not hold yet | NIM ("needs investor presentation (M6)") |

`not_primary` is a fourth, softer rule: the metric may be computed but may not be the primary valuation
(P/E for life insurers, cement, metals, holdcos, and for loss-makers).

**Definitions** (all trailing, INR, one basis per computation; `consolidated` if the company reported it
within 400 days, else `standalone`; never mixed):

| Metric | Formula |
|---|---|
| TTM flow | sum of the latest four consecutive quarters (gaps 80–100 days), or the latest 12-month figure if newer; older than 18 months → NotAvailable |
| EBITDA | revenue from operations − (total expenses − finance costs − depreciation). Excludes other income and exceptional items. Reported **post-Ind AS 116** (lease payments are not in the results filings), flagged on every value |
| EBIT / margins | EBITDA − depreciation; margins ÷ revenue from operations |
| Shares outstanding | paid-up equity capital ÷ face value, divided by the factor of any split/bonus that went ex after that filing became known |
| Market cap | last close (≤ 10 days old) × shares |
| Net debt | borrowings (current + non-current) − cash & equivalents − other bank balances. Investments are not netted |
| EV | market cap + net debt + non-controlling interest (book) |
| P/E | market cap ÷ trailing profit attributable to owners |
| P/B | market cap ÷ equity attributable to owners |
| ROE, ROA | trailing profit ÷ closing equity (assets) |
| ROCE | EBIT ÷ (total assets − current liabilities) |
| Receivable / inventory / payable days | closing balance ÷ (revenue, or COGS = materials + traded purchases + inventory change) × 365 |
| Altman Z″ (emerging-market, non-financials) | 3.25 + 6.56 WC/TA + 3.26 RE/TA + 6.72 EBIT/TA + 1.05 BookEquity/TL (reserves = other equity) |
| FCF | latest 12-month operating cash flow + purchases of PPE and intangibles (reported as outflows) |

Inputs that came from the pre-2018 HTML pages add a warning (`old_page_input:…`); where companies typed the
template inconsistently the warning says so.

**Valuation** (`valuation.py`, pure functions; `lab.py` supplies point-in-time inputs). No hidden defaults:
rates and growth are always passed in, labelled `user`, or requested from `template_assumptions` and labelled
`template` (conventional starting values the user must confirm). Missing assumptions raise an error naming them.

- DCF (FCFF): growth fades linearly from `g_start` in year 1 to `g_terminal` in year N, then Gordon growth;
  EV = PV(flows) + PV(terminal); equity = EV − net debt − minorities. FCFF base = latest 12-month
  (operating cash flow + capex) + finance costs × (1 − effective tax rate, bounded 0–40%). Requires WACC > g.
- FCFE, DDM: same fade at the cost of equity (DDM per share).
- **Reverse DCF**: bisection for the year-1 growth at which DCF equity value equals market cap. If the market
  value lies outside what growth in [−30%, +80%] can produce, the answer is "no solution", never a clamped number.
- Justified P/B = (ROE − g) / (Ke − g); justified P/E = payout × (1 + g) / (Ke − g).
- Residual income: B0 + Σ PV[(ROE_t − Ke) B_{t−1}] + terminal residual income (persistence-adjusted).
- SOTP: Σ stake × part value − holdco net debt, then × (1 − holdco discount). Unlisted parts are flagged `assumed`.
- NAV, EV/tonne, EV/MW: arithmetic on user-supplied asset values or capacity.
- **Scenarios**: explicit bear/base/bull with probabilities summing to 1 → a per-share *range* and the
  probability-weighted value. Output is never a rating or target price; `value_to_price` is a ratio.
- **Relative valuation (G4)**: a multiple is reported with its percentile in the company's own history
  (month-end observations over 5 years, each computed strictly as of its date) and among same-sector, same-playbook
  peers as of the same date. Fewer than 8 observations or `min_peers` comparable peers → no percentile, with a
  warning. A cyclical company with a low P/E at margins in the top 20% of its own history gets
  `cyclical_peak_trap`.

## Banks (2026-10-13)

Bank filings differ from industrial ones, so three rules live in `config/line_items.yaml` and `PitReader.financials`:

- **Equity** has no line in a bank balance sheet: `equity_owners` falls back to `sum: [Capital, ReservesAndSurplus]` (concept shown as `sum:Capital+ReservesAndSurplus`). Used by ROE, P/B and assets/equity.
- **Asset quality is filed on the standalone statement.** The consolidated block of the same results file carries a placeholder `0.0` ("not reported here"). Line items marked `prefer_basis: standalone` + `zero_is_missing: true` (GNPA/NNPA amount and %, CET1, AT1, reported ROA) take the standalone value and drop zeros, so a placeholder is never shown as a real 0% NPA (this showed HDFC Bank's GNPA as 0 until 13-Oct-2026).
- Metrics: `nii` = interest earned − interest expended (TTM); `nii_to_assets` = NII / average total assets (a proxy: reported NIM divides by average interest-earning assets, which filings do not give); `cost_to_income` = operating expenses / (NII + other income); `ldr` = advances / deposits; `credit_cost` = TTM provisions / average advances; `gnpa_pct`, `nnpa_pct`, `cet1` as reported. Balance-sheet items use the latest date and the one about a year earlier (half-yearly for banks); with a single date the output carries `single_balance_sheet_date`.
- Still needing other sources (M6): NIM, CASA, PCR, slippage, total CAR (the filing gives CET1 and AT1, not Tier 2).

## Sector sensitivities, SHOCK and exposure context (M5, 2026-10-13)

For every sector s and macro driver d, at every month-end t the pipeline fits, over the trailing 60 months (at least 36),
`r_s,m = a + b · Δd_m + k · r_mkt,m + ε`, where `r_s` is the equal-weight return of the sector's members that month (members as
known then, split/bonus adjusted prices), `r_mkt` the equal-weight return of all members, and `Δd` the driver's monthly change
(log change for prices, percentage points for rates). `b` is the response **relative to the market**; the market's own response
`m` comes from the same regression on `r_mkt` (stored under sector `__MKT__`). A window is usable only from `usable_from`
(the later of the window's last month-end close and the release time of the newest driver observation in it), so a rewound as-of never sees a later estimate.

- Impact of a shock Δ on sector s = `b · Δ` (relative) + `m · Δ` (market) = total. Combined shocks add the per-driver impacts.
- Shock grammar: `CRUDE +20` (percent), `INR 90` (target level, converted with the driver's current value), `REPO +50bp`
  (call-money rate stands in for the REPO), joined by `&`. Units: log change for price drivers, percentage points for rates.
- Confidence: high = n ≥ 48, |t| ≥ 2.5, mostly real sector labels; medium = n ≥ 36 and |t| ≥ 1.65; else low (dimmed in the UI).
  A shock larger than 3× the driver's typical monthly standard deviation is flagged as a straight-line extension.
- It is an estimated price response from history. It is not an earnings forecast, not a causal channel, and not advice.
- Chokepoint intensity = dated news items matching the area's keyword pattern in the trailing 3 months, as a percentile of the same
  count for every earlier 3-month window up to the as-of. Context only; never an input to any metric.

## KASAUTI v1 (2026-10-16, config/scores/kasauti_v1.yaml)

For a company C on scoring date t, with peer set P (same playbook among the Nifty 500 members on t; the parent group if |P| < 8):
- metric percentile `p(m) = (#{x < v} + 0.5·#{x = v}) / n` over the peers with a value (at least 5), flipped (`1 − p`) when lower is better;
- pillar score = Σ w_m·p(m) / Σ w_m over the metrics with a value; pillar coverage = Σ w_m (with value) / Σ w_m (all); a pillar below 50% coverage is dropped;
- score = 100 · Σ W_k·pillar_k / Σ W_k over kept pillars, requiring at least 3; confidence = Σ W_k·coverage_k over kept pillars (weights sum to 1, so a dropped pillar lowers it);
- driver points of a metric = 100·(W_k/ΣW)·(w_m/Σw)·(p(m) − 0.5).
Ownership inputs are changes over about four quarters (promoter, and mutual funds + FPI + insurance together, in percentage points) and the pledge as % of total shares (live record only: the exchange keeps no pledge history). Momentum is the adjusted close 21 sessions ago over the close 252 sessions ago (12-1 months) and the 126-session return.
Report card: forward return = open at the first session on or after (entry + h months) over the open of the first session after the scoring date; rank IC = Spearman correlation of score and forward return per date; t-statistic of the mean IC with Newey-West (Bartlett) weights and lag `ceil(h/3) − 1`; the portfolio holds the top 10% equal weight from one scoring date to the next and pays `cost_per_side` on every name bought or sold.

## KASAUTI v2 (2026-10-18, config/scores/kasauti_v2.yaml)

Same scoring as v1 plus two pillars and a few weights moved (industrial: quality .20, growth .14, valuation .18, balance .13, ownership .09, momentum .13, earnings quality .08, credibility .05; financial: no earnings quality, quality .24, growth .15, valuation .19, balance .15, ownership .09, momentum .13, credibility .05).
- `cfo_to_profit` = latest 12-month cash flow from operations / profit attributable to owners of the same 12 months (undefined if profit <= 0); `accruals_ratio` = (profit - cash flow from operations) / total assets (lower is better); `other_income_share` = trailing other income / trailing profit before tax (lower is better; undefined if PBT <= 0). Not defined for financials.
- `promise_kept` = (Σ s + 0.5·2) / (n + 2), s = 1 for a statement judged delivered, 0.5 partially, 0 missed; n = statements judged with results public on the scoring date; none if n < 2. Ranked among every scored company of the date (a metric marked `all` in the config), not within the sector.

