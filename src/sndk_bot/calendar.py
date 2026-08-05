from __future__ import annotations

from datetime import UTC, datetime, time, timedelta
from zoneinfo import ZoneInfo

import exchange_calendars as xcals

MANDATORY_WINDOWS = {
    "1030": (time(10, 30), time(10, 44, 59)),
    "1115": (time(11, 15), time(11, 29, 59)),
}


def riyadh_date(now: datetime, timezone: str = "Asia/Riyadh") -> str:
    return now.astimezone(ZoneInfo(timezone)).date().isoformat()


def is_us_trading_day(now: datetime, calendar_name: str = "XNYS") -> bool:
    local_day = now.astimezone(ZoneInfo("America/New_York")).date()
    calendar = xcals.get_calendar(calendar_name)
    return bool(calendar.is_session(local_day))


def latest_completed_session_close(now: datetime, calendar_name: str = "XNYS") -> datetime:
    """Return the close of the most recent fully completed exchange session."""
    calendar = xcals.get_calendar(calendar_name)
    start = (now.astimezone(UTC) - timedelta(days=14)).date()
    end = now.astimezone(UTC).date()
    sessions = calendar.sessions_in_range(start, end)
    completed = [calendar.session_close(session) for session in sessions]
    completed = [value.to_pydatetime() for value in completed if value.to_pydatetime() <= now]
    if not completed:
        raise RuntimeError("No completed US exchange session found in the prior 14 days")
    return max(completed)


def mandatory_slot(now: datetime, timezone: str, state_dates: dict[str, str | None]) -> str | None:
    local = now.astimezone(ZoneInfo(timezone))
    day = local.date().isoformat()
    for slot, (start, end) in MANDATORY_WINDOWS.items():
        if start <= local.time().replace(tzinfo=None) <= end and state_dates.get(slot) != day:
            return slot
    return None


def change_alerts_enabled(now: datetime, timezone: str, last_1115: str | None) -> bool:
    """Only enable non-mandatory changes after today's 11:15 report was delivered."""
    return last_1115 == riyadh_date(now, timezone)
