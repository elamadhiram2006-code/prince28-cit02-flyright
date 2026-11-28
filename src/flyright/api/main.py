"""FastAPI application setup."""

import asyncio
import signal
from contextlib import asynccontextmanager, suppress

from arq.worker import Worker
from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError

from flyright.api.deps import get_app_settings
from flyright.api.errors import (
    AppError,
    app_error_handler,
    validation_error_handler,
)
from flyright.api.middleware import RequestLoggingMiddleware
from flyright.api.routes import chat
from flyright.api.routes.documents import router as documents_router
from flyright.api.routes.health import router as health_router
from flyright.config import Settings, get_settings
from flyright.db.llm_calls import make_recorder
from flyright.db.session import make_engine, make_sessionmaker
from flyright.llm.gateway import build_gateway
from flyright.logging_setup import setup_logging
from flyright.workers.ingest import ingest_document
from flyright.workers.main import shutdown, startup
from flyright.workers.queue import redis_settings


def create_app(settings: Settings | None = None) -> FastAPI:
    """Create and configure the FlyRight application."""
    if settings is None:
        settings = get_settings()

    setup_logging(settings.log_level)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        engine = make_engine(settings)
        app.state.engine = engine
        app.state.session_factory = make_sessionmaker(engine)
        app.state.gateway = build_gateway(
            settings,
            make_recorder(app.state.session_factory),
        )

        embedded_worker = None
        worker_task = None
        ready_task = None

        try:
            if settings.worker_in_api:
                ready = asyncio.Event()

                async def embedded_startup(ctx: dict) -> None:
                    ctx["settings"] = settings
                    await startup(ctx)
                    ready.set()

                embedded_worker = Worker(
                    functions=[ingest_document],
                    redis_settings=redis_settings(settings.redis_url),
                    on_startup=embedded_startup,
                    on_shutdown=shutdown,
                    max_jobs=settings.ingest_concurrency,
                    job_timeout=settings.ingest_job_timeout,
                    max_tries=settings.ingest_max_tries,
                    ctx={"settings": settings},
                )

                worker_task = asyncio.create_task(
                    embedded_worker.async_run(),
                    name="flyright-embedded-worker",
                )
                ready_task = asyncio.create_task(ready.wait())

                done, _ = await asyncio.wait(
                    {worker_task, ready_task},
                    return_when=asyncio.FIRST_COMPLETED,
                )

                if worker_task in done:
                    await worker_task
                    if not ready.is_set():
                        raise RuntimeError("Embedded worker stopped before startup completed.")

                await ready_task
                app.state.worker = embedded_worker
                app.state.worker_task = worker_task

            yield

        finally:
            if ready_task is not None:
                ready_task.cancel()
                with suppress(asyncio.CancelledError):
                    await ready_task

            try:
                if embedded_worker is not None:
                    if worker_task is not None and not worker_task.done():
                        embedded_worker.handle_sig(signal.SIGINT)
                        with suppress(asyncio.CancelledError):
                            await worker_task

                    await embedded_worker.close()
            finally:
                await engine.dispose()

    app = FastAPI(title=settings.app_name, lifespan=lifespan)
    app.state.system_prompt = chat.load_prompt(settings.prompts_dir)
    app.dependency_overrides[get_app_settings] = lambda: settings

    app.add_middleware(RequestLoggingMiddleware)
    app.add_exception_handler(AppError, app_error_handler)
    app.add_exception_handler(
        RequestValidationError,
        validation_error_handler,
    )

    app.include_router(health_router)
    app.include_router(documents_router)
    app.include_router(chat.router, prefix="/v1")

    return app


app = create_app()
