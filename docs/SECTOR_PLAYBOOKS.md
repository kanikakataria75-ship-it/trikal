# TRIKAL — Sector Playbooks (M0 draft)

Playbooks are the finance-rule backbone: they decide which metrics exist, which valuation methods may run, and how peers are formed. They are **enforced in the engine** (ARCHITECTURE §5). The UI only reflects what the engine allows.

Status: **implemented in M4** (2026-10-12). The YAML files are in `/config/playbooks/` (`_global`, `financials`, `operating_sectors`, `overlays`, `mapping`); `analytics/trikal_analytics/playbook.py` loads, merges, validates and enforces them. This document remains the human-readable spec and rationale; where the two differ, the YAML is authoritative and DECISIONS ADR-018/019 explain the changes (e.g. loss-making is a `not_primary` overlay, not a prohibition).

---

## 1. Schema

```yaml
# /config/playbooks/banks.yaml
id: banks
version: 1
parent: financials                 # inherits forbidden list + global rules
label: Banks
membership:                        # how a company maps here (PIT, via classification history)
  nse_iic_basic_industry: [Public Sector Bank, Private Sector Bank, Other Bank]
  overrides: []                    # explicit ISIN overrides, each with a reason + date
peer_group:
  min_peers: 8
  fallback: financials
  split_by: [size_bucket]          # optional sub-grouping (e.g. PSU vs private banks)
key_metrics:                       # shown first on desks; inputs to KASAUTI pillars
  - nim, casa_ratio, gnpa_pct, nnpa_pct, pcr, credit_cost, slippage_ratio, car, cet1, roa, roe, ldr, loan_mix
valuation:
  primary:   [p_abv, justified_pb]
  secondary: [residual_income, pe]
forbidden:                         # engine raises ForbiddenMetric / ForbiddenMethod
  metrics: [ebitda, ebitda_margin, ev_ebitda, ev_sales, debt_to_equity, current_ratio, net_debt_ebitda,
            interest_coverage, altman_z, inventory_days, receivable_days, ccc]
  methods: [dcf_fcff, ev_multiples]
caution:                           # allowed, but rendered with a warning badge + reason
  - {metric: pe, reason: "Earnings swing with provisioning cycle; anchor on P/ABV"}
cycle: {type: credit_cycle, indicators: [system_credit_growth, gnpa_system, credit_cost]}
macro_sensitivities:               # priors only; estimated betas replace them in M5
  - {driver: repo_rate, channel: "NIM via EBLR repricing vs deposit lag", sign: "+ short-term for high-EBLR books"}
  - {driver: system_liquidity, channel: "cost of deposits", sign: "+"}
red_flags: [rising_slippages_with_falling_pcr, restructured_book_growth, evergreening_signals, rising_sma2,
            divergence_reported_by_rbi, concentrated_wholesale_deposits]
charts: [nim_trend, asset_quality_waterfall, casa_trend, pb_band, roa_tree]
sources:                           # citations for the rules above
  - "Damodaran, *Investment Valuation* 3e, ch. 21 (Valuing Financial Service Firms)"
  - "RBI Master Circular on Prudential Norms (IRACP) for NPA definitions"
```

**Overlays** (`psu`, `holdco`, `cyclical`) are partial playbooks merged *on top of* a base playbook. Precedence: `global → parent → base → overlays (in order)`. A metric forbidden at any level stays forbidden; an overlay may add forbidden items but never remove them (merge is a union).

**Mapping a company → playbook** (PIT): use the NSE/BSE India Industry Classification *Basic Industry* as of `as_of`; for pre-2022 dates use the reconstructed classification (DATA_SOURCES §2) and propagate its `confidence`. Conglomerates with no segment > 50% get the `holdco` overlay when listed-subsidiary value exceeds a threshold (rule in M4).

---

## 2. Global rules (encoded in the engine)

