import httpx
import pytest

from kalshi_quotes_mcp.client import KalshiClient, KalshiError
from kalshi_quotes_mcp.service import MarketService


async def test_batch_preserves_order_deduplicates_and_reports_missing(market):
    calls = []

    def handler(request):
        calls.append(request)
        assert request.url.params["tickers"] == "B,TEST-YES,MISSING"
        assert "status" not in request.url.params
        return httpx.Response(200, json={"markets": [market, {**market, "ticker": "B"}]})

    async with KalshiClient(transport=httpx.MockTransport(handler)) as api:
        result = await MarketService(api).get_quotes(["b", "TEST-YES", "B", "MISSING"])
    assert [q["ticker"] for q in result["quotes"]] == ["B", "TEST-YES"]
    assert result["errors"][0]["code"] == "not_returned"
    assert len(calls) == 1


async def test_unexpected_pagination_is_followed(market):
    def handler(request):
        if "cursor" not in request.url.params:
            return httpx.Response(200, json={"markets": [market], "cursor": "next"})
        assert request.url.params["cursor"] == "next"
        return httpx.Response(200, json={"markets": [{**market, "ticker": "B"}], "cursor": ""})

    async with KalshiClient(
        transport=httpx.MockTransport(handler), requests_per_second=10000
    ) as api:
        result = await MarketService(api).get_quotes(["TEST-YES", "B"])
    assert len(result["quotes"]) == 2
    assert len(result["sources"]) == 2


async def test_repeated_cursor_fails_instead_of_looping():
    async with KalshiClient(
        transport=httpx.MockTransport(
            lambda r: httpx.Response(200, json={"markets": [], "cursor": "same"})
        ),
        requests_per_second=10000,
    ) as api:
        with pytest.raises(KalshiError, match="repeated"):
            await MarketService(api).get_quotes(["A"])


async def test_discovery_filters_and_cursor(market):
    def handler(request):
        assert dict(request.url.params) == {
            "status": "open",
            "limit": "2",
            "mve_filter": "exclude",
            "series_ticker": "SERIES",
            "cursor": "opaque+/=",
        }
        return httpx.Response(200, json={"markets": [market], "cursor": "next"})

    async with KalshiClient(transport=httpx.MockTransport(handler)) as api:
        result = await MarketService(api).list_markets(
            series_ticker="series", limit=2, cursor="opaque+/="
        )
    assert result["has_more"] and result["next_cursor"] == "next"


async def test_unknown_market_is_not_labeled_an_empty_book():
    calls = []

    def handler(request):
        calls.append(request.url.path)
        return httpx.Response(404)

    async with KalshiClient(transport=httpx.MockTransport(handler)) as api:
        with pytest.raises(KalshiError, match="not found"):
            await MarketService(api).get_orderbook("MISSING")
    assert len(calls) == 1
    assert not calls[0].endswith("/orderbook")


async def test_known_empty_book_and_rules(market):
    def handler(request):
        payload = {"orderbook_fp": {"yes_dollars": [], "no_dollars": []}}
        return httpx.Response(
            200, json=payload if request.url.path.endswith("/orderbook") else {"market": market}
        )

    async with KalshiClient(
        transport=httpx.MockTransport(handler), requests_per_second=10000
    ) as api:
        service = MarketService(api)
        assert (await service.get_orderbook("TEST-YES"))["empty"]
        assert (await service.get_market("TEST-YES"))["rules_primary"] == market["rules_primary"]


@pytest.mark.parametrize("tickers", [[], ["A"] * 101, ["https://example.com"], ["../../orders"]])
async def test_bad_inputs_do_not_reach_upstream(tickers):
    def handler(request):
        pytest.fail("Invalid input reached upstream")

    async with KalshiClient(transport=httpx.MockTransport(handler)) as api:
        with pytest.raises(ValueError):
            await MarketService(api).get_quotes(tickers)
