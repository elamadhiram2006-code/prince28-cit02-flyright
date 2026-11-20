"""Health and readiness endpoints."""

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from flyright.api.deps import get_app_settings, get_db_session
from flyright.config import Settings

router = APIRouter()


@router.get("/health")
def health(settings: Settings = Depends(get_app_settings)):
    """Check whether the API is running and report its version."""
    return {
        "status": "ok",
        "app": settings.app_name,
        "env": settings.app_env,
        "version": settings.git_sha,
    }


@router.get("/ready")
async def ready(session: AsyncSession = Depends(get_db_session)):
    """Check database connectivity."""
    try:
        await session.execute(text("SELECT 1"))
        return {"status": "ready", "checks": {"database": True}}
    except Exception:
        return JSONResponse(
            status_code=503,
            content={
                "status": "not_ready",
                "checks": {"database": False},
            },
        )