| ID | Rule | Rationale / source |
|---|---|---|
| G1 | **P/E is `Undefined` when EPS ≤ 0.** Never negative, never ranked. Same for any multiple whose denominator ≤ 0 (EV/EBITDA with EBITDA ≤ 0, P/B with negative book). | Standard practice. Negative multiples are meaningless and wreck percentiles. |
| G2 | **Financials** (banks, NBFC/HFC, insurers, AMCs/brokers/exchanges where noted) never compute EBITDA, EV-based multiples, debt/equity, current ratio, Altman Z, working-capital days. | Debt is raw material for a lender, not financing; EV is undefined (Damodaran ch. 21; CFA L2 Equity). |
| G3 | **Cyclicals** (metals, cement, commodity chemicals, sugar, upstream O&G, auto at segment level): if current margin percentile vs own 10-year history ≥ 80th, a low P/E produces a **`cyclical_peak_trap` warning** and valuation shifts to mid-cycle EBITDA (average of the full cycle, min 7 years). | "Buy cyclicals at high P/E, sell at low P/E" convention; Damodaran *Dark Side of Valuation* ch. on cyclical firms. |
| G4 | **Every multiple is shown vs own history AND vs peers**, never alone. The API returns the triple `(value, own_hist_percentile, peer_percentile)`; a bare multiple is not a valid response type. | Prompt §5. |
| G5 | **Holdcos look through.** Listed-subsidiary stakes are marked to market PIT; SOTP is the primary method; the holdco discount is a scenario input (default range 20–50%, with historical own-discount shown), never a hidden constant. | Common Indian sell-side practice. |
| G6 | **Standalone vs consolidated** is always explicit. Default = consolidated where it exists. A ratio never mixes bases (numerator and denominator must share `basis`). | Ind AS 110. |
| G7 | **Exceptional items**: reported PAT and adjusted PAT (ex-exceptionals, tax-effected where disclosed) are separate metrics; P/E defaults to adjusted, labelled. | FORMULAS.md. |
| G8 | **Ind AS 116**: EBITDA is post-Ind AS 116 by default for FY20+; a `pre_116` EBITDA (less lease payments) is computed where disclosure allows, and is used for time series that cross FY20, so history is comparable. Retail, QSR, aviation, hospitals and hotels default to the pre-116 view for peer comparison. | Ind AS 116 effective 1-Apr-2019. |
| G9 | **Minority interest**: EV includes NCI at market value where the subsidiary is listed, book otherwise; EPS uses profit attributable to owners. | Standard. |
| G10 | **Trailing vs forward**: TRIKAL computes trailing (TTM / FY) only. Forward numbers come only from management guidance (Promise Tracker) and user scenarios, labelled as such. No consensus estimates are fabricated (and none are licensed yet). | Invariant 1. |
| G11 | **Illiquidity**: names below an ADV threshold are flagged; their prices are excluded from peer *valuation* percentiles (stale prices), kept for fundamentals percentiles. | Reliability of quoted prices. |
| G12 | **Units**: every value carries unit + currency (₹ cr default for Indian figures; per-share in ₹; ratios in x or %). | UI rule. |

---

## 3. Per-sector playbooks (draft)

Columns: **Key metrics** (beyond universal ones) · **Primary / secondary valuation** · **Forbidden (F) / caution (C)** · **Cycle & macro** · **Typical red flags**.

### Financials (parent: `financials`; inherits G2)

| Playbook | Key metrics | Valuation | F / C | Cycle & macro | Red flags |
|---|---|---|---|---|---|
| `banks` | NIM, CASA, GNPA/NNPA, PCR, credit cost, slippages, CAR/CET1, RoA, RoE, loan mix, LDR | P/ABV, justified P/B (`(RoE−g)/(Ke−g)`), residual income / P/E (C) | F: all G2 + EV/EBITDA, EBITDA margin, D/E, current ratio | Credit cycle; repo, liquidity, CRR | Slippages ↑ & PCR ↓, SMA-2 growth, RBI divergence, wholesale deposit concentration |
| `nbfc_hfc` | AUM growth, yield, spread, cost of funds, Stage 2/3, credit cost, ALM gaps, leverage (assets/equity) | P/B, P/ABV / P/E | F: G2 + EV/EBITDA | Funding cost, liquidity events (2018 IL&FS template) | ST borrowings funding LT assets, Stage 2 creep, rating watch |
| `insurance_life` | VNB, VNB margin, APE, persistency (13/61m), EV, RoEV, product mix | P/EV, (EV + n×VNB) / — | F: G2; C: P/E as primary | Rates, equity markets, regulation (IRDAI surrender norms) | Falling persistency, VNB margin compression |
| `insurance_general` | GWP growth, loss ratio, expense ratio, combined ratio, solvency, float, investment yield | P/B, P/E | F: G2 | Motor/health pricing cycles, catastrophe | Reserve releases flattering combined ratio |
| `capital_markets` (AMC, broker, exchange, RTA, depository) | AUM & market share, yield on AUM, ADTO, active clients, F&O share | P/E, mcap/AUM (AMC) | F: G2 for brokers with lending books; EBITDA allowed for exchanges/RTAs (C) | Market volumes, SEBI rule changes (F&O curbs) | Revenue concentration in F&O, regulatory exposure |

