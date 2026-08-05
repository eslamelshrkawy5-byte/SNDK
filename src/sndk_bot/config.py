from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


class ConfigurationError(RuntimeError):
    """Raised when required runtime configuration is invalid."""


@dataclass(frozen=True)
class Config:
    telegram_bot_token: str
    telegram_chat_id: str
    state_path: Path
    timezone: str = "Asia/Riyadh"
    market_calendar: str = "XNYS"
    interval: str = "15m"
    lookback: str = "10d"
    stale_minutes: int = 45
    persistence_runs: int = 2
    enter_threshold: float = 3.5
    exit_threshold: float = 1.5
    request_timeout: int = 20

    @classmethod
    def from_env(cls) -> Config:
        token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
        chat_id = os.getenv("TELEGRAM_CHAT_ID", "").strip()
        if not token:
            raise ConfigurationError("TELEGRAM_BOT_TOKEN is required")
        if not chat_id:
            raise ConfigurationError("TELEGRAM_CHAT_ID is required")
        if not chat_id.lstrip("-").isdigit():
            raise ConfigurationError("TELEGRAM_CHAT_ID must be numeric")
        return cls(
            telegram_bot_token=token,
            telegram_chat_id=chat_id,
            state_path=Path(os.getenv("STATE_PATH", "data/state.json")),
        )
