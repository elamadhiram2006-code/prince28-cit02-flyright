"""Application dependencies."""

from collections.abc import AsyncIterator

from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from flyright.config import Settings, get_settings
from flyright.db.repository import DocumentRepository


def get_app_settings() -> Settings:
    """Return application settings."""
    return get_settings()


async def get_db_session(request: Request) -> AsyncIterator[AsyncSession]:
    """Provide a database session."""
    session_factory = request.app.state.session_factory

    async with session_factory() as session:
        yield session


async def get_repo(
    session: AsyncSession = Depends(get_db_session),
) -> DocumentRepository:
    """Provide the document repository."""
    return DocumentRepository(session)
