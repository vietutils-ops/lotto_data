"""Small, dependency-free HTTP client with robots.txt, retries, backoff and
rate limiting.

Deliberately NOT included: browser impersonation, rotating user agents or
proxies, CAPTCHA solving, cookie harvesting or any other technique for getting
around access controls. A refusal from the source, or a robots.txt rule, is
reported, never evaded.
"""

from __future__ import annotations

import os
import time
import urllib.error
import urllib.parse
import urllib.request
import urllib.robotparser
from dataclasses import dataclass, field
from typing import Callable, Dict, Mapping, Optional

from .errors import AccessDenied, RateLimited, RobotsDisallowed, SourceUnavailable

#: Product token matched against robots.txt groups.
ROBOTS_TOKEN = "LottoStat-DataCollector"
DEFAULT_USER_AGENT = (
    f"{ROBOTS_TOKEN}/2.0 (+https://github.com/vietutils-ops/lotto_data; "
    "historical statistics dataset maintenance)"
)
RETRYABLE_STATUS = {429, 500, 502, 503, 504}
ACCESS_DENIED_STATUS = {401, 403, 451}
MAX_RETRY_AFTER_SECONDS = 120.0




@dataclass(frozen=True)
class CollectorConfig:
    timeout: float = 20.0
    retry_count: int = 3
    retry_backoff: float = 2.0
    user_agent: str = DEFAULT_USER_AGENT
    rate_limit_delay: float = 1.5
    proxy: Optional[str] = None

    @staticmethod
    def from_env(env: Optional[Mapping[str, str]] = None, **overrides) -> "CollectorConfig":
        env = os.environ if env is None else env

        def _float(name: str, default: float) -> float:
            raw = env.get(name)
            if raw in (None, ""):
                return default
            try:
                value = float(raw)
            except ValueError as exc:
                raise ValueError(f"{name} must be a number, got {raw!r}") from exc
            if value < 0:
                raise ValueError(f"{name} must be >= 0")
            return value

        config = CollectorConfig(
            timeout=_float("LOTTO_HTTP_TIMEOUT", 20.0),
            retry_count=int(_float("LOTTO_RETRY_COUNT", 3)),
            retry_backoff=_float("LOTTO_RETRY_BACKOFF", 2.0),
            user_agent=env.get("LOTTO_USER_AGENT") or DEFAULT_USER_AGENT,
            rate_limit_delay=max(_float("LOTTO_RATE_LIMIT_DELAY", 1.5), 1.0),
            proxy=env.get("LOTTO_PROXY") or None,
        )
        clean = {k: v for k, v in overrides.items() if v is not None}
        return CollectorConfig(**{**config.__dict__, **clean})


@dataclass
class HttpResponse:
    status: int
    body: bytes
    headers: Dict[str, str] = field(default_factory=dict)


Transport = Callable[[str, str, Dict[str, str], Optional[bytes], float], HttpResponse]


def urllib_transport(proxy: Optional[str]) -> Transport:
    handlers = []
    if proxy:
        handlers.append(urllib.request.ProxyHandler({"http": proxy, "https": proxy}))
    opener = urllib.request.build_opener(*handlers)

    def send(method: str, url: str, headers: Dict[str, str], body: Optional[bytes],
             timeout: float) -> HttpResponse:
        request = urllib.request.Request(url, data=body, headers=headers, method=method)
        try:
            with opener.open(request, timeout=timeout) as response:
                return HttpResponse(response.status, response.read(),
                                    {k.lower(): v for k, v in response.headers.items()})
        except urllib.error.HTTPError as exc:
            payload = exc.read() if hasattr(exc, "read") else b""
            return HttpResponse(exc.code, payload,
                                {k.lower(): v for k, v in (exc.headers or {}).items()})

    return send


