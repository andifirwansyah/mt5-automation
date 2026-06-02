"""WebSocket endpoints for realtime dashboard events."""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone

from fastapi import APIRouter, WebSocket, WebSocketDisconnect, status

from src.api.deps_auth import authenticate_access_token
from src.infrastructure.database.session import SessionLocal
from src.services.position_stream_service import PositionStreamService

router = APIRouter(tags=["ws"])


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@router.websocket("/ws/v1/positions")
async def stream_positions(websocket: WebSocket) -> None:
    token = websocket.query_params.get("access_token")
    if not token:
        auth_header = websocket.headers.get("authorization")
        if auth_header and auth_header.lower().startswith("bearer "):
            token = auth_header.split(" ", 1)[1].strip()

    if not token:
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION, reason="Missing access token")
        return

    auth_session = SessionLocal()
    try:
        auth_result = authenticate_access_token(token=token, db=auth_session)
    except Exception:
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION, reason="Unauthorized")
        return
    finally:
        auth_session.close()

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
