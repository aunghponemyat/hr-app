from collections.abc import Awaitable, Callable
from uuid import uuid4

from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import Settings, get_settings
from app.core.errors import register_error_handlers
from app.routers.admin_employees import router as admin_employees_router
from app.routers.admin_locations import router as admin_locations_router
from app.routers.admin_teams import router as admin_teams_router
from app.routers.attendance import router as attendance_router
from app.routers.auth import router as auth_router
from app.routers.health import router as health_router
from app.routers.me import router as me_router
from app.routers.team import router as team_router
from app.schemas.common import ErrorResponse
from app.services.login_limiter import LoginRateLimiter


def create_app(settings: Settings | None = None) -> FastAPI:
    config = settings if settings is not None else get_settings()
    docs_enabled = config.app_env != "production"
    application = FastAPI(
        title="HR Management & Attendance API",
        version="0.1.0",
        debug=False,
        docs_url="/docs" if docs_enabled else None,
        redoc_url="/redoc" if docs_enabled else None,
        openapi_url="/openapi.json" if docs_enabled else None,
        responses={
            status: {"model": ErrorResponse} for status in (401, 403, 404, 409, 422, 429, 500, 503)
        },
    )

    def application_settings() -> Settings:
        return config

    application.dependency_overrides[get_settings] = application_settings
    application.state.login_limiter = LoginRateLimiter(config)
    application.add_middleware(
        CORSMiddleware,
        allow_origins=config.allowed_origins,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PATCH", "PUT", "DELETE", "OPTIONS"],
        allow_headers=["Authorization", "Content-Type"],
        expose_headers=["Content-Disposition", "X-Request-ID"],
    )

    @application.middleware("http")
    async def request_id_middleware(
        request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        request.state.request_id = uuid4().hex
        response = await call_next(request)
        response.headers["X-Request-ID"] = request.state.request_id
        if request.url.path.startswith("/api/v1/"):
            response.headers["Cache-Control"] = "no-store"
        return response

    register_error_handlers(application)
    application.include_router(health_router)
    application.include_router(auth_router)
    application.include_router(me_router)
    application.include_router(admin_employees_router)
    application.include_router(admin_teams_router)
    application.include_router(admin_locations_router)
    application.include_router(team_router)
    application.include_router(attendance_router)
    return application


app = create_app()
