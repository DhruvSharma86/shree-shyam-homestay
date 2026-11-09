"""FastAPI application entry point.

Run with::

    uvicorn app.main:app --reload

Wiring order: settings → logging → FastAPI app → error handlers → routers.
No business logic lives here; each capability is a router module.
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app import models as _models  # noqa: F401  (registers ORM models on Base.metadata)
from app.api.health import router as health_router
from app.auth.router import router as auth_router
from app.auth.users_router import router as users_router
from app.billing.router import router as billing_router
from app.bookings.router import router as bookings_router
from app.core.config import get_settings
from app.core.errors import register_error_handlers
from app.core.logging_config import configure_logging, get_logger
from app.guests.router import router as guests_router
from app.hotel.restaurant_router import router as restaurant_router
from app.hotel.router import router as hotel_router
from app.reports.router import router as reports_router


def create_app() -> FastAPI:
    """Application factory — builds and wires the FastAPI app."""
    settings = get_settings()
    configure_logging(settings.log_level)
    logger = get_logger(__name__)

    app = FastAPI(
        title=settings.app_name,
        version="0.1.0",
        debug=settings.app_debug,
    )

    # CORS: the Next.js frontend is a separate origin in development.
    # Tighten allow_origins via env in production (Phase 1.2+).
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:3000"],
        allow_credentials=True,
        allow_methods=["GET", "POST", "PATCH", "PUT", "DELETE", "OPTIONS"],
        allow_headers=["*"],
    )

    register_error_handlers(app)

    # Health endpoints are intentionally outside /api/v1 (see health.py).
    app.include_router(health_router)

    # Versioned API routers. Later phases add bookings/billing/etc. here.
    app.include_router(auth_router, prefix=settings.api_v1_prefix)
    app.include_router(users_router, prefix=settings.api_v1_prefix)
    app.include_router(hotel_router, prefix=settings.api_v1_prefix)
    app.include_router(restaurant_router, prefix=settings.api_v1_prefix)
    app.include_router(guests_router, prefix=settings.api_v1_prefix)
    app.include_router(bookings_router, prefix=settings.api_v1_prefix)
    app.include_router(billing_router, prefix=settings.api_v1_prefix)
    app.include_router(reports_router, prefix=settings.api_v1_prefix)

    logger.info(
        "Application initialised",
        extra={"context": {"environment": settings.app_env}},
    )
    return app


app = create_app()
