"""Health endpoints.

These live at the root path (``/health*``) rather than under ``/api/v1`` so
that load balancers, container orchestrators, and monitoring can probe them
without knowing the API version. This is the one deliberate exception to the
``/api/v1`` convention in ``docs/API_DESIGN.md``.

- ``GET /health``       — aggregate status (liveness + readiness)
- ``GET /health/live``  — liveness only: process is up (no dependencies)
- ``GET /health/ready`` — readiness: database connectivity verified
"""

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from app.core.config import get_settings
from app.core.db import check_database_connection

router = APIRouter(tags=["health"])


@router.get("/health/live")
def liveness() -> dict[str, str]:
    """Liveness probe — succeeds whenever the process is running."""
    return {"status": "ok"}


@router.get("/health/ready")
def readiness() -> JSONResponse:
    """Readiness probe — verifies database connectivity.

    Returns 200 when the database answers, 503 with the standard error
    envelope otherwise. Orchestrators should route traffic only to ready
    instances.
    """
    settings = get_settings()
    db_ok = check_database_connection()
    if db_ok:
        return JSONResponse(
            status_code=200,
            content={"status": "ready", "database": "ok", "environment": settings.app_env},
        )
    return JSONResponse(
        status_code=503,
        content={
            "error": {
                "code": "SERVICE_UNAVAILABLE",
                "message": "Database is not reachable.",
            }
        },
    )


@router.get("/health")
def health() -> JSONResponse:
    """Aggregate health — liveness plus readiness in one call."""
    settings = get_settings()
    db_ok = check_database_connection()
    if db_ok:
        return JSONResponse(
            status_code=200,
            content={
                "status": "ok",
                "database": "ok",
                "environment": settings.app_env,
                "app": settings.app_name,
            },
        )
    return JSONResponse(
        status_code=503,
        content={
            "error": {
                "code": "SERVICE_UNAVAILABLE",
                "message": "Database is not reachable.",
            }
        },
    )
