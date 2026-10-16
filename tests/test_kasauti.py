"""KASAUTI: peer percentiles, pillars, dropped pillars, no imputation; the report-card statistics on synthetic series."""

from __future__ import annotations

import datetime as dt
import json

import numpy as np
import pytest

from trikal_kasauti import backtest as BT
from trikal_kasauti import config as KC
from trikal_kasauti.factors import PriceBook
from trikal_kasauti.scoring import _percentile, score_panel

D = dt.date


def cfg():
    return KC.load(1)


def company(i, playbook="it_services", profile="industrial", **vals):
    base = {m: None for m in ("roce", "roe", "ebitda_margin", "net_margin", "revenue_growth", "profit_growth", "ev_ebitda", "pe", "pb",
                              "fcf_yield", "net_debt_ebitda", "debt_to_equity", "interest_coverage", "altman_z", "promoter_change_4q",
                              "pledge_pct", "institution_change_4q", "momentum_12_1", "momentum_6")}
    base.update(vals)
    return {"security_id": f"S:{i:03d}", "playbook": playbook, "profile": profile,
            "parent": "financials" if profile == "financial" else "industrial", "values": base, "skipped": {}}


def full(i, q):
    """A company whose every metric moves with q (higher q = better on every metric, lower on the 'lower is better' ones)."""
    return company(i, roce=q, roe=q, ebitda_margin=q, net_margin=q, revenue_growth=q, profit_growth=q, ev_ebitda=-q, pe=-q, pb=-q, fcf_yield=q,
                   net_debt_ebitda=-q, debt_to_equity=-q, interest_coverage=q, altman_z=q, promoter_change_4q=q, pledge_pct=-q,
                   institution_change_4q=q, momentum_12_1=q, momentum_6=q)


def test_config_is_valid_and_weights_sum_to_one():
    c = cfg()
    for prof in c.profiles.values():
        assert sum(p.weight for p in prof) == pytest.approx(1.0)
    assert "credibility" in c.not_in_v1 and len(c.sha256) == 64


def test_percentile_uses_mid_rank_for_ties():
    assert _percentile([1, 2, 3, 4], 4) == pytest.approx(0.875) and _percentile([1, 2, 2, 3], 2) == pytest.approx(0.5)


def test_better_on_every_metric_scores_higher_and_direction_is_respected():
    rows = [full(i, q) for i, q in enumerate(range(1, 13))]
    out = {r["security_id"]: r for r in score_panel(rows, cfg(), D(2025, 3, 28))}
    scores = [out[f"S:{i:03d}"]["score"] for i in range(12)]
    assert scores == sorted(scores) and scores[-1] > 90 and scores[0] < 10              # lower-is-better metrics were flipped too
    top = out["S:011"]
    assert top["confidence"] == pytest.approx(1.0) and top["status"] == "ok" and top["peer_group"] == "it_services"
    assert "credibility" in top["dropped"] and top["dropped"]["credibility"].startswith("not in v1")   # reported, not hidden


def test_missing_is_never_imputed_and_thin_pillars_are_dropped():
    rows = [full(i, q) for i, q in enumerate(range(1, 13))]
    rows[5] = company(5, roce=5, roe=5, ebitda_margin=5, net_margin=5)                     # quality only
    r5 = next(r for r in score_panel(rows, cfg(), D(2025, 3, 28)) if r["security_id"] == "S:005")
    assert r5["score"] is None and r5["status"].startswith("insufficient data")
    rows[5] = full(5, 5)
    rows[5]["values"].update(roce=None, roe=None, ebitda_margin=None, net_margin=None)     # quality pillar has no data at all
    r5 = next(r for r in score_panel(rows, cfg(), D(2025, 3, 28)) if r["security_id"] == "S:005")
    assert "quality" in r5["dropped"] and "quality" not in r5["pillars"] and r5["score"] is not None
    assert r5["confidence"] < 0.8                                                           # confidence reflects what was missing


