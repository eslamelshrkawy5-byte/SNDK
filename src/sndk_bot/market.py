from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta

import pandas as pd
import requests
import yfinance as yf

from .calendar import latest_completed_session_close
from .models import MarketSeries

LOG = logging.getLogger(__name__)
REQUIRED_COLUMNS = {"Open", "High", "Low", "Close", "Volume"}


class MarketDataError(RuntimeError):
    """Raised when no safe market-data source is available."""


def _normalize(frame: pd.DataFrame, ticker: str, now: datetime) -> MarketSeries:
    if frame.empty:
        raise MarketDataError(f"No data returned for {ticker}")
    if isinstance(frame.columns, pd.MultiIndex):
        frame.columns = frame.columns.get_level_values(0)
    missing = REQUIRED_COLUMNS.difference(frame.columns)
    if missing:
        raise MarketDataError(f"Missing columns for {ticker}: {sorted(missing)}")
    frame = frame[list(REQUIRED_COLUMNS)].copy().sort_index()
    frame = frame[~frame.index.duplicated(keep="last")].dropna(subset=["Close"])
    index = pd.to_datetime(frame.index, utc=True)
    frame.index = index
    timestamp = index[-1].to_pydatetime()
    return MarketSeries(
        ticker=ticker, frame=frame, source="Yahoo Finance/yfinance", timestamp=timestamp
    )


def _yahoo_chart(ticker: str, timeout: int, now: datetime) -> MarketSeries:
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{ticker}"
    params = {"interval": "15m", "range": "10d", "includePrePost": "true"}
    response = requests.get(
        url, params=params, timeout=timeout, headers={"User-Agent": "Mozilla/5.0"}
    )
    response.raise_for_status()
    result = response.json()["chart"]["result"][0]
    quote = result["indicators"]["quote"][0]
    frame = pd.DataFrame(quote, index=pd.to_datetime(result["timestamp"], unit="s", utc=True))
    frame.columns = [name.title() for name in frame.columns]
    series = _normalize(frame, ticker, now)
    return MarketSeries(
        ticker=ticker,
        frame=series.frame,
        source="Yahoo Finance chart API",
        timestamp=series.timestamp,
    )


def fetch_series(
    ticker: str, interval: str, lookback: str, timeout: int, now: datetime
) -> MarketSeries:
    try:
        frame = yf.download(
            ticker,
            period=lookback,
            interval=interval,
            prepost=True,
            progress=False,
            auto_adjust=False,
            threads=False,
            timeout=timeout,
        )
        return _normalize(frame, ticker, now)
    except Exception as first_error:  # library/network failure; fallback is deliberate
        LOG.warning("yfinance failed for %s: %s", ticker, first_error)
        try:
            return _yahoo_chart(ticker, timeout, now)
        except Exception as second_error:
            message = (
                f"Both free sources failed for {ticker}: "
                f"yfinance={first_error}; chart={second_error}"
            )
            raise MarketDataError(message) from second_error


def fetch_market_bundle(
    interval: str, lookback: str, timeout: int, now: datetime
) -> dict[str, MarketSeries]:
    result: dict[str, MarketSeries] = {}
    failures: dict[str, str] = {}
    for ticker in ("SNDK", "QQQ", "SMH"):
        try:
            result[ticker] = fetch_series(ticker, interval, lookback, timeout, now)
        except MarketDataError as exc:
            failures[ticker] = str(exc)
    if "SNDK" not in result:
        raise MarketDataError(f"SNDK data unavailable; refusing to signal. {failures.get('SNDK')}")
    if len(result) < 2:
        raise MarketDataError(f"Insufficient market context; refusing to signal. {failures}")
    return result


def assert_fresh(bundle: dict[str, MarketSeries], now: datetime, stale_minutes: int) -> None:
    limit = timedelta(minutes=stale_minutes)
    stale = [
        f"{ticker} ({series.timestamp.isoformat()})"
        for ticker, series in bundle.items()
        if now.astimezone(UTC) - series.timestamp.astimezone(UTC) > limit
    ]
    if stale:
        raise MarketDataError("Stale market data; no directional alert: " + ", ".join(stale))


def completed_session_bundle(
    bundle: dict[str, MarketSeries], now: datetime, calendar_name: str
) -> tuple[dict[str, MarketSeries], datetime]:
    """Trim all inputs to the latest completed session and reject incomplete coverage."""
    completed_close = latest_completed_session_close(now, calendar_name)
    earliest_acceptable = completed_close - timedelta(minutes=60)
    prepared: dict[str, MarketSeries] = {}
    missing: list[str] = []
    for ticker, series in bundle.items():
        frame = series.frame.loc[series.frame.index <= completed_close].copy()
        if frame.empty:
            missing.append(f"{ticker} (no bars through {completed_close.isoformat()})")
            continue
        timestamp = frame.index[-1].to_pydatetime()
        if timestamp < earliest_acceptable:
            missing.append(f"{ticker} ({timestamp.isoformat()})")
            continue
        prepared[ticker] = MarketSeries(ticker, frame, series.source, timestamp)
    if missing:
        raise MarketDataError(
            "Latest completed-session data unavailable; no directional alert: " + ", ".join(missing)
        )
    return prepared, completed_close
