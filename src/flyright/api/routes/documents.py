"""Document API endpoints."""

from fastapi import APIRouter, Depends, Query, Request

from flyright.api.deps import get_repo
from flyright.api.errors import AppError
from flyright.db.repository import DocumentRepository

router = APIRouter(prefix="/v1/documents", tags=["Documents"])


@router.get("")
async def list_documents(
    request: Request,
    q: str | None = None,
    limit: int = Query(default=10, ge=1, le=100),
    repository: DocumentRepository = Depends(get_repo),
):
    """List documents with optional text search and metadata filters."""
    filters = {
        key: value for key, value in request.query_params.items() if key not in {"q", "limit"}
    }

    try:
        total, items = await repository.list(
            q=q,
            limit=limit,
            filters=filters,
        )
    except ValueError as exc:
        raise AppError(status_code=400, detail=str(exc)) from exc

    return {"total": total, "items": items}


@router.get("/{document_id}")
async def get_document(
    document_id: str,
    repository: DocumentRepository = Depends(get_repo),
):
    """Retrieve a document by ID."""
    document = await repository.get(document_id)

    if document is None:
        raise AppError(
            status_code=404,
            detail=f"No document with id '{document_id}'.",
        )

    return document
