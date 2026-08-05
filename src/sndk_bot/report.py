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
        Signal.SNXX: "SNXX — إشارة صعود نشطة",
        Signal.SNDQ: "SNDQ — إشارة هبوط نشطة",
        Signal.WAIT: "WAIT — لا توجد إشارة دخول مؤكدة",
    }
    return labels[signal]


def _direction_summary(
    decision: SignalDecision,
    state: BotState,
    enter_threshold: float,
    confirmation_required: int,
) -> tuple[str, str, str]:
    if decision.score >= enter_threshold:
        direction = "🟢 صاعد قوي"
    elif decision.score >= 1.5:
        direction = "🟡 ميل صاعد غير مؤكد"
    elif decision.score <= -enter_threshold:
        direction = "🔴 هابط قوي"
    elif decision.score <= -1.5:
        direction = "🟠 ميل هابط غير مؤكد"
    else:
        direction = "⚪ محايد"

    if decision.raw_signal == Signal.SNXX and decision.signal == Signal.SNXX:
        confirmation = f"✅ {confirmation_required}/{confirmation_required} — صعود مؤكد"
    elif decision.raw_signal == Signal.SNDQ and decision.signal == Signal.SNDQ:
        confirmation = f"✅ {confirmation_required}/{confirmation_required} — هبوط مؤكد"
    elif decision.raw_signal == Signal.SNXX:
        count = min(state.candidate_count, confirmation_required)
        confirmation = f"⏳ {count}/{confirmation_required} — صعود قيد التأكيد"
    elif decision.raw_signal == Signal.SNDQ:
        count = min(state.candidate_count, confirmation_required)
        confirmation = f"⏳ {count}/{confirmation_required} — هبوط قيد التأكيد"
    else:
        confirmation = f"❌ 0/{confirmation_required} — شروط الدخول غير مكتملة"

    current_snxx = decision.signal == Signal.SNXX and decision.raw_signal == Signal.SNXX
    current_sndq = decision.signal == Signal.SNDQ and decision.raw_signal == Signal.SNDQ
    if state.confirmed_position == "SNXX":
        if decision.signal == Signal.SNXX:
            decision_now = "🟢 استمر في SNXX"
        elif current_sndq:
            decision_now = "🔴 اخرج من SNXX؛ الانعكاس إلى SNDQ مؤكد"
        else:
            decision_now = "🟠 اخرج من SNXX الآن؛ شرط الخروج/WAIT مؤكد"
    elif state.confirmed_position == "SNDQ":
        if decision.signal == Signal.SNDQ:
            decision_now = "🔴 استمر في SNDQ"
        elif current_snxx:
            decision_now = "🟢 اخرج من SNDQ؛ الانعكاس إلى SNXX مؤكد"
        else:
            decision_now = "🟠 اخرج من SNDQ الآن؛ شرط الخروج/WAIT مؤكد"
    elif current_snxx:
        decision_now = "🟢 ادخل SNXX"
    elif current_sndq:
        decision_now = "🔴 ادخل SNDQ"
    elif decision.raw_signal == Signal.SNXX:
        decision_now = "⛔ لا تدخل الآن؛ انتظر اكتمال تأكيد الصعود"
    elif decision.raw_signal == Signal.SNDQ:
        decision_now = "⛔ لا تدخل الآن؛ انتظر اكتمال تأكيد الهبوط"
    else:
        decision_now = "⛔ لا تدخل SNXX أو SNDQ الآن"
    return direction, confirmation, decision_now


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
    if text.startswith("Balanced entry gate passed: "):
        details = text.removeprefix("Balanced entry gate passed: ")
        return f"اكتملت بوابة الدخول المتوازن: {details}"
    if text.startswith("Strong entry gate passed: "):
        details = text.removeprefix("Strong entry gate passed: ")
        return f"اكتمل مسار الدخول القوي: {details}"
    if text.startswith("Entry blocked by high-impact event: "):
        event = text.removeprefix("Entry blocked by high-impact event: ")
        return f"مُنع دخول جديد مؤقتًا بسبب حدث حديث عالي التأثير: {event}"
    if text.startswith("Entry blocked: "):
        details = text.removeprefix("Entry blocked: ")
        details = details.replace("SNDK direction votes", "أصوات اتجاه SNDK")
        details = details.replace("QQQ/SMH market support", "دعم اتجاهي من QQQ أو SMH")
        details = details.replace("SNDK volume", "حجم SNDK")
        return f"شروط الدخول غير مكتملة: {details}"
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
    enter_threshold: float = 2.5,
    confirmation_required: int = 1,
    strong_enter_threshold: float = 3.5,
    min_sndk_votes: int = 3,
    min_volume_ratio: float = 0.8,
    exit_threshold: float = 1.5,
    exit_confirmation_required: int = 2,
) -> str:
    local = now.astimezone(ZoneInfo("Asia/Riyadh"))
    label = (
        "تحليل فوري بطلب منك"
        if mandatory_slot == "manual"
        else "تقرير إلزامي"
        if mandatory_slot
        else "تغير مؤكد في الإشارة"
    )
    new_entry_signal = (
        decision.signal if decision.signal == decision.raw_signal else Signal.WAIT
    )
    if state.confirmed_position:
        action = "إدارة المركز القائم حسب القرار المباشر أعلاه؛ لا تفتح مركزًا إضافيًا."
    else:
        action = {
            Signal.SNXX: "الاتجاه الصاعد مكتمل الفلاتر: يمكن دراسة SNXX بعد مراجعتك الشخصية.",
            Signal.SNDQ: "الاتجاه الهابط مكتمل الفلاتر: يمكن دراسة SNDQ بعد مراجعتك الشخصية.",
            Signal.WAIT: "انتظار: لا يوجد تأكيد كافٍ لدخول جديد الآن.",
        }[new_entry_signal]
    reasons = "\n".join(f"• {_arabic_reason(item)}" for item in decision.reasons[:5])
    reasons = reasons or "• لا توجد عوامل مؤكدة كافية"
    risks = "\n".join(f"• {_arabic_reason(item)}" for item in decision.risks[:4])
    risks = risks or "• مخاطر تذبذب وفجوات سعرية معتادة"
    headlines = "\n".join(f"• {item.title[:110]} ({item.source})" for item in news.items[:3])
    if not headlines:
        headlines = "• لم يتم الحصول على أخبار حديثة؛ خُفّضت درجة الثقة"
    position_labels = {"SNXX": "داخل SNXX", "SNDQ": "داخل SNDQ", None: "لم تؤكد دخولًا"}
    position = position_labels.get(state.confirmed_position, "لم تؤكد دخولًا")
    direction, confirmation, decision_now = _direction_summary(
        decision, state, enter_threshold, confirmation_required
    )
    basis = data_basis or "بيانات 15 دقيقة حديثة مع الأخبار الحالية"
    return (
        f"📊 SNDK | {label}\n"
        f"الرياض: {local:%Y-%m-%d %H:%M}\n"
        f"الاتجاه الفني الحالي: {direction} | الدرجة: {decision.score:+.2f}\n"
        f"تأكيد الدخول: {confirmation}\n"
        f"القرار الآن: {decision_now}\n"
        f"قاعدة الدخول المتوازن: ±{enter_threshold:.1f} بتأكيد واحد؛ "
        f"{min_sndk_votes}/4 من مؤشرات SNDK + دعم QQQ أو SMH + "
        f"حجم SNDK ≥ {min_volume_ratio:.1f}× + شمعة 15 دقيقة مكتملة\n"
        f"المسار القوي: |الدرجة| ≥ {strong_enter_threshold:.1f} مع توافق SNDK وSMH والحجم\n"
        f"قاعدة الخروج: ±{exit_threshold:.1f} مع "
        f"{exit_confirmation_required} تحليلين متتاليين\n"
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
