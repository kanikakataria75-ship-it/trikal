"""Parse NSE results XBRL (Ind-AS, Banking, NBFC Ind-AS, Non-Ind-AS, Integrated Filing) into facts.

Hard-won rules (verified on real filings, 2026-10-12; see docs/FORMULAS.md §Financial statements):

* Values are full INR, signed. `LevelOfRounding` ("Lakhs", "Crores") only describes precision.
* Context ids carry the column: `OneD` = current reporting period (the quarter), `FourD` = year-to-date
  (or the full year in a Q4 filing). **The XML dates of FourD are wrong**: they repeat the quarter's
  dates (TCS FY24: FourD revenue 2.41 lakh cr, dated Jan-Mar 2024). The true period is
  [financial-year start, reporting-period end], so periods are derived from the column, never from the
  FourD context dates.
* Columns other than One/Four are not interpreted; their facts are skipped and counted (never guessed).
"""

from __future__ import annotations

import datetime as dt
import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field

XBRLI = "{http://www.xbrl.org/2003/instance}"
LINK = "{http://www.xbrl.org/2003/linkbase}"
XBRLDI_EXPLICIT = "{http://xbrl.org/2006/xbrldi}explicitMember"
XBRLDI_TYPED = "{http://xbrl.org/2006/xbrldi}typedMember"

_COL = re.compile(r"^(One|Two|Three|Four|Five|Six|Seven|Eight|Nine|Ten)")
_END = re.compile(r"(D|I)$")

META_KEYS = {
    "Symbol", "ScripCode", "NameOfTheCompany", "ISIN", "ReportingQuarter", "NatureOfReportStandaloneConsolidated",
    "WhetherResultsAreAuditedOrUnaudited", "DateOfStartOfReportingPeriod", "DateOfEndOfReportingPeriod",
    "DateOfStartOfFinancialYear", "DateOfEndOfFinancialYear", "LevelOfRoundingUsedInFinancialStatements",
    "DateOfBoardMeetingWhenFinancialResultsWereApproved", "TypeOfCashFlowStatement",
}


@dataclass
class Fact:
    concept: str
    dims: str
    col: str
    period_start: dt.date | None
    period_end: dt.date
    is_instant: bool
    value: float
    unit: str


@dataclass
class Parsed:
    meta: dict[str, str] = field(default_factory=dict)
    facts: list[Fact] = field(default_factory=list)
    skipped_columns: dict[str, int] = field(default_factory=dict)
    problems: list[str] = field(default_factory=list)


def family_from_url(url: str) -> str:
    name = url.rsplit("/", 1)[-1].upper()
    if name.startswith("INTEGRATED_FILING"):
        return "INTEGRATED"
    for fam in ("NBFC_INDAS", "BANKING", "NONINDAS", "INDAS"):
        if name.startswith(fam):
            return fam
    return "OTHER"


def _d(s: str | None) -> dt.date | None:
    if not s:
        return None
    try:
        return dt.date.fromisoformat(s.strip()[:10])
    except ValueError:
        return None


def parse_results_xbrl(body: bytes) -> Parsed:
    out = Parsed()
    root = ET.fromstring(body)
    ctx: dict[str, tuple] = {}
    for c in root.findall(XBRLI + "context"):
        per = c.find(XBRLI + "period")
        if per is None:
            continue
        inst, s, e = per.find(XBRLI + "instant"), per.find(XBRLI + "startDate"), per.find(XBRLI + "endDate")
        dims = []
        for m in c.iter():
            if m.tag == XBRLDI_EXPLICIT:
                dims.append(f"{m.attrib.get('dimension', '').split(':')[-1]}={(m.text or '').strip().split(':')[-1]}")
            elif m.tag == XBRLDI_TYPED:
                dims.append(f"{m.attrib.get('dimension', '').split(':')[-1]}=" + "".join(m.itertext()).strip())
        cid = c.attrib["id"]
        mcol = _COL.match(cid)
        ctx[cid] = (mcol.group(1) if mcol else "?", inst is not None, _d(inst.text) if inst is not None else _d(s.text if s is not None else None),
                    _d(e.text) if e is not None else None, ";".join(sorted(dims)))

    # Document-level text facts (first occurrence wins).
    for el in root:
        if el.tag.startswith((XBRLI, LINK)) or el.attrib.get("unitRef"):
            continue
        n = el.tag.split("}")[-1]
        if n in META_KEYS and n not in out.meta and el.text:
            out.meta[n] = el.text.strip()

    fy_start = _d(out.meta.get("DateOfStartOfFinancialYear"))
    rep_end = _d(out.meta.get("DateOfEndOfReportingPeriod"))
    for el in root:
        unit = el.attrib.get("unitRef")
        cref = el.attrib.get("contextRef")
        if not unit or not cref or cref not in ctx or el.tag.startswith((XBRLI, LINK)):
            continue
        txt = (el.text or "").strip()
        if not txt:
            continue
        try:
            val = float(txt)
        except ValueError:
            continue
        col, is_inst, a, b, dims = ctx[cref]
        concept = el.tag.split("}")[-1]
        if col not in ("One", "Four"):
            out.skipped_columns[col] = out.skipped_columns.get(col, 0) + 1
            continue
        if is_inst:
            ps, pe = None, a
        elif col == "One":
            ps, pe = a, b
        else:  # year-to-date: the context dates are those of the quarter and must not be used
            ps = fy_start
            pe = rep_end or b
        if pe is None or (not is_inst and ps is None):
            out.problems.append(f"no period for {concept} in {cref}")
            continue
        out.facts.append(Fact(concept, dims, col, ps, pe, is_inst, val, unit))
    return out


def months_between(start: dt.date | None, end: dt.date) -> int | None:
    """Whole months covered by an inclusive [start, end] duration (3 = quarter, 12 = year)."""
    if start is None:
        return None
    return round(((end.year - start.year) * 12 + end.month - start.month) + (end.day - start.day + 1) / 30.4)
