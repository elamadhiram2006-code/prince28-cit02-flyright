"""PostgreSQL repository for document operations."""

import re
from typing import Any

from sqlalchemy import Text, cast, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from flyright.db.models import Document

FILTER_KEY = re.compile(r"^[a-z_][a-z0-9_]{0,40}$")


def to_dict(doc: Document) -> dict[str, Any]:
    """Convert a document model into the API response format."""
    return {
        "id": doc.external_id,
        **(doc.metadata_ or {}),
        "title": doc.title,
        "doc_type": doc.doc_type,
        "source_url": doc.source_url,
        "licence": doc.licence,
        "published_on": doc.published_on.isoformat() if doc.published_on else None,
    }


class DocumentRepository:
    """Read and filter documents stored in PostgreSQL."""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def list(
        self,
        q: str | None = None,
        limit: int = 10,
        filters: dict[str, Any] | None = None,
    ) -> tuple[int, list[dict[str, Any]]]:
        """Return the total matching count and a limited list of documents."""
        query = select(Document)

        if q:
            pattern = f"%{q}%"
            query = query.where(
                or_(
                    Document.title.ilike(pattern),
                    cast(Document.metadata_, Text).ilike(pattern),
                )
            )

        for key, value in (filters or {}).items():
            if not FILTER_KEY.fullmatch(key):
                raise ValueError(f"Invalid filter key: {key}")

            if (
                isinstance(value, (str, bool, int, float))
                or isinstance(value, list)
                and all(isinstance(item, str) for item in value)
            ):
                query = query.where(Document.metadata_.contains({key: value}))
            else:
                raise ValueError(f"Unsupported filter value for '{key}'")

        count_query = select(func.count()).select_from(query.order_by(None).subquery())
        total = await self.session.scalar(count_query)

        result = await self.session.scalars(query.order_by(Document.id).limit(limit))
        return total or 0, [to_dict(doc) for doc in result.all()]

    async def get(self, document_id: str) -> dict[str, Any] | None:
        """Return one document by its external ID."""
        result = await self.session.scalar(
            select(Document).where(Document.external_id == document_id)
        )
        return to_dict(result) if result else None
