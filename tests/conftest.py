import pytest


@pytest.fixture
def market():
    return {
        "ticker": "TEST-YES",
        "title": "An example event",
        "event_ticker": "TEST",
        "status": "active",
        "yes_bid_dollars": "0.4325",
        "yes_ask_dollars": "0.4500",
        "no_bid_dollars": "0.5500",
        "no_ask_dollars": "0.5675",
        "yes_bid_size_fp": "12.50",
        "yes_ask_size_fp": "20.00",
        "last_price_dollars": "0.4400",
        "volume_fp": "100.50",
        "rules_primary": "Resolves based on the published result.",
    }
