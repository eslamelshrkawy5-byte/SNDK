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
    assert "تأكيد الدخول: ❌ 0/1 — شروط الدخول غير مكتملة" in report
    assert "القرار الآن: ⛔ لا تدخل SNXX أو SNDQ الآن" in report
    assert "قاعدة الدخول المتوازن: ±2.5 بتأكيد واحد" in report
    assert "3/4 من مؤشرات SNDK + دعم QQQ أو SMH" in report
    assert "حجم SNDK ≥ 0.8× + شمعة 15 دقيقة مكتملة" in report
    assert "المسار القوي: |الدرجة| ≥ 3.5" in report
    assert "قاعدة الخروج: ±1.5 مع 2 تحليلين متتاليين" in report


def test_moderate_bullish_score_is_only_unconfirmed_lean():
    report = format_report(
        decision(Signal.WAIT, Signal.WAIT, 2.1), NewsBundle(), BotState(), NOW, "manual"
    )

    assert "الاتجاه الفني الحالي: 🟡 ميل صاعد غير مؤكد" in report
    assert "تأكيد الدخول: ❌ 0/1" in report


def test_blocked_bearish_entry_does_not_recommend_entry():
    report = format_report(
        decision(Signal.WAIT, Signal.WAIT, -4.2), NewsBundle(), BotState(), NOW, "manual"
    )

    assert "الاتجاه الفني الحالي: 🔴 هابط قوي" in report
    assert "تأكيد الدخول: ❌ 0/1 — شروط الدخول غير مكتملة" in report
    assert "القرار الآن: ⛔ لا تدخل SNXX أو SNDQ الآن" in report


def test_confirmed_bullish_signal_is_explicit():
    report = format_report(
        decision(Signal.SNXX, Signal.SNXX, 4.5), NewsBundle(), BotState(), NOW, "manual"
    )

    assert "الاتجاه الفني الحالي: 🟢 صاعد قوي" in report
    assert "تأكيد الدخول: ✅ 1/1 — صعود مؤكد" in report
    assert "القرار الآن: 🟢 ادخل SNXX" in report


def test_confirmed_bearish_signal_is_explicit():
    report = format_report(
        decision(Signal.SNDQ, Signal.SNDQ, -4.5), NewsBundle(), BotState(), NOW, "manual"
    )

    assert "تأكيد الدخول: ✅ 1/1 — هبوط مؤكد" in report
    assert "القرار الآن: 🔴 ادخل SNDQ" in report


def test_existing_snxx_continues_during_first_weak_run():
    state = BotState(
        confirmed_position="SNXX",
        active_signal="SNXX",
        candidate_signal="WAIT",
        candidate_count=1,
    )
    report = format_report(
        decision(Signal.SNXX, Signal.WAIT, 0.9), NewsBundle(), state, NOW, "manual"
    )

    assert "القرار الآن: 🟢 استمر في SNXX" in report
    assert "التوصية: إدارة المركز القائم" in report
    assert "يمكن دراسة SNXX" not in report


def test_wait_signal_tells_confirmed_snxx_position_to_exit_after_confirmation():
    state = BotState(confirmed_position="SNXX", active_signal="WAIT")
    report = format_report(
        decision(Signal.WAIT, Signal.WAIT, 0.09), NewsBundle(), state, NOW, "manual"
    )

    assert "القرار الآن: 🟠 اخرج من SNXX الآن؛ شرط الخروج/WAIT مؤكد" in report
    assert "حالة مركزك: داخل SNXX" in report


def test_old_active_signal_does_not_offer_new_entry_without_position():
    state = BotState(active_signal="SNXX", candidate_signal="WAIT", candidate_count=1)
    report = format_report(
        decision(Signal.SNXX, Signal.WAIT, 0.9), NewsBundle(), state, NOW, "manual"
    )

    assert "القرار الآن: ⛔ لا تدخل SNXX أو SNDQ الآن" in report
    assert "التوصية: انتظار: لا يوجد تأكيد كافٍ لدخول جديد الآن" in report
