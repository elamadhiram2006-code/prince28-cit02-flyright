"""Configure structured JSON logging and request ID context."""

import json
import logging
import sys
from contextvars import ContextVar

request_id_ctx: ContextVar[str] = ContextVar("request_id", default="")


class JSONFormatter(logging.Formatter):
    def format(self, record):
        log_data = {
            "level": record.levelname,
            "msg": record.getMessage(),
        }

        request_id = getattr(record, "request_id", None) or request_id_ctx.get()

        if request_id:
            log_data["request_id"] = request_id

        if hasattr(record, "method"):
            log_data["method"] = record.method

        if hasattr(record, "path"):
            log_data["path"] = record.path

        if hasattr(record, "duration"):
            log_data["duration"] = record.duration

        return json.dumps(log_data)


def setup_logging(level="INFO"):
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JSONFormatter())

    logging.basicConfig(level=level, handlers=[handler], force=True)
