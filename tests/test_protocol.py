import sys

import httpx
import pytest
from mcp import Client, StdioServerParameters
from starlette.testclient import TestClient

from kalshi_quotes_mcp.cli import transport_security
from kalshi_quotes_mcp.client import KalshiClient
from kalshi_quotes_mcp.server import create_server

TOOL_NAMES = {"get_quotes", "list_markets", "get_market", "get_orderbook"}


def fake_server(market):
    def handler(request):
        return httpx.Response(200, json={"markets": [market]})

    return create_server(lambda: KalshiClient(transport=httpx.MockTransport(handler)))


async def test_mcp_discovery_and_structured_quotes(market):
    async with Client(fake_server(market), raise_exceptions=True) as client:
        tools = (await client.list_tools()).tools
        assert {tool.name for tool in tools} == TOOL_NAMES
        for tool in tools:
            annotations = tool.annotations.model_dump(by_alias=True)
            assert annotations["readOnlyHint"] is True
            assert annotations["destructiveHint"] is False
            assert "ctx" not in tool.input_schema["properties"]
        response = await client.call_tool("get_quotes", {"tickers": ["TEST-YES"]})
        assert not response.is_error
        assert response.structured_content["quotes"][0]["yes"]["bid_cents"] == "43.25"
        assert response.content[0].type == "text"


@pytest.mark.parametrize(
    "name,args",
    [
        ("get_quotes", {"tickers": []}),
        ("get_quotes", {"tickers": ["A"] * 101}),
        ("get_quotes", {"tickers": ["https://example.com"]}),
        ("get_orderbook", {"ticker": "TEST", "depth": 0}),
        ("list_markets", {"limit": 101}),
    ],
)
async def test_mcp_schema_validation(market, name, args):
    async with Client(fake_server(market)) as client:
        result = await client.call_tool(name, args)
        assert result.is_error


async def test_upstream_error_is_a_tool_error():
    server = create_server(
        lambda: KalshiClient(
            transport=httpx.MockTransport(
                lambda r: httpx.Response(
                    429, text="private upstream detail", headers={"Retry-After": "60"}
                )
            )
        )
    )
    async with Client(server) as client:
        result = await client.call_tool("get_quotes", {"tickers": ["A"]})
        assert result.is_error
        assert "rate limit" in result.content[0].text
        assert "private upstream" not in result.content[0].text


async def test_real_stdio_entrypoint_starts_and_discovers():
    params = StdioServerParameters(command=sys.executable, args=["-m", "kalshi_quotes_mcp"])
    async with Client(params, read_timeout_seconds=15) as client:
        assert {tool.name for tool in (await client.list_tools()).tools} == TOOL_NAMES
        result = await client.call_tool("get_quotes", {"tickers": []})
        assert result.is_error


def test_http_protocol_quotes_and_transport_protection(market):
    app = fake_server(market).streamable_http_app(
        stateless_http=True,
        json_response=True,
        max_request_body_size=65536,
        transport_security=transport_security([]),
    )
    headers = {"Accept": "application/json, text/event-stream"}
    with TestClient(app, base_url="http://127.0.0.1:8000") as client:
        initialized = client.post(
            "/mcp",
            headers=headers,
            json={
                "jsonrpc": "2.0",
                "id": 1,
                "method": "initialize",
                "params": {
                    "protocolVersion": "2025-11-25",
                    "capabilities": {},
                    "clientInfo": {"name": "test", "version": "1"},
                },
            },
        )
        assert initialized.status_code == 200, initialized.text
        headers["MCP-Protocol-Version"] = initialized.json()["result"]["protocolVersion"]
        response = client.post(
            "/mcp",
            headers=headers,
            json={
                "jsonrpc": "2.0",
                "id": 2,
                "method": "tools/call",
                "params": {
                    "name": "get_quotes",
                    "arguments": {"tickers": ["TEST-YES"]},
                },
            },
        )
        assert response.status_code == 200, response.text
        assert response.json()["result"]["structuredContent"]["quotes"][0]["ticker"] == "TEST-YES"
        assert (
            client.post("/mcp", headers={**headers, "Host": "evil.example"}, json={}).status_code
            == 421
        )
        assert (
            client.post(
                "/mcp", headers={**headers, "Origin": "https://evil.example"}, json={}
            ).status_code
            == 403
        )
        assert (
            client.post(
                "/mcp", headers={**headers, "Content-Type": "application/json"}, content="x" * 65537
            ).status_code
            == 413
        )
