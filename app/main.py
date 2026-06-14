import logging

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy.exc import IntegrityError
from starlette import status

from app.api.routes import auth, authors, books, health, imports, users
from app.core.config import get_settings
from app.core.exceptions import AppError, app_error_from_integrity_error
from app.core.logging import RequestIdMiddleware, configure_logging
from app.core.security import TokenError

settings = get_settings()
configure_logging(settings.log_level)
logger = logging.getLogger("app")


def create_app() -> FastAPI:
    app = FastAPI(
        title="Library Management API",
        version="0.1.0",
        description="Backend API for managing users, authors, books, and CSV imports.",
    )

    app.add_middleware(RequestIdMiddleware)
    if settings.cors_origins:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=settings.cors_origins,
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
        )

    app.include_router(health.router)
    app.include_router(auth.router)
    app.include_router(users.router)
    app.include_router(authors.router)
    app.include_router(books.router)
    app.include_router(imports.router)

    register_exception_handlers(app)
    return app


def request_id(request: Request) -> str:
    return str(getattr(request.state, "request_id", "unknown"))


def error_response(
    request: Request,
    *,
    status_code: int,
    code: str,
    message: str,
    details: object = None,
) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content={
            "error": {
                "code": code,
                "message": message,
                "details": details,
            },
            "request_id": request_id(request),
        },
    )


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(AppError)
    async def app_error_handler(request: Request, exc: AppError) -> JSONResponse:
        return error_response(
            request,
            status_code=exc.error.status_code,
            code=exc.error.code,
            message=exc.error.message,
            details=exc.error.details,
        )

    @app.exception_handler(RequestValidationError)
    async def validation_error_handler(
        request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        return error_response(
            request,
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            code="validation_error",
            message="Request validation failed.",
            details=exc.errors(),
        )

    @app.exception_handler(IntegrityError)
    async def integrity_error_handler(request: Request, exc: IntegrityError) -> JSONResponse:
        app_error = app_error_from_integrity_error(exc)
        return error_response(
            request,
            status_code=app_error.error.status_code,
            code=app_error.error.code,
            message=app_error.error.message,
            details=app_error.error.details,
        )

    @app.exception_handler(TokenError)
    async def token_error_handler(request: Request, exc: TokenError) -> JSONResponse:
        return error_response(
            request,
            status_code=status.HTTP_401_UNAUTHORIZED,
            code=exc.code,
            message=exc.message,
        )

    @app.exception_handler(Exception)
    async def unexpected_error_handler(request: Request, exc: Exception) -> JSONResponse:
        logger.exception(
            "unexpected request failure",
            extra={"request_id": request_id(request), "path": request.url.path},
        )
        return error_response(
            request,
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            code="internal_server_error",
            message="An unexpected server error occurred.",
        )


app = create_app()
