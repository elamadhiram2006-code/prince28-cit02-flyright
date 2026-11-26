"""Application dependencies."""

from collections.abc import AsyncIterator
from typing import Annotated

from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from flyright.config import Settings, get_settings
from flyright.db.llm_calls import UsageRepository
from flyright.db.repository import DocumentRepository
from flyright.llm.gateway import LLMGateway


def get_app_settings() -> Settings:
    """Return application settings."""
    return get_settings()


async def get_db_session(request: Request) -> AsyncIterator[AsyncSession]:
    """Provide a database session."""
    session_factory = request.app.state.session_factory

    async with session_factory() as session:
        yield session


async def get_repo(
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> DocumentRepository:
    """Provide the document repository."""
    return DocumentRepository(session)


def get_gateway(request: Request) -> LLMGateway:
    """Provide the configured LLM gateway."""
    return request.app.state.gateway


async def get_usage_repo(
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> UsageRepository:
    """Provide the usage repository."""
    return UsageRepository(session)


SettingsDep = Annotated[Settings, Depends(get_app_settings)]
GatewayDep = Annotated[LLMGateway, Depends(get_gateway)]
UsageDep = Annotated[UsageRepository, Depends(get_usage_repo)]
