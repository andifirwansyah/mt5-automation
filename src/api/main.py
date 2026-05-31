"""Main FastAPI application instance."""

from __future__ import annotations

from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware

from src.api.deps_auth import require_authenticated_user
from src.api.routes.account_routes import router as account_router
from src.api.routes.auth_routes import router as auth_router
from src.api.routes.bot_routes import router as bot_router
from src.api.routes.execution_routes import router as execution_router
from src.api.routes.health_routes import router as health_router
from src.api.routes.journal_routes import router as journal_router
from src.api.routes.market_routes import router as market_router
from src.api.routes.performance_routes import router as performance_router
from src.api.routes.position_routes import router as position_router
from src.api.routes.regime_routes import router as regime_router
from src.api.routes.risk_routes import router as risk_router
from src.api.routes.signal_routes import router as signal_router
from src.api.routes.strategy_routes import router as strategy_router
from src.config.settings import get_settings


def create_app() -> FastAPI:
    """Create FastAPI app with dashboard read/control routes."""

    settings = get_settings()
    app = FastAPI(title=settings.app_name, debug=settings.app_debug)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=[
            "http://localhost:3000",
            "http://127.0.0.1:3000",
            "http://localhost:5173",
            "http://127.0.0.1:5173",
        ],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(health_router)
    app.include_router(auth_router)
    protected_dependencies = [Depends(require_authenticated_user)]

    app.include_router(bot_router, dependencies=protected_dependencies)
    app.include_router(account_router, dependencies=protected_dependencies)
    app.include_router(market_router, dependencies=protected_dependencies)
    app.include_router(regime_router, dependencies=protected_dependencies)
    app.include_router(strategy_router, dependencies=protected_dependencies)
    app.include_router(signal_router, dependencies=protected_dependencies)
    app.include_router(risk_router, dependencies=protected_dependencies)
    app.include_router(execution_router, dependencies=protected_dependencies)
    app.include_router(position_router, dependencies=protected_dependencies)
    app.include_router(journal_router, dependencies=protected_dependencies)
    app.include_router(performance_router, dependencies=protected_dependencies)

    return app


app = create_app()
