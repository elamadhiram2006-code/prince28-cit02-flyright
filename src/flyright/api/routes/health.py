from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

router = APIRouter()


@router.get("/health")
def health():
    return {"status": "ok"}


@router.get("/ready")
def ready(request: Request):
    store = getattr(request.app.state, "store", None)

    records_loaded = store is not None and len(store.get_all()) > 0

    if records_loaded:
        return {"status": "ready", "checks": {"records_loaded": True}}

    return JSONResponse(
        status_code=503, content={"status": "not_ready", "checks": {"records_loaded": False}}
    )
