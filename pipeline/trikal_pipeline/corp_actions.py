"""Parse free-text corporate-action subjects into structured actions (golden-file tested).

The subject line is free text ("Fv Split Rs.10 To Re.1", "Bonus 1:1", "Rights 1:5 @ Premium Rs 90/-",
"AGM/Dividend - 30%"). One subject may carry several actions; we search for each pattern rather
than splitting on "/" (which also appears inside a single clause, e.g. "rights/1:3/prem of rs 25").

Price factor convention (FORMULAS.md §Corporate actions): `factor` multiplies prices dated strictly
before the ex-date so they are comparable with prices on/after it.
  split / consolidation  factor = new_fv / old_fv
  bonus a:b              factor = b / (a + b)      (a new shares for every b held)
  rights a:b at P        factor = TERP / P_cum, TERP = (b*P_cum + a*P) / (a + b)  (needs P_cum)
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

_NUM = r"(\d+(?:\.\d+)?)"
_RS = r"(?:rs|re|inr)\.?\s*"

ADJUSTING = ("split", "consolidation", "bonus", "rights", "demerger", "capital_reduction")


@dataclass
class Action:
    kind: str
    num: float | None = None
    den: float | None = None
    amount: float | None = None  # dividend Rs/share, rights premium/price, etc.
    note: str = ""


@dataclass
class Parsed:
    actions: list[Action] = field(default_factory=list)

    @property
    def kind(self) -> str:
        order = ["split", "consolidation", "bonus", "rights", "demerger", "capital_reduction",
                 "amalgamation", "buyback", "dividend", "other"]
        kinds = {a.kind for a in self.actions} or {"other"}
        return "+".join(k for k in order if k in kinds)

    @property
    def primary(self) -> Action | None:
        for k in ADJUSTING:
            for a in self.actions:
                if a.kind == k:
                    return a
        return self.actions[0] if self.actions else None

    @property
    def num(self) -> float | None:
        return self.primary.num if self.primary else None

    @property
    def den(self) -> float | None:
        return self.primary.den if self.primary else None

    @property
    def amount(self) -> float | None:
        divs = [a.amount for a in self.actions if a.kind == "dividend" and a.amount is not None]
        if divs:
            return sum(divs)
        return self.primary.amount if self.primary else None

    def static_factor(self) -> float | None:
        """Product of factors computable from the text alone (split/consolidation/bonus). None if none."""
        f, any_ = 1.0, False
        for a in self.actions:
            if a.kind in ("split", "consolidation") and a.num and a.den:
                f *= a.den / a.num
                any_ = True
            elif a.kind == "bonus" and a.num and a.den:
                f *= a.den / (a.num + a.den)
                any_ = True
        return f if any_ else None


def _norm(s: str) -> str:
    s = s.lower().replace("–", "-").replace("—", "-")
    s = re.sub(r"\s+", " ", s)
    return s.strip()


_SPLIT = re.compile(
    r"(?:split|sub[- ]?division|sub[- ]?divided)[^0-9]*?" + _RS + _NUM + r"[^0-9]*?(?:to|-)\s*" + _RS + _NUM)
_SPLIT_NO_RS = re.compile(r"(?:split|sub[- ]?division)[^0-9]*?" + _NUM + r"\s*(?:/-)?\s*to\s*" + _NUM)
_CONSOL = re.compile(r"consolidat\w*[^0-9]*?" + _RS + "?" + _NUM + r"[^0-9]*?to\s*" + _RS + "?" + _NUM)
_BONUS = re.compile(r"bonus(?:\s*issue)?[^0-9:]{0,12}" + _NUM + r"\s*:\s*" + _NUM)
_RIGHTS = re.compile(r"rights?(?:\s*issue)?[^0-9:]{0,12}" + _NUM + r"\s*:\s*" + _NUM + r"([^/]*(?:/[^/]*)?)")
_PREMIUM = re.compile(r"prem(?:ium)?\.?\s*(?:of\s*)?" + _RS + "?" + _NUM)
_AT_PRICE = re.compile(r"@\s*" + _RS + "?" + _NUM)
_DIV_RS = re.compile(r"\bdiv(?:idend)?\b[^/%]*?" + _RS + _NUM)
_DIV_PCT = re.compile(r"\bdiv(?:idend)?\b[^/]*?" + _NUM + r"\s*%")
_DIV_ANY = re.compile(r"\bdiv(?:idend)?\b(?!\s*-?\s*nil)")


def parse_subject(subject: str, face_value: float | None = None) -> Parsed:
    s = _norm(subject)
    p = Parsed()
    if not s or s in ("-", "nil"):
        return p

    m = _SPLIT.search(s) or _SPLIT_NO_RS.search(s)
    if m:
        old, new = float(m.group(1)), float(m.group(2))
        if old > 0 and new > 0 and old != new:
            p.actions.append(Action("split" if new < old else "consolidation", old, new))
    m = _CONSOL.search(s)
    if m and not any(a.kind in ("split", "consolidation") for a in p.actions):
        old, new = float(m.group(1)), float(m.group(2))
        if old > 0 and new > 0 and old != new:
            p.actions.append(Action("consolidation" if new > old else "split", old, new))
    for m in _BONUS.finditer(s):
        p.actions.append(Action("bonus", float(m.group(1)), float(m.group(2))))
    for m in _RIGHTS.finditer(s):
        tail = m.group(3) or ""
        prem = _PREMIUM.search(tail)
        at = _AT_PRICE.search(tail)
        price = None
        note = ""
        if at:
            price, note = float(at.group(1)), "issue_price"
        elif prem:
            price, note = float(prem.group(1)), "premium"
        p.actions.append(Action("rights", float(m.group(1)), float(m.group(2)), price, note))
    if "demerger" in s or "de-merger" in s or "spin off" in s or "spin-off" in s:
        p.actions.append(Action("demerger"))
    if re.search(r"(capital|share capital)\s*reduction|reduction (of|in) (share )?capital", s):
        p.actions.append(Action("capital_reduction"))
    if "amalgamation" in s or re.search(r"\bmerger\b", s):
        p.actions.append(Action("amalgamation"))
    if re.search(r"buy\s*-?\s*back", s):
        p.actions.append(Action("buyback"))

    divs = list(_DIV_RS.finditer(s))
    if divs:
        for m in divs:
            p.actions.append(Action("dividend", amount=float(m.group(1)), note="rs_per_share"))
    else:
        m = _DIV_PCT.search(s)
        if m:
            pct = float(m.group(1))
            amt = pct / 100.0 * face_value if face_value else None
            p.actions.append(Action("dividend", amount=amt, num=pct, note="pct_of_fv"))
        elif _DIV_ANY.search(s):
            p.actions.append(Action("dividend", note="amount_not_stated"))
    return p
