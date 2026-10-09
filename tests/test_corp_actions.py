"""Golden tests for corporate-action subject parsing (real subject lines from the NSE feed)."""

import pytest

from trikal_pipeline.corp_actions import parse_subject

CASES = [
    # subject, kind, static_factor, dividend amount
    ("Fv Split Rs.10 To Re.1", "split", 0.1, None),
    ("Face Value Split (Sub-Division) - From Rs 10/- Per Share To Re 1/- Per Share", "split", 0.1, None),
    ("Face Value Split (Sub-Division) - From Rs 2/- Per Share To Re 1/- Per Share", "split", 0.5, None),
    ("Bonus 1:1", "bonus", 0.5, None),
    ("Bonus 1:2", "bonus", 2 / 3, None),
    ("Bonus 3:2", "bonus", 0.4, None),
    ("Consolidation Of Shares From Rs 2 To Rs 10", "consolidation", 5.0, None),
    ("Int Div-Rs.3/- Per Share Purpose Revised", "dividend", None, 3.0),
    ("Interim Dividend - Rs 10 Per Share", "dividend", None, 10.0),
    ("Dividend - Rs 2.50 Per Share", "dividend", None, 2.5),
    ("Annual General Meeting/Dividend - Rs 8 Per Share", "dividend", None, 8.0),
    ("Annual General Meeting", "other", None, None),
    ("AGM/Dividend - Nil", "other", None, None),
    ("Demerger", "demerger", None, None),
    ("Div 20%/Bonus 1:1", "bonus+dividend", 0.5, None),
    ("Div 20%/Bonus 1:2/Rights 1:5", "bonus+rights+dividend", 2 / 3, None),
]


@pytest.mark.parametrize("subject,kind,factor,amount", CASES)
def test_parse(subject, kind, factor, amount):
    p = parse_subject(subject)
    assert p.kind == kind
    if factor is None:
        assert p.static_factor() is None
    else:
        assert p.static_factor() == pytest.approx(factor)
    if amount is not None:
        assert p.amount == pytest.approx(amount)


def test_rights_premium_captured():
    p = parse_subject("Rights 1:5 @ Premium Rs 90/-")
    r = p.primary
    assert r.kind == "rights" and r.num == 1 and r.den == 5 and r.amount == 90 and r.note == "premium"


def test_pct_dividend_uses_face_value():
    p = parse_subject("Dividend - 30%", face_value=10)
    assert p.amount == pytest.approx(3.0)
    assert parse_subject("Dividend - 30%").amount is None  # never guess the face value