def test_small_playbook_falls_back_to_the_parent_group_and_says_so():
    rows = [full(i, q) for i, q in enumerate(range(1, 11))]
    rows += [full(20 + i, q) for i, q in enumerate(range(1, 4))]
    for r in rows[10:]:
        r["playbook"] = "cement"                                                            # 3 peers < min_peers
    out = {r["security_id"]: r for r in score_panel(rows, cfg(), D(2025, 3, 28))}
    assert out["S:020"]["peer_fallback"] is True and out["S:020"]["peer_group"] == "industrial" and out["S:020"]["n_peers"] == 13
    assert out["S:001"]["peer_fallback"] is False


def test_financial_profile_uses_its_own_metrics():
    rows = []
    for i, q in enumerate(range(1, 11)):
        r = company(i, playbook="banks", profile="financial", roe=q, roa=q, cost_to_income=-q, revenue_growth=q, profit_growth=q, pb=-q, pe=-q,
                    gnpa_pct=-q, nnpa_pct=-q, cet1=q, credit_cost=-q, leverage_assets_to_equity=-q, promoter_change_4q=q, momentum_12_1=q, momentum_6=q)
        rows.append(r)
    out = {r["security_id"]: r for r in score_panel(rows, cfg(), D(2025, 3, 28))}
    assert out["S:009"]["score"] > out["S:000"]["score"] and "gnpa_pct" in out["S:009"]["pillars"]["balance"]["metrics"]
    assert out["S:009"]["drivers"] and out["S:009"]["drivers"][0]["points"] > 0


# ---- report card ------------------------------------------------------------------------------------------

def test_rank_ic_and_newey_west():
    a = list(range(100))
    assert BT.rank_ic(a, [x * 2 for x in a]) == pytest.approx(1.0) and BT.rank_ic(a, [-x for x in a]) == pytest.approx(-1.0)
    assert BT.rank_ic(a[:10], a[:10]) is None                                              # too few names to rank
    rng = np.random.default_rng(3)
    ar = [0.1]
    for _ in range(299):
        ar.append(0.05 + 0.8 * (ar[-1] - 0.05) + rng.normal(0, 0.02))
    assert abs(BT.newey_west_t(ar, 4)) < abs(BT.newey_west_t(ar, 0))                       # positive serial correlation lowers the t-statistic


def test_add_months_clamps_to_month_end():
    assert BT.add_months(D(2024, 1, 31), 1) == D(2024, 2, 29) and BT.add_months(D(2024, 11, 30), 3) == D(2025, 2, 28)


def make_book(n=120, signal=True, days=800):
    """Securities whose daily drift is proportional to their score rank (signal) or unrelated to it."""
    b = PriceBook.__new__(PriceBook)
    b.dates, b.open, b.close = {}, {}, {}
    ds = [D(2019, 1, 1) + dt.timedelta(days=i) for i in range(days) if (D(2019, 1, 1) + dt.timedelta(days=i)).weekday() < 5]
    rng = np.random.default_rng(7)
    scores = {}
    for i in range(n):
        sid = f"S:{i:03d}"
        scores[sid] = float(i)
        drift = (i - n / 2) / n * 0.002 if signal else 0.0
        px = 100 * np.cumprod(1 + drift + rng.normal(0, 0.01, len(ds)))
        b.dates[sid], b.open[sid], b.close[sid] = ds, px.tolist(), px.tolist()
    return b, scores, ds


def test_a_real_signal_shows_monotone_deciles_and_positive_ic_and_noise_does_not():
    b, scores, ds = make_book(signal=True)
    sd = {D(2019, 3, 29): scores, D(2019, 6, 28): scores, D(2019, 9, 30): scores, D(2019, 12, 31): scores}
    rep = BT.evaluate(sd, b, [3], ds[-1])
    h = rep["horizons"][3]
    assert h["dates"] >= 2 and h["ic_mean"] > 0.3 and h["d10_minus_d1"] > 0 and h["decile_mean_return"][10] > h["decile_mean_return"][1]
    b2, scores2, ds2 = make_book(signal=False)
    h2 = BT.evaluate({D(2019, 3, 29): scores2, D(2019, 6, 28): scores2}, b2, [3], ds2[-1])["horizons"][3]
    assert abs(h2["ic_mean"]) < 0.2


