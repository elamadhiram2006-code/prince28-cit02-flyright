from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError

from flyright.api.errors import (
    AppError,
    app_error_handler,
    validation_error_handler,
)
from flyright.api.middleware import RequestLoggingMiddleware
from flyright.api.routes.documents import router as documents_router
from flyright.api.routes.health import router as health_router
from flyright.config import Settings, get_settings
from flyright.logging_setup import setup_logging
from flyright.store import Store


def create_app(settings: Settings | None = None):

    if settings is None:
        settings = get_settings()

    setup_logging(settings.log_level)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        app.state.store = Store(settings.data_file)
        app.state.store.load()
        yield

    app = FastAPI(title=settings.app_name, lifespan=lifespan)

    app.add_middleware(RequestLoggingMiddleware)

    app.add_exception_handler(AppError, app_error_handler)

    app.add_exception_handler(RequestValidationError, validation_error_handler)

    app.include_router(health_router)
    app.include_router(documents_router)

    return app
