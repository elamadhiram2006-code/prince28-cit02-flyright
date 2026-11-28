"""Database operations for ingestion jobs and their items."""

from uuid import uuid4

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from flyright.db.models import (
    Document,
    IngestItem,
    IngestJob,
    ParseFailure,
)


class IngestRepository:
    """Create ingestion jobs and track item progress."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def known_ids(self) -> set[str]:
        """Return hashes already parsed or previously marked as parse failures."""
        parsed = await self.session.scalars(
            select(Document.sha256).where(Document.doc_type != "record")
        )
        failed = await self.session.scalars(select(ParseFailure.sha256))
        return set(parsed).union(failed)

    async def create(self, records: list[dict]) -> str:
        """Create a job and its queued items."""
        job_id = uuid4().hex
        job = IngestJob(id=job_id, requested=len(records))
        job.items = [
            IngestItem(job_id=job_id, record=record, status="queued") for record in records
        ]
        self.session.add(job)
        await self.session.commit()
        return job_id

    async def progress(self, job_id: str) -> dict:
        """Return counts of items in each status."""
        rows = await self.session.execute(
            select(IngestItem.status, func.count(IngestItem.id))
            .where(IngestItem.job_id == job_id)
            .group_by(IngestItem.status)
        )
        counts = dict(rows.all())
        total = await self.session.scalar(
            select(func.count(IngestItem.id)).where(IngestItem.job_id == job_id)
        )
        return {
            "job_id": job_id,
            "total": total or 0,
            "queued": counts.get("queued", 0),
            "running": counts.get("running", 0),
            "done": counts.get("done", 0),
            "skipped": counts.get("skipped", 0),
            "failed": counts.get("failed", 0),
        }

    async def dead_letter(self, job_id: str) -> list[dict]:
        """Return failed items for inspection."""
        rows = await self.session.scalars(
            select(IngestItem)
            .where(
                IngestItem.job_id == job_id,
                IngestItem.status == "failed",
            )
            .order_by(IngestItem.id)
        )
        return [
            {
                "id": item.id,
                "record": item.record,
                "attempts": item.attempts,
                "error": item.error,
            }
            for item in rows
        ]

    async def failed_records(self, job_id: str) -> list[dict]:
        """Return the source records belonging to failed items."""
        rows = await self.session.scalars(
            select(IngestItem.record).where(
                IngestItem.job_id == job_id,
                IngestItem.status == "failed",
            )
        )
        return list(rows)

    async def open_item_ids(self, job_id: str) -> list[int]:
        """Return queued or running item IDs."""
        rows = await self.session.scalars(
            select(IngestItem.id)
            .where(
                IngestItem.job_id == job_id,
                IngestItem.status.in_(("queued", "running")),
            )
            .order_by(IngestItem.id)
        )
        return list(rows)
