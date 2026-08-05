from __future__ import annotations

from datetime import timedelta

import pytest
from conftest import make_series

from sndk_bot.market import MarketDataError, assert_fresh


def test_stale_market_data_is_rejected(now):
    stale_time = now - timedelta(minutes=46)
    bundle = {"SNDK": make_series("SNDK", 1, stale_time)}
    with pytest.raises(MarketDataError, match="Stale market data"):
        assert_fresh(bundle, now, stale_minutes=45)


def test_fresh_market_data_is_accepted(now):
    bundle = {"SNDK": make_series("SNDK", 1, now)}
    assert_fresh(bundle, now, stale_minutes=45)
