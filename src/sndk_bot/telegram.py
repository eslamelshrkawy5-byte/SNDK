from __future__ import annotations

import logging
from dataclasses import dataclass

import requests

LOG = logging.getLogger(__name__)


class TelegramError(RuntimeError):
    """Raised for Telegram API failures."""


@dataclass(frozen=True)
class Confirmation:
    update_id: int
    position: str
    callback_query_id: str


class TelegramClient:
    def __init__(self, token: str, chat_id: str, timeout: int = 20):
        self.base = f"https://api.telegram.org/bot{token}"
        self.chat_id = str(chat_id)
        self.timeout = timeout

    def _post(self, method: str, payload: dict) -> dict:
        response = requests.post(f"{self.base}/{method}", json=payload, timeout=self.timeout)
        response.raise_for_status()
        body = response.json()
        if not body.get("ok"):
            raise TelegramError(
                f"Telegram {method} failed: {body.get('description', 'unknown error')}"
            )
        return body

    def poll_confirmations(self, offset: int) -> tuple[list[Confirmation], int]:
        body = self._post(
            "getUpdates", {"offset": offset, "timeout": 0, "allowed_updates": ["callback_query"]}
        )
        confirmations: list[Confirmation] = []
        next_offset = offset
        for update in body.get("result", []):
            update_id = int(update["update_id"])
            next_offset = max(next_offset, update_id + 1)
            callback = update.get("callback_query") or {}
            message = callback.get("message") or {}
            chat = (message.get("chat") or {}).get("id")
            data = callback.get("data", "")
            if str(chat) == self.chat_id and data in {
                "CONFIRM_SNXX",
                "CONFIRM_SNDQ",
                "CONFIRM_EXIT",
            }:
                confirmations.append(
                    Confirmation(update_id, data.removeprefix("CONFIRM_"), callback["id"])
                )
            if callback.get("id"):
                self._post(
                    "answerCallbackQuery",
                    {"callback_query_id": callback["id"], "text": "تم حفظ حالة المركز"},
                )
        return confirmations, next_offset

    def health_check(self) -> None:
        """Validate credentials and send exactly one market-independent test message."""
        self._post("getMe", {})
        self.send(
            "✅ اختبار اتصال بوت SNDK\n"
            "بيانات Telegram صحيحة والإرسال يعمل. لم يتم طلب بيانات سوق ولم يتم تنفيذ أي صفقة."
        )

    def send_button_test(self) -> None:
        """Send all position buttons for an explicit interaction test."""
        self._post("getMe", {})
        self._post(
            "sendMessage",
            {
                "chat_id": self.chat_id,
                "text": (
                    "🧪 اختبار أزرار بوت SNDK\n"
                    "اختر أحد الأزرار لتجربة تأكيد حالة المركز. هذا اختبار فقط ولا ينفّذ أي صفقة."
                ),
                "disable_web_page_preview": True,
                "reply_markup": {
                    "inline_keyboard": [
                        [{"text": "✅ أكّد دخول SNXX", "callback_data": "CONFIRM_SNXX"}],
                        [{"text": "✅ أكّد دخول SNDQ", "callback_data": "CONFIRM_SNDQ"}],
                        [{"text": "⬜ أنا خارج المركز", "callback_data": "CONFIRM_EXIT"}],
                    ]
                },
            },
        )

    def send(self, text: str, signal: str | None = None) -> None:
        """Send an Arabic report plus position-confirmation buttons on every analysis."""
        payload: dict = {"chat_id": self.chat_id, "text": text, "disable_web_page_preview": True}
        payload["reply_markup"] = {
            "inline_keyboard": [
                [{"text": "✅ دخلت SNXX", "callback_data": "CONFIRM_SNXX"}],
                [{"text": "✅ دخلت SNDQ", "callback_data": "CONFIRM_SNDQ"}],
                [{"text": "⬜ لم أدخل / خرجت من المركز", "callback_data": "CONFIRM_EXIT"}],
            ]
        }
        self._post("sendMessage", payload)
