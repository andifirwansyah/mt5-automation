"""Service layer for WhatsApp session and QR management."""

from __future__ import annotations

from collections.abc import Mapping

from src.infrastructure.notification import WahaClient
from src.infrastructure.notification.models import WhatsappQrCodeResult, WhatsappSessionInfo


class WhatsappSessionService:
    """High-level operations for dashboard-driven WhatsApp onboarding."""

    def __init__(self, client: WahaClient) -> None:
        self.client = client

    def list_sessions(self, *, include_all: bool = True) -> list[WhatsappSessionInfo]:
        return self.client.list_sessions(include_all=include_all)

    def get_session(self, session_name: str) -> WhatsappSessionInfo:
        return self.client.get_session(session_name)

    def create_session(
        self,
        *,
        session_name: str,
        start: bool = True,
        metadata: Mapping[str, str] | None = None,
    ) -> WhatsappSessionInfo:
        config: dict[str, object] | None = None
        if metadata:
            config = {"metadata": dict(metadata)}
        return self.client.create_session(session_name=session_name, start=start, config=config)

    def start_session(self, session_name: str) -> WhatsappSessionInfo:
        return self.client.start_session(session_name)

    def stop_session(self, session_name: str) -> WhatsappSessionInfo:
        return self.client.stop_session(session_name)

    def restart_session(self, session_name: str) -> WhatsappSessionInfo:
        return self.client.restart_session(session_name)

    def logout_session(self, session_name: str) -> WhatsappSessionInfo:
        return self.client.logout_session(session_name)

    def get_qr_code(self, session_name: str, *, qr_format: str = "image") -> WhatsappQrCodeResult:
        return self.client.get_qr_code(session_name, qr_format=qr_format)
