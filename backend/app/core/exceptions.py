import logging
from typing import cast

from fastapi import FastAPI, Request, status
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

logger = logging.getLogger(__name__)


class AppError(Exception):
    """Base class for domain-level application errors.

    Not raised anywhere yet in Phase 1A — no domain logic exists. Establishes
    the error-handling seam that future business-logic exceptions will use,
    so later phases extend this rather than inventing a second error pattern.
    """

    def __init__(
        self,
        message: str,
        *,
        code: str = "app_error",
        status_code: int = status.HTTP_400_BAD_REQUEST,
    ) -> None:
        self.message = message
        self.code = code
        self.status_code = status_code
        super().__init__(message)


def _error_envelope(code: str, message: str, details: object = None) -> dict[str, object]:
    """jsonable_encoder converts non-JSON-native types (Decimal, datetime,
    ...) that can end up in `details` - e.g. Pydantic's own validation
    error context includes the raw constraint value, so a failed
    `Field(ge=Decimal("0"))` check puts a real Decimal in exc.errors().
    Plain JSONResponse uses json.dumps directly and has no idea what to do
    with that; discovered via a real Decimal-typed validation failure, not
    a hypothetical one.
    """
    return cast(
        "dict[str, object]",
        jsonable_encoder({"error": {"code": code, "message": message, "details": details}}),
    )


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(AppError)
    async def handle_app_error(request: Request, exc: AppError) -> JSONResponse:
        return JSONResponse(
            status_code=exc.status_code,
            content=_error_envelope(exc.code, exc.message),
        )

    @app.exception_handler(RequestValidationError)
    async def handle_validation_error(
        request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            content=_error_envelope("validation_error", "Request validation failed", exc.errors()),
        )

    @app.exception_handler(Exception)
    async def handle_unexpected_error(request: Request, exc: Exception) -> JSONResponse:
        logger.exception("Unhandled exception processing request", extra={"path": request.url.path})
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content=_error_envelope("internal_error", "An unexpected error occurred"),
        )
