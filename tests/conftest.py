from __future__ import annotations

from datetime import UTC, datetime

import numpy as np
import pandas as pd
import pytest

from sndk_bot.models import MarketSeries


@pytest.fixture
def now() -> datetime:
    return datetime(2026, 8, 5, 8, 15, tzinfo=UTC)


def make_series(ticker: str, direction: int, now: datetime, bars: int = 60) -> MarketSeries:
    index = pd.date_range(end=now, periods=bars, freq="15min", tz="UTC")
    base = np.linspace(100, 110 if direction > 0 else 90, bars)
    close = base + np.sin(np.arange(bars) / 4) * 0.05
    frame = pd.DataFrame(
        {
            "Open": close - direction * 0.05,
            "High": close + 0.15,
            "Low": close - 0.15,
            "Close": close,
            "Volume": np.full(bars, 1_000_000.0),
        },
        index=index,
    )
    return MarketSeries(ticker, frame, "mock", now)
