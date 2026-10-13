"""Live quotes from the owner's OWN Angel One SmartAPI account — read-only market data.

Safety rules (enforced in code, tested):
  * only two endpoints can ever be called: login and market quotes. Any other path raises before a request is made,
    so nothing in this module can place, modify or cancel an order or read the account.
  * credentials come from the environment or the gitignored `.env`; they are never logged or returned.
  * a failed login is not retried for 10 minutes (repeated wrong PIN/TOTP attempts can lock a broker account).
  * quotes are cached for a few seconds and requests are spaced >= 1.1 s (the API allows about one call per second).

Not configured → every call returns a clear "not available: set X in .env", never a guessed price.
"""

from __future__ import annotations

import base64
import datetime as dt
import hashlib
import hmac
import json
import os
import struct
import threading
import time
from pathlib import Path

import httpx

BASE = "https://apiconnect.angelone.in"
LOGIN = "/rest/auth/angelbroking/user/v1/loginByPassword"
QUOTE = "/rest/secure/angelbroking/market/v1/quote/"
ALLOWED = frozenset({LOGIN, QUOTE})
SCRIP_MASTER = "https://margincalculator.angelbroking.com/OpenAPI_File/files/OpenAPIScripMaster.json"
ROOT = Path(__file__).resolve().parents[2]
IST = dt.timezone(dt.timedelta(hours=5, minutes=30))
NEEDED = {"BROKER_API_KEY": "your SmartAPI api key", "ANGEL_CLIENT_CODE": "your Angel One client code (e.g. A123456)",
          "ANGEL_PIN": "your 4-digit trading MPIN", "ANGEL_TOTP_SECRET": "the TOTP secret shown when you enable TOTP on SmartAPI"}


class LiveError(Exception):
    """A problem the UI can show as-is (no secrets inside)."""


def _env(name: str) -> str:
    v = os.environ.get(name)
    if v:
        return v.strip()
    p = ROOT / ".env"
    if p.exists():
        for line in p.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, _, val = line.partition("=")
                if k.strip() == name:
                    return val.strip().strip("\"'")
    return ""


