from __future__ import annotations

from conftest import make_series

from sndk_bot.models import NewsBundle, Signal
from sndk_bot.signals import apply_hysteresis, decide
from sndk_bot.state import BotState


def test_bullish_requires_two_persistent_runs(now):
    bundle = {ticker: make_series(ticker, 1, now) for ticker in ("SNDK", "QQQ", "SMH")}
    state = BotState()
    first = decide(bundle, NewsBundle(sources=["mock"]), state, now, 2, 3.5, 1.5)
    assert first.signal == Signal.WAIT
    assert first.raw_signal == Signal.SNXX
    second = decide(bundle, NewsBundle(sources=["mock"]), state, now, 2, 3.5, 1.5)
    assert second.signal == Signal.SNXX
    assert second.confirmed is True


def test_bearish_requires_two_persistent_runs(now):
    bundle = {ticker: make_series(ticker, -1, now) for ticker in ("SNDK", "QQQ", "SMH")}
    state = BotState()
    decide(bundle, NewsBundle(sources=["mock"]), state, now, 2, 3.5, 1.5)
    decision = decide(bundle, NewsBundle(sources=["mock"]), state, now, 2, 3.5, 1.5)
    assert decision.signal == Signal.SNDQ
    assert decision.score < -3.5


def test_hysteresis_holds_existing_bullish_signal():
    state = BotState(active_signal="SNXX")
    signal, changed = apply_hysteresis(
        state, score=2.0, persistence_runs=2, enter_threshold=3.5, exit_threshold=1.5
    )
    assert signal == Signal.SNXX
    assert changed is False


def test_wait_exit_also_requires_persistence():
    state = BotState(active_signal="SNXX")
    assert apply_hysteresis(state, 0.5, 2, 3.5, 1.5) == (Signal.SNXX, False)
    assert apply_hysteresis(state, 0.5, 2, 3.5, 1.5) == (Signal.WAIT, True)
