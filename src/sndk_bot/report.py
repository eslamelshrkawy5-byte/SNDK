from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

from .models import NewsBundle, Signal, SignalDecision
from .state import BotState

DISCLAIMER = (
    "⚠️ SNXX وSNDQ منتجات يومية برافعة/عكسية ويُعاد ضبطها يوميًا. "
    "التذبذب قد يسبب خسائر سريعة؛ وهي للاستخدام التكتيكي قصير الأجل وليست للاحتفاظ طويل الأجل. "
    "لا ينفذ البوت أي صفقة. التحليل من بيانات عامة وليس نصيحة استثمارية."
)


def _arabic_signal(signal: Signal) -> str:
    labels = {
        Signal.SNXX: "صعود — يمكن دراسة SNXX",
        Signal.SNDQ: "هبوط — يمكن دراسة SNDQ",
        Signal.WAIT: "انتظار / لا توجد إشارة مؤكدة",
    }
    return labels[signal]


def _direction_summary(decision: SignalDecision) -> tuple[str, str]:
    if decision.score > 0:
        direction = "🟢 صاعد"
    elif decision.score < 0:
        direction = "🔴 هابط"
    else:
        direction = "⚪ محايد"

    if decision.signal == Signal.SNXX:
        confirmation = "✅ صعود مؤكد — إشارة SNXX نشطة"
    elif decision.signal == Signal.SNDQ:
        confirmation = "✅ هبوط مؤكد — إشارة SNDQ نشطة"
    elif decision.raw_signal == Signal.SNXX:
        confirmation = "⏳ صعود قوي قيد التأكيد — انتظر قبل الدخول"
    elif decision.raw_signal == Signal.SNDQ:
        confirmation = "⏳ هبوط قوي قيد التأكيد — انتظر قبل الدخول"
    else:
        confirmation = "❌ غير مؤكد للدخول — الإشارة الحالية WAIT"
    return direction, confirmation


def _arabic_reason(text: str) -> str:
    replacements = {
        "EMA9 is above EMA21": "المتوسط EMA9 أعلى من EMA21",
        "EMA9 is below EMA21": "المتوسط EMA9 أدنى من EMA21",
        "45-minute momentum is positive": "زخم آخر 45 دقيقة إيجابي",
        "45-minute momentum is negative": "زخم آخر 45 دقيقة سلبي",
        "RSI is overextended": "مؤشر RSI في منطقة تمدد مرتفع",
        "RSI is deeply oversold": "مؤشر RSI في منطقة تشبع بيعي قوي",
        "No recent directional headline catalyst": "لا توجد أخبار حديثة ذات اتجاه واضح",
        "QQQ and SMH context disagree; confidence reduced": "اتجاه QQQ وSMH متعارض؛ الثقة أقل",
        "SNDK volume confirmation is weak": "تأكيد الحجم على SNDK ضعيف",
        "News sources unavailable; technical-only confidence": (
            "مصادر الأخبار غير متاحة؛ الثقة مبنية على التحليل الفني فقط"
        ),
    }
    if text.startswith("Headline tone "):
        return "نبرة الأخبار الحديثة محايدة أو محدودة التأثير"
    if text.startswith("Candidate "):
        return "الإشارة ما زالت تحت التأكيد ولم تكتمل شروطها"
    if text.startswith(("QQQ: ", "SMH: ")):
        ticker, detail = text.split(": ", 1)
        return f"{ticker}: {_arabic_reason(detail)}"
    if text.startswith("Finviz technical signal: "):
        signal = text.removeprefix("Finviz technical signal: ")
        translated = {
            "top gainer": "ضمن الأعلى صعودًا",
            "new high": "قمة سعرية جديدة",
            "top loser": "ضمن الأعلى هبوطًا",
            "new low": "قاع سعري جديد",
        }.get(signal, "إشارة فنية إضافية")
        return f"Finviz: {translated}"
    return replacements.get(text, text)


def format_report(
    decision: SignalDecision,
    news: NewsBundle,
    state: BotState,
    now: datetime,
    mandatory_slot: str | None = None,
    data_basis: str | None = None,
) -> str:
    local = now.astimezone(ZoneInfo("Asia/Riyadh"))
    label = (
        "تحليل فوري بطلب منك"
        if mandatory_slot == "manual"
        else "تقرير إلزامي"
        if mandatory_slot
        else "تغير مؤكد في الإشارة"
    )
    action = {
        Signal.SNXX: "الاتجاه صاعد: يمكن دراسة SNXX فقط بعد مراجعتك الشخصية.",
        Signal.SNDQ: "الاتجاه هابط: يمكن دراسة SNDQ فقط بعد مراجعتك الشخصية.",
        Signal.WAIT: "انتظار: لا يوجد تأكيد كافٍ لاتجاه دخول الآن.",
    }[decision.signal]
    reasons = "\n".join(f"• {_arabic_reason(item)}" for item in decision.reasons[:5])
    reasons = reasons or "• لا توجد عوامل مؤكدة كافية"
    risks = "\n".join(f"• {_arabic_reason(item)}" for item in decision.risks[:4])
    risks = risks or "• مخاطر تذبذب وفجوات سعرية معتادة"
    headlines = "\n".join(f"• {item.title[:110]} ({item.source})" for item in news.items[:3])
    if not headlines:
        headlines = "• لم يتم الحصول على أخبار حديثة؛ خُفّضت درجة الثقة"
    position_labels = {"SNXX": "داخل SNXX", "SNDQ": "داخل SNDQ", None: "لم تؤكد دخولًا"}
    position = position_labels.get(state.confirmed_position, "لم تؤكد دخولًا")
    direction, confirmation = _direction_summary(decision)
    basis = data_basis or "بيانات 15 دقيقة حديثة مع الأخبار الحالية"
    return (
        f"📊 SNDK | {label}\n"
        f"الرياض: {local:%Y-%m-%d %H:%M}\n"
        f"الاتجاه الفني الحالي: {direction} | الدرجة: {decision.score:+.2f}\n"
        f"تأكيد الدخول: {confirmation}\n"
        f"الإشارة المعتمدة: {_arabic_signal(decision.signal)}\n"
        f"التوصية: {action}\n"
        f"حالة مركزك: {position}\n"
        f"أساس التحليل: {basis}\n\n"
        f"العوامل:\n{reasons}\n\nالمخاطر:\n{risks}\n\n"
        f"أحدث الأخبار:\n{headlines}\n\n"
        f"آخر شمعة سوق: {decision.data_timestamp.isoformat()}\n"
        f"المصادر: {decision.source_summary or 'مصدر السوق فقط'}\n\n{DISCLAIMER}"
    )


def format_data_error(message: str, now: datetime, mandatory: bool) -> str:
    local = now.astimezone(ZoneInfo("Asia/Riyadh"))
    kind = "تقرير أمان إلزامي" if mandatory else "تنبيه أمان للبيانات"
    return (
        f"⚠️ SNDK | {kind}\nالرياض: {local:%Y-%m-%d %H:%M}\n"
        "الإشارة: انتظار\n"
        f"السبب: تعذّر الحصول على بيانات سوق حديثة وموثوقة ({message[:260]}).\n"
        f"لا توجد توصية دخول اتجاهية.\n\n{DISCLAIMER}"
    )
