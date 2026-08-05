from __future__ import annotations

from datetime import timedelta

from conftest import make_series

from sndk_bot.models import NewsBundle, NewsItem, Signal
from sndk_bot.signals import apply_hysteresis, decide
from sndk_bot.state import BotState


def aligned_bundle(now, direction: int):
    return {ticker: make_series(ticker, direction, now) for ticker in ("SNDK", "QQQ", "SMH")}


def test_balanced_bullish_entry_is_confirmed_in_one_run(now):
    decision = decide(
        aligned_bundle(now, 1), NewsBundle(sources=["mock"]), BotState(), now, 1, 2.5, 1.5
    )

    assert decision.signal == Signal.SNXX
    assert decision.raw_signal == Signal.SNXX
    assert decision.confirmed is True
    assert any("SNDK 3/4" in reason for reason in decision.reasons)


def test_balanced_bearish_entry_is_confirmed_in_one_run(now):
    decision = decide(
        aligned_bundle(now, -1), NewsBundle(sources=["mock"]), BotState(), now, 1, 2.5, 1.5
    )

    assert decision.signal == Signal.SNDQ
    assert decision.raw_signal == Signal.SNDQ
    assert decision.confirmed is True
    assert decision.score < -2.5


def test_low_volume_blocks_entry_even_when_score_is_strong(now):
    bundle = aligned_bundle(now, 1)
    bundle["SNDK"].frame.loc[bundle["SNDK"].frame.index[-1], "Volume"] = 100_000.0

    decision = decide(bundle, NewsBundle(sources=["mock"]), BotState(), now, 1, 2.5, 1.5)

    assert decision.signal == Signal.WAIT
    assert decision.raw_signal == Signal.WAIT
    assert any("SNDK volume" in risk for risk in decision.risks)


def test_recent_high_impact_news_blocks_new_entry(now):
    news = NewsBundle(
        items=[NewsItem("SNDK earnings results released", "", now - timedelta(hours=1), "mock")],
        sources=["mock"],
    )

    decision = decide(aligned_bundle(now, 1), news, BotState(), now, 1, 2.5, 1.5)

    assert decision.signal == Signal.WAIT
    assert decision.raw_signal == Signal.WAIT
    assert any("high-impact event" in risk for risk in decision.risks)


def test_hysteresis_holds_existing_bullish_signal_above_exit_threshold():
    state = BotState(active_signal="SNXX")
    signal, changed = apply_hysteresis(
        state,
        score=2.0,
        persistence_runs=1,
        enter_threshold=2.5,
        exit_threshold=1.5,
        entry_signal=Signal.WAIT,
        exit_persistence_runs=2,
    )

    assert signal == Signal.SNXX
    assert changed is False


def test_wait_exit_still_requires_two_runs():
    state = BotState(active_signal="SNXX")
    first = apply_hysteresis(
        state, 0.5, 1, 2.5, 1.5, entry_signal=Signal.WAIT, exit_persistence_runs=2
    )
    second = apply_hysteresis(
        state, 0.5, 1, 2.5, 1.5, entry_signal=Signal.WAIT, exit_persistence_runs=2
    )

    assert first == (Signal.SNXX, False)
    assert second == (Signal.WAIT, True)


def test_direction_reversal_also_requires_two_runs():
    state = BotState(active_signal="SNXX")
    first = apply_hysteresis(
        state, -4.0, 1, 2.5, 1.5, entry_signal=Signal.SNDQ, exit_persistence_runs=2
    )
    second = apply_hysteresis(
        state, -4.0, 1, 2.5, 1.5, entry_signal=Signal.SNDQ, exit_persistence_runs=2
    )

    assert first == (Signal.SNXX, False)
    assert second == (Signal.SNDQ, True)
