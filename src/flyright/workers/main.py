"""ARQ worker configuration and application lifecycle."""

import asyncio
import logging
import signal

from arq.worker import Worker

from flyright.config import Settings, get_settings
from flyright.db.ingest_jobs import IngestRepository
from flyright.db.llm_calls import make_recorder
from flyright.db.session import make_engine, make_sessionmaker
from flyright.ingest.fetch import make_client
from flyright.llm.gateway import build_gateway
from flyright.logging_setup import setup_logging
from flyright.workers.ingest import Pace, ingest_document
from flyright.workers.queue import Queue, redis_settings

logger = logging.getLogger("flyright.worker")


async def startup(ctx: dict) -> None:
    """Initialize resources and recover unfinished ingestion jobs."""
    settings = ctx.get("settings") or get_settings()
    setup_logging(settings.log_level)

    engine = make_engine(settings)
    sessionmaker = make_sessionmaker(engine)
    http = make_client(settings.ingest_concurrency)

    ctx.update(
        {
            "settings": settings,
            "engine": engine,
            "sessionmaker": sessionmaker,
            "http": http,
            "gateway": build_gateway(
                settings,
                recorder=make_recorder(sessionmaker),
            ),
            "pace": Pace(settings.ingest_rpm),
        }
    )

    async with sessionmaker() as session:
        item_ids = await IngestRepository(session).open_item_ids()

    recovered = await Queue(ctx["redis"]).put(item_ids)

    if item_ids:
        logger.info(
            "Worker startup recovered %s unfinished item(s); %s newly queued",
            len(item_ids),
            recovered,
        )


async def shutdown(ctx: dict) -> None:
    """Close worker resources cleanly."""
    http = ctx.get("http")
    if http is not None:
        await http.aclose()

    engine = ctx.get("engine")
    if engine is not None:
        await engine.dispose()


def worker_options(settings: Settings, *, embedded: bool = False) -> dict:
    """Build the shared ARQ worker configuration."""
    options = {
        "functions": [ingest_document],
        "redis_settings": redis_settings(settings.redis_url),
        "on_startup": startup,
        "on_shutdown": shutdown,
        "max_jobs": settings.ingest_concurrency,
        "job_timeout": settings.ingest_job_timeout,
        "max_tries": settings.ingest_max_tries,
        "handle_signals": not embedded,
    }

    if embedded:
        options["ctx"] = {"settings": settings}

    return options


async def run_embedded(
    settings: Settings,
    ready: asyncio.Event | None = None,
) -> None:
    """Run an ARQ worker inside the API process."""
    options = worker_options(settings, embedded=True)

    if ready is not None:

        async def embedded_startup(ctx: dict) -> None:
            await startup(ctx)
            ready.set()

        options["on_startup"] = embedded_startup

    worker = Worker(**options)

    try:
        await worker.async_run()
    except asyncio.CancelledError:
        raise
    except Exception:
        logger.exception("Embedded ingestion worker stopped unexpectedly")
    finally:
        # ARQ close() uses SIGUSR1 when signal handling is disabled.
        # SIGUSR1 is unavailable on Windows, so use portable SIGINT
        # and prevent close() from sending SIGUSR1 again.
        if not worker._handle_signals:
            worker.handle_sig(signal.SIGINT)
            worker._handle_signals = True

        await worker.close()


_settings = get_settings()


class WorkerSettings:
    """Configuration consumed by the ARQ worker."""

    functions = [ingest_document]
    redis_settings = redis_settings(_settings.redis_url)
    on_startup = startup
    on_shutdown = shutdown
    max_jobs = _settings.ingest_concurrency
    job_timeout = _settings.ingest_job_timeout
    max_tries = _settings.ingest_max_tries