class HttpClient:
    def __init__(self, config: CollectorConfig, transport: Optional[Transport] = None,
                 sleep: Callable[[float], None] = time.sleep,
                 log: Callable[[str], None] = lambda message: None):
        self.config = config
        self.transport = transport or urllib_transport(config.proxy)
        self.sleep = sleep
        self.log = log
        self._last_request: Optional[float] = None
        self._clock = time.monotonic
        self.robots = RobotsGate(self)

    def _respect_rate_limit(self) -> None:
        if self._last_request is None:
            return
        elapsed = self._clock() - self._last_request
        wait = self.config.rate_limit_delay - elapsed
        if wait > 0:
            self.sleep(wait)

    def request(self, method: str, url: str, *, headers: Optional[Dict[str, str]] = None,
                body: Optional[bytes] = None, check_robots: bool = True) -> HttpResponse:
        if check_robots:
            self.robots.require_allowed(url)
        merged = {"User-Agent": self.config.user_agent, "Accept": "*/*"}
        merged.update(headers or {})
        attempts = self.config.retry_count + 1
        last_error = "no attempt made"
        for attempt in range(1, attempts + 1):
            self._respect_rate_limit()
            self._last_request = self._clock()
            try:
                response = self.transport(method, url, merged, body, self.config.timeout)
            except (urllib.error.URLError, TimeoutError, ConnectionError, OSError) as exc:
                last_error = f"network error: {exc}"
                self.log(f"attempt {attempt}/{attempts} {method} {url}: {last_error}")
            else:
                if response.status in ACCESS_DENIED_STATUS:
                    raise AccessDenied(
                        f"{method} {url} returned HTTP {response.status}. The source refused access "
                        "(it may be geo-restricted). The collector does not bypass access controls; "
                        "run it from a network where the public site is normally reachable.")
                if response.status in RETRYABLE_STATUS:
                    last_error = f"HTTP {response.status}"
                    self.log(f"attempt {attempt}/{attempts} {method} {url}: {last_error}")
                    if attempt < attempts and response.status == 429:
                        retry_after = response.headers.get("retry-after", "")
                        if retry_after.isdigit():
                            self.sleep(min(float(retry_after), MAX_RETRY_AFTER_SECONDS))
                            continue
                elif 200 <= response.status < 300:
                    return response
                else:
                    raise SourceUnavailable(f"{method} {url} returned HTTP {response.status}")
            if attempt < attempts:
                self.sleep(self.config.retry_backoff * (2 ** (attempt - 1)))
        if last_error == "HTTP 429":
            raise RateLimited(f"{method} {url} kept answering HTTP 429 after {attempts} attempt(s)")
        raise SourceUnavailable(f"{method} {url} failed after {attempts} attempt(s): {last_error}")


class RobotsGate:
    """Honours each host's robots.txt (RFC 9309) for the collector's token.

    * 2xx: the rules apply.
    * 4xx (no robots.txt): everything is allowed.
    * 5xx or unreachable: nothing is allowed until it can be read.
    """

    def __init__(self, client: "HttpClient"):
        self.client = client
        self._parsers: Dict[str, Optional[urllib.robotparser.RobotFileParser]] = {}
        self._failures: Dict[str, Exception] = {}

    def _load(self, origin: str) -> None:
        robots_url = origin + "/robots.txt"
        self.client._respect_rate_limit()
        self.client._last_request = self.client._clock()
        try:
            response = self.client.transport(
                "GET", robots_url, {"User-Agent": self.client.config.user_agent}, None, self.client.config.timeout)
        except (urllib.error.URLError, TimeoutError, ConnectionError, OSError) as exc:
            self._failures[origin] = SourceUnavailable(f"{origin} is unreachable ({exc}); robots.txt could not be read")
            return
        if 200 <= response.status < 300:
            parser = urllib.robotparser.RobotFileParser(robots_url)
            parser.parse(response.body.decode("utf-8", errors="replace").splitlines())
            self._parsers[origin] = parser
        elif 400 <= response.status < 500:
            self._parsers[origin] = None
        else:
            self._failures[origin] = RobotsDisallowed(
                f"{robots_url} answered HTTP {response.status}; nothing is fetched until it can be read")

    def require_allowed(self, url: str) -> None:
        parts = urllib.parse.urlsplit(url)
        origin = f"{parts.scheme}://{parts.netloc}"
        if origin not in self._parsers and origin not in self._failures:
            self._load(origin)
        failure = self._failures.get(origin)
        if failure is not None:
            raise type(failure)(str(failure))
        parser = self._parsers.get(origin)
        if parser is not None and not parser.can_fetch(ROBOTS_TOKEN, url):
            raise RobotsDisallowed(f"{url} is disallowed by {origin}/robots.txt for {ROBOTS_TOKEN}")
