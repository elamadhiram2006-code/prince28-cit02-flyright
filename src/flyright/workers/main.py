"""ARQ worker configuration and application lifecycle."""

from flyright.config import get_settings
from flyright.db.llm_calls import make_recorder
from flyright.db.session import make_engine, make_sessionmaker
from flyright.ingest.fetch import make_client
from flyright.llm.gateway import build_gateway
from flyright.logging_setup import setup_logging
from flyright.workers.ingest import Pace, ingest_document
from flyright.workers.queue import redis_settings


async def startup(ctx: dict) -> None:
    """Initialize resources required by ingestion jobs."""
    settings = get_settings()
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


async def shutdown(ctx: dict) -> None:
    """Close worker resources cleanly."""
    http = ctx.get("http")
    if http is not None:
        await http.aclose()

    engine = ctx.get("engine")
    if engine is not None:
        await engine.dispose()


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
