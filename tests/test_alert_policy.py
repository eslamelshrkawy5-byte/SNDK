from sndk_bot.main import _should_alert
from sndk_bot.models import Signal


def test_confirmed_position_suppresses_same_direction():
    assert not _should_alert("SNXX", "WAIT", Signal.SNXX, True)


def test_confirmed_position_allows_opposite_and_risk_exit():
    assert _should_alert("SNXX", "SNXX", Signal.SNDQ, True)
    assert _should_alert("SNXX", "SNXX", Signal.WAIT, True)


def test_flat_user_gets_confirmed_change():
    assert _should_alert(None, "WAIT", Signal.SNXX, True)
    assert not _should_alert(None, "SNXX", Signal.SNXX, False)
