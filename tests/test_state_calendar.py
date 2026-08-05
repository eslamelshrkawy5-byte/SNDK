from __future__ import annotations

from datetime import UTC, datetime

from sndk_bot.calendar import mandatory_slot
from sndk_bot.state import BotState, StateStore


def test_atomic_state_roundtrip(tmp_path):
    path = tmp_path / "nested" / "state.json"
    store = StateStore(path)
    state = BotState(confirmed_position="SNXX", telegram_update_offset=42)
    store.save(state)
    loaded = store.load()
    assert loaded.confirmed_position == "SNXX"
    assert loaded.telegram_update_offset == 42


def test_mandatory_1030_riyadh_once_per_day():
    now = datetime(2026, 8, 5, 7, 30, tzinfo=UTC)
    assert mandatory_slot(now, "Asia/Riyadh", {"1030": None, "1115": None}) == "1030"
    assert mandatory_slot(now, "Asia/Riyadh", {"1030": "2026-08-05", "1115": None}) is None


def test_mandatory_1115_riyadh():
    now = datetime(2026, 8, 5, 8, 15, tzinfo=UTC)
    assert mandatory_slot(now, "Asia/Riyadh", {"1030": None, "1115": None}) == "1115"