def totp(secret: str, at: float | None = None, digits: int = 6, step: int = 30) -> str:
    """RFC 6238 (HMAC-SHA1) time-based one-time password."""
    s = secret.replace(" ", "").upper()
    key = base64.b32decode(s + "=" * (-len(s) % 8))
    counter = int((time.time() if at is None else at) // step)
    h = hmac.new(key, struct.pack(">Q", counter), hashlib.sha1).digest()
    o = h[-1] & 0x0F
    code = (struct.unpack(">I", h[o:o + 4])[0] & 0x7FFFFFFF) % (10 ** digits)
    return str(code).zfill(digits)


def market_open(now: dt.datetime | None = None) -> bool:
    """Mon-Fri 09:15-15:30 IST. Exchange holidays are not known here; the quote's own timestamp is what the UI shows."""
    n = (now or dt.datetime.now(IST)).astimezone(IST)
    return n.weekday() < 5 and dt.time(9, 15) <= n.time() <= dt.time(15, 30)


class AngelQuotes:
    def __init__(self, client: httpx.Client | None = None, cache_dir: Path | None = None, clock=time.time) -> None:
        self.client = client or httpx.Client(timeout=20, headers={"User-Agent": "TRIKAL-research/0.3"})
        self.cache_dir = cache_dir or ROOT / "data" / "cache"
        self.clock = clock
        self.lock = threading.Lock()
        self.jwt: str | None = None
        self.jwt_until = 0.0
        self.login_blocked_until = 0.0
        self.last_login_error = ""
        self.last_call = 0.0
        self.tokens: dict[str, str] | None = None
        self.cache: dict[str, tuple[float, dict]] = {}

    # ---- configuration --------------------------------------------------------------------------------------
    def missing(self) -> list[str]:
        return [k for k in NEEDED if not _env(k)]

    def configured(self) -> bool:
        return not self.missing()

    # ---- the only network path -----------------------------------------------------------------------------
    def _post(self, path: str, body: dict, auth: bool = False) -> dict:
        if path not in ALLOWED:
            raise LiveError(f"endpoint not allowed: {path}")        # nothing else can ever be called
        wait = 1.1 - (self.clock() - self.last_call)
        if wait > 0:
            time.sleep(wait)
        self.last_call = self.clock()
        headers = {"Content-Type": "application/json", "Accept": "application/json", "X-UserType": "USER", "X-SourceID": "WEB",
                   "X-ClientLocalIP": "127.0.0.1", "X-ClientPublicIP": "127.0.0.1", "X-MACAddress": "00:00:00:00:00:00",
                   "X-PrivateKey": _env("BROKER_API_KEY")}
        if auth:
            headers["Authorization"] = f"Bearer {self.jwt}"
        try:
            r = self.client.post(BASE + path, content=json.dumps(body), headers=headers)
        except httpx.HTTPError as e:
            raise LiveError(f"Angel One unreachable ({type(e).__name__})") from None
        try:
            j = r.json()
        except ValueError:
            raise LiveError(f"Angel One returned HTTP {r.status_code} without JSON") from None
        return j

    # ---- session ----------------------------------------------------------------------------------------------
    def _login(self) -> None:
        if self.clock() < self.login_blocked_until:
            raise LiveError(f"login paused after an error (retry in {int(self.login_blocked_until - self.clock())} s): {self.last_login_error}")
        try:
            j = self._post(LOGIN, {"clientcode": _env("ANGEL_CLIENT_CODE"), "password": _env("ANGEL_PIN"),
                                   "totp": totp(_env("ANGEL_TOTP_SECRET"), self.clock())})
        except (LiveError, ValueError) as e:
            self.login_blocked_until = self.clock() + 600
            self.last_login_error = str(e)
            raise
        data = j.get("data") or {}
        if not j.get("status") or not data.get("jwtToken"):
            self.login_blocked_until = self.clock() + 600
            self.last_login_error = f"login refused: {j.get('message') or j.get('errorcode') or 'unknown'}"
            raise LiveError(self.last_login_error)
        self.jwt, self.jwt_until = data["jwtToken"], self.clock() + 6 * 3600
        self.login_blocked_until = 0.0

    def _session(self) -> None:
        if not self.jwt or self.clock() >= self.jwt_until:
            self._login()

    # ---- instrument tokens ------------------------------------------------------------------------------------
    def _token_map(self) -> dict[str, str]:
        if self.tokens is not None:
            return self.tokens
        f = self.cache_dir / "angel_scrip_master.json"
        if not f.exists() or self.clock() - f.stat().st_mtime > 7 * 86400:
            try:
                r = self.client.get(SCRIP_MASTER, timeout=120)
                if r.status_code == 200:
                    self.cache_dir.mkdir(parents=True, exist_ok=True)
                    f.write_bytes(r.content)
            except httpx.HTTPError:
                if not f.exists():
                    raise LiveError("could not download Angel One's instrument list") from None
        rows = json.loads(f.read_text(encoding="utf-8"))
        self.tokens = {x["name"]: x["token"] for x in rows if x.get("exch_seg") == "NSE" and str(x.get("symbol", "")).endswith("-EQ")}
        return self.tokens

    # ---- quotes ---------------------------------------------------------------------------------------------------
    def quotes(self, codes: list[str]) -> dict[str, dict]:
        """NSE equity quotes keyed by code. Codes without a quote are simply absent."""
        miss = self.missing()
        if miss:
            raise LiveError("not configured: set " + ", ".join(miss) + " in .env")
        now = self.clock()
        out: dict[str, dict] = {}
        with self.lock:
            tmap = self._token_map()
            todo = []
            for c in dict.fromkeys(x.upper() for x in codes):
                hit = self.cache.get(c)
                if hit and now - hit[0] < 4:
                    out[c] = hit[1]
                elif c in tmap:
                    todo.append(c)
            for i in range(0, len(todo), 50):
                batch = todo[i:i + 50]
                self._session()
                j = self._post(QUOTE, {"mode": "FULL", "exchangeTokens": {"NSE": [tmap[c] for c in batch]}}, auth=True)
                if not j.get("status") and str(j.get("errorcode", "")).upper() in ("AG8001", "AG8002", "AB8050", "AB8051"):
                    self.jwt = None                                   # token rejected: log in once more next time
                    raise LiveError("session expired; will log in again on the next request")
                if not j.get("status"):
                    raise LiveError(f"quote refused: {j.get('message') or j.get('errorcode') or 'unknown'}")
                by_token = {v: k for k, v in tmap.items() if k in batch}
                for q in (j.get("data") or {}).get("fetched") or []:
                    code = by_token.get(str(q.get("symbolToken")))
                    if code:
                        shaped = _shape(code, q)
                        self.cache[code] = (self.clock(), shaped)
                        out[code] = shaped
        return out


def _f(x) -> float | None:
    try:
        return float(x)
    except (TypeError, ValueError):
        return None


def _shape(code: str, q: dict) -> dict:
    ltp, prev = _f(q.get("ltp")), _f(q.get("close"))
    return {"code": code, "ltp": ltp, "open": _f(q.get("open")), "high": _f(q.get("high")), "low": _f(q.get("low")),
            "prev_close": prev, "change": (ltp - prev) if ltp is not None and prev else None,
            "change_pct": (ltp / prev - 1) if ltp is not None and prev else None,
            "volume": _f(q.get("tradeVolume")), "exchange_time": q.get("exchFeedTime") or q.get("exchTradeTime"),
            "week52_high": _f(q.get("52WeekHighPrice")), "week52_low": _f(q.get("52WeekLowPrice"))}


ANGEL = AngelQuotes()
