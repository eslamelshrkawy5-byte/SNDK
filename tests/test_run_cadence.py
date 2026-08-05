from __future__ import annotations

from datetime import UTC, datetime

from conftest import make_series

import sndk_bot.main as app
from sndk_bot.config import Config
from sndk_bot.models import NewsBundle, Signal, SignalDecision
from sndk_bot.state import StateStore


class FakeTelegram:
    instances = []

    def __init__(self, *args):
        self.messages = []
        self.__class__.instances.append(self)

    def poll_confirmations(self, offset):
        return [], offset

    def send(self, text, signal=None):
        self.messages.append((text, signal))


def config(tmp_path):
    return Config("fake-token", "123", tmp_path / "state.json")


def test_1030_sends_completed_session_report_without_intraday_freshness(monkeypatch, tmp_path):
    now = datetime(2026, 8, 5, 7, 30, tzinfo=UTC)
    completed = datetime(2026, 8, 4, 20, 0, tzinfo=UTC)
    bundle = {ticker: make_series(ticker, 1, completed) for ticker in ("SNDK", "QQQ", "SMH")}
    FakeTelegram.instances.clear()
    monkeypatch.setattr(app, "TelegramClient", FakeTelegram)
    monkeypatch.setattr(app, "is_us_trading_day", lambda *_: True)
    monkeypatch.setattr(app, "mandatory_slot", lambda *_: "1030")
    monkeypatch.setattr(app, "fetch_market_bundle", lambda *_: bundle)
    monkeypatch.setattr(app, "fetch_news", lambda *_: NewsBundle(sources=["mock"]))

    def forbidden_freshness(*_):
        raise AssertionError("10:30 must not apply intraday freshness")

    monkeypatch.setattr(app, "assert_fresh", forbidden_freshness)
    assert app.run(config(tmp_path), now) == 0
    messages = FakeTelegram.instances[0].messages
    assert len(messages) == 1
    assert "Latest completed US session" in messages[0][0]
    assert "plus news fetched now" in messages[0][0]


def test_pre_1115_change_is_persisted_but_not_alerted(monkeypatch, tmp_path):
    now = datetime(2026, 8, 5, 8, 0, tzinfo=UTC)  # 11:00 Riyadh
    bundle = {ticker: make_series(ticker, 1, now) for ticker in ("SNDK", "QQQ", "SMH")}
    FakeTelegram.instances.clear()
    monkeypatch.setattr(app, "TelegramClient", FakeTelegram)
    monkeypatch.setattr(app, "is_us_trading_day", lambda *_: True)
    monkeypatch.setattr(app, "mandatory_slot", lambda *_: None)
    monkeypatch.setattr(app, "fetch_market_bundle", lambda *_: bundle)
    monkeypatch.setattr(app, "assert_fresh", lambda *_: None)
    monkeypatch.setattr(app, "fetch_news", lambda *_: NewsBundle(sources=["mock"]))

    def confirmed_change(_bundle, _news, state, *_):
        state.active_signal = Signal.SNXX.value
        return SignalDecision(
            Signal.SNXX,
            Signal.SNXX,
            5.0,
            ["mock confirmed change"],
            [],
            now,
            "mock",
            True,
        )

    monkeypatch.setattr(app, "decide", confirmed_change)
    cfg = config(tmp_path)
    assert app.run(cfg, now) == 0
    assert FakeTelegram.instances[0].messages == []
    assert StateStore(cfg.state_path).load().active_signal == Signal.SNXX.value
