from __future__ import annotations

import json
import os
import tempfile
from dataclasses import asdict, dataclass
from pathlib import Path

from .models import Signal


@dataclass
class BotState:
    confirmed_position: str | None = None
    active_signal: str = Signal.WAIT.value
    candidate_signal: str = Signal.WAIT.value
    candidate_count: int = 0
    telegram_update_offset: int = 0
    last_mandatory_1030: str | None = None
    last_mandatory_1115: str | None = None
    last_alert_at: str | None = None
    last_data_timestamp: str | None = None


class StateStore:
    def __init__(self, path: Path):
        self.path = path

    def load(self) -> BotState:
        if not self.path.exists():
            return BotState()
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
            allowed = BotState.__dataclass_fields__.keys()
            return BotState(**{k: v for k, v in payload.items() if k in allowed})
        except (OSError, json.JSONDecodeError, TypeError) as exc:
            raise RuntimeError(f"Cannot read state file {self.path}: {exc}") from exc

    def save(self, state: BotState) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        data = json.dumps(asdict(state), indent=2, sort_keys=True) + "\n"
        fd, temporary = tempfile.mkstemp(dir=self.path.parent, prefix="state-", suffix=".json")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                handle.write(data)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, self.path)
        finally:
            if os.path.exists(temporary):
                os.unlink(temporary)
