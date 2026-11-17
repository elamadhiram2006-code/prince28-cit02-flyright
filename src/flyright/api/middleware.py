import logging
import time
import uuid

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware

logger = logging.getLogger("flyright")


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):

        # Get or create request ID
        request_id = request.headers.get("X-Request-ID", str(uuid.uuid4()))

        # Save request ID so error handlers can access it
        request.state.request_id = request_id

        # Start timer
        start_time = time.time()

        try:
            response = await call_next(request)

            response.headers["X-Request-ID"] = request_id

            return response

        except Exception:
            logger.exception("Request failed", extra={"request_id": request_id})
            raise

        finally:
            duration = time.time() - start_time

            logger.info(
                "Request completed",
                extra={
                    "request_id": request_id,
                    "method": request.method,
                    "path": request.url.path,
                    "duration": round(duration, 4),
                },
            )
