from __future__ import annotations

from datetime import datetime

import numpy as np
import pandas as pd

from .models import MarketSeries, NewsBundle, Signal, SignalDecision
from .state import BotState


def _rsi(close: pd.Series, length: int = 14) -> float:
    delta = close.diff()
    gain = delta.clip(lower=0).ewm(alpha=1 / length, adjust=False).mean()
    loss = (-delta.clip(upper=0)).ewm(alpha=1 / length, adjust=False).mean()
    rs = gain / loss.replace(0, np.nan)
    value = 100 - (100 / (1 + rs))
    return float(value.iloc[-1]) if pd.notna(value.iloc[-1]) else 50.0


def _features(series: MarketSeries) -> dict[str, float]:
    frame = series.frame
    if len(frame) < 30:
        raise ValueError(f"At least 30 bars required for {series.ticker}; received {len(frame)}")
    close = frame["Close"].astype(float)
    volume = frame["Volume"].astype(float).fillna(0)
    ema9 = close.ewm(span=9, adjust=False).mean()
    ema21 = close.ewm(span=21, adjust=False).mean()
    ema12 = close.ewm(span=12, adjust=False).mean()
    ema26 = close.ewm(span=26, adjust=False).mean()
    macd = ema12 - ema26
    histogram = macd - macd.ewm(span=9, adjust=False).mean()
    return {
        "close": float(close.iloc[-1]),
        "ema_spread": float((ema9.iloc[-1] / ema21.iloc[-1] - 1) * 100),
        "macd_hist": float(histogram.iloc[-1]),
        "rsi": _rsi(close),
        "momentum": float((close.iloc[-1] / close.iloc[-4] - 1) * 100),
        "volume_ratio": float(volume.iloc[-1] / max(volume.tail(20).median(), 1.0)),
    }


def _ticker_score(features: dict[str, float], weight: float) -> tuple[float, list[str]]:
    score = 0.0
    reasons: list[str] = []
    if features["ema_spread"] > 0.10:
        score += 1.0 * weight
        reasons.append("EMA9 is above EMA21")
    elif features["ema_spread"] < -0.10:
        score -= 1.0 * weight
        reasons.append("EMA9 is below EMA21")
    if features["macd_hist"] > 0:
        score += 0.7 * weight
    elif features["macd_hist"] < 0:
        score -= 0.7 * weight
    if features["momentum"] > 0.20:
        score += 0.8 * weight
        reasons.append("45-minute momentum is positive")
    elif features["momentum"] < -0.20:
        score -= 0.8 * weight
        reasons.append("45-minute momentum is negative")
    if 52 <= features["rsi"] <= 72:
        score += 0.5 * weight
    elif 28 <= features["rsi"] <= 48:
        score -= 0.5 * weight
    elif features["rsi"] > 78:
        score -= 0.3 * weight
        reasons.append("RSI is overextended")
    elif features["rsi"] < 22:
        score += 0.3 * weight
        reasons.append("RSI is deeply oversold")
    return score, reasons


def _news_score(news: NewsBundle, now: datetime) -> tuple[float, list[str]]:
    recent = []
    for item in news.items:
        if item.published is None or (now - item.published).total_seconds() <= 72 * 3600:
            recent.append(item)
    if not recent:
        return 0.0, ["No recent directional headline catalyst"]
    mean = float(np.mean([item.sentiment for item in recent[:20]]))
    score = max(-0.75, min(0.75, mean * 1.5))
    return score, [f"Headline tone {mean:+.2f} across {len(recent[:20])} recent items"]


def calculate_score(
    bundle: dict[str, MarketSeries], news: NewsBundle, now: datetime
) -> tuple[float, list[str], list[str]]:
    sndk = _features(bundle["SNDK"])
    score, reasons = _ticker_score(sndk, 1.0)
    context_votes = []
    for ticker, weight in (("QQQ", 0.55), ("SMH", 0.75)):
        if ticker in bundle:
            component, details = _ticker_score(_features(bundle[ticker]), weight)
            score += component
            context_votes.append(np.sign(component))
            reasons.extend(f"{ticker}: {detail}" for detail in details[:1])
    news_component, news_reasons = _news_score(news, now)
    score += news_component
    reasons.extend(news_reasons)
    finviz_signal = news.finviz_snapshot.get("Signal", "").lower()
    if "top gainer" in finviz_signal or "new high" in finviz_signal:
        score += 0.35
        reasons.append(f"Finviz technical signal: {finviz_signal}")
    elif "top loser" in finviz_signal or "new low" in finviz_signal:
        score -= 0.35
        reasons.append(f"Finviz technical signal: {finviz_signal}")
    risks: list[str] = []
    if len(context_votes) == 2 and context_votes[0] != context_votes[1]:
        score *= 0.75
        risks.append("QQQ and SMH context disagree; confidence reduced")
    if sndk["volume_ratio"] < 0.55:
        score *= 0.80
        risks.append("SNDK volume confirmation is weak")
    if not news.sources:
        risks.append("News sources unavailable; technical-only confidence")
    return round(float(score), 3), reasons[:6], risks


def apply_hysteresis(
    state: BotState,
    score: float,
    persistence_runs: int,
    enter_threshold: float,
    exit_threshold: float,
) -> tuple[Signal, bool]:
    active = Signal(state.active_signal)
    if score >= enter_threshold:
        target = Signal.SNXX
    elif score <= -enter_threshold:
        target = Signal.SNDQ
    elif active == Signal.SNXX and score >= exit_threshold:
        target = Signal.SNXX
    elif active == Signal.SNDQ and score <= -exit_threshold:
        target = Signal.SNDQ
    else:
        target = Signal.WAIT

    if target == active:
        state.candidate_signal = target.value
        state.candidate_count = 0
        return active, False
    if state.candidate_signal == target.value:
        state.candidate_count += 1
    else:
        state.candidate_signal = target.value
        state.candidate_count = 1
    if state.candidate_count >= persistence_runs:
        state.active_signal = target.value
        state.candidate_count = 0
        return target, True
    return active, False


def decide(
    bundle: dict[str, MarketSeries],
    news: NewsBundle,
    state: BotState,
    now: datetime,
    persistence_runs: int,
    enter_threshold: float,
    exit_threshold: float,
) -> SignalDecision:
    score, reasons, risks = calculate_score(bundle, news, now)
    before = Signal(state.active_signal)
    signal, changed = apply_hysteresis(
        state, score, persistence_runs, enter_threshold, exit_threshold
    )
    candidate = Signal(state.candidate_signal)
    timestamps = [item.timestamp for item in bundle.values()]
    source_summary = "; ".join(
        sorted({item.source for item in bundle.values()} | set(news.sources))
    )
    if not changed and signal == before and candidate != signal:
        reasons.append(
            f"Candidate {candidate.value}: {state.candidate_count}/{persistence_runs} confirmations"
        )
    raw = (
        Signal.SNXX
        if score >= enter_threshold
        else Signal.SNDQ
        if score <= -enter_threshold
        else Signal.WAIT
    )
    return SignalDecision(
        signal, raw, score, reasons, risks, min(timestamps), source_summary, changed
    )
