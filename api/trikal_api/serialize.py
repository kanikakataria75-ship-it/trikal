"""JSON shapes for the UI. Metric results keep their state; nothing is coerced to a number or to zero."""

from __future__ import annotations

import dataclasses
import datetime as dt
import math

from trikal_analytics.result import Forbidden, NotAvailable, Undefined, Value


def plain(o):
    """dataclasses, dates, sets, NaN/inf -> JSON-safe values (NaN/inf become null, never 0)."""
    if isinstance(o, float):
        return o if math.isfinite(o) else None
    if isinstance(o, dt.datetime):
        return o.isoformat()
    if isinstance(o, dt.date):
        return o.isoformat()
    if dataclasses.is_dataclass(o) and not isinstance(o, type):
        return {f.name: plain(getattr(o, f.name)) for f in dataclasses.fields(o)}
    if isinstance(o, dict):
        return {str(k): plain(v) for k, v in o.items()}
    if isinstance(o, (list, tuple)):
        return [plain(v) for v in o]
    if isinstance(o, (set, frozenset)):
        return sorted(plain(v) for v in o)
    return o


def result(r) -> dict:
    """One metric result in the UI's value-state vocabulary (UI_SPEC §6)."""
    if isinstance(r, Value):
        return {"state": "value", "metric": r.metric, "value": plain(r.value), "unit": r.unit,
                "formula": r.formula, "basis": r.basis, "warnings": list(r.warnings),
                "low_confidence": any(w.startswith(("playbook_confidence", "old_page")) for w in r.warnings),
                "inputs": [plain(i) for i in r.inputs]}
    if isinstance(r, Forbidden):
        return {"state": "forbidden", "metric": r.what, "playbook": r.playbook, "rule": r.rule, "reason": r.why}
    if isinstance(r, Undefined):
        return {"state": "undefined", "metric": r.metric, "reason": r.reason}
    if isinstance(r, NotAvailable):
        return {"state": "na", "metric": r.metric, "missing": list(r.missing), "reason": r.reason}
    raise TypeError(type(r))
