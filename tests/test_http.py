"""HTTP client and robots.txt (every request is faked)."""

import urllib.error

import pytest

from scripts.lottodata.errors import AccessDenied, RateLimited, RobotsDisallowed, SourceUnavailable
from scripts.lottodata.http import CollectorConfig, HttpClient, HttpResponse


class FakeTransport:
    def __init__(self, routes):
        self.routes = routes
        self.calls = []

    def __call__(self, method, url, headers, body, timeout):
        self.calls.append((method, url, headers.get("User-Agent")))
        handler = self.routes.get(url)
        if handler is None:
            return HttpResponse(404, b"")
        if isinstance(handler, Exception):
            raise handler
        return handler() if callable(handler) else handler


def client(routes, sleeps=None):
    transport = FakeTransport(routes)
    c = HttpClient(CollectorConfig(retry_count=2, retry_backoff=1.0, rate_limit_delay=1.5), transport=transport,
                   sleep=(sleeps.append if sleeps is not None else lambda s: None))
    return c, transport


ROBOTS = "https://example.test/robots.txt"
PAGE = "https://example.test/results"


def test_robots_rules_are_honoured_for_the_collector_token():
    c, _ = client({ROBOTS: HttpResponse(200, b"User-agent: LottoStat-DataCollector\nDisallow: /results\n"),
                   PAGE: HttpResponse(200, b"ok")})
    with pytest.raises(RobotsDisallowed):
        c.request("GET", PAGE)
    c, _ = client({ROBOTS: HttpResponse(200, b"User-agent: *\nDisallow: /private\n"), PAGE: HttpResponse(200, b"ok")})
    assert c.request("GET", PAGE).body == b"ok"


def test_robots_missing_allows_and_robots_failing_blocks():
    c, transport = client({PAGE: HttpResponse(200, b"ok")})  # robots.txt 404
    assert c.request("GET", PAGE).body == b"ok"
    c.request("GET", PAGE)
    assert [u for _, u, _ in transport.calls].count(ROBOTS) == 1, "robots.txt is read once per host"
    c, _ = client({ROBOTS: HttpResponse(503, b""), PAGE: HttpResponse(200, b"ok")})
    with pytest.raises(RobotsDisallowed):
        c.request("GET", PAGE)
    c, _ = client({ROBOTS: urllib.error.URLError("tunnel refused"), PAGE: HttpResponse(200, b"ok")})
    with pytest.raises(SourceUnavailable):
        c.request("GET", PAGE)


def test_refusals_are_reported_never_retried_around():
    c, transport = client({PAGE: HttpResponse(403, b"denied")})
    with pytest.raises(AccessDenied):
        c.request("GET", PAGE)
    assert [u for _, u, _ in transport.calls].count(PAGE) == 1
    assert all(ua.startswith("LottoStat-DataCollector/") for _, _, ua in transport.calls)


def test_retries_with_backoff_and_rate_limit():
    sleeps = []
    c, transport = client({PAGE: HttpResponse(429, b"", {"retry-after": "3"})}, sleeps)
    with pytest.raises(RateLimited):
        c.request("GET", PAGE)
    assert [u for _, u, _ in transport.calls].count(PAGE) == 3
    assert 3.0 in sleeps
    responses = iter([HttpResponse(502, b""), HttpResponse(200, b"ok")])
    c, _ = client({PAGE: lambda: next(responses)}, sleeps)
    assert c.request("GET", PAGE).body == b"ok"


def test_rate_limit_delay_has_a_floor():
    assert CollectorConfig.from_env({"LOTTO_RATE_LIMIT_DELAY": "0.1"}).rate_limit_delay == 1.0
