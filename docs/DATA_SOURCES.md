# TRIKAL — Data Sources Registry (M0)

**Verification run:** 2026-10-09, from the owner's machine (Windows 11, residential Indian IP assumed), plain HTTPS with a browser User-Agent, no cookies, no login. "Verified" means *the endpoint answered with the expected content on that date*. It says nothing about legal clearance (see the **Terms** column and RISKS R-1). Any endpoint can change without notice, so M1 builds a daily `source_health` check.

Legend: ✅ verified working · ⚠️ works with caveats · ❌ failed / blocked · 🔎 not yet probed (planned for the milestone shown)

Machine-readable twin: `/config/sources.yaml` (created in M1, mirrors this table: key, url pattern, cadence, format, terms, licence status, owner of record).

---

## 1. Exchange data — prices & security master (M1)

| Key | Source / URL pattern | Status | What we saw | Notes |
|---|---|---|---|---|
| `nse.bhav.udiff` | `nsearchives.nseindia.com/content/cm/BhavCopy_NSE_CM_0_0_0_{YYYYMMDD}_F_0000.csv.zip` | ✅ | 2025-10-08 file, 180 KB zip. Columns: `TradDt, BizDt, Sgmt, Src, FinInstrmTp, FinInstrmId, ISIN, TckrSymb, SctySrs, …, OpnPric, HghPric, LwPric, ClsPric, LastPric, PrvsClsgPric, …, TtlTradgVol, TtlTrfVal, TtlNbOfTxsExctd …` | Current (UDiFF) format, **has ISIN**. The exact cutover date from the legacy format is pinned in M1 by probing the boundary. |
| `nse.bhav.legacy` | `nsearchives.nseindia.com/content/historical/EQUITIES/{YYYY}/{MON}/cm{DD}{MON}{YYYY}bhav.csv.zip` | ✅ | 2010-01-04 file. Columns: `SYMBOL, SERIES, OPEN, HIGH, LOW, CLOSE, LAST, PREVCLOSE, TOTTRDQTY, TOTTRDVAL, TIMESTAMP` | **No ISIN in early files.** Needs symbol-history join (ARCHITECTURE §4.4). Earliest available year to be probed in M1 (NSE equity trading began Nov 1994). |
| `nse.delivery` | MTO / `sec_bhavdata_full` files | 🔎 M1 | — | Delivery % for Flows desk. |
| `bse.bhav.udiff` | `bseindia.com/download/BhavCopy/Equity/BhavCopy_BSE_CM_0_0_0_{YYYYMMDD}_F_0000.CSV` | ✅ | 2025-10-08, 815 KB, same UDiFF schema, `FinInstrmId` = BSE scrip code, has ISIN | Covers BSE-only listings (a large share of the 5,000+ universe is BSE-only). Legacy BSE bhav format for older years: 🔎 M1. |
| `nse.equity_list` | `nsearchives.nseindia.com/content/equities/EQUITY_L.csv` | ✅ | `SYMBOL, NAME OF COMPANY, SERIES, DATE OF LISTING, PAID UP VALUE, MARKET LOT, ISIN NUMBER, FACE VALUE` | Current snapshot only. Not PIT. Daily snapshots from M1 onward give forward PIT. |
| `nse.delisted` | `nsearchives.nseindia.com/content/equities/delisted.csv` | ✅ | `Symbol, Company, Delisted Date, Type of Delisting` (from 2002) | **No ISIN.** Join via symbol history. |
| `nse.symbol_change` | `…/content/equities/symbolchange.csv` | 🔎 M1 | — | Critical for the pre-ISIN join. |
| `nse.name_change` | `…/content/equities/namechange.csv` | 🔎 M1 | — | |
| `bse.scrip_master` | `api.bseindia.com/BseIndiaAPI/api/ListofScripData/…` (incl. `status=Delisted`) | ❌ | HTTP 403 with and without Referer | BSE's JSON API blocks non-browser clients. Alternatives for M1: BSE downloadable scrip lists, or ISINs harvested from historical BSE bhavcopies (has ISIN in UDiFF era). |
| `nse.indices.close` | `nsearchives.nseindia.com/content/indices/ind_close_all_{DDMMYYYY}.csv` | ✅ | All NSE indices daily OHLC + **P/E, P/B, Div Yield** | Index-level valuation history for sector bands. |

