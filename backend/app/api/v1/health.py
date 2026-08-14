import logging

from fastapi import APIRouter, Depends, Response, status
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.db.session import get_db

logger = logging.getLogger(__name__)

router = APIRouter()


class HealthCheckResponse(BaseModel):
    status: str
    checks: dict[str, str]


def check_database(db: Session = Depends(get_db)) -> str:
    try:
        db.execute(text("SELECT 1"))
    except Exception:
        logger.warning("Database health check failed", exc_info=True)
        return "error"
    return "ok"


@router.get("/health", response_model=HealthCheckResponse)
async def health(
    response: Response,
    database_status: str = Depends(check_database),
) -> HealthCheckResponse:
    """Liveness + readiness check.

    "api" reflects the process being up (always "ok" if this code runs at
    all). "database" reflects the SELECT 1 readiness check. Overall status
    is "degraded" with a 503 if any check fails, so a load balancer or
    orchestrator polling this endpoint can distinguish ready from not-ready
    by status code alone, not just by parsing the body.
    """
    checks = {"api": "ok", "database": database_status}
    overall_status = "ok" if all(value == "ok" for value in checks.values()) else "degraded"

    if overall_status != "ok":
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE

    return HealthCheckResponse(status=overall_status, checks=checks)
