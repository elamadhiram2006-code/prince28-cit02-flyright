"""Health and readiness endpoints."""

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from flyright.api.deps import get_db_session

router = APIRouter()


@router.get("/health")
def health():
    """Check whether the API is running."""
    return {"status": "ok"}


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
