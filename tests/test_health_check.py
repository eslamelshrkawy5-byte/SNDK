from sndk_bot.telegram import TelegramClient


def test_health_check_validates_credentials_and_sends_exactly_one_message(monkeypatch):
    client = TelegramClient("fake-token", "1210859976")
    calls = []

    def fake_post(method, payload):
        calls.append((method, payload))
        return {"ok": True, "result": True}

    monkeypatch.setattr(client, "_post", fake_post)
    client.health_check()

    assert [method for method, _ in calls] == ["getMe", "sendMessage"]
    send_payload = calls[1][1]
    assert send_payload["chat_id"] == "1210859976"
    assert "CONNECTION TEST" in send_payload["text"]
    assert "No market data" in send_payload["text"]
    assert "reply_markup" not in send_payload
