"""Metric results are a tagged union (ADR-007): a number, or an explicit reason there is no number.

  Value          a number with unit, as-of lineage and the inputs it was computed from
  Undefined      the metric has no meaning for this company right now (P/E when EPS <= 0): never a negative multiple
  NotAvailable   the inputs are missing from our data (named), or the sector metric needs a source we do not have yet
  Forbidden      the sector playbook disallows the metric/method for this company (EBITDA for a bank)

`Forbidden` is raised as an exception by `Engine.compute` / `Lab.run` when the caller asks for a forbidden
combination: it must be impossible to obtain such a number, not merely hidden (invariant 5)."""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field


@dataclass(frozen=True)
class Input:
    name: str
    value: float
    period_end: dt.date | None
    concept: str
    filing_id: str
    known_at: dt.datetime


@dataclass(frozen=True)
class Value:
    metric: str
    value: float
    unit: str
    as_of: dt.datetime
    inputs: tuple[Input, ...] = ()
    basis: str | None = None
    warnings: tuple[str, ...] = ()       # e.g. "cyclical_peak_trap"
    formula: str = ""


@dataclass(frozen=True)
class Undefined:
    metric: str
    reason: str


@dataclass(frozen=True)
class NotAvailable:
    metric: str
    missing: tuple[str, ...]
    reason: str = ""


class ForbiddenError(Exception):
    """A metric or valuation method that the company's sector playbook forbids."""

    def __init__(self, what: str, playbook: str, rule: str, why: str = "") -> None:
        super().__init__(f"{what!r} is forbidden for playbook {playbook!r} ({rule}){': ' + why if why else ''}")
        self.what, self.playbook, self.rule, self.why = what, playbook, rule, why


class ForbiddenMetric(ForbiddenError):
    pass


class ForbiddenMethod(ForbiddenError):
    pass


@dataclass(frozen=True)
class Forbidden:
    """Returned (not raised) by the explainer APIs so a UI can show the rule and the reason."""

    what: str
    playbook: str
    rule: str
    why: str = ""
    sources: tuple[str, ...] = field(default_factory=tuple)


Result = Value | Undefined | NotAvailable
