from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum

import pandas as pd


class Signal(StrEnum):
    SNXX = "SNXX"
    SNDQ = "SNDQ"
    WAIT = "WAIT"


@dataclass(frozen=True)
class MarketSeries:
    ticker: str
    frame: pd.DataFrame
    source: str
    timestamp: datetime


@dataclass(frozen=True)
class NewsItem:
    title: str
    url: str
    published: datetime | None
    source: str
    sentiment: float = 0.0


@dataclass(frozen=True)
class NewsBundle:
    items: list[NewsItem] = field(default_factory=list)
    finviz_snapshot: dict[str, str] = field(default_factory=dict)
    fetched_at: datetime | None = None
    sources: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class SignalDecision:
    signal: Signal
    raw_signal: Signal
    score: float
    reasons: list[str]
    risks: list[str]
    data_timestamp: datetime
    source_summary: str
    confirmed: bool
