from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

from .models import NewsBundle, Signal, SignalDecision
from .state import BotState

DISCLAIMER = (
    "⚠️ SNXX/SNDQ are daily-reset leveraged/inverse products. Volatility drag and path dependence "
    "can cause rapid losses; they are for short-term tactical use, not buy-and-hold. No trade is "
    "executed. Public-data analysis only—not financial advice."
)


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
        "ON-DEMAND ANALYSIS"
        if mandatory_slot == "manual"
        else "MANDATORY REPORT"
        if mandatory_slot
        else "CONFIRMED STATE CHANGE"
    )
    action = {
        Signal.SNXX: "Bullish SNDK setup → consider SNXX only after your own checks",
        Signal.SNDQ: "Bearish SNDK setup → consider SNDQ only after your own checks",
        Signal.WAIT: "WAIT / explicit risk exit: directional confirmation is insufficient",
    }[decision.signal]
    reasons = "\n".join(f"• {item}" for item in decision.reasons[:5]) or "• No validated factors"
    risks = (
        "\n".join(f"• {item}" for item in decision.risks[:4]) or "• Standard market and gap risk"
    )
    headlines = "\n".join(f"• {item.title[:110]} ({item.source})" for item in news.items[:3])
    if not headlines:
        headlines = "• No fresh headlines retrieved; signal confidence is reduced"
    position = state.confirmed_position or "FLAT / not confirmed"
    basis = data_basis or "Strictly fresh 15-minute intraday bars plus current news"
    return (
        f"📊 SNDK {label}\n"
        f"Riyadh: {local:%Y-%m-%d %H:%M %Z}\n"
        f"Signal: {decision.signal.value} | Score: {decision.score:+.2f}\n"
        f"Action: {action}\n"
        f"Confirmed position: {position}\n"
        f"Data basis: {basis}\n\n"
        f"Factors:\n{reasons}\n\nRisks:\n{risks}\n\n"
        f"Latest headlines:\n{headlines}\n\n"
        f"Market bar timestamp: {decision.data_timestamp.isoformat()}\n"
        f"Sources: {decision.source_summary or 'market source only'}\n\n{DISCLAIMER}"
    )


def format_data_error(message: str, now: datetime, mandatory: bool) -> str:
    local = now.astimezone(ZoneInfo("Asia/Riyadh"))
    kind = "MANDATORY SAFETY REPORT" if mandatory else "DATA RISK EXIT"
    return (
        f"⚠️ SNDK {kind}\nRiyadh: {local:%Y-%m-%d %H:%M %Z}\n"
        f"Signal: WAIT\nReason: {message}\nNo directional trade signal is issued.\n\n{DISCLAIMER}"
    )
