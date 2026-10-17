# KASAUTI v1 report card (generated 2026-10-16; in-sample backtest)

Score file `config/scores/kasauti_v1.yaml`, frozen 2026-10-16 (SHA-256 `e43ad59a…e77bb`). Universe: Nifty 500 members on each scoring date
(about 477 scored per date). Scoring dates: last session of Mar / Jun / Sep / Dec, **2023-03 to 2026-09 (15 dates)**. Earlier dates have no
usable inputs: the exchange's 2018-2021 XBRL result files are partial and the HTML era ends in 2017 (RISKS R-38). Forward returns are price
returns on split/bonus-adjusted prices (no dividends) from the next session's open; shares that stopped trading are closed at their last
close (4-18 per horizon). Benchmark: equal-weight average of the scored universe.

| Horizon | Dates | Rank IC (mean) | Newey-West t | IC > 0 on | Top decile − universe | D10 − D1 | Top beat universe on |
|---|---|---|---|---|---|---|---|
| 1 month | 13 | 0.007 | 0.31 | 46% | +0.2% | +0.1% | 54% |
| 3 months | 13 | 0.028 | 1.34 | 77% | +1.2% | +1.7% | 69% |
| 6 months | 12 | 0.037 | 2.14 | 75% | +3.0% | +3.4% | 92% |
| 12 months | 10 | 0.041 | 2.13 | 70% | +5.4% | +6.8% | 80% |

Mean 12-month return by score decile (1 = lowest score): 10.2, 10.2, 9.9, 13.1, 8.2, 13.0, 10.2, 11.0, 13.8, **17.0** (%).
Top-decile portfolio, quarterly, 0.25% cost per side, turnover 48% a quarter: **18.6% a year vs 14.1%** for the equal-weight universe,
maximum drawdown −16.5% vs −19.3% (13 periods, 3.3 years).

## How to read it
- The ranking has a small positive relationship with later returns that grows with the horizon, and only at 6 and 12 months does it
  clear |t| = 2. With 10-13 overlapping observations that is suggestive, not proof.
- **It is fading.** Mean 3-month IC by scoring year: 2023 +0.066, 2024 +0.048, 2025 +0.007, 2026 −0.026 (2026 has only a few dates). Most of
  the average comes from 2023-24; a ranking that earned its keep once and then stopped is a real possibility.
- One market regime (an Indian up-cycle), one definition tried, dividends excluded. Nothing here is a forecast or advice.
- The live record starts at the freeze (2026-10-16): scores computed from now on are never merged with this table.
