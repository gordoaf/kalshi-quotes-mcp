import pytest

from kalshi_quotes_mcp.client import KalshiError
from kalshi_quotes_mcp.quotes import market_quote, orderbook_levels


def test_subcent_prices_and_fractional_sizes(market):
    quote = market_quote(market)
    assert quote["yes"] == {
        "bid_cents": "43.25",
        "ask_cents": "45",
        "bid_size": "12.5",
        "ask_size": "20",
    }
    assert quote["no"]["ask_cents"] == "56.75"
    assert quote["no"]["bid_size"] == "20"
    assert quote["no"]["ask_size"] == "12.5"
    assert quote["last_trade_cents"] == "44"
    assert quote["quote_state"] == "available"


def test_empty_boundary_prices_are_not_free_contracts(market):
    market.update(
        yes_bid_dollars="0.0000",
        yes_ask_dollars="0.0000",
        no_bid_dollars="1.0000",
        no_ask_dollars="1.0000",
        volume_fp="0",
    )
    quote = market_quote(market)
    assert quote["quote_state"] == "empty"
    assert quote["yes"]["ask_cents"] is None
    assert quote["no"]["bid_cents"] is None
    assert quote["last_trade_cents"] is None
    assert quote["raw_quote_fields"]["yes_ask_dollars"] == "0.0000"


def test_missing_size_is_unknown_but_zero_size_suppresses_quote(market):
    market.pop("yes_bid_size_fp")
    market["yes_ask_size_fp"] = "0"
    quote = market_quote(market)
    assert quote["yes"]["bid_size"] is None
    assert quote["yes"]["bid_cents"] == "43.25"
    assert quote["yes"]["ask_cents"] is None
    assert quote["no"]["bid_cents"] is None
    assert quote["quote_state"] == "partial"


@pytest.mark.parametrize("bad", ["NaN", "Infinity", "broken", "-0.1", "1.2", True])
def test_invalid_price_is_omitted_with_warning(market, bad):
    market["yes_bid_dollars"] = bad
    quote = market_quote(market)
    assert quote["yes"]["bid_cents"] is None
    assert any("Invalid upstream" in warning for warning in quote["warnings"])


def test_invalid_size_is_not_treated_as_unknown(market):
    market["yes_bid_size_fp"] = "-3"
    quote = market_quote(market)
    assert quote["yes"]["bid_cents"] is None
    assert quote["no"]["ask_cents"] is None


def test_closed_quotes_keep_history_but_are_labeled(market):
    market["status"] = "settled"
    quote = market_quote(market)
    assert quote["quote_state"] == "inactive"
    assert quote["yes"]["bid_cents"] == "43.25"
    assert "historical" in quote["warnings"][0]


def test_crossed_snapshot_is_flagged_without_repair(market):
    market["yes_bid_dollars"] = "0.60"
    quote = market_quote(market)
    assert quote["yes"]["bid_cents"] == "60"
    assert any("Crossed" in warning for warning in quote["warnings"])


def test_unknown_volume_and_zero_last_price_is_not_a_trade(market):
    market.pop("volume_fp")
    market["last_price_dollars"] = "0.0000"
    assert market_quote(market)["last_trade_cents"] is None


def test_orderbook_complements_sorting_depth_and_quantities():
    book = orderbook_levels(
        {
            "orderbook_fp": {
                "yes_dollars": [["0.42", "3.25"], ["0.10", "100"]],
                "no_dollars": [["0.40", "5"], ["0.56", "9.50"]],
            }
        },
        1,
    )
    assert book["yes"]["bids"] == [{"price_cents": "42", "size": "3.25"}]
    assert book["yes"]["asks"] == [{"price_cents": "44", "size": "9.5"}]
    assert book["no"]["asks"] == [{"price_cents": "58", "size": "3.25"}]
    assert not book["empty"] and not book["crossed"]


def test_empty_book_has_no_synthetic_asks():
    book = orderbook_levels({"orderbook_fp": {"yes_dollars": [], "no_dollars": []}}, 5)
    assert book["empty"]
    assert book["yes"]["asks"] == []


@pytest.mark.parametrize("row", [["NaN", "3"], ["0.5", "-1"], ["0.2"], "bad"])
def test_bad_orderbook_levels_fail_explicitly(row):
    with pytest.raises(KalshiError):
        orderbook_levels({"orderbook_fp": {"yes_dollars": [row], "no_dollars": []}}, 10)
