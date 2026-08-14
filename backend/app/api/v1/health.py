from fastapi import APIRouter
from pydantic import BaseModel

router = APIRouter()


class HealthCheckResponse(BaseModel):
    status: str
    checks: dict[str, str]


@router.get("/health", response_model=HealthCheckResponse)
async def health() -> HealthCheckResponse:
    """Liveness check: confirms the process is up and serving requests.

    No dependency checks yet (e.g. database) — those are added in step 5 as
    a readiness check, extending the `checks` field rather than replacing it.
    """
    return HealthCheckResponse(status="ok", checks={"api": "ok"})
