"""Concalls without a model: statements with numbers, deterministic verdicts, word-list tone."""

from __future__ import annotations

import datetime as dt

import pytest
from fastapi.testclient import TestClient

from conftest import D, add_quarters, seed_company
from trikal_analytics import metrics as M
from trikal_analytics import promises as PR
from trikal_core.db import insert_many
from trikal_core.pit import PitReader
from trikal_core.timeutil import AsOf, at_ist
from trikal_pipeline import call_parse as CP

CALL_Q = D(2025, 6, 30)                          # a call held in July 2025 about the June quarter
FY26 = D(2026, 3, 31)


def promise(s, page=3):
    return CP.read_promise(s, page, CP.fy_end_of(CALL_Q))


def test_a_guided_range_with_a_period_becomes_a_promise():
    p = promise("For this financial year we expect revenue growth of 8% to 10%.")
    assert (p.metric, p.op, p.low, p.high, p.horizon_end, p.horizon_kind) == ("revenue_growth", "range", 8.0, 10.0, FY26, "fy")
    p = promise("Our operating margin guidance for FY27 is at least 22%.")
    assert (p.metric, p.op, p.low, p.horizon_end) == ("ebit_margin", "at_least", 22.0, D(2027, 3, 31))
    p = promise("We are aiming for double-digit revenue growth next year.")
    assert p.op == "at_least" and p.low == 10.0 and p.horizon_end == D(2027, 3, 31)


def test_questions_the_past_negations_and_multi_year_targets_are_not_judged_promises():
    assert promise("Can you tell us whether you expect revenue growth of 10% this year?") is None            # a question
    assert promise("Revenue grew 12% last year and margins were at 21% in the quarter.") is None             # the past
    assert promise("We do not expect revenue growth of more than 5% this year.") is None                      # negated: not interpreted
    assert promise("You guided to margins of 20% to 22% for FY26, what changed?") is None                     # an analyst speaking
    assert promise("We will grow revenue 15% in the near future.").horizon_kind == "none"                     # no period: kept, not judged
    p = promise("We target revenue growth of 15% CAGR over the next five years.")
    assert p.horizon_kind == "multi" and p.horizon_end is None


def test_tone_counts_words_not_questions_and_finds_evasive_answers():
    sents = ["Demand remains strong and margins improved with robust growth in the quarter overall.",
             "There are significant headwinds and the environment is challenging with volatile input costs ahead.",
             "We may possibly see something roughly around this level depending on how things go next year.",
             "Can you give us the guidance for next year given all the headwinds in the market today?",
             "That is something we would rather take offline because it is too early to say anything useful."]
    tone, ex = CP.tone_of(sents)
    assert tone["positive_rate"] > 0 and tone["negative_rate"] > 0 and tone["hedge_rate"] > 0
    assert tone["evasive_count"] == 1 and ex["evasive"] and "offline" in ex["evasive"][0]
    assert tone["words"] < sum(len(s.split()) for s in sents)                                                # the question was left out


def test_parse_text_splits_prepared_remarks_from_questions_and_skips_the_covering_letter():
    cover = "Dear Sirs, Disclosure under Regulation 30. Scrip Code 500325. " * 20
    prepared = ("Good morning everyone and welcome to the call. " + "We delivered a strong quarter with healthy demand across segments. " * 150
                + "For this financial year we expect revenue growth of 8% to 10%. ")
    qa = "Now we will begin the question and answer session. " + "Thank you for the question, we will see how it goes and it may vary. " * 100
    r = CP.parse_text([cover, prepared, qa], D(2025, 7, 20), CALL_Q)
    assert r.status == "ok" and r.tone["has_qa"] is True and r.tone["prepared"]["words"] > 0 and r.tone["qa"]["words"] > 0
    assert [p.metric for p in r.promises] == ["revenue_growth"] and r.promises[0].page == 2
    assert CP.parse_text(["short"], D(2025, 7, 20), CALL_Q).status.startswith("too short")


# ---- verdicts against point-in-time results ---------------------------------------------------------------------------

def test_verdict_rules():
    assert PR.verdict_for("range", 8, 10, 9.0) == "delivered" and PR.verdict_for("range", 8, 10, 12.0) == "delivered"
    assert PR.verdict_for("range", 8, 10, 7.5) == "partially" and PR.verdict_for("range", 8, 10, 3.0) == "missed"
    assert PR.verdict_for("about", 21, 21, 21.9) == "delivered" and PR.verdict_for("about", 21, 21, 12.0) == "missed"
    assert PR.verdict_for("at_most", 5, 5, 4.0) == "delivered" and PR.verdict_for("at_most", 5, 5, 7.0) == "missed"


