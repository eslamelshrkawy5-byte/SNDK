from __future__ import annotations

import argparse
import logging
import sys
from datetime import UTC, datetime
from zoneinfo import ZoneInfo

from .calendar import change_alerts_enabled, is_us_trading_day, mandatory_slot
from .config import Config, ConfigurationError
from .market import (
    MarketDataError,
    assert_fresh,
    completed_session_bundle,
    fetch_market_bundle,
)
from .models import Signal
from .news import fetch_news
from .report import format_data_error, format_report
from .signals import decide
from .state import StateStore
from .telegram import TelegramClient

LOG = logging.getLogger(__name__)


def _should_alert(position: str | None, old_signal: str, new_signal: Signal, changed: bool) -> bool:
    if not changed:
        return False
    if position == "SNXX":
        return new_signal in {Signal.SNDQ, Signal.WAIT}
    if position == "SNDQ":
        return new_signal in {Signal.SNXX, Signal.WAIT}
    return old_signal != new_signal.value


def run_health_check(config: Config) -> int:
    telegram = TelegramClient(
        config.telegram_bot_token, config.telegram_chat_id, config.request_timeout
    )
    telegram.health_check()
    LOG.info("Telegram connection test succeeded")
    return 0


def run_button_test(config: Config) -> int:
    telegram = TelegramClient(
        config.telegram_bot_token, config.telegram_chat_id, config.request_timeout
    )
    telegram.send_button_test()
    LOG.info("Telegram button test sent")
    return 0


def run(config: Config, now: datetime | None = None) -> int:
    now = now or datetime.now(UTC)
    store = StateStore(config.state_path)
    state = store.load()
    telegram = TelegramClient(
        config.telegram_bot_token, config.telegram_chat_id, config.request_timeout
    )

    confirmations, next_offset = telegram.poll_confirmations(state.telegram_update_offset)
    state.telegram_update_offset = next_offset
    for confirmation in confirmations:
        state.confirmed_position = (
            None if confirmation.position == "EXIT" else confirmation.position
        )
        LOG.info("Saved Telegram confirmation: %s", confirmation.position)

    trading_day = is_us_trading_day(now, config.market_calendar)
    slot = (
        mandatory_slot(
            now,
            config.timezone,
            {"1030": state.last_mandatory_1030, "1115": state.last_mandatory_1115},
        )
        if trading_day
        else None
    )
    if not trading_day:
        store.save(state)
        LOG.info("Not a US exchange session; polling state saved")
        return 0

    old_signal = state.active_signal
    alerts_were_enabled = change_alerts_enabled(now, config.timezone, state.last_mandatory_1115)
    mandatory_sent = False
    try:
        bundle = fetch_market_bundle(config.interval, config.lookback, config.request_timeout, now)
        if slot == "1030":
            bundle, completed_close = completed_session_bundle(bundle, now, config.market_calendar)
            data_basis = (
                "Latest completed US session through "
                f"{completed_close.isoformat()} plus news fetched now"
            )
        else:
            assert_fresh(bundle, now, config.stale_minutes)
            data_basis = "Strictly fresh 15-minute intraday bars plus news fetched now"
        news = fetch_news(config.request_timeout, now)
        decision = decide(
            bundle,
            news,
            state,
            now,
            config.persistence_runs,
            config.enter_threshold,
            config.exit_threshold,
        )
        change_alert = alerts_were_enabled and _should_alert(
            state.confirmed_position, old_signal, decision.signal, decision.confirmed
        )
        send = slot is not None or change_alert
        if send:
            telegram.send(
                format_report(decision, news, state, now, slot, data_basis),
                decision.signal.value,
            )
            mandatory_sent = slot is not None
            state.last_alert_at = now.isoformat()
        state.last_data_timestamp = decision.data_timestamp.isoformat()
    except MarketDataError as exc:
        LOG.error("Market data safety stop: %s", exc)
        risk_exit = (
            alerts_were_enabled
            and state.confirmed_position is not None
            and state.active_signal != Signal.WAIT.value
        )
        should_send = slot is not None or risk_exit
        if should_send:
            telegram.send(format_data_error(str(exc), now, slot is not None))
            mandatory_sent = slot is not None
            state.last_alert_at = now.isoformat()
        state.active_signal = Signal.WAIT.value
        state.candidate_signal = Signal.WAIT.value
        state.candidate_count = 0
    finally:
        local_day = now.astimezone(ZoneInfo(config.timezone)).date().isoformat()
        if mandatory_sent and slot == "1030":
            state.last_mandatory_1030 = local_day
        elif mandatory_sent and slot == "1115":
            state.last_mandatory_1115 = local_day
        store.save(state)
    return 0


def main() -> int:
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s"
    )
    parser = argparse.ArgumentParser(description="SNDK Telegram signal monitor")
    parser.add_argument(
        "--health-check",
        action="store_true",
        help="Validate Telegram and send one connection-test message without market data",
    )
    parser.add_argument(
        "--button-test",
        action="store_true",
        help="Send position-confirmation buttons without fetching market data",
    )
    args = parser.parse_args()
    try:
        config = Config.from_env()
        if args.health_check:
            return run_health_check(config)
        if args.button_test:
            return run_button_test(config)
        return run(config)
    except (ConfigurationError, RuntimeError) as exc:
        LOG.critical("Fatal error: %s", exc)
        return 2


if __name__ == "__main__":
    sys.exit(main())
