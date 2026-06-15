"""WAHA HTTP client foundation for WhatsApp delivery."""

from __future__ import annotations

import json
from collections.abc import Callable, Mapping
from typing import Any
from urllib import error, request
from urllib.parse import quote, urlencode

from src.infrastructure.notification.models import WhatsappQrCodeResult, WhatsappSessionInfo


class WahaClientError(RuntimeError):
    """Raised when WAHA request fails."""

    def __init__(self, message: str, *, status_code: int | None = None, response_body: str | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.response_body = response_body


RequestCallable = Callable[[request.Request, float], Any]


class WahaClient:
    """Small WAHA API client for health checks and text delivery."""

    def __init__(
        self,
        *,
        base_url: str,
        api_key: str,
        default_session: str = "default",
        timeout_seconds: float = 10.0,
        requester: RequestCallable | None = None,
    ) -> None:
        normalized_base_url = base_url.strip().rstrip("/")
        if not normalized_base_url:
            raise ValueError("waha base_url must be provided")
        if timeout_seconds <= 0:
            raise ValueError("waha timeout_seconds must be greater than zero")

        self.base_url = normalized_base_url
        self.api_key = api_key.strip()
        self.default_session = default_session.strip() or "default"
        self.timeout_seconds = timeout_seconds
        self._requester = requester or request.urlopen

    def _build_headers(self) -> dict[str, str]:
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json",
            "User-Agent": "Mozilla/5.0 (compatible; MT5Automation/1.0; +https://trading-api.lalapan.online)",
        }
        if self.api_key:
            headers["X-Api-Key"] = self.api_key
        return headers

    @staticmethod
    def _escape_session_name(session_name: str) -> str:
        normalized = session_name.strip()
        if not normalized:
            raise ValueError("session_name must be provided")
        return quote(normalized, safe="")

    def _request_json(
        self,
        method: str,
        path: str,
        payload: Mapping[str, Any] | None = None,
        *,
        query_params: Mapping[str, Any] | None = None,
        extra_headers: Mapping[str, str] | None = None,
    ) -> Any:
        body = json.dumps(payload or {}).encode("utf-8") if payload is not None else None
        url = f"{self.base_url}{path}"
        if query_params:
            encoded_query = urlencode({key: value for key, value in query_params.items() if value is not None})
            if encoded_query:
                url = f"{url}?{encoded_query}"
        headers = self._build_headers()
        if extra_headers:
            headers.update(extra_headers)
        req = request.Request(
            url=url,
            data=body,
            headers=headers,
            method=method.upper(),
        )
        try:
            with self._requester(req, timeout=self.timeout_seconds) as response:
                raw = response.read().decode("utf-8")
                return json.loads(raw) if raw else None
        except error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="ignore")
            raise WahaClientError(
                f"WAHA HTTP error {exc.code}: {detail}",
                status_code=exc.code,
                response_body=detail,
            ) from exc
        except error.URLError as exc:
            raise WahaClientError(f"WAHA connection error: {exc.reason}") from exc
        except json.JSONDecodeError as exc:
            raise WahaClientError("WAHA returned invalid JSON") from exc

    def get_health(self) -> Any:
        """Read WAHA health endpoint."""

        return self._request_json("GET", "/api/health")

    def list_sessions(self, *, include_all: bool = True) -> list[WhatsappSessionInfo]:
        """List WAHA sessions visible to current API key."""

        payload = self._request_json("GET", "/api/sessions", query_params={"all": str(include_all).lower()}) or []
        return [self._parse_session(item) for item in payload if isinstance(item, Mapping)]

    def get_session(self, session_name: str) -> WhatsappSessionInfo:
        """Get a single WAHA session by name."""

        escaped_session_name = self._escape_session_name(session_name)
        payload = self._request_json("GET", f"/api/sessions/{escaped_session_name}") or {}
        if not isinstance(payload, Mapping):
            raise WahaClientError("WAHA returned invalid session payload")
        return self._parse_session(payload)

    def create_session(
        self,
        *,
        session_name: str,
        start: bool = True,
        config: Mapping[str, Any] | None = None,
    ) -> WhatsappSessionInfo:
        """Create a new WAHA session."""

        normalized_session_name = session_name.strip()
        if not normalized_session_name:
            raise ValueError("session_name must be provided")
        body: dict[str, Any] = {"name": normalized_session_name, "start": start}
        if config:
            body["config"] = dict(config)
        payload = self._request_json("POST", "/api/sessions", body) or {}
        if not isinstance(payload, Mapping):
            raise WahaClientError("WAHA returned invalid session payload")
        return self._parse_session(payload)

    def start_session(self, session_name: str) -> WhatsappSessionInfo:
        return self._session_action(session_name, "start")

    def stop_session(self, session_name: str) -> WhatsappSessionInfo:
        return self._session_action(session_name, "stop")

    def restart_session(self, session_name: str) -> WhatsappSessionInfo:
        return self._session_action(session_name, "restart")

    def logout_session(self, session_name: str) -> WhatsappSessionInfo:
        return self._session_action(session_name, "logout")

    def get_qr_code(self, session_name: str, *, qr_format: str = "image") -> WhatsappQrCodeResult:
        """Fetch QR code as base64 image JSON or raw value JSON."""

        normalized_format = qr_format.strip().lower()
        if normalized_format not in {"image", "raw"}:
            raise ValueError("qr_format must be 'image' or 'raw'")

        escaped_session_name = self._escape_session_name(session_name)
        payload = self._request_json(
            "GET",
            f"/api/{escaped_session_name}/auth/qr",
            query_params={"format": normalized_format},
            extra_headers={"Accept": "application/json"},
        ) or {}
        if not isinstance(payload, Mapping):
            raise WahaClientError("WAHA returned invalid QR payload")
        result = WhatsappQrCodeResult(
            session_name=session_name,
            format=normalized_format,
            mimetype=str(payload.get("mimetype")) if payload.get("mimetype") is not None else None,
            data=str(payload.get("data")) if payload.get("data") is not None else None,
            value=str(payload.get("value")) if payload.get("value") is not None else None,
        )
        if normalized_format == "image" and not result.data:
            raise WahaClientError("WAHA QR image payload missing data")
        if normalized_format == "raw" and not result.value:
            raise WahaClientError("WAHA QR raw payload missing value")
        return result

    def _session_action(self, session_name: str, action: str) -> WhatsappSessionInfo:
        escaped_session_name = self._escape_session_name(session_name)
        payload = self._request_json("POST", f"/api/sessions/{escaped_session_name}/{action}", payload={}) or {}
        if not isinstance(payload, Mapping):
            raise WahaClientError("WAHA returned invalid session payload")
        return self._parse_session(payload)

    @staticmethod
    def _parse_session(payload: Mapping[str, Any]) -> WhatsappSessionInfo:
        name = str(payload.get("name") or "").strip()
        if not name:
            raise WahaClientError("WAHA returned session payload without name")
        return WhatsappSessionInfo(
            name=name,
            status=str(payload.get("status") or "UNKNOWN"),
            me=dict(payload.get("me")) if isinstance(payload.get("me"), Mapping) else None,
            engine=dict(payload.get("engine")) if isinstance(payload.get("engine"), Mapping) else None,
            config=dict(payload.get("config")) if isinstance(payload.get("config"), Mapping) else None,
        )

    def send_text_message(self, *, chat_id: str, text: str, session: str | None = None) -> Any:
        """Send text message through WAHA sendText endpoint."""

        payload = {
            "session": session or self.default_session,
            "chatId": chat_id,
            "text": text,
        }
        return self._request_json("POST", "/api/sendText", payload)
