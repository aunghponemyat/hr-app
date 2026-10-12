import logging
from collections.abc import Mapping
from typing import cast
from uuid import uuid4

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from pydantic import JsonValue
from starlette.exceptions import HTTPException
from starlette.responses import JSONResponse

from app.schemas.common import ErrorResponse

logger = logging.getLogger(__name__)


class AppError(Exception):
    def __init__(
        self,
        status_code: int,
        code: str,
        message: str,
        details: dict[str, JsonValue] | None = None,
        headers: Mapping[str, str] | None = None,
    ) -> None:
        super().__init__(code)
        self.status_code = status_code
        self.code = code
        self.message = message
        self.details = details
        self.headers = headers


def error_response(
    status_code: int,
    code: str,
    message: str,
    details: dict[str, JsonValue] | None = None,
    headers: Mapping[str, str] | None = None,
) -> JSONResponse:
    body = ErrorResponse(code=code, message=message, details=details)
    return JSONResponse(status_code=status_code, content=body.model_dump(), headers=headers)


async def app_error_handler(_request: Request, exc: Exception) -> JSONResponse:
    error = cast(AppError, exc)
    return error_response(
        error.status_code, error.code, error.message, error.details, error.headers
    )


async def validation_error_handler(_request: Request, exc: Exception) -> JSONResponse:
    error = cast(RequestValidationError, exc)
    # Never serialize input, ctx, or the request body: these can contain credentials.
    errors: list[JsonValue] = [
        {"location": list(item["loc"]), "type": item["type"]} for item in error.errors()
    ]
    return error_response(422, "VALIDATION_ERROR", "Invalid request data.", {"errors": errors})


async def http_error_handler(_request: Request, exc: Exception) -> JSONResponse:
    error = cast(HTTPException, exc)
    messages = {
        401: ("UNAUTHENTICATED", "Authentication required."),
        403: ("PERMISSION_DENIED", "Permission denied."),
        404: ("NOT_FOUND", "Resource not found."),
        405: ("METHOD_NOT_ALLOWED", "Method not allowed."),
    }
    code, message = messages.get(error.status_code, ("HTTP_ERROR", "Request failed."))
    return error_response(error.status_code, code, message, headers=error.headers)


async def internal_error_handler(request: Request, exc: Exception) -> JSONResponse:
    request_id = getattr(request.state, "request_id", uuid4().hex)
    # Exception messages and traceback locals may contain passwords/tokens or SQL parameters.
    logger.error("Unhandled %s; request_id=%s", type(exc).__name__, request_id)
    return error_response(
        500,
        "INTERNAL_ERROR",
        "An unexpected error occurred.",
        headers={"X-Request-ID": request_id},
    )


def register_error_handlers(app: FastAPI) -> None:
    app.add_exception_handler(AppError, app_error_handler)
    app.add_exception_handler(RequestValidationError, validation_error_handler)
    app.add_exception_handler(HTTPException, http_error_handler)
    app.add_exception_handler(Exception, internal_error_handler)
