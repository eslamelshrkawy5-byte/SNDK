from __future__ import annotations

from datetime import timedelta

import pytest
from conftest import make_series

from sndk_bot.market import MarketDataError, assert_fresh, completed_intraday_bundle


def test_stale_market_data_is_rejected(now):
    stale_time = now - timedelta(minutes=46)
    bundle = {"SNDK": make_series("SNDK", 1, stale_time)}
    with pytest.raises(MarketDataError, match="Stale market data"):
        assert_fresh(bundle, now, stale_minutes=45)


def test_fresh_market_data_is_accepted(now):
    bundle = {"SNDK": make_series("SNDK", 1, now)}
    assert_fresh(bundle, now, stale_minutes=45)


def test_completed_intraday_bundle_removes_forming_bar(now):
    bundle = {
        ticker: make_series(ticker, 1, now)
        for ticker in ("SNDK", "QQQ", "SMH")
    }

    prepared = completed_intraday_bundle(bundle, now)

    expected_timestamp = now - timedelta(minutes=15)
    assert set(prepared) == {"SNDK", "QQQ", "SMH"}
    assert all(series.timestamp == expected_timestamp for series in prepared.values())
    assert all(len(series.frame) == 59 for series in prepared.values())
    assert all(now not in series.frame.index for series in prepared.values())


def test_completed_intraday_bundle_keeps_latest_completed_bar_between_boundaries(now):
    analysis_time = now + timedelta(minutes=7)
    bundle = {
        ticker: make_series(ticker, 1, now)
        for ticker in ("SNDK", "QQQ")
    }

    prepared = completed_intraday_bundle(bundle, analysis_time)

    assert prepared["SNDK"].timestamp == now - timedelta(minutes=15)
    assert prepared["QQQ"].timestamp == now - timedelta(minutes=15)


def test_completed_intraday_bundle_rejects_insufficient_history(now):
    bundle = {
        ticker: make_series(ticker, 1, now, bars=30)
        for ticker in ("SNDK", "QQQ")
    }

    with pytest.raises(MarketDataError, match="Insufficient completed 15-minute bars"):
        completed_intraday_bundle(bundle, now)


def test_completed_intraday_bundle_requires_market_context(now):
    bundle = {"SNDK": make_series("SNDK", 1, now)}

    with pytest.raises(MarketDataError, match="Insufficient completed 15-minute bars"):
        completed_intraday_bundle(bundle, now)