def test_delisted_names_are_closed_at_their_last_price_and_counted_not_dropped():
    b, scores, ds = make_book(n=80, signal=False, days=500)
    gone = "S:005"
    cut = 150
    b.dates[gone], b.open[gone], b.close[gone] = ds[:cut], b.open[gone][:cut], b.close[gone][:cut]       # stops trading ~Jul-2019
    fr = BT.forward_returns(b, list(scores), D(2019, 3, 29), 6, ds[-1])
    assert gone in fr and fr[gone][1] is True                                                             # exited at the last close, flagged
    assert len(fr) == 80
    far = BT.forward_returns(b, list(scores), D(2021, 6, 30), 12, ds[-1])
    assert far == {}                                                                                      # beyond the data: no return, not a zero


def test_portfolio_charges_costs_on_turnover():
    b, scores, ds = make_book(signal=True)
    sd = {D(2019, 3, 29): scores, D(2019, 6, 28): scores, D(2019, 9, 30): scores, D(2019, 12, 31): scores}
    free = BT.portfolio(sd, b, ds[-1], 0.1, 0.0)
    costly = BT.portfolio(sd, b, ds[-1], 0.1, 0.01)
    assert free["periods"] >= 2 and costly["cagr_net"] < free["cagr_net"]
    assert free["avg_turnover"] < 0.5                                                                     # same scores every time: little trading


def test_frozen_file_is_pinned_by_hash():
    frozen = KC.frozen()
    if frozen is not None:
        assert KC.load(frozen["version"]).sha256 == frozen["sha256"], "a frozen score file must never change: write kasauti_v2.yaml"


def test_stored_scores_are_served_point_in_time_and_labelled(con, monkeypatch, tmp_path):
    from fastapi.testclient import TestClient

    import trikal_api.app as appmod
    from conftest import seed_company
    from trikal_core.db import insert_many
    from trikal_core.pit import PitReader
    from trikal_core.timeutil import utcnow

    sid = seed_company(con, sid="S:INE000K01", code="KASCO")
    detail = json.dumps({"profile": "industrial", "peer_fallback": False, "dropped": {"credibility": "not in v1: needs the Promise Tracker"},
                         "skipped": {}, "drivers": [], "pillars": {"quality": {"score": 0.8, "coverage": 1.0, "metrics": {}}}}, default=str)
    for day, score in ((D(2024, 6, 28), 55.0), (D(2024, 9, 30), 61.0)):
        insert_many(con, "INSERT INTO kasauti_score VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                    [(1, day, sid, score, 0.9, "ok", "it_services", "it_services", 12, detail, utcnow())])      # written now: a reconstruction
    monkeypatch.setattr(appmod, "open_reader", lambda read_only=True: PitReader(con))
    monkeypatch.setattr(appmod.DB, "reader", None)
    monkeypatch.setenv("TRIKAL_DATA", str(tmp_path))
    c = TestClient(appmod.app)
    j = c.get("/api/company/KASCO/kasauti?as_of=2024-08-15").json()
    assert j["available"] and j["score"] == 55.0 and j["scoring_date"] == "2024-06-28"                      # the September score does not exist yet
    assert j["kind"] == "in-sample reconstruction" and j["detail"]["dropped"]["credibility"].startswith("not in v1")
    assert c.get("/api/company/KASCO/kasauti?as_of=2024-03-01").json()["available"] is False
    assert c.get("/api/company/KASCO/kasauti").status_code == 422
    r = c.get("/api/kasauti/report?as_of=2024-08-15").json()
    assert r["available"] is False and "NOW only" in r["reason"]                                            # no hindsight in a rewound view
    assert c.get("/api/kasauti/report?as_of=NOW").json()["available"] is False                              # no report generated yet
