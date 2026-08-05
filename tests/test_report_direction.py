from __future__ import annotations

from datetime import UTC, datetime

from sndk_bot.models import NewsBundle, Signal, SignalDecision
from sndk_bot.report import format_report
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


def test_wait_report_still_shows_current_bullish_direction():
    report = format_report(
        decision(Signal.WAIT, Signal.WAIT, 2.1), NewsBundle(), BotState(), NOW, "manual"
    )

    assert "الاتجاه الفني الحالي: 🟢 صاعد" in report
    assert "تأكيد الدخول: ❌ غير مؤكد للدخول" in report
    assert "الإشارة المعتمدة: انتظار" in report


def test_pending_bearish_confirmation_is_explicit():
    report = format_report(
        decision(Signal.WAIT, Signal.SNDQ, -4.2), NewsBundle(), BotState(), NOW, "manual"
    )

    assert "الاتجاه الفني الحالي: 🔴 هابط" in report
    assert "تأكيد الدخول: ⏳ هبوط قوي قيد التأكيد" in report


def test_confirmed_bullish_signal_is_explicit():
    report = format_report(
        decision(Signal.SNXX, Signal.SNXX, 4.5), NewsBundle(), BotState(), NOW, "manual"
    )

    assert "الاتجاه الفني الحالي: 🟢 صاعد" in report
    assert "تأكيد الدخول: ✅ صعود مؤكد — إشارة SNXX نشطة" in report
