"""Console entrypoint. stdout is reserved for MCP unless a diagnostic flag is used."""

import argparse
import asyncio
import json
import re
import sys

from mcp.server.transport_security import TransportSecuritySettings

from . import __version__
from .client import KalshiClient, KalshiError
from .server import create_server
from .service import MarketService


def allowed_hostname(value: str) -> str:
    if not re.fullmatch(r"[A-Za-z0-9](?:[A-Za-z0-9.-]*[A-Za-z0-9])?(?::[0-9]{1,5})?", value):
        raise argparse.ArgumentTypeError(
            "Use an exact hostname, optionally with a port; no URL or wildcard."
        )
    return value.lower()


def transport_security(hosts: list[str]) -> TransportSecuritySettings:
    return TransportSecuritySettings(
        enable_dns_rebinding_protection=True,
        allowed_hosts=[
            "localhost",
            "localhost:*",
            "127.0.0.1",
            "127.0.0.1:*",
            "[::1]",
            "[::1]:*",
            *hosts,
        ],
        allowed_origins=[
            "http://localhost:*",
            "http://127.0.0.1:*",
            "http://[::1]:*",
            *(f"https://{host}" for host in hosts),
        ],
    )


async def check() -> dict:
    """Exercise all data operations with discovered public tickers; no fixed test market."""
    async with KalshiClient() as client:
        service = MarketService(client)
        page = await service.list_markets(limit=2)
        tickers = [market["ticker"] for market in page["markets"]]
        if not tickers:
            raise KalshiError("Connected to Kalshi, but no open markets were returned.")
        quotes = await service.get_quotes(tickers)
        detail = await service.get_market(tickers[0])
        book = await service.get_orderbook(tickers[0], depth=2)
        return {
            "ok": not quotes["errors"],
            "version": __version__,
            "checked": ["list_markets", "get_quotes", "get_market", "get_orderbook"],
            "tickers": tickers,
            "quotes": quotes,
            "market_status": detail["quote"]["status"],
            "orderbook_empty": book["empty"],
        }


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="kalshi-quotes-mcp",
        description="Read-only Kalshi market data over MCP. No API keys.",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    parser.add_argument(
        "--check", action="store_true", help="Check the live public API and print JSON, then exit."
    )
    parser.add_argument("--transport", choices=["stdio", "streamable-http"], default="stdio")
    parser.add_argument(
        "--host", default="127.0.0.1", help="HTTP bind address (default: loopback)."
    )
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument(
        "--allowed-host",
        action="append",
        type=allowed_hostname,
        default=[],
        help="Additional trusted HTTP hostname, repeatable; used behind HTTPS proxies.",
    )
    parser.add_argument(
        "--requests-per-second",
        type=float,
        default=5,
        help="Per-process upstream request pace (default: 5, maximum: 20).",
    )
    args = parser.parse_args()
    if not 1 <= args.port <= 65535:
        parser.error("--port must be between 1 and 65535")
    if not 0 < args.requests_per_second <= 20:
        parser.error("--requests-per-second must be positive and at most 20")
    if args.check:
        try:
            report = asyncio.run(check())
        except KalshiError as exc:
            print(json.dumps({"ok": False, "error": str(exc)}))
            sys.exit(1)
        print(json.dumps(report, indent=2))
        sys.exit(0 if report["ok"] else 1)
    server = create_server(lambda: KalshiClient(requests_per_second=args.requests_per_second))
    if args.transport == "stdio":
        server.run()
    else:
        server.run(
            transport="streamable-http",
            host=args.host,
            port=args.port,
            stateless_http=True,
            json_response=True,
            max_request_body_size=65536,
            transport_security=transport_security(args.allowed_host),
        )
