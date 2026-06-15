from __future__ import annotations

import json

from src.config.settings import get_settings
from src.infrastructure.notification import NotificationEventType, WahaClient
from src.infrastructure.notification.groq_narrator_client import GroqNarratorClient
from src.services.notification_message_builder import NotificationMessageBuilder
from src.services.notification_narrator_service import NotificationNarratorService


class FakeResponse:
    def __init__(self, payload: dict) -> None:
        self._payload = payload

    def read(self) -> bytes:
        return json.dumps(self._payload).encode("utf-8")

    def __enter__(self) -> "FakeResponse":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        return None


def test_notification_settings_reads_waha_and_groq_env(monkeypatch) -> None:
    monkeypatch.setenv("WAHA_BASE_URL", "https://example-waha.test")
    monkeypatch.setenv("WAHA_API_KEY", "waha-key")
    monkeypatch.setenv("WAHA_DEFAULT_SESSION", "ops-main")
    monkeypatch.setenv("GROQ_SECRET_KEY", "groq-key")
    monkeypatch.setenv("GROQ_MODEL", "llama-test")
    monkeypatch.setenv("NOTIFICATION_AI_MAX_SENTENCES", "2")
    get_settings.cache_clear()

    settings = get_settings()

    assert settings.waha_base_url == "https://example-waha.test"
    assert settings.waha_api_key == "waha-key"
    assert settings.waha_default_session == "ops-main"
    assert settings.groq_secret_key == "groq-key"
    assert settings.groq_model == "llama-test"
    assert settings.notification_ai_max_sentences == 2

    get_settings.cache_clear()


def test_waha_client_send_text_uses_expected_payload() -> None:
    captured: dict[str, object] = {}

    def fake_requester(req, timeout):
        captured["url"] = req.full_url
        captured["timeout"] = timeout
        captured["body"] = json.loads(req.data.decode("utf-8"))
        captured["headers"] = dict(req.header_items())
        return FakeResponse({"id": "msg-1", "status": "queued"})

    client = WahaClient(
        base_url="https://waha.example.com",
        api_key="secret",
        default_session="ops-main",
        requester=fake_requester,
    )

    response = client.send_text_message(chat_id="628123@c.us", text="hello")

    assert captured["url"] == "https://waha.example.com/api/sendText"
    assert captured["timeout"] == 10.0
    assert captured["body"] == {
        "session": "ops-main",
        "chatId": "628123@c.us",
        "text": "hello",
    }
    headers = {str(key).lower(): str(value) for key, value in captured["headers"].items()}
    assert headers["x-api-key"] == "secret"
    assert response["status"] == "queued"


def test_waha_client_get_qr_code_uses_json_accept_header() -> None:
    captured: dict[str, object] = {}

    def fake_requester(req, timeout):
        captured["url"] = req.full_url
        captured["headers"] = dict(req.header_items())
        return FakeResponse({"mimetype": "image/png", "data": "base64-qr"})

    client = WahaClient(
        base_url="https://waha.example.com",
        api_key="secret",
        requester=fake_requester,
    )

    result = client.get_qr_code("ops-main", qr_format="image")

    headers = {str(key).lower(): str(value) for key, value in captured["headers"].items()}
    assert captured["url"] == "https://waha.example.com/api/ops-main/auth/qr?format=image"
    assert headers["accept"] == "application/json"
    assert result.data == "base64-qr"


def test_waha_client_encodes_session_name_for_qr_path() -> None:
    captured: dict[str, object] = {}

    def fake_requester(req, timeout):
        captured["url"] = req.full_url
        return FakeResponse({"value": "raw-qr"})

    client = WahaClient(
        base_url="https://waha.example.com",
        api_key="secret",
        requester=fake_requester,
    )

    result = client.get_qr_code("ops main", qr_format="raw")

    assert captured["url"] == "https://waha.example.com/api/ops%20main/auth/qr?format=raw"
    assert result.value == "raw-qr"


def test_waha_client_rejects_missing_qr_payload_data() -> None:
    def fake_requester(req, timeout):
        return FakeResponse({"mimetype": "image/png"})

    client = WahaClient(
        base_url="https://waha.example.com",
        api_key="secret",
        requester=fake_requester,
    )

    try:
        client.get_qr_code("ops-main", qr_format="image")
    except Exception as exc:
        assert "missing data" in str(exc).lower()
    else:
        raise AssertionError("Expected missing QR data to raise error")


