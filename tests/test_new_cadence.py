from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from conftest import make_series

from sndk_bot.calendar import change_alerts_enabled, latest_completed_session_close
from sndk_bot.market import MarketDataError, completed_session_bundle


def test_latest_completed_session_before_open_uses_prior_trading_day():
    now = datetime(2026, 8, 5, 7, 30, tzinfo=UTC)
    completed = latest_completed_session_close(now)
    assert completed == datetime(2026, 8, 4, 20, 0, tzinfo=UTC)


def test_latest_completed_session_handles_monday_weekend():
    now = datetime(2026, 8, 10, 7, 30, tzinfo=UTC)
    completed = latest_completed_session_close(now)
    assert completed == datetime(2026, 8, 7, 20, 0, tzinfo=UTC)


def test_completed_session_data_accepts_naturally_stale_premarket_bars():
    now = datetime(2026, 8, 5, 7, 30, tzinfo=UTC)
    last_bar = datetime(2026, 8, 4, 20, 0, tzinfo=UTC)
    bundle = {ticker: make_series(ticker, 1, last_bar) for ticker in ("SNDK", "QQQ")}
    prepared, completed = completed_session_bundle(bundle, now, "XNYS")
    assert completed == last_bar
    assert all(series.timestamp == last_bar for series in prepared.values())


def test_completed_session_bundle_excludes_current_premarket_bars():
    now = datetime(2026, 8, 5, 7, 30, tzinfo=UTC)
    series = make_series("SNDK", 1, datetime(2026, 8, 5, 7, 30, tzinfo=UTC), bars=80)
    prepared, completed = completed_session_bundle({"SNDK": series}, now, "XNYS")
    assert prepared["SNDK"].timestamp <= completed
    assert prepared["SNDK"].timestamp == datetime(2026, 8, 4, 20, 0, tzinfo=UTC)


def test_completed_session_data_rejects_previous_old_session():
    now = datetime(2026, 8, 5, 7, 30, tzinfo=UTC)
    old = now - timedelta(days=2)
    bundle = {"SNDK": make_series("SNDK", 1, old)}
    with pytest.raises(MarketDataError, match="completed-session data unavailable"):
        completed_session_bundle(bundle, now, "XNYS")


def test_change_alerts_wait_until_today_1115_report_is_recorded():
    now = datetime(2026, 8, 5, 8, 30, tzinfo=UTC)
    assert not change_alerts_enabled(now, "Asia/Riyadh", None)
    assert not change_alerts_enabled(now, "Asia/Riyadh", "2026-08-04")
    assert change_alerts_enabled(now, "Asia/Riyadh", "2026-08-05")
