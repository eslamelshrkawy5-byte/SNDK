from __future__ import annotations

from sndk_bot.telegram import TelegramClient


def test_poll_confirmation_filters_chat_and_advances_offset(monkeypatch):
    client = TelegramClient("fake-token", "1210859976")
    calls = []

    def fake_post(method, payload):
        calls.append((method, payload))
        if method == "getUpdates":
            return {
                "ok": True,
                "result": [
                    {
                        "update_id": 7,
                        "callback_query": {
                            "id": "a",
                            "data": "CONFIRM_SNXX",
                            "message": {"chat": {"id": 1210859976}},
                        },
                    },
                    {
                        "update_id": 8,
                        "callback_query": {
                            "id": "b",
                            "data": "CONFIRM_SNDQ",
                            "message": {"chat": {"id": 999}},
                        },
                    },
                ],
            }
        return {"ok": True, "result": True}

    monkeypatch.setattr(client, "_post", fake_post)
    confirmations, offset = client.poll_confirmations(0)
    assert [item.position for item in confirmations] == ["SNXX"]
    assert offset == 9
    assert any(method == "answerCallbackQuery" for method, _ in calls)
