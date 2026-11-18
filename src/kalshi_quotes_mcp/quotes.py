"""Exact price conversion and explicit treatment of unavailable/historical liquidity."""

from __future__ import annotations

from decimal import Decimal, InvalidOperation
from typing import Any

from .client import KalshiError

PRICE_NOTE = (
    "Prices are decimal strings in cents per contract. Buy at the ask; sell at the bid. "
    "Quotes are indicative, exclude fees, and depend on available size. Last trade is not a quote. "
    "retrieved_at is response-receipt time, not an exchange quote timestamp; upstream may cache."
)


def decimal_value(value: Any) -> Decimal | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        number = Decimal(str(value))
        return number if number.is_finite() else None
    except InvalidOperation:
        return None


def decimal_string(value: Decimal) -> str:
    text = format(value, "f")
    return text.rstrip("0").rstrip(".") if "." in text else text


def cents(value: Decimal) -> str:
    return decimal_string(value * 100)


def _size(market: dict[str, Any], field: str) -> str | None:
    number = decimal_value(market.get(field))
    return decimal_string(number) if number is not None and number >= 0 else None


def market_quote(market: dict[str, Any]) -> dict[str, Any]:
    warnings: list[str] = []
    status = market.get("status")
    active = status == "active"
    if not active:
        warnings.append("Market is not active; returned prices may be historical.")
    size_fields = {
        "yes_bid": "yes_bid_size_fp",
        "yes_ask": "yes_ask_size_fp",
        "no_bid": "yes_ask_size_fp",
        "no_ask": "yes_bid_size_fp",
    }
    sizes = {side: _size(market, field) for side, field in size_fields.items()}
    prices: dict[str, str | None] = {}
    raw = {}
    for side in ("yes_bid", "yes_ask", "no_bid", "no_ask"):
        field = side + "_dollars"
        raw[field] = market.get(field)
        price = decimal_value(market.get(field))
        size = sizes[side]
        # 0/1 boundary values often stand for an empty side. Never advertise a free contract.
        invalid_size = market.get(size_fields[side]) is not None and size is None
        if invalid_size:
            warnings.append(f"Invalid upstream size for {side}; price omitted.")
        if price is None or not 0 < price < 1 or size == "0" or invalid_size:
            prices[side] = None
            if market.get(field) is not None and (price is None or price < 0 or price > 1):
                warnings.append(f"Invalid upstream {field}; price omitted.")
        else:
            prices[side] = cents(price)
    for side in ("yes", "no"):
        bid, ask = prices[f"{side}_bid"], prices[f"{side}_ask"]
        if bid is not None and ask is not None and Decimal(bid) > Decimal(ask):
            warnings.append(f"Crossed {side.upper()} snapshot; do not assume it can be traded.")
    count = sum(price is not None for price in prices.values())
    state = (
        "inactive" if not active else "available" if count == 4 else "partial" if count else "empty"
    )
    if active and count < 4:
        warnings.append("Some quote sides are missing, at a 0/100 boundary, or have zero size.")
    last = decimal_value(market.get("last_price_dollars"))
    volume = decimal_value(market.get("volume_fp"))
    last_cents = (
        cents(last)
        if last is not None
        and 0 <= last <= 1
        and volume != 0
        and (last > 0 or (volume is not None and volume > 0))
        else None
    )
    return {
        "ticker": market["ticker"],
        "title": market.get("title"),
        "event_ticker": market.get("event_ticker"),
        "yes_label": market.get("yes_sub_title"),
        "no_label": market.get("no_sub_title"),
        "status": status,
        "quote_state": state,
        "close_time": market.get("close_time"),
        "market_updated_at": market.get("updated_time"),
        "yes": {
            "bid_cents": prices["yes_bid"],
            "ask_cents": prices["yes_ask"],
            "bid_size": sizes["yes_bid"],
            "ask_size": sizes["yes_ask"],
        },
        "no": {
            "bid_cents": prices["no_bid"],
            "ask_cents": prices["no_ask"],
            "bid_size": sizes["no_bid"],
            "ask_size": sizes["no_ask"],
        },
        "last_trade_cents": last_cents,
        "volume_contracts": _size(market, "volume_fp"),
        "warnings": warnings,
        **({"raw_quote_fields": raw} if count < 4 or warnings else {}),
    }


def orderbook_levels(data: dict[str, Any], depth: int) -> dict[str, Any]:
    book = data.get("orderbook_fp")
    if not isinstance(book, dict):
        raise KalshiError("Kalshi returned no fixed-point orderbook; no prices were inferred.")

    def levels(name: str) -> list[tuple[Decimal, Decimal]]:
        raw = book.get(name)
        if not isinstance(raw, list):
            raise KalshiError("Kalshi returned an invalid orderbook side.")
        result = []
        for row in raw:
            if not isinstance(row, list) or len(row) != 2:
                raise KalshiError("Kalshi returned an invalid price level.")
            price, size = (decimal_value(v) for v in row)
            if price is None or size is None or not 0 < price < 1 or size < 0:
                raise KalshiError("Kalshi returned an invalid orderbook price or quantity.")
            if size > 0:
                result.append((price, size))
        return sorted(result, key=lambda row: row[0], reverse=True)[:depth]

    yes, no = levels("yes_dollars"), levels("no_dollars")

    def render(
        rows: list[tuple[Decimal, Decimal]], complement: bool = False
    ) -> list[dict[str, str]]:
        return [
            {"price_cents": cents(1 - price if complement else price), "size": decimal_string(size)}
            for price, size in rows
        ]

    return {
        "yes": {"bids": render(yes), "asks": render(no, True)},
        "no": {"bids": render(no), "asks": render(yes, True)},
        "empty": not yes and not no,
        "crossed": bool(yes and no and yes[0][0] + no[0][0] > 1),
        "asks_derived_from_opposite_bids": True,
    }
