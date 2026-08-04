"""FastAPI application factory.

``create_app()`` builds and returns a fully-configured app with no reliance on
module-level global state, so tests can construct an isolated instance. A
module-level ``app`` is still exported for ``uvicorn app.main:app`` in
development and production.
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from collections.abc import AsyncIterator

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.auth.routes import auth_router, user_router
from app.dashboard.routes import dashboard_router
from app.health import router as health_router
from app.history.routes import history_admin_router, history_router
from app.intelligence.routes import intelligence_router
from app.market.routes import admin_router, market_router
from app.news.routes import news_admin_router, news_router
from app.portfolio.routes import portfolio_router, watchlist_router
from app.reports.routes import reports_router
from app.scheduler.scheduler import shutdown_scheduler, start_scheduler
from app.shared.database import dispose_engine
from app.shared.exceptions import register_exception_handlers
from app.shared.middleware import RequestIDMiddleware
from config.logging import configure_logging, get_logger
from config.settings import settings

logger = get_logger(__name__)


@asynccontextmanager
async def _lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Startup/shutdown hooks."""
    logger.info("app_startup", extra={"env": settings.app_env})
    start_scheduler()
    yield
    shutdown_scheduler()
    await dispose_engine()
    logger.info("app_shutdown")


def create_app() -> FastAPI:
    """Construct and return a configured FastAPI application."""
    configure_logging()

    app = FastAPI(
        title=settings.app_name,
        version="0.1.0",
        docs_url="/docs",
        redoc_url="/redoc",
        openapi_url="/openapi.json",
        lifespan=_lifespan,
    )

    # Order matters: request-ID middleware runs outermost so every log (and the
    # CORS response) carries a correlation ID.
    app.add_middleware(RequestIDMiddleware)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    register_exception_handlers(app)

    # Infrastructure routes (unversioned).
    app.include_router(health_router)

    # Feature routers, versioned under /api/v1.
    app.include_router(auth_router, prefix=settings.api_v1_prefix)
    app.include_router(user_router, prefix=settings.api_v1_prefix)
    app.include_router(market_router, prefix=settings.api_v1_prefix)
    app.include_router(admin_router, prefix=settings.api_v1_prefix)
    app.include_router(portfolio_router, prefix=settings.api_v1_prefix)
    app.include_router(watchlist_router, prefix=settings.api_v1_prefix)
    app.include_router(history_router, prefix=settings.api_v1_prefix)
    app.include_router(history_admin_router, prefix=settings.api_v1_prefix)
    app.include_router(news_router, prefix=settings.api_v1_prefix)
    app.include_router(news_admin_router, prefix=settings.api_v1_prefix)
    app.include_router(reports_router, prefix=settings.api_v1_prefix)
    app.include_router(intelligence_router, prefix=settings.api_v1_prefix)
    app.include_router(dashboard_router, prefix=settings.api_v1_prefix)

    return app


app = create_app()
