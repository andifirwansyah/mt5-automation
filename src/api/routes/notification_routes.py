"""Dashboard routes for notification channel onboarding and WhatsApp sessions."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from src.api.deps import get_db, serialize_value
from src.config.settings import get_settings
from src.infrastructure.database.models import NotificationDelivery, NotificationRecipient, NotificationSubscription
from src.infrastructure.notification import GroqNarratorClient, NotificationEventType, WahaClient, WahaClientError
from src.schemas.notification import (
    WhatsappDispatchPayload,
    WhatsappDispatchResponse,
    WhatsappDispatchResultResponse,
    WhatsappDeliveryListResponse,
    WhatsappDeliveryResponse,
    WhatsappRetryCandidateListResponse,
    WhatsappRecipientCreatePayload,
    WhatsappRecipientListResponse,
    WhatsappRecipientResponse,
    WhatsappTestMessagePayload,
    WhatsappRecipientUpdatePayload,
    WhatsappQrCodeResponse,
    WhatsappRetryDeliveryResponse,
    WhatsappRetryPolicyResponse,
    WhatsappSessionCreatePayload,
    WhatsappSessionListResponse,
    WhatsappSessionResponse,
)
from src.repositories.notification_repository import NotificationRepository
from src.services.notification_message_builder import NotificationMessageBuilder
from src.services.notification_narrator_service import NotificationNarratorService
from src.services.whatsapp_dispatch_service import WhatsappDispatchService, WhatsappSendResult
from src.services.whatsapp_session_service import WhatsappSessionService
from src.services.whatsapp_recipient_service import WhatsappRecipientService

router = APIRouter(prefix="/api/v1/notifications/whatsapp", tags=["notifications"])


def _whatsapp_session_service() -> WhatsappSessionService:
    settings = get_settings()
    return WhatsappSessionService(
        WahaClient(
            base_url=settings.waha_base_url,
            api_key=settings.waha_api_key,
            default_session=settings.waha_default_session,
            timeout_seconds=settings.waha_request_timeout_seconds,
        )
    )


def _whatsapp_recipient_service(db: Session) -> WhatsappRecipientService:
    settings = get_settings()
    return WhatsappRecipientService(
        repository=NotificationRepository(db),
        default_session_name=settings.waha_default_session,
    )


def _notification_narrator_service() -> NotificationNarratorService:
    settings = get_settings()
    client = None
    if settings.notification_ai_enabled and settings.groq_secret_key.strip():
        client = GroqNarratorClient(
            base_url=settings.groq_base_url,
            api_key=settings.groq_secret_key,
            model=settings.groq_model,
            timeout_seconds=settings.groq_request_timeout_seconds,
        )
    return NotificationNarratorService(
        client=client,
        enabled=settings.notification_ai_enabled and bool(settings.groq_secret_key.strip()),
        max_sentences=settings.notification_ai_max_sentences,
    )


def _whatsapp_dispatch_service(db: Session) -> WhatsappDispatchService:
    settings = get_settings()
    return WhatsappDispatchService(
        repository=NotificationRepository(db),
        waha_client=WahaClient(
            base_url=settings.waha_base_url,
            api_key=settings.waha_api_key,
            default_session=settings.waha_default_session,
            timeout_seconds=settings.waha_request_timeout_seconds,
        ),
        message_builder=NotificationMessageBuilder(),
        narrator_service=_notification_narrator_service(),
        retry_enabled=settings.notification_retry_enabled,
        retry_max_attempts=settings.notification_retry_max_attempts,
        retry_batch_limit=settings.notification_retry_batch_limit,
    )


def _to_session_response(item: object) -> WhatsappSessionResponse:
    return WhatsappSessionResponse.model_validate(item, from_attributes=True)


def _map_waha_error(exc: WahaClientError) -> HTTPException:
    detail = str(exc)
    if exc.status_code == 400:
        return HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=detail)
    if exc.status_code == 401:
        return HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=detail)
    if exc.status_code == 404:
        return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=detail)
    if exc.status_code == 409:
        return HTTPException(status_code=status.HTTP_409_CONFLICT, detail=detail)
    return HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=detail)


def _map_value_error(exc: ValueError) -> HTTPException:
    return HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(exc))


def _to_recipient_response(
    recipient: NotificationRecipient,
    subscriptions: list[NotificationSubscription],
) -> WhatsappRecipientResponse:
    phone_number = WhatsappRecipientService.phone_number_from_chat_id(recipient.destination)
    metadata = dict(recipient.metadata_json or {})
    return WhatsappRecipientResponse(
        id=str(recipient.id),
        channel_type=recipient.channel_type,
        display_name=recipient.display_name,
        phone_number=phone_number,
        chat_id=recipient.destination,
        session_name=recipient.session_name,
        is_active=recipient.is_active,
        subscribed_events=[subscription.event_type for subscription in subscriptions],
        metadata=serialize_value(metadata),
        created_at=recipient.created_at.isoformat(),
        updated_at=recipient.updated_at.isoformat(),
    )


def _to_dispatch_result_response(result: WhatsappSendResult) -> WhatsappDispatchResultResponse:
    return WhatsappDispatchResultResponse(
        delivery_id=str(result.delivery_id) if result.delivery_id is not None else None,
        retry_of_delivery_id=str(result.retry_of_delivery_id) if result.retry_of_delivery_id is not None else None,
        attempt_number=result.attempt_number,
        recipient_id=str(result.recipient_id),
        chat_id=result.chat_id,
        session_name=result.session_name,
        provider_message_id=result.provider_message_id,
        status=result.status,
        text=result.text,
        narrative_provider=result.narrative_provider,
        used_fallback=result.used_fallback,
        event_type=result.event_type,
        error_message=result.error_message,
    )


def _to_delivery_response(delivery: NotificationDelivery) -> WhatsappDeliveryResponse:
    return WhatsappDeliveryResponse(
        id=str(delivery.id),
        recipient_id=str(delivery.recipient_id),
        retry_of_delivery_id=str(delivery.retry_of_delivery_id) if delivery.retry_of_delivery_id is not None else None,
        attempt_number=int(delivery.attempt_number),
        event_type=delivery.event_type,
        provider_name=delivery.provider_name,
        session_name=delivery.session_name,
        destination=delivery.destination,
        status=delivery.status,
        provider_message_id=delivery.provider_message_id,
        narrative_provider=delivery.narrative_provider,
        used_fallback=delivery.used_fallback,
        message_text=delivery.message_text,
        error_message=delivery.error_message,
        details=serialize_value(dict(delivery.details or {})),
        created_at=delivery.created_at.isoformat(),
    )


def _retry_policy_response() -> WhatsappRetryPolicyResponse:
    settings = get_settings()
    return WhatsappRetryPolicyResponse(
        enabled=settings.notification_retry_enabled,
        max_attempts=settings.notification_retry_max_attempts,
        batch_limit=settings.notification_retry_batch_limit,
    )


@router.get("/sessions", response_model=WhatsappSessionListResponse)
def list_whatsapp_sessions(include_all: bool = Query(default=True)) -> WhatsappSessionListResponse:
    service = _whatsapp_session_service()
    try:
        items = service.list_sessions(include_all=include_all)
    except WahaClientError as exc:
        raise _map_waha_error(exc) from exc
    return WhatsappSessionListResponse(items=[_to_session_response(item) for item in items])


@router.post("/sessions", response_model=WhatsappSessionResponse)
def create_whatsapp_session(payload: WhatsappSessionCreatePayload) -> WhatsappSessionResponse:
    service = _whatsapp_session_service()
    try:
        created = service.create_session(
            session_name=payload.session_name,
            start=payload.start,
            metadata=payload.metadata,
        )
    except WahaClientError as exc:
        raise _map_waha_error(exc) from exc
    return _to_session_response(created)


@router.get("/sessions/{session_name}", response_model=WhatsappSessionResponse)
def get_whatsapp_session(session_name: str) -> WhatsappSessionResponse:
    service = _whatsapp_session_service()
    try:
        session = service.get_session(session_name)
    except WahaClientError as exc:
        raise _map_waha_error(exc) from exc
    return _to_session_response(session)


@router.post("/sessions/{session_name}/start", response_model=WhatsappSessionResponse)
def start_whatsapp_session(session_name: str) -> WhatsappSessionResponse:
    service = _whatsapp_session_service()
    try:
        session = service.start_session(session_name)
    except WahaClientError as exc:
        raise _map_waha_error(exc) from exc
    return _to_session_response(session)


@router.post("/sessions/{session_name}/stop", response_model=WhatsappSessionResponse)
def stop_whatsapp_session(session_name: str) -> WhatsappSessionResponse:
    service = _whatsapp_session_service()
    try:
        session = service.stop_session(session_name)
    except WahaClientError as exc:
        raise _map_waha_error(exc) from exc
    return _to_session_response(session)


@router.post("/sessions/{session_name}/restart", response_model=WhatsappSessionResponse)
def restart_whatsapp_session(session_name: str) -> WhatsappSessionResponse:
    service = _whatsapp_session_service()
    try:
        session = service.restart_session(session_name)
    except WahaClientError as exc:
        raise _map_waha_error(exc) from exc
    return _to_session_response(session)


@router.post("/sessions/{session_name}/logout", response_model=WhatsappSessionResponse)
def logout_whatsapp_session(session_name: str) -> WhatsappSessionResponse:
    service = _whatsapp_session_service()
    try:
        session = service.logout_session(session_name)
    except WahaClientError as exc:
        raise _map_waha_error(exc) from exc
    return _to_session_response(session)


@router.get("/sessions/{session_name}/qr", response_model=WhatsappQrCodeResponse)
def get_whatsapp_session_qr(
    session_name: str,
    qr_format: str = Query(default="image", pattern="^(image|raw)$"),
) -> WhatsappQrCodeResponse:
    service = _whatsapp_session_service()
    try:
        result = service.get_qr_code(session_name, qr_format=qr_format)
    except WahaClientError as exc:
        raise _map_waha_error(exc) from exc
    return WhatsappQrCodeResponse.model_validate(result, from_attributes=True)


@router.get("/recipients", response_model=WhatsappRecipientListResponse)
def list_whatsapp_recipients(
    limit: int = Query(default=100, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
    include_inactive: bool = Query(default=False),
    db: Session = Depends(get_db),
) -> WhatsappRecipientListResponse:
    service = _whatsapp_recipient_service(db)
    recipients, total = service.list_recipients(limit=limit, offset=offset, include_inactive=include_inactive)
    items = []
    for recipient in recipients:
        _, subscriptions = service.get_recipient(recipient.id)
        items.append(_to_recipient_response(recipient, subscriptions))
    return WhatsappRecipientListResponse(items=items, total=total, limit=limit, offset=offset)


@router.post("/recipients", response_model=WhatsappRecipientResponse)
def create_whatsapp_recipient(
    payload: WhatsappRecipientCreatePayload,
    db: Session = Depends(get_db),
) -> WhatsappRecipientResponse:
    service = _whatsapp_recipient_service(db)
    try:
        recipient, subscriptions = service.create_recipient(
            display_name=payload.display_name,
            phone_number=payload.phone_number,
            session_name=payload.session_name,
            is_active=payload.is_active,
            subscribed_events=[item.value for item in payload.subscribed_events],
            metadata=payload.metadata,
        )
    except ValueError as exc:
        raise _map_value_error(exc) from exc
    db.commit()
    db.refresh(recipient)
    return _to_recipient_response(recipient, subscriptions)


@router.get("/recipients/{recipient_id}", response_model=WhatsappRecipientResponse)
def get_whatsapp_recipient(recipient_id: uuid.UUID, db: Session = Depends(get_db)) -> WhatsappRecipientResponse:
    service = _whatsapp_recipient_service(db)
    recipient, subscriptions = service.get_recipient(recipient_id)
    if recipient is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="WhatsApp recipient not found")
    return _to_recipient_response(recipient, subscriptions)


@router.put("/recipients/{recipient_id}", response_model=WhatsappRecipientResponse)
def update_whatsapp_recipient(
    recipient_id: uuid.UUID,
    payload: WhatsappRecipientUpdatePayload,
    db: Session = Depends(get_db),
) -> WhatsappRecipientResponse:
    service = _whatsapp_recipient_service(db)
    try:
        recipient, subscriptions = service.update_recipient(
            recipient_id,
            display_name=payload.display_name,
            phone_number=payload.phone_number,
            session_name=payload.session_name,
            is_active=payload.is_active,
            subscribed_events=[item.value for item in payload.subscribed_events] if payload.subscribed_events is not None else None,
            metadata=payload.metadata,
        )
    except ValueError as exc:
        raise _map_value_error(exc) from exc
    if recipient is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="WhatsApp recipient not found")
    db.commit()
    db.refresh(recipient)
    return _to_recipient_response(recipient, subscriptions)


@router.post("/recipients/{recipient_id}/test-message", response_model=WhatsappDispatchResponse)
def send_whatsapp_test_message(
    recipient_id: uuid.UUID,
    payload: WhatsappTestMessagePayload,
    db: Session = Depends(get_db),
) -> WhatsappDispatchResponse:
    service = _whatsapp_dispatch_service(db)
    try:
        result = service.send_test_message(recipient_id=recipient_id, message=payload.message)
    except ValueError as exc:
        raise _map_value_error(exc) from exc
    except WahaClientError as exc:
        raise _map_waha_error(exc) from exc
    return WhatsappDispatchResponse(total_sent=1, results=[_to_dispatch_result_response(result)])


@router.post("/dispatch", response_model=WhatsappDispatchResponse)
def dispatch_whatsapp_event(
    payload: WhatsappDispatchPayload,
    db: Session = Depends(get_db),
) -> WhatsappDispatchResponse:
    service = _whatsapp_dispatch_service(db)
    try:
        if payload.recipient_ids == []:
            return WhatsappDispatchResponse(event_type=payload.event_type, total_sent=0, results=[])
        results = service.dispatch_event(
            event_type=payload.event_type,
            payload=payload.payload,
            recipient_ids=payload.recipient_ids,
        )
    except ValueError as exc:
        raise _map_value_error(exc) from exc
    except WahaClientError as exc:
        raise _map_waha_error(exc) from exc
    return WhatsappDispatchResponse(
        event_type=payload.event_type,
        total_sent=len(results),
        results=[_to_dispatch_result_response(item) for item in results],
    )


@router.post("/deliveries/{delivery_id}/retry", response_model=WhatsappRetryDeliveryResponse)
def retry_whatsapp_delivery(delivery_id: uuid.UUID, db: Session = Depends(get_db)) -> WhatsappRetryDeliveryResponse:
    service = _whatsapp_dispatch_service(db)
    try:
        result = service.retry_delivery(delivery_id=delivery_id)
    except ValueError as exc:
        raise _map_value_error(exc) from exc
    except WahaClientError as exc:
        raise _map_waha_error(exc) from exc
    return WhatsappRetryDeliveryResponse(delivery=_to_dispatch_result_response(result))


@router.get("/deliveries/retry-candidates", response_model=WhatsappRetryCandidateListResponse)
def list_whatsapp_retry_candidates(db: Session = Depends(get_db)) -> WhatsappRetryCandidateListResponse:
    service = _whatsapp_dispatch_service(db)
    items = service.list_retry_candidates()
    return WhatsappRetryCandidateListResponse(
        policy=_retry_policy_response(),
        items=[_to_delivery_response(item) for item in items],
        total=len(items),
    )


@router.get("/deliveries/{delivery_id}", response_model=WhatsappDeliveryResponse)
def get_whatsapp_delivery(delivery_id: uuid.UUID, db: Session = Depends(get_db)) -> WhatsappDeliveryResponse:
    repository = NotificationRepository(db)
    delivery = repository.get_delivery_by_id(delivery_id)
    if delivery is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Notification delivery not found")
    return _to_delivery_response(delivery)


@router.get("/deliveries", response_model=WhatsappDeliveryListResponse)
def list_whatsapp_deliveries(
    limit: int = Query(default=100, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
    recipient_id: uuid.UUID | None = Query(default=None),
    event_type: NotificationEventType | None = Query(default=None),
    status_value: str | None = Query(default=None, alias="status"),
    db: Session = Depends(get_db),
) -> WhatsappDeliveryListResponse:
    repository = NotificationRepository(db)
    items = repository.list_deliveries(
        limit=limit,
        offset=offset,
        recipient_id=recipient_id,
        event_type=event_type.value if event_type is not None else None,
        status=status_value,
    )
    total = repository.count_deliveries(
        recipient_id=recipient_id,
        event_type=event_type.value if event_type is not None else None,
        status=status_value,
    )
    return WhatsappDeliveryListResponse(
        items=[_to_delivery_response(item) for item in items],
        total=total,
        limit=limit,
        offset=offset,
    )