def test_groq_narrator_client_parses_chat_completion() -> None:
    captured: dict[str, object] = {}

    def fake_requester(req, timeout):
        captured["url"] = req.full_url
        captured["timeout"] = timeout
        captured["body"] = json.loads(req.data.decode("utf-8"))
        return FakeResponse({"choices": [{"message": {"content": "Narasi singkat manusiawi."}}]})

    client = GroqNarratorClient(
        base_url="https://api.groq.com/openai/v1",
        api_key="secret",
        model="llama-test",
        requester=fake_requester,
    )

    content = client.generate_narrative(system_prompt="sys", user_prompt="user")

    assert content == "Narasi singkat manusiawi."
    assert captured["url"] == "https://api.groq.com/openai/v1/chat/completions"
    assert captured["body"]["model"] == "llama-test"


def test_groq_narrator_client_requires_non_empty_key() -> None:
    try:
        GroqNarratorClient(base_url="https://api.groq.com/openai/v1", api_key="", model="llama-test")
    except ValueError as exc:
        assert "api_key" in str(exc)
    else:
        raise AssertionError("GroqNarratorClient should reject empty api_key")


def test_notification_narrator_falls_back_when_provider_fails() -> None:
    builder = NotificationMessageBuilder()
    payload = builder.build_payload(
        NotificationEventType.SIGNAL_READY,
        {
            "symbol": "XAUUSD",
            "direction": "BUY",
            "entry_price": 2345.1,
            "stop_loss": 2339.5,
            "take_profit": 2354.8,
            "strategy": "EMA_ATR_TREND",
            "mode": "DRY_RUN",
            "trace_id": "trace-123",
        },
    )

    class BrokenClient:
        def generate_narrative(self, **kwargs):
            raise RuntimeError("provider down")

    narrator = NotificationNarratorService(client=BrokenClient(), enabled=True, max_sentences=3)
    narrative = narrator.narrate(payload)
    rendered = builder.render_message(payload, narrative)

    assert narrative.used_fallback is True
    assert "Sinyal BUY untuk XAUUSD" in rendered.text
    assert "Trace ID: trace-123" in rendered.text


def test_notification_narrator_uses_ai_response_when_available() -> None:
    builder = NotificationMessageBuilder()
    payload = builder.build_payload(
        NotificationEventType.TRADE_OPENED,
        {
            "symbol": "XAUUSD",
            "side": "BUY",
            "lot_size": 0.1,
            "entry_price": 2345.1,
            "stop_loss": 2339.5,
            "take_profit": 2354.8,
            "strategy": "EMA_ATR_TREND",
            "opened_at": "2026-06-15T10:31:02+00:00",
        },
    )

    class HappyClient:
        def generate_narrative(self, **kwargs):
            return "Posisi dibuka dalam kondisi yang sudah tervalidasi oleh sistem."

    narrator = NotificationNarratorService(client=HappyClient(), enabled=True, max_sentences=3)
    narrative = narrator.narrate(payload)
    rendered = builder.render_message(payload, narrative)

    assert narrative.used_fallback is False
    assert "Posisi dibuka dalam kondisi yang sudah tervalidasi oleh sistem." in rendered.text


def test_notification_narrator_uses_fallback_provider_when_ai_returns_empty() -> None:
    builder = NotificationMessageBuilder()
    payload = builder.build_payload(
        NotificationEventType.TRADE_CLOSED,
        {
            "symbol": "XAUUSD",
            "side": "SELL",
            "entry_price": 2340.0,
            "close_price": 2330.0,
            "pnl": 15.5,
        },
    )

    class EmptyClient:
        def generate_narrative(self, **kwargs):
            return ""

    narrator = NotificationNarratorService(client=EmptyClient(), enabled=True, max_sentences=3)
    narrative = narrator.narrate(payload)

    assert narrative.used_fallback is True
    assert narrative.provider == "fallback_template"
    assert "Trade pada XAUUSD sudah ditutup" in narrative.narrative
