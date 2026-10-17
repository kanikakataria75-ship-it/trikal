"""The screening language: safe parsing, percent signs, three-valued logic (missing data never matches), and the endpoint over stored scores."""

from __future__ import annotations

import datetime as dt
import json

import pytest
from fastapi.testclient import TestClient

from conftest import D, seed_company
from trikal_analytics import screener as SC
from trikal_core.db import insert_many
from trikal_core.pit import PitReader
from trikal_core.timeutil import utcnow

ROWS = [
    {"code": "AAA", "name": "Alpha Bank", "sector": "Financial Services", "playbook": "banks", "score": 80.0, "roce": 0.25, "pe": 12.0, "pledge_pct": 0.0},
    {"code": "BBB", "name": "Beta Tech", "sector": "Information Technology", "playbook": "it_services", "score": 65.0, "roce": 0.35, "pe": 30.0, "pledge_pct": None},
    {"code": "CCC", "name": "Gamma Steel", "sector": "Metals & Mining", "playbook": "metals_mining", "score": 40.0, "roce": None, "pe": 8.0, "pledge_pct": 0.2},
]
F = set(ROWS[0])


def codes(q):
    return [r["code"] for r in SC.run(q, ROWS, F)]


def test_numbers_percent_and_text():
    assert codes("roce > 20%") == ["AAA", "BBB"]                                   # 20% is 0.2; CCC has no ROCE
    assert codes("pe < 15 and score >= 40") == ["AAA", "CCC"]
    assert codes("sector = 'information technology'") == ["BBB"]                   # text is case-insensitive
    assert codes("playbook in ('banks', 'metals_mining')") == ["AAA", "CCC"]
    assert codes("name contains 'tech'") == ["BBB"]
    assert codes("") == ["AAA", "BBB", "CCC"]


def test_missing_data_never_matches_and_not_does_not_rescue_it():
    assert codes("pledge_pct = 0") == ["AAA"]                                      # BBB has no figure: not a zero
    assert codes("not (pledge_pct > 0)") == ["AAA"]                                # CCC pledges; BBB unknown stays out
    assert codes("roce > 30% or pe < 10") == ["BBB", "CCC"]                        # unknown or true is true
    assert codes("roce > 30% and pe < 10") == []                                   # unknown and false is false, unknown and true is unknown


def test_precedence_and_parentheses():
    assert codes("score > 70 or roce > 30% and pe < 20") == ["AAA"]                # and binds tighter than or
    assert codes("(score > 70 or roce > 30%) and pe < 20") == ["AAA"]
    assert codes("(score > 70 or roce > 30%) and pe > 20") == ["BBB"]


@pytest.mark.parametrize("bad, msg", [("roce >", "ends too early"), ("bogus > 3", "unknown field"), ("roce > 3 and", "ends too early"),
                                      ("score > 'x'", "text field"), ("roce > 3 )", "unexpected"), ("sector > 'a'", "only be compared"),
                                      ("pe # 3", "unexpected character")])
def test_errors_are_explained_not_executed(bad, msg):
    with pytest.raises(SC.ScreenError, match=msg):
        SC.run(bad, ROWS, F)


def test_nothing_is_evaluated_as_code():
    with pytest.raises(SC.ScreenError):
        SC.run("__import__('os').system('echo hi')", ROWS, F)
    with pytest.raises(SC.ScreenError):
        SC.run("score > 1; drop table x", ROWS, F)


def test_endpoint_screens_the_stored_scores_as_of_a_date(con, monkeypatch):
    import trikal_api.app as appmod

    sid1 = seed_company(con, sid="S:INE000S01", code="SCRA", name="Screen A Ltd", sector="Information Technology")
    sid2 = seed_company(con, sid="S:INE000S02", code="SCRB", name="Screen B Ltd", sector="Information Technology")
    for sid, score, roce in ((sid1, 71.0, 0.31), (sid2, 52.0, 0.12)):
        det = {"profile": "industrial", "peer_fallback": False, "dropped": {}, "skipped": {}, "drivers": [],
               "pillars": {"quality": {"score": score / 100, "coverage": 1.0, "metrics": {"roce": {"value": roce, "percentile": score / 100}}}}}
        insert_many(con, "INSERT INTO kasauti_score VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                    [(1, D(2025, 3, 28), sid, score, 0.9, "ok", "it_services", "it_services", 10, json.dumps(det), utcnow())])
    insert_many(con, "INSERT INTO index_membership VALUES (?,?,?,?,?,?,?,?,?)",
                [("NIFTY500", sid, code, D(2020, 1, 1), D(2030, 1, 1), "press", 1.0, utcnow(), "x") for sid, code in ((sid1, "SCRA"), (sid2, "SCRB"))]) \
        if False else None
    monkeypatch.setattr(appmod, "open_reader", lambda read_only=True: PitReader(con))
    monkeypatch.setattr(appmod.DB, "reader", None)
    appmod._SCREEN_CACHE.clear()
    c = TestClient(appmod.app)
    j = c.get("/api/screen?as_of=2025-06-01&q=roce > 20%").json()
    assert j["matched"] == 1 and j["rows"][0]["name"] == "Screen A Ltd" and j["scoring_date"] == "2025-03-28" and "roce" in j["columns"]
    assert c.get("/api/screen?as_of=2024-01-01&q=score > 1").status_code == 409          # no scores that early: said, not faked
    assert c.get("/api/screen?as_of=2025-06-01&q=nonsense > 1").status_code == 422
    assert c.get("/api/screen?q=score > 1").status_code == 422                            # as_of is required
    f = c.get("/api/screen/fields?as_of=2025-06-01").json()
    assert "roce" in f["metrics"] and "score" in f["numbers"]
