"""Schema package for API and internal DTOs."""

from src.schemas.common import MessageResponse, PaginatedResponse
from src.schemas.health import HealthResponse
from src.schemas.runtime_config import RuntimeConfigUpdatePayload
from src.schemas.auth import UserLoginRequest, UserLoginResponse
from src.schemas.strategy_config import StrategyConfigUpdatePayload

__all__ = [
    "HealthResponse",
    "MessageResponse",
    "PaginatedResponse",
    "UserLoginRequest",
    "UserLoginResponse",
    "RuntimeConfigUpdatePayload",
    "StrategyConfigUpdatePayload",
]
