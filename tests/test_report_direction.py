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


def test_neutral_report_for_weak_score_is_explicit():
    report = format_report(
        decision(Signal.WAIT, Signal.WAIT, 0.09), NewsBundle(), BotState(), NOW, "manual"
    )

    assert "الاتجاه الفني الحالي: ⚪ محايد" in report
    assert "تأكيد الدخول: ❌ 0/2 — لا توجد إشارة دخول" in report
    assert "القرار الآن: ⛔ لا تدخل SNXX أو SNDQ الآن" in report
    assert "قاعدة الدخول: +3.5 لـSNXX أو −3.5 لـSNDQ في 2 تحليلين متتاليين" in report


def test_moderate_bullish_score_is_only_unconfirmed_lean():
    report = format_report(
        decision(Signal.WAIT, Signal.WAIT, 2.1), NewsBundle(), BotState(), NOW, "manual"
    )

    assert "الاتجاه الفني الحالي: 🟡 ميل صاعد غير مؤكد" in report
    assert "تأكيد الدخول: ❌ 0/2" in report


def test_pending_bearish_confirmation_shows_progress():
    state = BotState(candidate_signal="SNDQ", candidate_count=1)
    report = format_report(
        decision(Signal.WAIT, Signal.SNDQ, -4.2), NewsBundle(), state, NOW, "manual"
    )

    assert "الاتجاه الفني الحالي: 🔴 هابط قوي" in report
    assert "تأكيد الدخول: ⏳ 1/2 — هبوط قيد التأكيد" in report
    assert "القرار الآن: ⛔ لا تدخل الآن؛ انتظر اكتمال تأكيد الهبوط" in report


def test_confirmed_bullish_signal_is_explicit():
    report = format_report(
        decision(Signal.SNXX, Signal.SNXX, 4.5), NewsBundle(), BotState(), NOW, "manual"
    )

    assert "الاتجاه الفني الحالي: 🟢 صاعد قوي" in report
    assert "تأكيد الدخول: ✅ 2/2 — صعود مؤكد" in report
    assert "القرار الآن: 🟢 ادخل SNXX" in report


def test_wait_signal_tells_confirmed_snxx_position_to_exit():
    state = BotState(confirmed_position="SNXX")
    report = format_report(
        decision(Signal.WAIT, Signal.WAIT, 0.09), NewsBundle(), state, NOW, "manual"
    )

    assert "القرار الآن: 🟠 اخرج من SNXX الآن؛ شرط الخروج/WAIT مؤكد" in report
    assert "حالة مركزك: داخل SNXX" in report
