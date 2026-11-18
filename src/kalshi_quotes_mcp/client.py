"""Bounded, pooled GET access to a fixed set of public Kalshi endpoints."""

from __future__ import annotations

import asyncio
import re
from dataclasses import dataclass
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from typing import Any

import httpx

from . import __version__

API_BASE = "https://external-api.kalshi.com/trade-api/v2"
TICKER_PATTERN = r"[A-Za-z0-9][A-Za-z0-9_.-]{0,199}"
_PATH = re.compile(rf"/markets(?:/{TICKER_PATTERN}(?:/orderbook)?)?\Z")


class KalshiError(Exception):
    """An upstream failure whose message is safe to show to an MCP caller."""

    def __init__(self, message: str, *, status_code: int | None = None):
        super().__init__(message)
        self.status_code = status_code


def ticker_value(value: str) -> str:
    value = value.strip().upper()
    if not re.fullmatch(TICKER_PATTERN, value):
        raise ValueError(
            "Use a market ticker (1-200 letters, digits, dots, underscores or hyphens)."
        )
    return value


@dataclass(frozen=True)
class Snapshot:
    data: dict[str, Any]
    source_url: str
    retrieved_at: str
    upstream_date: str | None
    upstream_age_seconds: str | None

    def metadata(self) -> dict[str, Any]:
        return {
            "source_url": self.source_url,
            "retrieved_at": self.retrieved_at,
            "upstream_date": self.upstream_date,
            "upstream_age_seconds": self.upstream_age_seconds,
            "server_cache": "disabled",
        }


def retry_after_seconds(value: str | None) -> float | None:
    if value is None:
        return None
    try:
        seconds = float(value)
        return seconds if 0 <= seconds < float("inf") else None
    except ValueError:
        try:
            return max(0, (parsedate_to_datetime(value) - datetime.now(UTC)).total_seconds())
        except (TypeError, ValueError, OverflowError):
            return None


class KalshiClient:
    """A client shared by the server lifespan; never accepts credentials or arbitrary URLs."""

    def __init__(
        self,
        *,
        transport: httpx.AsyncBaseTransport | None = None,
        requests_per_second: float = 5.0,
    ) -> None:
        if not 0 < requests_per_second <= 10000:
            raise ValueError("requests_per_second must be positive and at most 10000")
        self._http = httpx.AsyncClient(
            timeout=httpx.Timeout(10, pool=5),
            limits=httpx.Limits(max_connections=4, max_keepalive_connections=4),
            follow_redirects=False,
            headers={
                "Accept": "application/json",
                "User-Agent": f"kalshi-quotes-mcp/{__version__}",
            },
            transport=transport,
        )
        self._slots = asyncio.Semaphore(4)
        self._rate_lock = asyncio.Lock()
        self._interval = 1 / requests_per_second
        self._next_request = 0.0

    async def __aenter__(self) -> KalshiClient:
        return self

    async def __aexit__(self, *args: object) -> None:
        await self._http.aclose()

    async def _pace(self) -> None:
        async with self._rate_lock:
            loop = asyncio.get_running_loop()
            await asyncio.sleep(max(0, self._next_request - loop.time()))
            self._next_request = loop.time() + self._interval

    async def get(self, path: str, params: dict[str, Any] | None = None) -> Snapshot:
        if not _PATH.fullmatch(path):
            raise ValueError("Only public market read endpoints are allowed.")
        try:
            async with asyncio.timeout(30), self._slots:
                return await self._request(path, params)
        except TimeoutError as exc:
            raise KalshiError("Kalshi request exceeded the 30-second deadline; try again.") from exc

    async def _request(self, path: str, params: dict[str, Any] | None) -> Snapshot:
        for attempt in range(3):
            await self._pace()
            try:
                response = await self._http.get(API_BASE + path, params=params)
            except httpx.TransportError as exc:
                if attempt == 2:
                    raise KalshiError(
                        "Unable to reach Kalshi after 3 attempts; try again."
                    ) from exc
                await asyncio.sleep(0.5 * 2**attempt)
                continue
            if response.status_code == 429 or response.status_code in (500, 502, 503, 504):
                delay = retry_after_seconds(response.headers.get("Retry-After"))
                if attempt == 2 or (delay is not None and delay > 5):
                    message = (
                        "Kalshi rate limit reached"
                        if response.status_code == 429
                        else "Kalshi is temporarily unavailable"
                    )
                    raise KalshiError(
                        f"{message}; wait before retrying.", status_code=response.status_code
                    )
                await asyncio.sleep(delay if delay is not None else 0.5 * 2**attempt)
                continue
            if not response.is_success:
                message = (
                    "Market not found in Kalshi's current market endpoint."
                    if response.status_code == 404
                    else f"Kalshi returned HTTP {response.status_code}; check the request or retry."
                )
                raise KalshiError(message, status_code=response.status_code)
            try:
                data = response.json()
            except ValueError as exc:
                raise KalshiError("Kalshi returned invalid JSON; no prices were inferred.") from exc
            if not isinstance(data, dict):
                raise KalshiError("Kalshi returned an unexpected response shape.")
            return Snapshot(
                data=data,
                source_url=str(response.request.url),
                retrieved_at=datetime.now(UTC)
                .isoformat(timespec="milliseconds")
                .replace("+00:00", "Z"),
                upstream_date=response.headers.get("Date"),
                upstream_age_seconds=response.headers.get("Age"),
            )
        raise AssertionError("unreachable")
