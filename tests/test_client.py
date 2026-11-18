import asyncio

import httpx
import pytest

from kalshi_quotes_mcp.client import KalshiClient, KalshiError, retry_after_seconds


async def test_only_public_gets_and_fresh_requests():
    calls = []

    def handler(request):
        calls.append(request)
        assert request.method == "GET"
        assert request.url.host == "external-api.kalshi.com"
        assert "Authorization" not in request.headers
        return httpx.Response(200, json={"markets": []}, headers={"Age": "2"})

    async with KalshiClient(
        transport=httpx.MockTransport(handler), requests_per_second=10000
    ) as api:
        first = await api.get("/markets", {"tickers": "A,B"})
        second = await api.get("/markets", {"tickers": "A,B"})
        assert len(calls) == 2
        assert first.metadata()["server_cache"] == "disabled"
        assert first.upstream_age_seconds == "2"
        assert first.retrieved_at <= second.retrieved_at
        assert first.retrieved_at.endswith("Z")
        for path in (
            "/portfolio/orders",
            "https://example.com",
            "/markets/../portfolio",
            "/markets/A?x=y",
        ):
            with pytest.raises(ValueError):
                await api.get(path)


async def test_rate_limit_retries_are_bounded(monkeypatch):
    calls, sleeps = [], []

    async def sleep(seconds):
        sleeps.append(seconds)

    monkeypatch.setattr(asyncio, "sleep", sleep)

    def handler(request):
        calls.append(request)
        return httpx.Response(429, headers={"Retry-After": "1"})

    async with KalshiClient(transport=httpx.MockTransport(handler)) as api:
        with pytest.raises(KalshiError, match="rate limit"):
            await api.get("/markets")
    assert len(calls) == 3
    assert sleeps.count(1) == 2


async def test_long_retry_after_is_not_retried_early():
    calls = []

    def handler(request):
        calls.append(request)
        return httpx.Response(429, headers={"Retry-After": "60"})

    async with KalshiClient(transport=httpx.MockTransport(handler)) as api:
        with pytest.raises(KalshiError):
            await api.get("/markets")
    assert len(calls) == 1


@pytest.mark.parametrize("failure", ["timeout", "server"])
async def test_transient_failure_then_success(monkeypatch, failure):
    calls = 0

    async def sleep(seconds):
        pass

    monkeypatch.setattr(asyncio, "sleep", sleep)

    def handler(request):
        nonlocal calls
        calls += 1
        if calls == 1:
            if failure == "timeout":
                raise httpx.ReadTimeout("private detail", request=request)
            return httpx.Response(503)
        return httpx.Response(200, json={"markets": []})

    async with KalshiClient(transport=httpx.MockTransport(handler)) as api:
        assert (await api.get("/markets")).data == {"markets": []}
    assert calls == 2


@pytest.mark.parametrize(
    "status,body", [(404, "secret"), (302, "redirect"), (200, "not-json"), (200, "[]")]
)
async def test_bad_responses_are_sanitized_and_not_followed(status, body):
    calls = []

    def handler(request):
        calls.append(request)
        return httpx.Response(status, text=body, headers={"Location": "https://example.com"})

    async with KalshiClient(transport=httpx.MockTransport(handler)) as api:
        with pytest.raises(KalshiError) as error:
            await api.get("/markets/TEST")
        assert body not in str(error.value)
    assert len(calls) == 1


@pytest.mark.parametrize("value", ["NaN", "inf", "-1", "garbage", None])
def test_bad_retry_after_is_ignored(value):
    assert retry_after_seconds(value) is None
