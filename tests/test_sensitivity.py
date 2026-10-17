"""Sector sensitivities: the estimator recovers a known beta, never reads later data, and the shock grammar is strict."""

from __future__ import annotations

import datetime as dt

import numpy as np
import pytest

from conftest import D
from trikal_analytics import sensitivity as S
from trikal_core.db import insert_many
from trikal_core.pit import PitReader
from trikal_core.timeutil import IST, AsOf, at_ist


def months(n: int, start=(2012, 1)):
    y, m = start
    out = []
    for _ in range(n):
        out.append((y, m))
        y, m = (y + 1, 1) if m == 12 else (y, m + 1)
    return out


def test_monthly_changes_never_bridge_a_gap():
    lv = {(2020, 1): (100.0, None), (2020, 2): (110.0, None), (2020, 4): (121.0, None)}   # March is missing
    ch = S.monthly_changes(lv, "log")
    assert set(ch) == {(2020, 2)} and ch[(2020, 2)][0] == pytest.approx(np.log(1.1))
    assert S.monthly_changes({(2020, 1): (5.0, None), (2020, 2): (5.75, None)}, "pp")[(2020, 2)][0] == pytest.approx(0.75)


def test_ols_recovers_known_coefficients():
    rng = np.random.default_rng(7)
    d, mk = rng.normal(0, 0.05, 120), rng.normal(0, 0.04, 120)
    y = 0.002 + 0.6 * d + 0.9 * mk + rng.normal(0, 0.005, 120)
    f = S.ols(y, np.column_stack([np.ones(120), d, mk]))
    assert f["beta"][1] == pytest.approx(0.6, abs=0.05) and f["beta"][2] == pytest.approx(0.9, abs=0.05)
    assert f["beta"][1] / f["se"][1] > 10 and f["r2"] > 0.9


def _series(n=84, true_beta=0.5, seed=3):
    rng = np.random.default_rng(seed)
    ms = months(n)
    d = {m: (float(x), dt.datetime(*S.month_end(*m).timetuple()[:3], 18, tzinfo=IST)) for m, x in zip(ms, rng.normal(0, 0.06, n))}
    mk = {m: float(x) for m, x in zip(ms, rng.normal(0.01, 0.04, n))}
    sec = {m: 0.001 + true_beta * d[m][0] + 1.0 * mk[m] + float(rng.normal(0, 0.004)) for m in ms}
    return ms, sec, mk, d


def test_estimate_recovers_beta_and_labels_confidence():
    ms, sec, mk, d = _series()
    e = S.estimate(sec, mk, d, ms[-1])
    assert e["beta"] == pytest.approx(0.5, abs=0.05) and e["n"] == S.WINDOW and e["beta_mkt"] == pytest.approx(1.0, abs=0.1)
    assert S.confidence(e["n"], e["tstat"], 0.0) == "high"
    assert S.confidence(e["n"], e["tstat"], 0.9) == "medium"            # mostly back-projected sector labels cap the label
    assert S.confidence(30, 5.0, 0.0) == "low"                          # too few observations


def test_estimate_uses_only_months_up_to_its_end():
    ms, sec, mk, d = _series()
    early = S.estimate(sec, mk, d, ms[59])
    poisoned = dict(sec)
    for m in ms[60:]:
        poisoned[m] = 50.0                                              # absurd later data must not matter
    assert S.estimate(poisoned, mk, d, ms[59])["beta"] == pytest.approx(early["beta"])
    assert S.estimate(sec, mk, d, ms[10]) is None                       # fewer than 36 months of history: no estimate


def test_shock_grammar():
    cur = {"usdinr": 83.0, "ind10y": 7.0}
    s = S.parse_shocks("CRUDE +20 & INR 90 & REPO +50bp & GSEC 7.5", cur)
    assert [(x.driver, round(x.delta, 4)) for x in s] == [("brent", 0.1823), ("usdinr", 0.0810), ("callrate", 0.5), ("ind10y", 0.5)]
    assert S.apply(0.4, s[0]) == pytest.approx(0.4 * np.log(1.2))
    for bad in ("FOO +1", "CRUDE", "INR +10bp", "CRUDE -100", ""):
        with pytest.raises(S.ShockError):
            S.parse_shocks(bad, cur)
    with pytest.raises(S.ShockError, match="current level unknown"):
        S.parse_shocks("INR 90", {})                                    # a target level needs the current value: never guessed


