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


def _direction_votes(features: dict[str, float]) -> tuple[int, int]:
    bullish = sum(
        (
            features["ema_spread"] > 0.10,
            features["macd_hist"] > 0,
            features["momentum"] > 0.20,
            52 <= features["rsi"] <= 72,
        )
    )
    bearish = sum(
        (
            features["ema_spread"] < -0.10,
            features["macd_hist"] < 0,
            features["momentum"] < -0.20,
            28 <= features["rsi"] <= 48,
        )
    )
    return bullish, bearish


def _recent_high_impact_event(news: NewsBundle, now: datetime) -> str | None:
    keywords = {
        "earnings",
        "guidance",
        "fomc",
        "federal reserve",
        "cpi",
        "inflation report",
        "jobs report",
        "nonfarm payroll",
        "sec investigation",
        "bankruptcy",
        "share offering",
        "acquisition",
        "merger",
    }
    for item in news.items:
        if item.published is None:
            continue
        age_seconds = (now - item.published).total_seconds()
        if 0 <= age_seconds <= 6 * 3600:
            title = item.title.lower()
            if any(keyword in title for keyword in keywords):
                return item.title[:110]
    return None


def _balanced_entry_signal(
    bundle: dict[str, MarketSeries],
    news: NewsBundle,
    now: datetime,
    score: float,
    enter_threshold: float,
    strong_enter_threshold: float,
    min_sndk_votes: int,
    min_volume_ratio: float,
) -> tuple[Signal, list[str], list[str]]:
    if score >= enter_threshold:
        target = Signal.SNXX
        direction = 1
    elif score <= -enter_threshold:
        target = Signal.SNDQ
        direction = -1
    else:
        return Signal.WAIT, [], []

    high_impact_event = _recent_high_impact_event(news, now)
    if high_impact_event:
        return Signal.WAIT, [], [f"Entry blocked by high-impact event: {high_impact_event}"]

    sndk = _features(bundle["SNDK"])
    bullish_votes, bearish_votes = _direction_votes(sndk)
    directional_votes = bullish_votes if direction > 0 else bearish_votes
    sndk_component, _ = _ticker_score(sndk, 1.0)
    context_components = {
        ticker: _ticker_score(_features(bundle[ticker]), 1.0)[0]
        for ticker in ("QQQ", "SMH")
        if ticker in bundle
    }
    market_support = any(component * direction > 0 for component in context_components.values())
    volume_ok = sndk["volume_ratio"] >= min_volume_ratio

    regular_entry = directional_votes >= min_sndk_votes and market_support and volume_ok
    strong_entry = (
        abs(score) >= strong_enter_threshold
        and sndk_component * direction > 0
        and context_components.get("SMH", 0.0) * direction > 0
        and volume_ok
    )
    if regular_entry or strong_entry:
        mode = "strong" if strong_entry and not regular_entry else "balanced"
        return (
            target,
            [
                f"{mode.title()} entry gate passed: SNDK {directional_votes}/4; "
                f"volume {sndk['volume_ratio']:.2f}x"
            ],
            [],
        )

    missing: list[str] = []
    if directional_votes < min_sndk_votes and not strong_entry:
        missing.append(f"SNDK direction votes {directional_votes}/4")
    if not market_support and not strong_entry:
        missing.append("QQQ/SMH market support")
    if not volume_ok:
        missing.append(f"SNDK volume {sndk['volume_ratio']:.2f}x")
    return Signal.WAIT, [], ["Entry blocked: " + "; ".join(missing)]


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
    entry_signal: Signal | None = None,
    exit_persistence_runs: int | None = None,
) -> tuple[Signal, bool]:
    active = Signal(state.active_signal)
    if entry_signal is None:
        entry_signal = (
            Signal.SNXX
            if score >= enter_threshold
            else Signal.SNDQ
            if score <= -enter_threshold
            else Signal.WAIT
        )
    if entry_signal != Signal.WAIT:
        target = entry_signal
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
    required_runs = (
        exit_persistence_runs
        if active != Signal.WAIT and target != active and exit_persistence_runs is not None
        else persistence_runs
    )
    if state.candidate_count >= required_runs:
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
    strong_enter_threshold: float = 3.5,
    min_sndk_votes: int = 3,
    min_volume_ratio: float = 0.8,
    exit_persistence_runs: int = 2,
) -> SignalDecision:
    score, reasons, risks = calculate_score(bundle, news, now)
    raw, gate_reasons, gate_risks = _balanced_entry_signal(
        bundle,
        news,
        now,
        score,
        enter_threshold,
        strong_enter_threshold,
        min_sndk_votes,
        min_volume_ratio,
    )
    reasons.extend(gate_reasons)
    risks.extend(gate_risks)
    before = Signal(state.active_signal)
    signal, changed = apply_hysteresis(
        state,
        score,
        persistence_runs,
        enter_threshold,
        exit_threshold,
        entry_signal=raw,
        exit_persistence_runs=exit_persistence_runs,
    )
    candidate = Signal(state.candidate_signal)
    timestamps = [item.timestamp for item in bundle.values()]
    source_summary = "; ".join(
        sorted({item.source for item in bundle.values()} | set(news.sources))
    )
    if not changed and signal == before and candidate != signal:
        required = exit_persistence_runs if before != Signal.WAIT else persistence_runs
        reasons.append(
            f"Candidate {candidate.value}: {state.candidate_count}/{required} confirmations"
        )
    return SignalDecision(
        signal, raw, score, reasons[:8], risks[:6], min(timestamps), source_summary, changed
    )
