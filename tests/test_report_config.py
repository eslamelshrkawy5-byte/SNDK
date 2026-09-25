from __future__ import annotations

import sys
from datetime import UTC, datetime
from zoneinfo import ZoneInfo

import pytest

import sndk_bot.main as app
from sndk_bot import __version__
from sndk_bot.models import NewsBundle, Signal, SignalDecision
from sndk_bot.report import format_data_error, format_report
from sndk_bot.state import BotState

NOW = datetime(2026, 8, 5, 15, 0, tzinfo=UTC)


def decision(signal: Signal, raw_signal: Signal, score: float) -> SignalDecision:
    return SignalDecision(
        signal=signal,
        raw_signal=raw_signal,
        score=score,
        reasons=[],
        risks=[],
        data_timestamp=NOW,
        source_summary="mock",
        confirmed=signal != Signal.WAIT,
    )


def test_package_exposes_a_version():
    assert __version__ == "1.0.0"


def test_cli_version_flag_prints_version_and_exits_zero(monkeypatch, capsys):
    monkeypatch.setattr(sys, "argv", ["sndk-bot", "--version"])
    with pytest.raises(SystemExit) as excinfo:
        app.main()
    assert excinfo.value.code == 0
    assert f"sndk-bot {__version__}" in capsys.readouterr().out


def test_report_timestamp_follows_configured_timezone():
    report = format_report(
        decision(Signal.WAIT, Signal.WAIT, 0.09),
        NewsBundle(),
        BotState(),
        NOW,
        "manual",
        timezone="America/New_York",
    )
    local = NOW.astimezone(ZoneInfo("America/New_York"))
    assert f"الرياض: {local:%Y-%m-%d %H:%M}" in report
    # Same instant must render differently in the default timezone.
    default = NOW.astimezone(ZoneInfo("Asia/Riyadh"))
    assert f"الرياض: {default:%Y-%m-%d %H:%M}" not in report


def test_data_error_timestamp_follows_configured_timezone():
    text = format_data_error("boom", NOW, True, timezone="America/New_York")
    local = NOW.astimezone(ZoneInfo("America/New_York"))
    assert f"الرياض: {local:%Y-%m-%d %H:%M}" in text


def test_unconfirmed_band_follows_configured_exit_threshold():
    report = format_report(
        decision(Signal.WAIT, Signal.WAIT, 1.3),
        NewsBundle(),
        BotState(),
        NOW,
        "manual",
        exit_threshold=1.2,
    )
    assert "🟡 ميل صاعد غير مؤكد" in report


def test_default_exit_threshold_keeps_below_1_5_neutral():
    report = format_report(
        decision(Signal.WAIT, Signal.WAIT, 1.3), NewsBundle(), BotState(), NOW, "manual"
    )
    assert "⚪ محايد" in report


def test_bearish_unconfirmed_band_follows_configured_exit_threshold():
    report = format_report(
        decision(Signal.WAIT, Signal.WAIT, -1.3),
        NewsBundle(),
        BotState(),
        NOW,
        "manual",
        exit_threshold=1.2,
    )
    assert "🟠 ميل هابط غير مؤكد" in report