def make_universe(con, mkt_drift=0.01):
    """Two sectors of six stocks over 84 months (2012-2018); Alpha truly moves 0.5 x the Brent driver, Beta not at all."""
    rng = np.random.default_rng(11)
    ms = months(84)
    drv = rng.normal(0, 0.06, 84)
    mkt = rng.normal(0.01, 0.03, 84)
    level, k, kn = 100.0, [], []
    for i, m in enumerate(ms):
        level *= np.exp(drv[i])
        k.append((S.month_end(*m), float(level)))
    ka = lambda e: at_ist(e + dt.timedelta(days=2), dt.time(18, 0))      # noqa: E731
    insert_many(con, "INSERT INTO macro_obs VALUES (?,?,?,?,?,?,?,?,?)",
                [("brent", e, e, v, ka(e), "imputed", None, "s", ka(e)) for e, v in k])
    ids = []
    for sec, beta in (("Alpha", 0.5), ("Beta", 0.0)):
        for j in range(6):
            sid = f"S:{sec[0]}{j}"
            ids.append(sid)
            insert_many(con, "INSERT INTO security VALUES (?,?,?,?,?,?,?,?)", [(sid, sid[2:], sid[2:], sid, D(2000, 1, 1), D(2030, 1, 1), "isin", 1.0)])
            insert_many(con, "INSERT INTO listing VALUES (?,?,?,?,?,?,?)", [(sid, "NSE", sid[2:], D(2000, 1, 1), D(2030, 1, 1), "isin", 1.0)])
            insert_many(con, "INSERT INTO classification VALUES (?,?,?,?,?,?,?,?,?)",
                        [(sid, "NSE_INDUSTRY", sec, D(1990, 1, 1), D(9999, 12, 31), at_ist(D(1990, 1, 1), dt.time(0)), "official_snapshot", 1.0, "")])
            insert_many(con, "INSERT INTO index_membership VALUES (?,?,?,?,?,?,?,?,?)",
                        [("NIFTY500", sid, sid[2:], D(2000, 1, 1), D(9999, 12, 31), at_ist(D(2000, 1, 1), dt.time(0)), "x", 1.0, "")])
            p = 100.0
            rows = []
            for i, m in enumerate(ms):
                p *= float(np.exp(beta * drv[i] + mkt[i] + rng.normal(0, 0.01)))
                e = S.month_end(*m)
                rows.append(("NSE", e, sid[2:], "EQ", None, None, "STK", p, p, p, p, p, p, 1000.0, p * 1000, 10, at_ist(e, dt.time(16)), "convention", at_ist(e, dt.time(16)), "f"))
            insert_many(con, "INSERT INTO price_eod VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)", rows)
    return ids


def test_build_end_to_end_on_synthetic_universe(con, monkeypatch):
    """Two sectors of six stocks; sector A truly moves 0.5 x the driver. build() must find it and respect usable_from."""
    from trikal_pipeline import sensitivity as B

    monkeypatch.setattr(B, "MIN_MARKET_MEMBERS", 10)          # the synthetic universe has 12 stocks, not 500
    make_universe(con)
    stats = B.build(con)
    assert stats["sectors"] == 2 and "brent" in stats["drivers"]
    r = PitReader(con)
    est = r.sector_sensitivities(AsOf.end_of(D(2019, 6, 30)))
    a = next(x for x in est if x["sector"] == "Alpha" and x["driver"] == "brent")
    b = next(x for x in est if x["sector"] == "Beta" and x["driver"] == "brent")
    m = next(x for x in est if x["sector"] == S.MARKET and x["driver"] == "brent")
    # the equal-weight market contains Alpha's six stocks, so the market itself responds with 0.5 x 6/12 = 0.25;
    # a sector's sensitivity is reported relative to the market, and the shock table adds the market's own response back
    assert m["beta"] == pytest.approx(0.25, abs=0.08)
    assert a["beta"] == pytest.approx(0.25, abs=0.1) and b["beta"] == pytest.approx(-0.25, abs=0.1)
    assert a["beta"] + m["beta"] == pytest.approx(0.5, abs=0.12) and abs(b["beta"] + m["beta"]) < 0.12   # the true betas
    assert a["usable_from"] <= at_ist(D(2019, 6, 30), dt.time(23, 59))
    # point in time: asked early in 2013 there is no estimate yet (needs 36 months), asked later there is one
    assert r.sector_sensitivities(AsOf.end_of(D(2013, 6, 30))) == []
    later = r.sector_sensitivities(AsOf.end_of(D(2016, 6, 30)))
    assert all(x["window_end"] <= D(2016, 6, 30) for x in later) and later
