"""Bot status and kill switch control endpoints."""

from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from src.api.deps import get_db, model_to_dict
from src.config.settings import get_settings
from src.infrastructure.database.models import BotInstance, BotRuntimeState
from src.repositories.safety_repository import SafetyRepository
from src.schemas import MessageResponse, RuntimeConfigUpdatePayload
from src.services.runtime_config_service import RuntimeConfigService
from src.infrastructure.database.session import SessionLocal

router = APIRouter(prefix="/api/v1/bot", tags=["bot"])


def _runtime_config_service() -> RuntimeConfigService:
    return RuntimeConfigService(
        session_factory=SessionLocal,
        bootstrap_settings=get_settings(),
        cache_ttl_seconds=0.0,
    )


class KillSwitchPayload(BaseModel):
    reason: str = "manual"
    actor: str = "api"


@router.get("/status")
def get_bot_status(db: Session = Depends(get_db)) -> dict:
    bot = db.execute(select(BotInstance).order_by(BotInstance.started_at.desc()).limit(1)).scalar_one_or_none()
    runtime = None
    if bot is not None:
        runtime = (
            db.execute(
                select(BotRuntimeState).where(BotRuntimeState.bot_instance_id == bot.id).order_by(BotRuntimeState.updated_at.desc()).limit(1)
            ).scalar_one_or_none()
        )
    return {"bot": model_to_dict(bot) if bot else None, "runtime_state": model_to_dict(runtime) if runtime else None}


@router.post("/kill-switch/activate", response_model=MessageResponse)
def activate_kill_switch(payload: KillSwitchPayload, db: Session = Depends(get_db)) -> MessageResponse:
    repo = SafetyRepository(db)
    repo.activate_kill_switch(reason=payload.reason, activated_by=payload.actor, activated_at=datetime.now(timezone.utc))
    db.commit()
    return MessageResponse(message="Kill switch activated")


@router.post("/kill-switch/deactivate", response_model=MessageResponse)
def deactivate_kill_switch(payload: KillSwitchPayload, db: Session = Depends(get_db)) -> MessageResponse:
    repo = SafetyRepository(db)
    repo.deactivate_kill_switch(deactivated_by=payload.actor, deactivated_at=datetime.now(timezone.utc), details={"reason": payload.reason})
    db.commit()
    return MessageResponse(message="Kill switch deactivated")


@router.get("/runtime-configs")
def list_runtime_configs() -> dict:
    service = _runtime_config_service()
    return {"items": service.list_effective_configs(force_refresh=True)}


@router.put("/runtime-configs/{config_key}")
def update_runtime_config(config_key: str, payload: RuntimeConfigUpdatePayload) -> dict:
    service = _runtime_config_service()
    try:
        updated = service.update_config(
            config_key=config_key,
            config_value=payload.value,
            updated_by=payload.actor,
            update_reason=payload.reason,
        )
    except (KeyError, ValueError) as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(exc)) from exc
    return {"config": model_to_dict(updated)}
