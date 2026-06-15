"""HTTP client for the self-hosted WhatsApp Web send-message service."""

from __future__ import annotations

import json
from collections.abc import Callable
from typing import Any
from urllib import error, request


class WwebClientError(RuntimeError):
    """Raised when the WhatsApp Web send-message request fails."""

    def __init__(self, message: str, *, status_code: int | None = None, response_body: str | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.response_body = response_body


RequestCallable = Callable[[request.Request, float], Any]


class WwebClient:
    """Small client for the self-hosted WhatsApp Web send-message endpoint."""

    def __init__(
        self,
        *,
        base_url: str,
        api_key: str = "",
        timeout_seconds: float = 10.0,
        requester: RequestCallable | None = None,
    ) -> None:
        normalized_base_url = base_url.strip().rstrip("/")
        if not normalized_base_url:
            raise ValueError("wweb base_url must be provided")
        if timeout_seconds <= 0:
            raise ValueError("wweb timeout_seconds must be greater than zero")

        self.base_url = normalized_base_url
        self.api_key = api_key.strip()
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

    def send_text_message(self, *, chat_id: str, text: str) -> Any:
        """Send a text message through the /send-message endpoint."""

        body = json.dumps({"chatId": chat_id, "message": text}).encode("utf-8")
        req = request.Request(
            url=f"{self.base_url}/send-message",
            data=body,
            headers=self._build_headers(),
            method="POST",
        )
        try:
            with self._requester(req, timeout=self.timeout_seconds) as response:
                raw = response.read().decode("utf-8")
                return json.loads(raw) if raw else None
        except error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="ignore")
            raise WwebClientError(
                f"WWEB HTTP error {exc.code}: {detail}",
                status_code=exc.code,
                response_body=detail,
            ) from exc
        except error.URLError as exc:
            raise WwebClientError(f"WWEB connection error: {exc.reason}") from exc
        except json.JSONDecodeError as exc:
            raise WwebClientError("WWEB returned invalid JSON") from exc
