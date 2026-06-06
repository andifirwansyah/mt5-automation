"""WebSocket endpoints for realtime dashboard events."""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, WebSocket, WebSocketDisconnect, status

from src.api.deps_auth import authenticate_access_token
from src.infrastructure.database.session import SessionLocal
from src.repositories.safety_repository import SafetyRepository
from src.services.kill_switch_stream_service import KillSwitchStreamService
from src.services.position_stream_service import PositionStreamService

router = APIRouter(tags=["ws"])
WEBSOCKET_POLL_INTERVAL_SECONDS = 1.0
WEBSOCKET_HEARTBEAT_INTERVAL_SECONDS = 15.0


class WebSocketAuthenticationError(Exception):
    """Raised when WebSocket authentication fails."""


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


async def _wait_for_disconnect(websocket: WebSocket, timeout_seconds: float) -> None:
    """Wait for a client disconnect without blocking the stream loop forever."""
    try:
        message = await asyncio.wait_for(websocket.receive(), timeout=timeout_seconds)
    except asyncio.TimeoutError:
        return

    if message.get("type") == "websocket.disconnect":
        raise WebSocketDisconnect(
            code=int(message.get("code") or status.WS_1000_NORMAL_CLOSURE),
            reason=message.get("reason"),
        )


async def _send_json_or_disconnect(websocket: WebSocket, payload: dict[str, Any]) -> None:
    """Send websocket JSON safely and normalize disconnect-like runtime errors."""
    try:
        await websocket.send_json(payload)
    except RuntimeError as exc:
        message = str(exc).lower()
        if (
            "close message" in message
            or "websocket is not connected" in message
            or "response already completed" in message
            or "after sending 'websocket.close'" in message
        ):
            raise WebSocketDisconnect(code=status.WS_1000_NORMAL_CLOSURE) from exc
        raise


def _heartbeat_message(event: str) -> dict[str, Any]:
    return {
        "event": event,
        "trace_id": None,
        "occurred_at": _utc_now_iso(),
        "payload": {"status": "alive"},
    }


async def _authenticate_websocket(websocket: WebSocket) -> dict[str, str | int]:
    token = websocket.query_params.get("access_token")
    if not token:
        auth_header = websocket.headers.get("authorization")
        if auth_header and auth_header.lower().startswith("bearer "):
            token = auth_header.split(" ", 1)[1].strip()

    if not token:
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION, reason="Missing access token")
        raise WebSocketAuthenticationError("Missing access token")

    auth_session = SessionLocal()
    try:
        auth_result = authenticate_access_token(token=token, db=auth_session)
    except Exception:
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION, reason="Unauthorized")
        raise WebSocketAuthenticationError("Unauthorized")
    finally:
        auth_session.close()

    return auth_result


@router.websocket("/ws/v1/positions")
async def stream_positions(websocket: WebSocket) -> None:
    await websocket.accept()
    try:
        auth_result = await _authenticate_websocket(websocket)
    except WebSocketAuthenticationError:
        return

    previous_state: dict[str, dict] = {}
    initial_snapshot_sent = False
    last_sent_at = datetime.now(timezone.utc)

    try:
        while True:
            outbound_messages: list[dict[str, object]] = []
            session = SessionLocal()
            try:
                stream_service = PositionStreamService(session)
                current_state = stream_service.load_open_positions()
                if not initial_snapshot_sent:
                    outbound_messages.append(
                        {
                            "event": "positions.snapshot",
                            "trace_id": None,
                            "occurred_at": _utc_now_iso(),
                            "payload": {
                                "authenticated_user": auth_result["email"],
                                "positions": list(current_state.values()),
                            },
                        }
                    )
                    initial_snapshot_sent = True
                else:
                    events = stream_service.diff_positions(previous_state=previous_state, current_state=current_state)
                    for item in events:
                        outbound_messages.append(
                            {
                                "event": item.event,
                                "trace_id": None,
                                "occurred_at": _utc_now_iso(),
                                "payload": item.position,
                            }
                        )
                previous_state = current_state
            finally:
                session.close()

            for message in outbound_messages:
                await _send_json_or_disconnect(websocket, message)
                last_sent_at = datetime.now(timezone.utc)

            seconds_since_last_send = (datetime.now(timezone.utc) - last_sent_at).total_seconds()
            if seconds_since_last_send >= WEBSOCKET_HEARTBEAT_INTERVAL_SECONDS:
                await _send_json_or_disconnect(websocket, _heartbeat_message("positions.heartbeat"))
                last_sent_at = datetime.now(timezone.utc)

            await _wait_for_disconnect(websocket, timeout_seconds=WEBSOCKET_POLL_INTERVAL_SECONDS)
    except WebSocketDisconnect:
        return


@router.websocket("/ws/v1/kill-switch")
async def stream_kill_switch_status(websocket: WebSocket) -> None:
    await websocket.accept()
    try:
        auth_result = await _authenticate_websocket(websocket)
    except WebSocketAuthenticationError:
        return

    previous_status: dict[str, object | None] | None = None
    last_sent_at = datetime.now(timezone.utc)

    try:
        while True:
            outbound_message: dict[str, object] | None = None
            session = SessionLocal()
            try:
                stream_service = KillSwitchStreamService(SafetyRepository(session))
                if previous_status is None:
                    current_status = stream_service.load_snapshot_status()
                    outbound_message = {
                        "event": "kill_switch.snapshot",
                        "trace_id": None,
                        "occurred_at": _utc_now_iso(),
                        "payload": {
                            "authenticated_user": auth_result["email"],
                            **current_status,
                        },
                    }
                    previous_status = current_status
                else:
                    current_status = stream_service.load_current_status()
                    if current_status != previous_status:
                        outbound_message = {
                            "event": "kill_switch.updated",
                            "trace_id": None,
                            "occurred_at": _utc_now_iso(),
                            "payload": current_status,
                        }
                    previous_status = current_status
            finally:
                session.close()

            if outbound_message is not None:
                await _send_json_or_disconnect(websocket, outbound_message)
                last_sent_at = datetime.now(timezone.utc)

            seconds_since_last_send = (datetime.now(timezone.utc) - last_sent_at).total_seconds()
            if seconds_since_last_send >= WEBSOCKET_HEARTBEAT_INTERVAL_SECONDS:
                await _send_json_or_disconnect(websocket, _heartbeat_message("kill_switch.heartbeat"))
                last_sent_at = datetime.now(timezone.utc)

            await _wait_for_disconnect(websocket, timeout_seconds=WEBSOCKET_POLL_INTERVAL_SECONDS)
    except WebSocketDisconnect:
        return
