"""Custom errors and global handlers. Every error response has the shape {detail, code}."""

import logging
from http import HTTPStatus

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

logger = logging.getLogger(__name__)


class AppError(Exception):
    """Base for expected errors. Subclasses set status_code, code and a default detail."""

    status_code = 500
    code = "INTERNAL_ERROR"
    default_detail = "Something went wrong. Please try again."

    def __init__(self, detail: str | None = None, headers: dict[str, str] | None = None):
        self.detail = detail or self.default_detail
        self.headers = headers
        super().__init__(self.detail)


class PatientNotFoundError(AppError):
    status_code = 404
    code = "PATIENT_NOT_FOUND"
    default_detail = "Patient not found."


class CaseSheetRequiredError(AppError):
    status_code = 409
    code = "CASE_SHEET_REQUIRED"
    default_detail = "Save a case sheet before generating a summary."


class AIUnavailableError(AppError):
    status_code = 503
    code = "AI_UNAVAILABLE"
    default_detail = "The AI service is temporarily unavailable. Please try again shortly."


def _error(status_code: int, detail: str, code: str, **extra) -> JSONResponse:
    return JSONResponse({"detail": detail, "code": code, **extra}, status_code=status_code)


async def _app_error_handler(request: Request, exc: AppError) -> JSONResponse:
    response = _error(exc.status_code, exc.detail, exc.code)
    if exc.headers:
        response.headers.update(exc.headers)
    return response


async def _validation_error_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    # Drop the location prefix ("body", "query", "path") so the frontend gets plain field names
    errors = [
        {
            "field": ".".join(str(part) for part in err["loc"][1:]) or str(err["loc"][0]),
            "message": err["msg"],
        }
        for err in exc.errors()
    ]
    return _error(422, "Invalid request data.", "VALIDATION_ERROR", errors=errors)


async def _http_error_handler(request: Request, exc: StarletteHTTPException) -> JSONResponse:
    # Framework errors such as unknown routes (404) or wrong methods (405)
    code = HTTPStatus(exc.status_code).name
    return _error(exc.status_code, str(exc.detail), code)


async def _unhandled_error_handler(request: Request, exc: Exception) -> JSONResponse:
    logger.exception("Unhandled error on %s %s", request.method, request.url.path)
    return _error(500, AppError.default_detail, AppError.code)


def register_exception_handlers(app: FastAPI) -> None:
    app.add_exception_handler(AppError, _app_error_handler)
    app.add_exception_handler(RequestValidationError, _validation_error_handler)
    app.add_exception_handler(StarletteHTTPException, _http_error_handler)
    app.add_exception_handler(Exception, _unhandled_error_handler)
