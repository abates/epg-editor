"""Response model for the health-check endpoint."""

from pydantic import BaseModel


class HealthStatus(BaseModel):
    """Minimal liveness report returned by `GET /api/health`."""

    status: str = "ok"
