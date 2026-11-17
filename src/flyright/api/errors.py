from fastapi import Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse


class AppError(Exception):
    def __init__(self, status_code: int, detail: str):
        self.status_code = status_code
        self.detail = detail


async def app_error_handler(request: Request, exc: AppError):
    return JSONResponse(
        status_code=exc.status_code,
        media_type="application/problem+json",
        content={
            "type": "about:blank",
            "title": "Not Found" if exc.status_code == 404 else "Error",
            "status": exc.status_code,
            "detail": exc.detail,
            "instance": request.url.path,
            "request_id": getattr(request.state, "request_id", None),
        },
    )


async def validation_error_handler(request: Request, exc: RequestValidationError):
    errors = [
        {"field": ".".join(str(part) for part in error["loc"]), "message": error["msg"]}
        for error in exc.errors()
    ]

    return JSONResponse(
        status_code=422,
        media_type="application/problem+json",
        content={
            "type": "about:blank",
            "title": "Unprocessable Entity",
            "status": 422,
            "instance": request.url.path,
            "request_id": getattr(request.state, "request_id", None),
            "errors": errors,
        },
    )
