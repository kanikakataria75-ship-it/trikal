# KASAUTI v2 report card (18-Oct-2026, draft, not frozen)

In-sample backtest, same conventions as v1 (docs/reports/kasauti_v1.md): 15 quarterly scoring dates from 31-Mar-2023, entry at the next session's open, price returns without dividends, equal-weight Nifty 500 as benchmark, 0.25% cost per side. v2 weights were fixed before this run and were not changed after seeing it. One v2 definition was tried.

| Horizon | v1 rank IC (t) | v2 rank IC (t) | v1 top decile - universe | v2 top decile - universe |
|---|---|---|---|---|
| 1 month | 0.007 (0.31) | 0.009 (0.38) | +0.2% | +0.2% |
| 3 months | 0.028 (1.34) | 0.033 (1.49) | +1.2% | +1.3% |
| 6 months | 0.037 (2.14) | 0.044 (2.59) | +3.0% | +3.2% |
| 12 months | 0.041 (2.13) | 0.049 (2.79) | +5.4% | +5.2% |

Top-decile portfolio, quarterly, costs included: v1 18.6% a year, v2 19.0%, universe 14.1%; max drawdown v1 -16.5%, v2 -15.3%; turnover 48% and 46% a quarter.

**Reading it.** v2 is a little better than v1 at every horizon, but the gap (about 0.005 to 0.008 of rank IC) is far smaller than the noise of a 10-to-13-date history, so the two are not statistically separable. Do not read it as v2 being proven better.

**Where the difference comes from.** Earnings quality is scored for about 80% of companies (cash-flow statements exist from 2022). Management credibility is scored for none of them before 2025 and for 50 companies on 30-Sep-2026 (the call transcripts we hold start in 2024; a statement needs its financial year's results before it can be judged), so it contributes nothing to the backtest. Its effect can only be judged on a live record.

**Status.** v1 remains the frozen reference and the default in the terminal. v2 is selectable in KAS and the heatmap ("v2 draft"). Freezing v2 is the owner's decision.

**Promise Tracker changes made while building v2 (all deterministic, 18/19-Oct-2026).** Reading a statement with no year named as "the year in progress" was tried and rejected (in a sample of 12, most verdicts were about a segment, an analyst's question or an old guide, and half were "missed"). Judging ROE/ROCE targets was also tried and rejected (a bank's NIM was read as ROE). Kept: statements about a segment, business unit or geography and percentages that are a share ("80% of revenue") are listed but not judged; "about X%" that is exceeded counts as delivered (all four judged figures are better when higher); a sector-forbidden metric (EBITDA margin for a bank) is "not judged", not an error. After these, 102 companies have at least one judged statement on 30-Sep-2026 and 50 have two or more (the credibility pillar needs two); v2 was re-scored from 31-Mar-2025 on. Even the explicit-year verdicts are only as good as the rules: a sample of 14 had roughly half clearly right, which is why credibility carries 5% and is shrunk toward 50%.