def seeded(con):
    sid = seed_company(con, sid="S:INE000C01", code="CALLCO", sector="Fast Moving Consumer Goods")
    # four quarters of FY25 and four of FY26: revenue 1000 a quarter then 1100: 10% growth; EBITDA margin constant
    fy25, fy26 = [D(2024, 6, 30), D(2024, 9, 30), D(2024, 12, 31), D(2025, 3, 31)], [D(2025, 6, 30), D(2025, 9, 30), D(2025, 12, 31), D(2026, 3, 31)]
    from conftest import add_fact_row
    for pe in fy25:
        add_fact_row(con, sid, "RevenueFromOperations", 1000.0, pe, 3, known=at_ist(pe + dt.timedelta(days=30), dt.time(18)))
    for pe in fy26:
        add_fact_row(con, sid, "RevenueFromOperations", 1100.0, pe, 3, known=at_ist(pe + dt.timedelta(days=30), dt.time(18)))
    return sid


def test_judge_waits_for_the_results_and_uses_only_what_was_public(con):
    sid = seeded(con)
    eng = M.Engine(PitReader(con))
    p = {"metric": "revenue_growth", "op": "range", "low": 8.0, "high": 12.0, "horizon_end": FY26, "horizon_kind": "fy"}
    early = PR.judge(eng, sid, p, AsOf.end_of(D(2026, 4, 15)))
    assert early["verdict"] == "pending"                                                                       # FY26 results are not public yet
    late = PR.judge(eng, sid, p, AsOf.end_of(D(2026, 8, 1)))
    assert late["verdict"] == "delivered" and late["actual"] == pytest.approx(10.0)
    miss = PR.judge(eng, sid, {**p, "low": 14.0, "high": 16.0}, AsOf.end_of(D(2026, 8, 1)))
    assert miss["verdict"] == "missed"
    assert PR.judge(eng, sid, {**p, "horizon_kind": "multi", "horizon_end": None}, AsOf.end_of(D(2026, 8, 1)))["verdict"] == "not judged"
    assert PR.judge(eng, sid, {**p, "metric": "capex"}, AsOf.end_of(D(2026, 8, 1)))["verdict"] == "not judged"
    other_year = PR.judge(eng, sid, {**p, "horizon_end": D(2027, 3, 31)}, AsOf.end_of(D(2028, 1, 1)))
    assert other_year["verdict"] == "no data"                                                                  # that year is not in the database


def test_credibility_needs_enough_judged_statements():
    few = PR.credibility([{"verdict": "delivered"}, {"verdict": "missed"}, {"verdict": "pending"}])
    assert few["score"] is None and few["judged"] == 2 and few["pending"] == 1
    many = PR.credibility([{"verdict": "delivered"}] * 3 + [{"verdict": "partially"}, {"verdict": "missed"}])
    assert many["score"] == pytest.approx((3 + 0.5) / 5)


def test_endpoint_serves_statements_judged_at_the_as_of_date(con, monkeypatch):
    import trikal_api.app as appmod

    sid = seeded(con)
    ka = at_ist(D(2025, 7, 20), dt.time(18))
    insert_many(con, "INSERT INTO concall VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                [("u1", sid, "CALLCO", ka, CALL_Q, 20, 9000, "ok", '{"all": {"net_tone": 0.3, "hedge_rate": 4.0, "negative_rate": 3.0, "evasive_count": 1, "words": 9000}, "has_qa": true}',
                  '{"evasive": ["take that offline"]}', ka)])
    insert_many(con, "INSERT INTO concall_promise VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                [("u1", sid, ka, CALL_Q, "revenue_growth", "range", 8.0, 12.0, FY26, "fy", "We expect revenue growth of 8% to 12% this year.", 4),
                 ("u1", sid, ka, CALL_Q, "revenue_growth", "range", 8.0, 12.0, FY26, "fy", "We expect revenue growth of 8% to 12% this year.", 9)])
    monkeypatch.setattr(appmod, "open_reader", lambda read_only=True: PitReader(con))
    monkeypatch.setattr(appmod.DB, "reader", None)
    c = TestClient(appmod.app)
    j = c.get("/api/company/CALLCO/concalls?as_of=2026-08-01").json()
    assert j["calls"] == 1 and len(j["promises"]) == 1 and j["promises"][0]["verdict"] == "delivered"          # the repeat was counted once
    assert j["tone"][0]["net_tone"] == 0.3 and j["credibility"]["score"] is None
    assert c.get("/api/company/CALLCO/concalls?as_of=2025-07-01").json()["calls"] == 0                         # not public yet
    assert c.get("/api/company/CALLCO/concalls?as_of=2025-08-01").json()["promises"][0]["verdict"] == "pending"
    assert c.get("/api/company/CALLCO/concalls").status_code == 422


