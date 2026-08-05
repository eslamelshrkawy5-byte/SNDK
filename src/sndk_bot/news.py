from __future__ import annotations

import logging
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime

import feedparser
import requests
from bs4 import BeautifulSoup

from .models import NewsBundle, NewsItem

LOG = logging.getLogger(__name__)
POSITIVE = {
    "beat",
    "growth",
    "upgrade",
    "raises",
    "record",
    "strong",
    "surge",
    "approval",
    "expands",
}
NEGATIVE = {"miss", "downgrade", "cuts", "weak", "decline", "lawsuit", "probe", "warning", "falls"}
RSS_FEEDS = (
    (
        "Google News RSS",
        "https://news.google.com/rss/search?q=SNDK+OR+SanDisk&hl=en-US&gl=US&ceid=US:en",
    ),
    (
        "SEC company filings",
        "https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&CIK=0002023554&type=&dateb=&owner=exclude&count=20&output=atom",
    ),
)


def headline_sentiment(title: str) -> float:
    words = {token.strip(".,:;!?()[]\"'").lower() for token in title.split()}
    return max(-1.0, min(1.0, (len(words & POSITIVE) - len(words & NEGATIVE)) / 3))


def _published(entry: dict) -> datetime | None:
    raw = entry.get("published") or entry.get("updated")
    if not raw:
        return None
    try:
        value = parsedate_to_datetime(raw)
        return value.replace(tzinfo=value.tzinfo or UTC).astimezone(UTC)
    except (TypeError, ValueError, OverflowError):
        return None


def fetch_finviz(timeout: int) -> tuple[dict[str, str], list[NewsItem]]:
    url = "https://finviz.com/quote.ashx?t=SNDK&p=d"
    response = requests.get(
        url, timeout=timeout, headers={"User-Agent": "Mozilla/5.0 sndk-monitor/1.0"}
    )
    response.raise_for_status()
    soup = BeautifulSoup(response.text, "html.parser")
    snapshot: dict[str, str] = {}
    table = soup.select_one("table.snapshot-table2")
    if table:
        cells = [cell.get_text(" ", strip=True) for cell in table.select("td")]
        snapshot = dict(zip(cells[0::2], cells[1::2], strict=False))
    items: list[NewsItem] = []
    for row in soup.select("table.fullview-news-outer tr")[:20]:
        link = row.select_one("a")
        if link:
            title = link.get_text(" ", strip=True)
            items.append(
                NewsItem(title, link.get("href", ""), None, "Finviz", headline_sentiment(title))
            )
    return snapshot, items


def fetch_rss(name: str, url: str, timeout: int) -> list[NewsItem]:
    response = requests.get(
        url, timeout=timeout, headers={"User-Agent": "sndk-monitor/1.0 contact@example.invalid"}
    )
    response.raise_for_status()
    feed = feedparser.loads(response.content)
    if feed.bozo and not feed.entries:
        raise RuntimeError(f"Invalid feed from {name}")
    return [
        NewsItem(
            title=entry.get("title", "Untitled"),
            url=entry.get("link", ""),
            published=_published(entry),
            source=name,
            sentiment=headline_sentiment(entry.get("title", "")),
        )
        for entry in feed.entries[:20]
    ]


def fetch_news(timeout: int, now: datetime) -> NewsBundle:
    sources: list[str] = []
    items: list[NewsItem] = []
    snapshot: dict[str, str] = {}
    try:
        snapshot, finviz_items = fetch_finviz(timeout)
        items.extend(finviz_items)
        sources.append("Finviz")
    except Exception as exc:
        LOG.warning("Finviz unavailable: %s", exc)
    for name, url in RSS_FEEDS:
        try:
            items.extend(fetch_rss(name, url, timeout))
            sources.append(name)
        except Exception as exc:
            LOG.warning("RSS source unavailable (%s): %s", name, exc)
    unique: dict[tuple[str, str], NewsItem] = {(item.title, item.url): item for item in items}
    return NewsBundle(list(unique.values()), snapshot, now, sources)
