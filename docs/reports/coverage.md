# TRIKAL data coverage — generated 2026-10-12 19:04 IST

## Trading calendar (from the fetch log)
Target range = earliest file we try to fetch -> today. Unknown = not answered yet (not fetched / fetch error / untrusted placeholder).

| exchange | target from | to | sessions | no session | unknown days |
|---|---|---|---|---|---|
| NSE | 1994-11-01 | 2026-10-12 | 7,942 | 3,725 | 2 |
| BSE | 2007-01-01 | 2026-10-12 | 4,868 | 2,322 | 35 |

## Prices (unadjusted, as published)

| exchange | from | to | rows | rows with ISIN | distinct codes |
|---|---|---|---|---|---|
| BSE | 2007-01-02 | 2026-10-09 | 16,108,846 | 9,027,353 | 16,194 |
| NSE | 1994-11-03 | 2026-10-09 | 11,995,742 | 7,804,691 | 9,321 |

## Security master

| identity method (weakest listing) | securities | avg confidence |
|---|---|---|
| code_continuity | 3,744 | 0.95 |
| synthetic | 3,111 | 0.8 |
| isin | 2,722 | 1.0 |
| symbol_chain | 204 | 0.9 |
| cross_exchange_price | 78 | 0.85 |

## Price adjustments

| exchange | agreement | applied | events |
|---|---|---|---|
| BSE | unverifiable | 0 | 69,798 |
| BSE | implied_only | 0 | 6,726 |
| BSE | parsed_confirmed | 1 | 1,336 |
| BSE | implied_confirmed | 0 | 213 |
| BSE | parsed_unconfirmed | 1 | 19 |
| BSE | parsed_price_disagrees | 0 | 15 |
| BSE | mismatch | 1 | 1 |
| NSE | implied_only | 0 | 14,675 |
| NSE | unverifiable | 0 | 4,171 |
| NSE | parsed_confirmed | 1 | 1,449 |
| NSE | implied_confirmed | 0 | 552 |
| NSE | parsed_price_disagrees | 0 | 17 |
| NSE | parsed_unconfirmed | 1 | 12 |
| NSE | match | 1 | 2 |

## Index membership reconstruction

| index | count checks | passing | earliest | latest |
|---|---|---|---|---|
| NIFTY500 | 241 | 109 | 1999-02-02 | 2026-10-10 |

Contiguous passing window (from today backwards) starts at **2011-12-06**.

| index | securities ever | unresolved placeholders | pre-coverage start |
|---|---|---|---|
| NIFTY500 | 1,443 | 114 | 537 |

Events by year (unresolved = name not matched to a security; superseded = revised/voided):

| year | events | unresolved | with symbol | superseded |
|---|---|---|---|---|
| 1999 | 100 | 28 | 0 | 0 |
| 2000 | 58 | 18 | 0 | 0 |
| 2001 | 40 | 8 | 0 | 2 |
| 2002 | 224 | 44 | 0 | 1 |
| 2003 | 78 | 13 | 0 | 0 |
| 2004 | 76 | 20 | 0 | 3 |
| 2005 | 50 | 8 | 0 | 1 |
| 2006 | 58 | 9 | 0 | 0 |
| 2007 | 57 | 5 | 0 | 0 |
| 2008 | 44 | 2 | 0 | 0 |
| 2009 | 89 | 3 | 0 | 20 |
| 2010 | 22 | 0 | 8 | 0 |
| 2011 | 96 | 2 | 62 | 0 |
| 2012 | 68 | 0 | 68 | 0 |
| 2013 | 84 | 0 | 84 | 4 |
| 2014 | 66 | 0 | 66 | 0 |
| 2015 | 82 | 0 | 82 | 0 |
| 2016 | 212 | 3 | 136 | 0 |
| 2017 | 132 | 0 | 132 | 8 |
| 2018 | 132 | 0 | 132 | 2 |
| 2019 | 130 | 0 | 130 | 0 |
| 2020 | 147 | 0 | 147 | 43 |
| 2021 | 100 | 0 | 100 | 0 |
| 2022 | 124 | 0 | 123 | 0 |
| 2023 | 86 | 0 | 86 | 0 |
| 2024 | 127 | 0 | 127 | 1 |
| 2025 | 104 | 0 | 104 | 0 |
| 2026 | 120 | 0 | 120 | 0 |

## Fundamentals & ownership (M2)

The 'known to exist' counts only cover companies whose filing lists have been downloaded so far.

| raw download | answered | known to exist |
|---|---|---|
| company lists (5 endpoints x symbols) | 1,811 | 7,950 |
| results XBRL documents (listed so far) | 153 | 12,778 |
| old results HTML pages (listed so far) | 58 | 9,417 |
| shareholding XBRL documents (listed so far) | 0 | 4,689 |

| kind | family | filings parsed | securities | earliest period | latest period |
|---|---|---|---|---|---|
| results_html | HTML | 75 | 57 | 2008-03-31 | 2017-12-31 |
| results_xbrl | INDAS | 106 | 77 | 2018-03-31 | 2024-12-31 |
| results_xbrl | INTEGRATED | 34 | 32 | 2025-03-31 | 2026-09-30 |
| results_xbrl | BANKING | 7 | 5 | 2018-09-30 | 2024-09-30 |
| results_xbrl | NBFC_INDAS | 6 | 6 | 2020-06-30 | 2024-09-30 |

PIT fact rows (value changes only): **16,309** for **133** securities.

Accounting-identity checks (each compares two quantities a filing states independently):

| identity | checked | holds | pass rate |
|---|---|---|---|
| Total assets = total equity + total liabilities (balance sheet) | 42 | 42 | 100.0% |
| Operating + investing + financing cash flow = net change in cash (before FX effect) | 44 | 44 | 100.0% |
| Old pages: profit before tax reconciles under at least one of the template conventions companies use (finance costs outside / inside 'total expenses'; other income separate / already in income) | 17 | 10 | 58.8% |
| Income - Expenses = Profit before exceptional items and tax (Ind AS income statement) | 138 | 138 | 100.0% |
| Profit before exceptional items + exceptional items = Profit before tax | 138 | 138 | 100.0% |
| Profit before tax - tax expense = profit from continuing operations | 138 | 138 | 100.0% |

Shareholding: 220 securities, 207 quarter-ends (2015-12-31 .. 2026-09-30); 0 with category detail (mutual funds / FPI / retail ...).

Promoter pledge snapshots: 92 for 91 securities (2026-03-31 .. 2026-09-30); history only accumulates forward (the exchange serves the latest quarter only).

Sector classification (every row carries method and confidence):

| scheme | method | rows | securities | avg confidence |
|---|---|---|---|---|
| NSE_INDUSTRY | assumed_static_backward | 751 | 751 | 0.5 |
| NSE_INDUSTRY | official_snapshot | 751 | 751 | 1.0 |
| NSE_LEGACY | press_release | 225 | 221 | 0.77 |

## Open data-quality issues

| kind | severity | count |
|---|---|---|
| adj_unverifiable | low | 73,969 |
| unexplained_price_jump | medium | 2,720 |
| adj_implied_confirmed | low | 765 |
| symbol_change_unmatched | low | 62 |
| index_in_not_member | medium | 60 |
| adj_parsed_price_disagrees | medium | 32 |
| adj_parsed_unconfirmed | low | 31 |
| index_out_already_member | medium | 19 |
| fin_html_income_statement_chain | low | 7 |
| multi_stem_episode | medium | 2 |
| adj_mismatch | medium | 1 |
| index_snapshot_placeholder | low | 1 |
