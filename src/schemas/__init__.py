"""Schema package for API and internal DTOs."""

from src.schemas.common import MessageResponse, PaginatedResponse
from src.schemas.health import HealthResponse

__all__ = [
    "HealthResponse",
    "MessageResponse",
    "PaginatedResponse",
]
