from __future__ import annotations

from datetime import UTC, datetime

import sndk_bot.main as app
from sndk_bot.config import Config
from sndk_bot.state import StateStore


class NoPollingTelegram:
    instances = []

    def __init__(self, *_args):
        self.messages = []
        self.__class__.instances.append(self)

    def poll_confirmations(self, _offset):
        raise AssertionError("Webhook mode must not call getUpdates polling")

    def send(self, text, signal=None):
        self.messages.append((text, signal))


def config(tmp_path, *, webhook_mode=False):
    return Config(
        "fake-token",
        "123",
        tmp_path / "state.json",
        telegram_webhook_mode=webhook_mode,
    )


def test_webhook_mode_skips_polling_on_non_trading_day(monkeypatch, tmp_path):
    NoPollingTelegram.instances.clear()
    monkeypatch.setattr(app, "TelegramClient", NoPollingTelegram)
    monkeypatch.setattr(app, "is_us_trading_day", lambda *_: False)

    assert app.run(config(tmp_path, webhook_mode=True), datetime(2026, 8, 8, tzinfo=UTC)) == 0


def test_position_update_persists_then_forces_reassessment(monkeypatch, tmp_path):
    cfg = config(tmp_path, webhook_mode=True)
    calls = []

    def fake_run(received_config, now=None, force_report=False):
        calls.append((received_config, now, force_report))
        return 0

    monkeypatch.setattr(app, "run", fake_run)

    assert app.run_position_update(cfg, "SNXX") == 0
    assert StateStore(cfg.state_path).load().confirmed_position == "SNXX"
    assert calls == [(cfg, None, True)]


def test_exit_update_clears_confirmed_position(monkeypatch, tmp_path):
    cfg = config(tmp_path)
    state = StateStore(cfg.state_path).load()
    state.confirmed_position = "SNDQ"
    StateStore(cfg.state_path).save(state)
    monkeypatch.setattr(app, "run", lambda *_args, **_kwargs: 0)

    assert app.run_position_update(cfg, "EXIT") == 0
    assert StateStore(cfg.state_path).load().confirmed_position is None
