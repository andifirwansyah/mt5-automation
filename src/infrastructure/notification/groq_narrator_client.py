"""Groq narrator client for constrained human-readable message generation."""

from __future__ import annotations

import json
from collections.abc import Callable, Mapping
from typing import Any
from urllib import error, request


class GroqNarratorClientError(RuntimeError):
    """Raised when Groq narration request fails."""


RequestCallable = Callable[[request.Request, float], Any]


class GroqNarratorClient:
    """Minimal OpenAI-compatible Groq client for short narration output."""

    def __init__(
        self,
        *,
        base_url: str,
        api_key: str,
        model: str,
        timeout_seconds: float = 15.0,
        requester: RequestCallable | None = None,
    ) -> None:
        normalized_base_url = base_url.strip().rstrip("/")
        normalized_api_key = api_key.strip()
        normalized_model = model.strip()
        if not normalized_base_url:
            raise ValueError("groq base_url must be provided")
        if not normalized_api_key:
            raise ValueError("groq api_key must be provided")
        if not normalized_model:
            raise ValueError("groq model must be provided")
        if timeout_seconds <= 0:
            raise ValueError("groq timeout_seconds must be greater than zero")

        self.base_url = normalized_base_url
        self.api_key = normalized_api_key
        self.model = normalized_model
        self.timeout_seconds = timeout_seconds
        self._requester = requester or request.urlopen

    def _build_headers(self) -> dict[str, str]:
        return {
            "Content-Type": "application/json",
            "Accept": "application/json",
            "Authorization": f"Bearer {self.api_key}",
        }

    def generate_narrative(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        temperature: float = 0.2,
        max_tokens: int = 180,
    ) -> str:
        """Generate a short constrained narrative from Groq."""

        body = {
            "model": self.model,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
        }
        req = request.Request(
            url=f"{self.base_url}/chat/completions",
            data=json.dumps(body).encode("utf-8"),
            headers=self._build_headers(),
            method="POST",
        )
        try:
            with self._requester(req, self.timeout_seconds) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="ignore")
            raise GroqNarratorClientError(f"Groq HTTP error {exc.code}: {detail}") from exc
        except error.URLError as exc:
            raise GroqNarratorClientError(f"Groq connection error: {exc.reason}") from exc
        except json.JSONDecodeError as exc:
            raise GroqNarratorClientError("Groq returned invalid JSON") from exc

        choices = payload.get("choices") or []
        if not choices:
            raise GroqNarratorClientError("Groq response does not contain choices")

        message = choices[0].get("message") or {}
        content = str(message.get("content") or "").strip()
        if not content:
            raise GroqNarratorClientError("Groq response content is empty")
        return content