def test_one_sentence_with_two_figures_gives_two_promises_each_with_its_own_metric():
    ps = CP.read_promises("Our FY27 growth guidance is now 2.5% to 4%, and our EBIT margin guidance remains at 17.5% to 18.5%.", 3, CP.fy_end_of(CALL_Q))
    got = {p.metric: (p.low, p.high) for p in ps}
    assert got == {"revenue_growth": (2.5, 4.0), "ebit_margin": (17.5, 18.5)}
    assert CP.read_promises("Revenue growth and margin guidance is 17% to 18% for FY27.", 3, CP.fy_end_of(CALL_Q)) == []     # two metrics, one figure: ambiguous


def test_constant_currency_and_unspecified_margins_are_listed_but_never_judged(con):
    cc = promise("We expect revenue growth of 8% to 10% in constant currency this year.")
    assert cc.metric == "revenue_growth_cc"
    assert promise("We expect EBITDA margin of 24% to 26% this year.").metric == "ebitda_margin"
    assert promise("We expect margins of around 20% this year.").metric == "margin_generic"
    sid = seeded(con)
    eng = M.Engine(PitReader(con))
    base = {"op": "range", "low": 8.0, "high": 10.0, "horizon_end": FY26, "horizon_kind": "fy"}
    for m in ("revenue_growth_cc", "margin_generic"):
        j = PR.judge(eng, sid, {**base, "metric": m}, AsOf.end_of(D(2026, 8, 1)))
        assert j["verdict"] == "not judged" and j["why"]


def test_a_statement_with_no_year_named_is_never_judged_and_a_forbidden_metric_is_not_an_error(con):
    sid = seeded(con)
    eng = M.Engine(PitReader(con))
    p = {"metric": "revenue_growth", "op": "range", "low": 8.0, "high": 12.0, "horizon_end": None, "horizon_kind": "none", "call_period_end": D(2025, 12, 31),
         "quote": "We expect revenue growth of 8% to 12%."}
    j = PR.judge(eng, sid, p, AsOf.end_of(D(2026, 8, 1)))
    assert j["verdict"] == "not judged" and "no single financial year" in j["why"]

    class Bank:
        def resolution(self, *a):
            return eng.resolution(*a)

        def compute(self, *a):
            from trikal_analytics.result import ForbiddenMetric
            raise ForbiddenMetric("ebitda_margin", "banks", "forbidden.metrics", "no EBITDA for a bank")

    f = PR.judge(Bank(), sid, {**p, "metric": "ebitda_margin", "horizon_kind": "fy", "horizon_end": FY26}, AsOf.end_of(D(2026, 8, 1)))
    assert f["verdict"] == "not judged" and "not defined" in f["why"]


def test_statements_about_a_segment_or_a_share_and_return_targets_are_listed_but_not_judged(con):
    sid = seeded(con)
    eng = M.Engine(PitReader(con))
    base = {"metric": "revenue_growth", "op": "range", "low": 8.0, "high": 12.0, "horizon_end": FY26, "horizon_kind": "fy"}
    late = AsOf.end_of(D(2026, 8, 1))
    assert PR.judge(eng, sid, {**base, "quote": "We expect revenue growth of 8% to 12% in our US business."}, late)["verdict"] == "not judged"
    assert PR.judge(eng, sid, {**base, "quote": "Our verticals accounted for approximately 80% of FY25 revenue."}, late)["verdict"] == "not judged"
    assert PR.judge(eng, sid, {**base, "quote": "We expect revenue growth of 8% to 12% for the company."}, late)["verdict"] == "delivered"
    assert PR.judge(eng, sid, {**base, "metric": "return_ratio", "quote": "ROE 16% to 17%, NIM 3.65% to 3.70%"}, late)["verdict"] == "not judged"
    assert PR.verdict_for("about", 15, 15, 41.0) == "delivered" and PR.verdict_for("about", 15, 15, 5.0) == "missed"    # beating a figure is not a broken promise
