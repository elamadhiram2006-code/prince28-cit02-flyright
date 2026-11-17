from fastapi import APIRouter, Depends, Query

from flyright.api.deps import get_store
from flyright.api.errors import AppError

router = APIRouter(prefix="/v1/documents", tags=["Documents"])


@router.get("")
def list_documents(
    q: str | None = None,
    limit: int = Query(default=10, ge=1, le=100),
    store=Depends(get_store),
):
    records = store.records

    if q:
        records = [record for record in records if q.lower() in str(record).lower()]

    return {"total": len(records), "items": records[:limit]}


@router.get("/{document_id}")
def get_document(
    document_id: str,
    store=Depends(get_store),
):
    for record in store.records:
        if record["id"] == document_id:
            return record

    raise AppError(status_code=404, detail=f"No document with id '{document_id}'.")
