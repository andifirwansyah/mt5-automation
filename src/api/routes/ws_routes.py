"""WebSocket endpoints for realtime dashboard events."""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone

from fastapi import APIRouter, WebSocket, WebSocketDisconnect, status

from src.api.deps_auth import authenticate_access_token
from src.infrastructure.database.session import SessionLocal
from src.repositories.safety_repository import SafetyRepository
from src.services.kill_switch_stream_service import KillSwitchStreamService
from src.services.position_stream_service import PositionStreamService

router = APIRouter(tags=["ws"])


class WebSocketAuthenticationError(Exception):
    """Raised when WebSocket authentication fails."""


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


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
    try:
        auth_result = await _authenticate_websocket(websocket)
    except WebSocketAuthenticationError:
        return

    await websocket.accept()

    previous_state: dict[str, dict] = {}
    initial_snapshot_sent = False

    try:
        while True:
            session = SessionLocal()
            try:
                stream_service = PositionStreamService(session)
                current_state = stream_service.load_open_positions()
                if not initial_snapshot_sent:
                    await websocket.send_json(
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
                        await websocket.send_json(
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

            await asyncio.sleep(1.0)
    except WebSocketDisconnect:
        return


@router.websocket("/ws/v1/kill-switch")
async def stream_kill_switch_status(websocket: WebSocket) -> None:
    try:
        auth_result = await _authenticate_websocket(websocket)
    except WebSocketAuthenticationError:
        return

    await websocket.accept()

    previous_status: dict[str, object | None] | None = None

    try:
        while True:
            session = SessionLocal()
            try:
                stream_service = KillSwitchStreamService(SafetyRepository(session))
                if previous_status is None:
                    current_status = stream_service.load_snapshot_status()
                    await websocket.send_json(
                        {
                            "event": "kill_switch.snapshot",
                            "trace_id": None,
                            "occurred_at": _utc_now_iso(),
                            "payload": {
                                "authenticated_user": auth_result["email"],
                                **current_status,
                            },
                        }
                    )
                    previous_status = current_status
                else:
                    current_status = stream_service.load_current_status()
                    if current_status != previous_status:
                        await websocket.send_json(
                            {
                                "event": "kill_switch.updated",
                                "trace_id": None,
                                "occurred_at": _utc_now_iso(),
                                "payload": current_status,
                            }
                        )
                    previous_status = current_status
            finally:
                session.close()

            await asyncio.sleep(1.0)
    except WebSocketDisconnect:
        return