## 2. Index & sector membership (M1/M2) — the hardest PIT gap

| Key | Source | Status | Notes |
|---|---|---|---|
| `niftyindices.constituents` | `niftyindices.com/IndexConstituent/ind_nifty500list.csv` (and per-index files) | ✅ | **Current snapshot only** (`Company Name, Industry, Symbol, Series, ISIN Code`). |
| `niftyindices.press_releases` | `niftyindices.com/Press_Release/ind_prs{DDMMYYYY}.pdf` | ✅ (individual PDFs exist back to at least 2008) | **No consolidated history file exists.** Membership history must be *reconstructed* by parsing every reconstitution press release (inclusions/exclusions + effective date) backwards from today's snapshot. Each reconstructed interval stores `method='reconstructed'`, `confidence`, and the PDF as lineage. Ad-hoc replacements (e.g. corporate events, Yes Bank removal on 19-Mar-2020) arrive via separate circulars and are included. |
| `nse.iic` | NSE/BSE common **India Industry Classification** (Macro-Economic Sector / Sector / Industry / Basic Industry). Introduced 31-Mar-2022, revised 2023. | ⚠️ | **Official history only from 2022.** Before that, NSE used an older single-level "Industry" field. Classification before 2022 is *reconstructed* (mapped from the old industry field and the company's then-revenue mix) and flagged `confidence < 1`. This is exactly the gap that broke the owner's earlier study, so it is surfaced explicitly in every backtest report (RISKS R-3). Option: licensed vendor PIT classification **[Q1]**. |
| BSE index constituents | asiaindex / BSE | 🔎 M1 | Lower priority than Nifty family. |

## 3. Corporate filings & fundamentals (M2)

| Key | Source | Status | What we saw | Notes |
|---|---|---|---|---|
| `nse.results` | `www.nseindia.com/api/corporates-financial-results?index=equities&period=Quarterly&symbol=…` | ✅ | TCS: 162 filings, oldest period 31-Mar-2005. Fields include `broadCastDate`, `filingDate`, `fromDate`, `toDate`, `consolidated`, `audited`, `indAs`, `reInd`, `xbrl` (direct XML URL), `resultDetailedDataLink` | Gives us `known_at` (`broadCastDate`) **with seconds**. ⚠️ the oldest rows have **no broadcast date** → `known_at` must be imputed for them (ARCHITECTURE §2). JSON API, not a published download; see Terms. |
| `nse.xbrl` | `nsearchives.nseindia.com/corporate/xbrl/INDAS_…xml` | ✅ (URL obtained, per-file fetch 🔎 M2) | | Primary fundamentals path (ladder step 1). |
| `nse.shareholding` | `www.nseindia.com/api/corporate-share-holdings-master?index=equities&symbol=…` | ⚠️ | TCS: 20 quarters, **oldest 30-Sep-2021**. Fields include `broadcastDate`, `submissionDate`, `revisedData/revisedDate` (revisions!), `xbrl` | Only ~5 years via this endpoint. Older shareholding: BSE shareholding pages / XBRL archive 🔎 M2. Revision fields map cleanly onto our restatement model. |
| `nse.pledge` | `www.nseindia.com/api/corporate-pledgedata?index=equities&symbol=…` | ✅ | 670 B response for ADANIENT | Structure 🔎 M2. |
| `nse.insider` | `www.nseindia.com/api/corporates-pit?index=equities&symbol=…` | ✅ | 16.5 KB for TCS | SEBI PIT Regulations disclosures. |
| `nse.corp_actions` | `www.nseindia.com/api/corporates-corporateActions?index=equities&symbol=…` | ✅ | Fields include `exDate`, `faceVal`, `isin`, purpose text | Purpose text needs parsing ("Bonus 1:1", "Face Value Split From Rs 10 To Rs 2"); golden-file tests. The announcement time (`known_at`) of a corporate action is **not** the ex-date, so it is taken from the board-meeting/announcement record. |
| `nse.announcements` | `www.nseindia.com/api/corporate-announcements?index=equities` | ✅ | Fields: `an_dt`, `sort_date`, `exchdisstime`, `attchmntFile`, `desc`, `sm_isin`, `hasXbrl` | Firehose for events, rating actions (Reg 30), concall transcripts (Reg 46(2)(oa)), investor presentations. |
| `nse.board_meetings` | `www.nseindia.com/api/corporate-board-meetings?…` | ✅ | | Events calendar (results dates). |
| `nse.annual_reports` | `www.nseindia.com/api/annual-reports?…` | ✅ | 5.4 KB list for TCS | PDFs → ladder step 3 (segment, RPT, contingent liabilities, auditor). |
| `nse.bulk_deals` | `nsearchives.nseindia.com/content/equities/bulk.csv` | ✅ | `Date, Symbol, Security Name, Client Name, Buy/Sell, Quantity Traded, Trade Price …` | Daily file = today only. History via the date-range endpoint 🔎 M2. Block deals likewise. |
| BSE filings (announcements, results, shareholding for BSE-only cos) | bseindia.com | 🔎 M2 | | BSE JSON API is 403 to scripts (above). The BSE attachment archive (`bseindia.com/xml-data/corpfiling/AttachHis/…pdf`) is publicly linked. **BSE-only company coverage is a real gap risk** (RISKS R-2). |
| MCA21 (statutory financials, CIN, charges) | mca.gov.in | 🔎 M2 | | Document downloads are **paid per document**. Treated as a paid service, so it needs owner approval **[Q1]**. |

### 3.1 Concall transcripts
Companies must upload call recordings/transcripts and file them with the exchanges under **LODR Reg 46(2)(oa)** (introduced by the May-2021 amendments; we will pin the exact deadline wording from the SEBI notification in M6). Example verified: LIC Housing Finance transcript filed on NSE, 07-Aug-2021. **Consequence:** systematic transcript coverage across the universe exists only from roughly mid-2021. Before that, coverage is patchy (mostly large caps). This bounds the history of the Management Credibility pillar (RISKS R-6).

## 4. Mutual funds (M2)

| Key | Source | Status | Notes |
|---|---|---|---|
| `amfi.nav` | `www.amfiindia.com/spages/NAVAll.txt` | ✅ | 1.5 MB, daily NAV all schemes, includes scheme ↔ ISIN. |
| `amfi.portfolio_disclosure` | `www.amfiindia.com/online-center/portfolio-disclosure` (links out) | ⚠️ | The page answers 200, but **scheme-level portfolios are published by each AMC on its own website** (SEBI mandate, monthly/fortnightly), in heterogeneous Excel layouts. About 45 AMCs means about 45 parsers. Plan: top 15 AMCs by AUM first (well over 80% of equity AUM; exact share computed in M2), then the long tail. |

## 5. Macro, rates, policy (M5)

| Key | Source | Status | Notes |
|---|---|---|---|
| `rbi.dbie` | `data.rbi.org.in/DBIE/` | ⚠️ | Portal reachable (SPA). Programmatic export path 🔎 M5. Covers credit, deposits, M3, sectoral deployment, rates, FX reserves, BoP. |
| `rbi.press` | rbi.org.in press releases / MPC statements | 🔎 M5 | Policy rate history with announcement timestamps (needed for PIT). |
| `mospi.api` | `api.mospi.gov.in` (Swagger UI) / `esankhyiki.mospi.gov.in` | ✅ reachable | Official API for CPI, IIP, GDP/GVA, WPI(?). Endpoint inventory 🔎 M5. **Release calendar** gives `known_at`; macro data is heavily *revised* (GDP, IIP), so every vintage is stored, not just the latest. |
| `fred` | `api.stlouisfed.org/fred/…` | ⚠️ | API host answers (400 without key, as expected). **Needs a free API key**, the owner to register **[Q5]**. The `fred.stlouisfed.org` website timed out from this machine. ALFRED (vintages) gives PIT US data. |
| `worldbank` | `api.worldbank.org/v2/…` | ✅ | JSON OK. Annual, low frequency. |
| `imf` | IMF data API (SDMX) | 🔎 M5 | |
| `gdelt` | `data.gdeltproject.org/gdeltv2/lastupdate.txt` | ✅ | 15-minute event/GKG files. Use for geopolitical intensity indices (Exposure Theatre). |
| `cea` | cea.nic.in | ✅ reachable | Power demand / generation reports (PDF/Excel). |
| `ppac` | ppac.gov.in | ✅ reachable | Fuel consumption, crude basket price. |
| `dgtr` | dgtr.gov.in | ✅ reachable | Anti-dumping / safeguard notifications. |
| PIB, Union Budget (indiabudget.gov.in), CGA, GST statistics, SEBI circulars, e-way bill, rail freight, SIAM/FADA auto sales, DGCA air traffic, HSN-level trade (tradestat.commerce.gov.in) | 🔎 M5 | SEBI `robots.txt` allows crawling except js/css. Several of these are PDF-only. |
| Commodity prices (Brent, steel, copper, coal, freight indices/Baltic Dry) | 🔎 M5 | ⚠️ Many "public" commodity series (LME, Platts, Baltic Exchange) are **licensed**. Free proxies: FRED/World Bank Pink Sheet (monthly), PPAC Indian basket, exchange futures settlement (MCX). Gap to discuss **[Q1]**. |
| PMI (S&P Global / HSBC India PMI) | — | ⚠️ | Headline numbers are in public press releases; the series is **proprietary**. Store headline only, with release PDF as lineage. |

## 6. Credit ratings (M2/M9)

Rating actions arrive two ways: (a) agency press releases (CRISIL, ICRA, CARE, India Ratings, Acuité, Brickwork, Infomerics) on agency sites; (b) the company's Reg 30 disclosure on the exchanges (already in `nse.announcements`). Plan: (b) first for coverage and `known_at`, (a) for detail. 🔎 M2.

## 7. Terms of use: summary (not legal advice)

- **NSE** `robots.txt` (fetched 2026-10-09): `Allow: /`, disallows only `/market-data-test`. But NSE's **Terms of Use** state the content is NSE's property and restrict aggregating or copying content *unless it is offered for download*, and NSE's **Data Policy** says redistribution of market data needs a licence via NSE Data & Analytics. The NSE data-portal terms explicitly prohibit automated collection without written consent. ([Terms of Use](https://www.nseindia.com/nse-terms-of-use), [Data policy](https://www.nseindia.com/market-data/nse-data-policy), [Data Sharing & Usage Policy PDF](https://nsearchives.nseindia.com/web/sites/default/files/inline-files/NSE_Data_Sharing%26Usage_Policy.pdf))
  - Our reading: archive files explicitly offered for download (bhavcopies, EQUITY_L, delisted, bulk.csv, index closes) are the lowest-risk tier. The `/api/*` JSON endpoints that power the website are a **grey zone** for automated use. **Public redistribution of any NSE data needs a licence.**
- **BSE**: `robots.txt` returns an HTML page (no machine-readable policy). The JSON API actively blocks scripts. Treat it like NSE.
- **niftyindices.com**: has its own terms ([link](https://niftyindices.com/terms-of-use)); index data is licensed commercially.
- **Government sources** (RBI, MOSPI, PIB, CEA, PPAC, DGTR, SEBI): generally under India's National Data Sharing and Accessibility Policy / Government Open Data Licence, permissive with attribution. Verify per source in M5.
- **FRED / World Bank / GDELT:** permissive with attribution (FRED: some series carry third-party copyright, flagged per series).

**Operating stance (proposed, ADR-006):** personal, non-commercial research use; prefer published download files over JSON endpoints wherever an equivalent exists; ≤ 1 req/s per exchange host, cache everything in raw so nothing is fetched twice; every source carries a `licence_status` in the registry (`public-open`, `public-restricted`, `licensed`, `unknown`), and the app refuses to start in a future `PUBLIC_MODE` while any `public-restricted`/`unknown` source feeds a visible screen. **The owner should decide whether this stance is acceptable [Q2].**

## 8. Licensed alternatives (for the owner to consider; none added without approval)

| Need | Free path weakness | Licensed options (indicative) |
|---|---|---|
| Deep PIT fundamentals (15y full statements, segments, restatement vintages) | XBRL only for the recent period; old years are PDFs | CMOTS, Accord Fintech (ACE Equity), Capitaline, Prowess (CMIE), LSEG/FactSet/S&P CapIQ |
| PIT sector classification & index history | Must be reconstructed before 2022 | NSE Indices data licence, Prowess, vendors above |
| Redistribution rights (if TRIKAL ever goes public) | Not available | NSE Data & Analytics, BSE data licence |
| Commodity prices | Monthly proxies only | Exchange/vendor feeds |

---

## 9. Findings during M1 ingestion (2026-10-09/10)

| Source | Finding | Consequence |
|---|---|---|
| `nse.bhav.legacy` | ISIN + TOTALTRADES columns appear from **Aug-2011**; files exist back to **Nov-1994** (e.g. 02-Jan-1995). | Pre-Aug-2011 rows get identity through code continuity / symbol chains (FORMULAS.md §Security identity). |
| `nse.bhav.legacy` | **PREVCLOSE is not adjusted** for corporate actions (TCS bonus 1:1, ex 31-May-2018: PREVCLOSE 3514.10, CLOSE 1741.05). | Adjustments come from announcements confirmed by the observed price move (ADR-012 revised). |
| `nse.bhav.udiff` | First UDiFF file: **08-Jul-2024**; legacy files still exist up to 05-Jul-2024. | Cut-over fixed in `sources/bhav.py`. |
| NSE archives | Days without a session answer **HTTP 404**. | Clean `no_session` signal for the calendar. |
| `bse.bhav.*` | Days without a file answer **HTTP 200 with an HTML placeholder** (14,287 B). Formats: legacy `EQDDMMYY_CSV.ZIP` from ~2007, `EQ_ISINCODE_DDMMYY.zip` (with ISIN) ~2017–2024, UDiFF from 2024. | Payloads validated by content. A BSE placeholder on an NSE session day is treated as **unknown**, not a holiday. |
| `bse.bhav.*` | **Source files have holes**: e.g. BSE 15-Jul-2022 file (3,019 rows) omits TCS (532540), which traded that day. | Price-signal comparisons require adjacent sessions; such gaps never create adjustment factors. |
| `nse.corp_actions` | Date-range endpoint returns all companies for a month (382 monthly calls for 1995–2026, 43,794 records). `caBroadcastDate` is null in old records. | `known_at` imputed as ex-date 09:00 IST (conservative). Old subjects quote dividends as % of face value. |
| `nse.symbol_change` | No header row; columns: company, old, new, date. 1,065 records. | Parsed positionally. |
| `nse.delisted` | Two-digit years (`15-Apr-02`), no ISIN; 328 records (from 2002). | Delisting dates split trading episodes. |
| `niftyindices.media` | All **1,513 press releases (Sep-1998 →)** are listed in the static HTML of `/media`; PDFs at `/Press_Release/ind_prsDDMMYYYY[_n].pdf`. 848 relevant PDFs fetched, 5 failed (logged). | Basis of the membership reconstruction (ADR-013). |
| `niftyindices` snapshots | Official constituent files can contain **placeholder rows** during corporate actions (e.g. `DUMMYHEG`, "Dummy HEG Ltd.", ISIN `DUM545A01024`, Oct-2026), and **REIT units** (Nifty 500 includes REITs from 30-Sep-2026). | Placeholders excluded and logged; REIT constituents identified by symbol → ISIN. |
| Press releases | Changes can be **voided, deferred or revoked** in later free-text releases (27-Mar-2020 rebalance voided on 13-May-2020; Vodafone Idea exclusion revoked 25-Sep-2024, Prism Johnson excluded instead). | Curated, cited overrides in `config/index_overrides.yaml`. |
| Press releases | Before ~2011 lists give company names only, often followed by the industry ("Munjal Showa Ltd. Auto Ancillaries"); pre-2010 PDFs are web-page printouts with navigation text mixed in. | Name matching with confidence; navigation text stripped. |

---

## 10. Findings during M2 ingestion (2026-10-12)

| Source | Finding | Consequence |
|---|---|---|
| `nse.results` list (`corporates-financial-results`) | Up to ~160 rows per company back to 2005; each row has an exact `broadCastDate`. XBRL links (`…/xbrl/*.xml`) exist only from period-end Jun-2017; earlier rows have `xbrl/-` and an HTML `resultDetailedDataLink` instead. Some old periods were re-broadcast years later (TCS FY16 in 2018). | Two parsers; the earliest-known value of an unchanged figure is kept (value-change PIT table). |
| `integrated-filing-results?index=equities&symbol=X&size=500` | New SEBI "Integrated Filing" endpoint carrying results from the Dec-2024 quarter (the old endpoint stops there). It also lists "Governance" documents (about 40% of rows) that are not financial statements. Paged at 20 rows unless `size` is given. | Added to the downloader; Governance rows filtered by `type`. |
| Results XBRL | Context ids encode the column (`OneD`, `FourD`); `FourD` dates are the quarter's, not the year's. Values in full rupees. Annual and half-yearly filings include balance sheet and cash flow. Families: `INDAS`, `BANKING`, `NBFC_INDAS`, `NONINDAS`, `INTEGRATED`. | FORMULAS.md, Financial statements. Banks expose NPA amounts and ROA but no loan-book or NIM concepts. |
| Old results HTML | Labels vary by company and year; amounts in ₹ lakh; "Total expenses" sometimes includes finance costs and sometimes not; Part II "Number of shares" rows are rendered one group earlier than their headers. | Lossless `html:<slug>` facts, validated Part II, convention-tolerant identity check. |
| `corporate-share-holdings-master` | Returns only the latest ~20 quarters (since Sep-2021) regardless of date parameters. Revised records replace the original (its values and broadcast time are not retained). SHP XBRL is 0.3–1.3 MB each; context naming changed between 2018, 2023 and 2025; the percentage scale varies (fraction vs percent). | Normalising parser. Shareholding before Sep-2021 is limited to the promoter/public summary (RISKS R-27). |
| `corporate-pledgedata` | Latest quarter only; `from_date`, `to_date`, `size` and `period_ended` do not return history. | Forward-accumulating snapshots (RISKS R-26). |
| `annual-reports` | PDF list per company and year (list only; the PDFs are for M6). | |
| niftyindices constituent files | Nifty Total Market (755 names) and Microcap 250 carry the NSE sector label per company, current only. | `classification` (FORMULAS.md). |
| `www.nseindia.com/api/*` | Needs a browser User-Agent and a Referer; read timeouts occur when the laptop sleeps. | The job is resumable and requests keep-awake while it runs. |

## 11. Context layer for the Time Machine (M3, 2026-10-13)

| Source key | URL pattern | Coverage | Licence |
|---|---|---|---|
| `wiki.day` | `https://en.wikipedia.org/wiki/Portal:Current_events/<YYYY>_<Month>_<D>?action=raw` | daily pages from 2003 | CC BY-SA 4.0 |
| `wiki.year` | `https://en.wikipedia.org/wiki/<YYYY>?action=raw` (Events section) | world events by date; used before 2003 | CC BY-SA 4.0 |
| `wiki.india` | `https://en.wikipedia.org/wiki/<YYYY>_in_India?action=raw` (Events section) | Indian events by date, 1994 onward | CC BY-SA 4.0 |

- robots.txt disallows `/w/` and `/api/` for crawlers but allows `/wiki/`; raw wikitext is fetched from `/wiki/…?action=raw`
  with a descriptive User-Agent at ≤ 1 request/second, stored in the raw zone, parsed by `trikal_pipeline.sources.wiki_context`
  into `context_event` (page title + raw sha kept for lineage).
- **What it is:** editorial summaries written by Wikipedia editors, often after the fact. Daily-page items keep their original
  outlet ("Reuters", "BBC News", …) and link. **What it is not:** data. It has no `known_at`, it never feeds a metric, score or
  backtest, and the UI shows only items dated on or before the session on screen, with source and licence.
- Commands: `trikal fetch-context` (the built-in Time Machine days ±3 + every year page), `trikal fetch-context --days all`
  (every day from 1994; ~8,700 daily pages, ≈ 2.5 h at the polite rate), `--days 2008-01-01:2008-12-31`.
- Before public sharing: CC BY-SA requires attribution (shown in the UI) and share-alike for adapted text; we display the text
  unmodified apart from markup removal.

## 12. Macro sources (M5, verified 2026-10-13)

| Source key | Endpoint | Series | Notes |
|---|---|---|---|
| `fred.csv` | `https://fred.stlouisfed.org/graph/fredgraph.csv?id=<ID>` | DEXINUS, DCOILBRENTEU, DGS10, DFF, DTWEXBGS, VIXCLS, INDIRLTLT01STM, INDCPIALLMINMEI, IRSTCI01INM156N | Keyless, latest vintage only; rejects browser-like user agents, works with a descriptive one. |
| `fred.vintage` | `https://api.stlouisfed.org/fred/series/observations?...&realtime_start=1776-07-04&realtime_end=9999-12-31` | same | Needs `FRED_API_KEY` in `.env` (owner). Gives every vintage → exact first-release dates. |
| `mospi.cpi` | `https://api.mospi.gov.in/api/cpi/getCPIIndex?base_year=2012&series=Current&year=<Y>&state_code=99&sector_code=3` | CPI general, consumer food price (All India, Combined) | eSankhyiki API; ≤ 200 rows/page; host needs legacy TLS renegotiation (scoped to it). 2012 base runs to Dec-2025; the 2024 base (from 2025) uses different codes, not wired yet. |
| `wb.pinksheet` | `https://thedocs.worldbank.org/.../CMO-Historical-Data-Monthly.xlsx` (link read from `worldbank.org/en/research/commodity-markets` each run) | 17 commodities, monthly since 1960 | The document id changes with every release; an old link silently serves a stale file. |

Not used yet: RBI DBIE (no stable public API), GDELT (unreliable responses during probing), FBIL reference rates.
`trikal fetch-macro` fetches and loads everything (~150k observations, 3 s load via CSV COPY).

## 13. Live prices (owner's own broker account)

NSE's public quote API (`/api/quote-equity`, `/api/allIndices`) answers `403 Access Denied` behind bot protection; TRIKAL does not try to get around it.
Live prices therefore come from the owner's own Angel One SmartAPI account (`api/trikal_api/live.py`):
login (`/rest/auth/angelbroking/user/v1/loginByPassword`, API key + client code + MPIN + TOTP) then market quotes
(`/rest/secure/angelbroking/market/v1/quote/`, FULL mode, up to 50 tokens per call, ~1 call/s). Symbol→token map from the public
instrument file `OpenAPIScripMaster.json` (cached 7 days). Read-only by construction: only those two paths can be called (tested).
Live exists only for `as_of=NOW`; rewound views use the exchange's end-of-day prices. Redistribution is not allowed by the broker's terms: personal use only.
