"""Live quotes (Angel One adapter). A fake broker answers; no credentials, no network."""

from __future__ import annotations

import json

import httpx
import pytest

from trikal_api import live
from trikal_api.live import ALLOWED, LOGIN, QUOTE, AngelQuotes, LiveError, totp


@pytest.fixture
def env(monkeypatch):
    for k, v in {"BROKER_API_KEY": "KEY12345", "ANGEL_CLIENT_CODE": "A1", "ANGEL_PIN": "1234",
                 "ANGEL_TOTP_SECRET": "GEZDGNBVGY3TQOJQGEZDGNBVGY3TQOJQ"}.items():
        monkeypatch.setenv(k, v)


class Broker:
    """A fake SmartAPI: records every request, answers login and quotes."""

    def __init__(self, login_ok=True):
        self.calls, self.login_ok = [], login_ok

    def __call__(self, req: httpx.Request) -> httpx.Response:
        self.calls.append((req.url.path, json.loads(req.content or b"{}"), dict(req.headers)))
        if req.url.path == LOGIN:
            if not self.login_ok:
                return httpx.Response(200, json={"status": False, "message": "Invalid totp", "errorcode": "AB1050"})
            return httpx.Response(200, json={"status": True, "data": {"jwtToken": "JWT-SECRET"}})
        if req.url.path == QUOTE:
            return httpx.Response(200, json={"status": True, "data": {"fetched": [
                {"symbolToken": "11536", "ltp": "2130.5", "close": "2125.0", "open": "2120", "high": "2140", "low": "2110",
                 "tradeVolume": 123456, "exchFeedTime": "13-Oct-2026 15:29:58", "52WeekHigh": 3000, "52WeekLow": 1900}]}})
        return httpx.Response(404)


def adapter(tmp_path, broker, t=[1_000_000.0]):
    (tmp_path / "angel_scrip_master.json").write_text(json.dumps(
        [{"token": "11536", "symbol": "TCS-EQ", "name": "TCS", "exch_seg": "NSE"},
         {"token": "99", "symbol": "TCS24OCTFUT", "name": "TCS", "exch_seg": "NFO"}]), encoding="utf-8")
    def clock():
        t[0] += 2.0        # every call looks 2 s later: rate spacing never sleeps in tests
        return t[0]
    a = AngelQuotes(client=httpx.Client(transport=httpx.MockTransport(broker)), cache_dir=tmp_path, clock=clock)
    (tmp_path / "angel_scrip_master.json").touch()
    import os
    os.utime(tmp_path / "angel_scrip_master.json", (t[0], t[0]))
    return a


def test_totp_matches_the_rfc6238_vector():
    secret = "GEZDGNBVGY3TQOJQGEZDGNBVGY3TQOJQ"          # ASCII "12345678901234567890"
    assert totp(secret, at=59, digits=8) == "94287082"
    assert totp(secret, at=1111111109, digits=8) == "07081804"


def test_a_quote_is_shaped_and_only_two_endpoints_are_ever_used(env, tmp_path):
    b = Broker()
    q = adapter(tmp_path, b).quotes(["tcs"])["TCS"]
    assert (q["week52_high"], q["week52_low"]) == (3000.0, 1900.0)  # real field names, seen on the live API
    assert q["ltp"] == 2130.5 and q["prev_close"] == 2125.0 and round(q["change_pct"], 5) == round(2130.5 / 2125 - 1, 5)
    assert {c[0] for c in b.calls} == {LOGIN, QUOTE}
    assert b.calls[1][1] == {"mode": "FULL", "exchangeTokens": {"NSE": ["11536"]}}      # the NSE equity, not the NFO future
    assert b.calls[1][2]["authorization"] == "Bearer JWT-SECRET"


def test_no_other_endpoint_can_be_called(env, tmp_path):
    a = adapter(tmp_path, Broker())
    for path in ("/rest/secure/angelbroking/order/v1/placeOrder", "/rest/secure/angelbroking/user/v1/getProfile"):
        assert path not in ALLOWED
        with pytest.raises(LiveError, match="not allowed"):
            a._post(path, {})


def test_not_configured_says_what_is_missing_and_calls_nothing(monkeypatch, tmp_path):
    for k in ("BROKER_API_KEY", "ANGEL_CLIENT_CODE", "ANGEL_PIN", "ANGEL_TOTP_SECRET"):
        monkeypatch.setenv(k, "")
    monkeypatch.setattr(live, "ROOT", tmp_path)            # no .env here either
    b = Broker()
    a = adapter(tmp_path, b)
    with pytest.raises(LiveError, match="not configured: set BROKER_API_KEY, ANGEL_CLIENT_CODE"):
        a.quotes(["TCS"])
    assert b.calls == []


def test_failed_login_is_not_retried_for_ten_minutes(env, tmp_path):
    b = Broker(login_ok=False)
    a = adapter(tmp_path, b)
    with pytest.raises(LiveError, match="login refused"):
        a.quotes(["TCS"])
    n = len(b.calls)
    with pytest.raises(LiveError, match="login paused"):
        a.quotes(["TCS"])
    assert len(b.calls) == n                                # no second attempt: repeated bad logins can lock the account


def test_secrets_never_appear_in_errors(env, tmp_path):
    b = Broker(login_ok=False)
    a = adapter(tmp_path, b)
    with pytest.raises(LiveError) as e:
        a.quotes(["TCS"])
    assert all(s not in str(e.value) for s in ("1234", "KEY12345", "GEZDGN", "JWT-SECRET"))


def test_endpoint_refuses_a_rewound_as_of():
    from fastapi.testclient import TestClient

    from trikal_api.app import app

    r = TestClient(app).get("/api/live/TCS?as_of=2020-03-23")
    assert r.status_code == 422 and "only for NOW" in r.json()["detail"]
