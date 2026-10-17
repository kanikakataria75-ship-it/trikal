"""The return calculator: splits and bonuses change shares, not value; dividends are ignored, kept as cash or reinvested."""

from __future__ import annotations

import datetime as dt

import pytest

from trikal_analytics import returns as RT

D = dt.date


def bars(prices, factors=None, start=D(2020, 1, 1)):
    out = []
    for i, p in enumerate(prices):
        f = (factors or [1.0] * len(prices))[i]
        out.append(RT.Bar(start + dt.timedelta(days=i), p * f, f))        # p = traded price, adjusted = traded x factor
    return out


def test_plain_holding_return_and_cagr():
    b = bars([100.0] * 365 + [200.0])
    r = RT.simulate(b, [], D(2020, 1, 1), D(2020, 1, 1) + dt.timedelta(days=365), 10000, "ignore")
    assert r["total_value"] == pytest.approx(20000) and r["return"] == pytest.approx(1.0) and r["shares_bought"] == pytest.approx(100)
    assert r["cagr"] == pytest.approx(1.0, abs=0.01) and r["buy_price_traded"] == 100 and r["end_price_traded"] == 200


def test_a_split_changes_the_share_count_not_the_value():
    # 1:5 split on day 10: the traded price falls 5x, so the earlier factor is 0.2 of the later one
    prices = [1000.0] * 10 + [200.0] * 10
    factors = [0.2] * 10 + [1.0] * 10
    r = RT.simulate(bars(prices, factors), [], D(2020, 1, 1), D(2020, 1, 20), 50000, "ignore")
    assert r["shares_bought"] == pytest.approx(50) and r["shares_at_end"] == pytest.approx(250)
    assert r["total_value"] == pytest.approx(50000) and r["return"] == pytest.approx(0.0)
    assert len(r["events"]) == 1 and r["events"][0]["share_multiplier"] == pytest.approx(5.0)


def test_dividend_modes():
    b = bars([100.0] * 10 + [100.0] * 10)
    div = [{"ex_date": D(2020, 1, 11), "amount": 5.0, "subject": "Dividend - Rs 5 Per Share"}]
    s, e = D(2020, 1, 1), D(2020, 1, 20)
    ignore = RT.simulate(b, div, s, e, 10000, "ignore")
    cash = RT.simulate(b, div, s, e, 10000, "cash")
    reinv = RT.simulate(b, div, s, e, 10000, "reinvest")
    assert ignore["total_value"] == pytest.approx(10000) and ignore["dividends_ignored"] == 1
    assert cash["dividends_total"] == pytest.approx(500) and cash["total_value"] == pytest.approx(10500)       # 100 shares x Rs 5
    assert reinv["total_value"] == pytest.approx(10500) and reinv["shares_at_end"] == pytest.approx(105)        # 5 more shares at Rs 100


def test_dividend_on_the_buy_day_or_after_the_end_is_not_received():
    b = bars([100.0] * 20)
    div = [{"ex_date": D(2020, 1, 1), "amount": 5.0}, {"ex_date": D(2020, 1, 25), "amount": 5.0}]
    r = RT.simulate(b, div, D(2020, 1, 1), D(2020, 1, 20), 10000, "cash")
    assert r["dividends_total"] == 0


def test_dividend_after_a_split_is_paid_on_the_new_share_count():
    prices = [1000.0] * 5 + [200.0] * 15
    factors = [0.2] * 5 + [1.0] * 15
    div = [{"ex_date": D(2020, 1, 11), "amount": 2.0}]
    r = RT.simulate(bars(prices, factors), div, D(2020, 1, 1), D(2020, 1, 20), 50000, "cash")
    assert r["dividends_total"] == pytest.approx(500)           # 250 shares after the split x Rs 2


def test_errors_are_clear():
    b = bars([100.0] * 10)
    with pytest.raises(RT.ReturnError, match="before the end"):
        RT.simulate(b, [], D(2020, 1, 9), D(2020, 1, 2), 1000)
    with pytest.raises(RT.ReturnError, match="not trading"):
        RT.simulate(b, [], D(2019, 1, 1), D(2020, 1, 9), 1000)           # starts a year before the first price
    with pytest.raises(RT.ReturnError, match="positive"):
        RT.simulate(b, [], D(2020, 1, 1), D(2020, 1, 9), 0)
    with pytest.raises(RT.ReturnError, match="dividends must"):
        RT.simulate(b, [], D(2020, 1, 1), D(2020, 1, 9), 100, "bogus")
