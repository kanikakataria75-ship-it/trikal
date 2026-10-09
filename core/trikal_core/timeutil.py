"""Time model (ARCHITECTURE §2, ADR-003).

Every canonical fact carries `known_at` (when it became public) and `recorded_at` (when TRIKAL
ingested it). All reads are bounded by an `AsOf`. There is deliberately no default `AsOf`: callers
must say which moment they are looking from.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass
from enum import Enum
from zoneinfo import ZoneInfo

IST = ZoneInfo("Asia/Kolkata")
UTC = dt.timezone.utc

# Conventions for exchange end-of-day data (documented in docs/FORMULAS.md §Time conventions).
EOD_KNOWN_TIME = dt.time(16, 0)  # closing price is final after the 15:30 close; bhavcopy follows
PREOPEN_TIME = dt.time(9, 0)  # ex-date adjustments are effective before the 09:15 open


class Precision(str, Enum):
    EXACT = "exact"  # source gives a timestamp
    DAY = "day"  # source gives a date only -> 23:59:59 IST that day
    CONVENTION = "convention"  # fixed documented rule (e.g. EOD prices at 16:00 IST)
    IMPUTED = "imputed"  # no publication time; conservative statutory/lag rule


def ist(year: int, month: int, day: int, hour: int = 0, minute: int = 0, second: int = 0) -> dt.datetime:
    return dt.datetime(year, month, day, hour, minute, second, tzinfo=IST)


def at_ist(d: dt.date, t: dt.time) -> dt.datetime:
    return dt.datetime.combine(d, t, tzinfo=IST)


def end_of_day_ist(d: dt.date) -> dt.datetime:
    return at_ist(d, dt.time(23, 59, 59))


def utcnow() -> dt.datetime:
    return dt.datetime.now(UTC)


@dataclass(frozen=True, order=True)
class AsOf:
    """A tz-aware instant from which the database is viewed. Facts with known_at > ts are invisible."""

    ts: dt.datetime

    def __post_init__(self) -> None:
        if self.ts.tzinfo is None:
            raise ValueError("AsOf requires a timezone-aware datetime")

    @classmethod
    def now(cls) -> AsOf:
        return cls(utcnow())

    @classmethod
    def end_of(cls, d: dt.date) -> AsOf:
        """End of an Indian calendar day: everything published that day is visible."""
        return cls(end_of_day_ist(d))

    @classmethod
    def parse(cls, s: str) -> AsOf:
        s = s.strip()
        if s.upper() == "NOW":
            return cls.now()
        if len(s) == 10:
            return cls.end_of(dt.date.fromisoformat(s))
        t = dt.datetime.fromisoformat(s)
        return cls(t if t.tzinfo else t.replace(tzinfo=IST))

    @property
    def date_ist(self) -> dt.date:
        return self.ts.astimezone(IST).date()

    def __str__(self) -> str:
        return self.ts.astimezone(IST).strftime("%d-%b-%Y %H:%M:%S IST").upper()