### Non-financials

| Playbook | Key metrics | Valuation | F / C | Cycle & macro | Red flags |
|---|---|---|---|---|---|
| `it_services` | CC revenue growth, TCV, book-to-bill, attrition, utilisation, EBIT margin, top-5/10 client share, offshore mix | P/E, FCF yield / EV/EBIT | F: inventory days, CCC | USD/INR, US/EU tech spend | DSO ↑, unbilled revenue ↑, client concentration |
| `pharma` | US generics erosion, ANDA filed/approved/pending, USFDA status (OAI/VAI/WL/import alert), R&D % sales, India branded growth (vs IPM), API vs formulation mix | P/E, EV/EBITDA | — | USD/INR, China API prices | USFDA OAI/WL at key site, capitalised R&D ↑ |
| `hospitals` | ARPOB, occupancy, ALOS, bed additions, payor mix, mature vs new-unit margin | EV/EBITDA (pre-116, G8) / DCF | C: P/E during heavy capex | — | New-unit losses masked in consolidated |
| `fmcg` | Volume vs price growth, gross margin, A&P % sales, direct reach, rural/urban mix | P/E, DCF | — | Palm oil, crude derivatives, wheat, monsoon | Channel stuffing (receivables ↑, trade inventory) |
| `retail_qsr` | SSSG, store adds, revenue/sq ft, store-level EBITDA, pre-116 EBITDA | EV/EBITDA (pre-116), EV/sales | C: P/E | Consumption, rentals | Store closures, SSSG < inflation |
| `auto_oem` | Volumes by segment, realisation/unit, market share, EV mix, dealer inventory days | P/E, EV/EBITDA | — | Steel/aluminium/precious metals, rates, rural income | Dealer inventory build, discounting |
| `auto_ancillary` | Content per vehicle, client concentration, export share, EV-agnostic share | P/E, EV/EBITDA | — | OEM cycle, EUR/USD | Single-OEM dependence |
| `cement` | Capacity, utilisation, realisation/t, cost/t (power & fuel, freight), EBITDA/t, regional mix | EV/tonne (replacement cost), EV/EBITDA | C: peak-cycle P/E as primary (G3) | Pet coke/coal, diesel, housing/infra capex | Capacity additions outpacing demand, regional price wars |
| `metals_mining` | Spreads (steel–coking coal–iron ore), cost-curve position, volumes, net debt/EBITDA | EV/EBITDA on mid-cycle (G3), P/B | F: peak-earnings P/E as primary → `cyclical_peak_trap` | China steel, LME, coking coal, safeguard duties | Leverage at peak, acquisitions at peak |
| `oil_gas_upstream` | Realisations, production, reserves, windfall tax | EV/EBITDA, P/E (C) | — | Brent, gas pricing formula (APM) | Govt pricing interventions |
| `oil_gas_omc` | GRMs, marketing margins (petrol/diesel/LPG), throughput, inventory gains | EV/EBITDA, SOTP | C: single-year P/E (inventory gains) | Brent, cracks, govt pricing | Under-recoveries, inventory-gain dependence |
| `oil_gas_cgd` | Volumes (CNG/PNG/industrial), gas cost, EBITDA/scm, GA expansion | P/E, DCF | — | APM gas allocation, LNG prices | APM allocation cuts |
| `power_regulated` (gen/T&D) | PLF, regulated equity, regulated RoE, capacity pipeline, discom receivables (days) | P/B, DCF | — | Rates, coal, discom health (LPS rules) | Receivable days ↑ |
| `renewables` | MW operational/pipeline, CUF, tariff, PPA counterparty, net debt/EBITDA | EV/MW, DCF | — | Rates, module prices, ALMM/BCD | Aggressive capex funded by short-term debt |
| `real_estate` | Pre-sales (₹, msf), collections, realisation/sq ft, land bank, net debt, OCF | NAV | F: P/E (Ind AS 115 lumpiness) | Rates, housing affordability | Collections < pre-sales, land-bank write-downs |
| `capital_goods_epc_defence` | Order book, book-to-bill, execution rate, NWC days, unbilled revenue, advances | P/E, EV/EBITDA | — | Govt capex, budget lines, defence indigenisation | Receivables/unbilled ↑, low-margin order intake |
| `chemicals_specialty` | Product mix, utilisation, customer contracts, R&D | P/E, EV/EBITDA | — | China prices, crude derivatives | Customer concentration |
| `chemicals_commodity` | Spreads, utilisation, China pricing | EV/EBITDA mid-cycle | Cyclical overlay (G3) | China, anti-dumping | Capacity glut |
| `telecom` | ARPU, subscribers, churn, capex intensity, spectrum liabilities | EV/EBITDA (pre-116) | C: P/E as primary | Tariff actions, AGR | Deferred spectrum dues |
| `aviation` | RASK, CASK (ex-fuel), yield, load factor, fuel % cost, fleet | EV/EBITDAR | C: P/E | ATF/Brent, USD/INR | Negative net worth, lease liabilities |
| `hotels` | RevPAR, ARR, occupancy, room additions, asset-light mix | EV/EBITDA | — | Travel demand | Leveraged expansion |
| `logistics` | Volumes, realisation/unit, asset turns, utilisation | EV/EBITDA | — | Diesel, GDP/IIP, rail freight policy | — |
| `agri_fert_sugar` | Subsidy receivables, monsoon, NBS/MRP regime, FRP (cane), ethanol mix | EV/EBITDA, P/E | Cyclical overlay for sugar | Monsoon, govt pricing | Subsidy receivable days ↑ |

