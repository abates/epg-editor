"""Health-check router.

Pure liveness check — no business logic, no storage/SD-client calls.
"""

from fastapi import APIRouter

from app.models.health import HealthStatus

router = APIRouter(tags=["health"])


@router.get("/health", response_model=HealthStatus)
def get_health() -> HealthStatus:
    """Report that the backend process is up and serving requests."""
    return HealthStatus()
