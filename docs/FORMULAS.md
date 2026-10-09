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