### Overlays

| Overlay | Adds |
|---|---|
| `holdco` (conglomerates / holding companies) | SOTP primary + holdco discount scenario; F: consolidated P/E as *primary*; requires look-through (G5) |
| `psu` | Dividend policy & payout trend, govt stake & divestment pipeline, capex mandates, board independence; governance overlay on KASAUTI (documented weight, not a hidden penalty) |
| `cyclical` | G3 behaviour, mid-cycle normalisation |
| `loss_making` | Activated automatically when TTM PAT ≤ 0: earnings multiples → `Undefined`; EV/sales, DCF, P/B become eligible per base playbook |

---

## 4. Open finance questions (flagged per working rules)

1. **Bank "ABV"**: use NNPA-adjusted book (BV − NNPA) as conventional; optionally also subtract restructured/SMA haircuts? Proposal: conventional ABV = BV − NNPA, with a second "stressed ABV" scenario input. Flag F-1.
2. **Mid-cycle window for G3**: 7 years minimum, or a full detected cycle (peak-to-peak on margin)? Proposal: max(7y, last full cycle). Flag F-2.
3. **Holdco discount default band 20–50%**: wide on purpose; the Lab shows the company's own historical implied discount. Flag F-3.
4. **Embedded value for life insurers** is disclosed semi-annually/annually, so P/EV between disclosures uses the last disclosed EV (+ optional roll-forward scenario, labelled). Flag F-4.

## 5. References (standard practice)
- A. Damodaran, *Investment Valuation* (3e), chs. 21 (financial services), 22 (negative earnings), 23 (young firms), 24 (private firms); *The Dark Side of Valuation* (cyclicals, commodity companies).
- McKinsey & Co., *Valuation: Measuring and Managing the Value of Companies* (7e): ROIC, economic profit, EV bridge, leases.
- CFA Institute curriculum, Level II Equity (residual income, justified multiples, industry analysis).
- Ind AS 103, 110, 115, 116; Schedule III (Companies Act 2013) for line-item definitions.
- RBI Master Directions (IRACP norms, Basel III capital); IRDAI regulations; Institute of Actuaries of India APS-10 (embedded value).
- NSE Indices / BSE *India Industry Classification* methodology (2022, revised 2023).
