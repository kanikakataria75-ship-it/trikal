"""Polite HTTP fetcher (ARCHITECTURE §4.2, ADR-006): per-host rate limit, retries, robots-aware."""

from __future__ import annotations

import time
import urllib.robotparser
from dataclasses import dataclass
from urllib.parse import urlsplit

import httpx

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128 Safari/537.36"

# Seconds between requests to the same host. Static archive hosts can take slightly more.
DEFAULT_INTERVAL = 1.0
HOST_INTERVAL = {
    "nsearchives.nseindia.com": 0.7,
    "www.bseindia.com": 1.0,
    "www.nseindia.com": 1.5,
    "www.niftyindices.com": 1.0,
    "niftyindices.com": 1.0,
}


@dataclass
class Response:
    url: str
    status: int
    body: bytes
    content_type: str | None


class Fetcher:
    def __init__(self, timeout: float = 45.0, retries: int = 3) -> None:
        self.client = httpx.Client(
            headers={"User-Agent": UA, "Accept": "*/*", "Accept-Language": "en-US,en;q=0.9"},
            timeout=timeout,
            follow_redirects=True,
            http2=False,
        )
        self.retries = retries
        self._last: dict[str, float] = {}
        self._robots: dict[str, urllib.robotparser.RobotFileParser | None] = {}

    def _wait(self, host: str) -> None:
        gap = HOST_INTERVAL.get(host, DEFAULT_INTERVAL)
        elapsed = time.monotonic() - self._last.get(host, 0.0)
        if elapsed < gap:
            time.sleep(gap - elapsed)
        self._last[host] = time.monotonic()

    def allowed(self, url: str) -> bool:
        parts = urlsplit(url)
        host = parts.netloc
        if host not in self._robots:
            rp = urllib.robotparser.RobotFileParser()
            try:
                r = self.client.get(f"{parts.scheme}://{host}/robots.txt")
                text = r.text if r.status_code == 200 and "text/plain" in r.headers.get("content-type", "") else ""
                rp.parse(text.splitlines())
                self._robots[host] = rp if text else None
            except httpx.HTTPError:
                self._robots[host] = None
        rp = self._robots[host]
        return True if rp is None else rp.can_fetch(UA, url)

    def get(self, url: str, referer: str | None = None) -> Response:
        if not self.allowed(url):
            raise PermissionError(f"robots.txt disallows {url}")
        host = urlsplit(url).netloc
        headers = {"Referer": referer} if referer else {}
        last_exc: Exception | None = None
        for attempt in range(self.retries + 1):
            self._wait(host)
            try:
                r = self.client.get(url, headers=headers)
                if r.status_code in (429, 500, 502, 503, 504):
                    raise httpx.HTTPStatusError("retryable", request=r.request, response=r)
                return Response(str(r.url), r.status_code, r.content, r.headers.get("content-type"))
            except (httpx.HTTPError,) as exc:  # network errors and retryable statuses
                last_exc = exc
                time.sleep(min(60, 2 ** (attempt + 1)))
        assert last_exc is not None
        raise last_exc

    def close(self) -> None:
        self.client.close()
