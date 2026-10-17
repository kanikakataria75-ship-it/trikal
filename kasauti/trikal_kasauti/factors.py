"""Score inputs that are not in the metric registry: ownership flow and price momentum. Pure functions over PIT data."""

from __future__ import annotations

import bisect
import datetime as dt

from trikal_core.pit import PitReader
from trikal_core.timeutil import AsOf

FACTOR_METRICS = ("promoter_change_4q", "institution_change_4q", "pledge_pct", "momentum_12_1", "momentum_6", "promise_kept")
STALE_PRICE_DAYS = 10
MAX_PLAUSIBLE_HOLDING_SWING = 12.0       # percentage points in about a year


def ownership_factors(reader: PitReader, security_id: str, as_of: AsOf) -> dict[str, float | None]:
    """Change over about four quarters in promoter holding and in mutual fund + foreign portfolio + insurance holding
    (percentage points), and the promoter pledge as % of total shares. None when a leg is not in the filings (never zero)."""
    out: dict[str, float | None] = {"promoter_change_4q": None, "institution_change_4q": None, "pledge_pct": None}
    q = reader.ownership(security_id, as_of, 8)
    if q:
        now = q[0]
        then = next((r for r in q[1:] if 330 <= (now["period_end"] - r["period_end"]).days <= 400), None)
        if then is not None:
            if now["promoter"] is not None and then["promoter"] is not None:
                out["promoter_change_4q"] = now["promoter"] - then["promoter"]
            legs = ("mutual_funds", "fpi", "insurance")
            if all(now[g] is not None and then[g] is not None for g in legs):
                d = sum(now[g] - then[g] for g in legs)
                # A swing of this size in a year is a change of filing taxonomy (the FPI categories were re-cut in 2026 filings), not
                # institutions buying or selling: treated as not available rather than scored.
                out["institution_change_4q"] = d if abs(d) <= MAX_PLAUSIBLE_HOLDING_SWING else None
            if out["promoter_change_4q"] is not None and abs(out["promoter_change_4q"]) > MAX_PLAUSIBLE_HOLDING_SWING:
                out["promoter_change_4q"] = None
    p = reader.pledge(security_id, as_of)
    if p and p[0][3] is not None:
        out["pledge_pct"] = float(p[0][3])
    return out


class PriceBook:
    """Split/bonus-adjusted daily bars for many securities, loaded once. Adjustments use every confirmed event, which is fine for
    ratios between two past dates (a split is a fact, not a forecast), and look-ahead free for the signal because only prices on
    or before the scoring date enter it."""

    def __init__(self, reader: PitReader, security_ids: list[str], end: AsOf, start: dt.date = dt.date(2017, 1, 1)) -> None:
        self.dates: dict[str, list[dt.date]] = {}
        self.open: dict[str, list[float | None]] = {}
        self.close: dict[str, list[float | None]] = {}
        for sid in security_ids:
            bars = reader.prices(sid, end, start=start, adjusted=True)
            self.dates[sid] = [b.trade_date for b in bars]
            self.open[sid] = [b.open for b in bars]
            self.close[sid] = [b.close for b in bars]

    def _idx(self, sid: str, day: dt.date) -> int:
        """Index of the last bar on or before `day`, -1 if none."""
        return bisect.bisect_right(self.dates.get(sid, []), day) - 1

    def momentum(self, sid: str, day: dt.date) -> dict[str, float | None]:
        out: dict[str, float | None] = {"momentum_12_1": None, "momentum_6": None}
        i = self._idx(sid, day)
        if i < 0 or (day - self.dates[sid][i]).days > STALE_PRICE_DAYS:
            return out
        c = self.close[sid]

        def ratio(a: int, b: int) -> float | None:
            return c[a] / c[b] - 1 if a >= 0 and b >= 0 and c[a] and c[b] else None

        out["momentum_12_1"] = ratio(i - 21, i - 252)        # the last month is skipped: short-term reversal
        out["momentum_6"] = ratio(i, i - 126)
        return out

    def entry_open(self, sid: str, day: dt.date) -> tuple[dt.date, float] | None:
        """(date, open) of the first session strictly after `day`: the earliest a signal known at the close of `day` can be traded."""
        ds = self.dates.get(sid, [])
        j = bisect.bisect_right(ds, day)
        while j < len(ds) and not self.open[sid][j]:
            j += 1
        return (ds[j], self.open[sid][j]) if j < len(ds) else None

    def exit_price(self, sid: str, day: dt.date, data_end: dt.date) -> tuple[float, bool] | None:
        """Open of the first session on or after `day`; if the share stopped trading earlier, its last close and True.
        None when `day` is beyond the data."""
        ds = self.dates.get(sid, [])
        if day > data_end or not ds:
            return None
        j = bisect.bisect_left(ds, day)
        while j < len(ds) and not self.open[sid][j]:
            j += 1
        if j < len(ds):
            return self.open[sid][j], False
        last = next((c for c in reversed(self.close[sid]) if c), None)
        return (last, True) if last and (day - ds[-1]).days > 15 else None

    def last_close_if_gone(self, sid: str, day: dt.date) -> float | None:
        """Last close of a share whose final bar is more than 15 days before `day` (it has stopped trading), else None."""
        ds = self.dates.get(sid, [])
        if not ds or (day - ds[-1]).days <= 15:
            return None
        return next((c for c in reversed(self.close[sid]) if c), None)
