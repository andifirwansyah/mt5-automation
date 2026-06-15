"""Schema package for API and internal DTOs."""

from src.schemas.common import MessageResponse, PaginatedResponse
from src.schemas.health import HealthResponse
from src.schemas.notification import (
    WhatsappRecipientCreatePayload,
    WhatsappDispatchPayload,
    WhatsappDispatchResponse,
    WhatsappDispatchResultResponse,
    WhatsappDeliveryListResponse,
    WhatsappDeliveryResponse,
    WhatsappRetryCandidateListResponse,
    WhatsappRetryDeliveryResponse,
    WhatsappRetryPolicyResponse,
    WhatsappRecipientListResponse,
    WhatsappRecipientResponse,
    WhatsappTestMessagePayload,
    WhatsappRecipientUpdatePayload,
)
from src.schemas.runtime_config import RuntimeConfigUpdatePayload
from src.schemas.auth import UserLoginRequest, UserLoginResponse
from src.schemas.strategy_config import StrategyConfigUpdatePayload

__all__ = [
    "HealthResponse",
    "MessageResponse",
    "PaginatedResponse",
    "WhatsappRecipientCreatePayload",
    "WhatsappDispatchPayload",
    "WhatsappDispatchResponse",
    "WhatsappDispatchResultResponse",
    "WhatsappDeliveryListResponse",
    "WhatsappDeliveryResponse",
    "WhatsappRetryCandidateListResponse",
    "WhatsappRetryDeliveryResponse",
    "WhatsappRetryPolicyResponse",
    "WhatsappRecipientListResponse",
    "WhatsappRecipientResponse",
    "WhatsappTestMessagePayload",
    "WhatsappRecipientUpdatePayload",
    "UserLoginRequest",
    "UserLoginResponse",
    "RuntimeConfigUpdatePayload",
    "StrategyConfigUpdatePayload",
]
