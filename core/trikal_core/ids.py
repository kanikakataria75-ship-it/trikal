"""Identifier helpers.

Indian ISIN layout (NSDL): `IN` + issuer-type char + 4-char issuer code + 2-char security type
+ 2-char serial + check digit. Example INE117A01022 = INE / 117A / 01 (equity) / 02 / 2.
A face-value change gives the same issuer+type a new serial, so the first nine characters
(the "stem") identify one equity line of one issuer across such changes (ADR-011).
"""

from __future__ import annotations

import re

_ISIN_RE = re.compile(r"^[A-Z]{2}[A-Z0-9]{9}[0-9]$")


def isin_check_digit_ok(isin: str) -> bool:
    if not _ISIN_RE.match(isin or ""):
        return False
    digits = "".join(str(int(c, 36)) for c in isin[:-1])
    total = 0
    for i, ch in enumerate(reversed(digits)):
        n = int(ch)
        if i % 2 == 0:
            n *= 2
            if n > 9:
                n -= 9
        total += n
    return (10 - total % 10) % 10 == int(isin[-1])


def is_valid_isin(isin: str | None) -> bool:
    return bool(isin) and isin_check_digit_ok(isin.strip().upper())


def isin_stem(isin: str) -> str:
    return isin[:9]


def is_company_equity_isin(isin: str | None) -> bool:
    """INE = company securities; type code 01 = equity shares. IN9 = partly paid / DVR lines (kept separate)."""
    if not is_valid_isin(isin):
        return False
    return isin[:3] in ("INE", "IN9") and isin[7:9] == "01"


def security_id_for_isin(isin: str) -> str:
    return security_id_for_stem(isin_stem(isin))


def security_id_for_stem(stem: str) -> str:
    return "S:" + stem


def synthetic_security_id(exchange: str, code: str, first_date: str) -> str:
    """For listings that never traded in an ISIN-carrying file (e.g. NSE delistings before Aug 2011)."""
    return f"X:{exchange}:{code}:{first_date}"
