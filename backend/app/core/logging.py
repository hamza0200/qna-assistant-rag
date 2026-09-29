"""Structured JSON logging with a per-request ID.

Why JSON: log aggregators (CloudWatch, Datadog, Loki) can index fields like
`request_id` or `llm_latency_ms` directly instead of regex-parsing text.
Why a ContextVar: async handlers interleave on one thread, so a thread-local
would leak IDs between requests; ContextVars are scoped to each task.
"""

import json
import logging
import sys
from contextvars import ContextVar
from datetime import UTC, datetime
from typing import Any

request_id_var: ContextVar[str] = ContextVar("request_id", default="-")

# Attributes every LogRecord has; anything else was passed via `extra=` and is ours.
_RESERVED = set(logging.makeLogRecord({}).__dict__) | {"message", "asctime"}


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "ts": datetime.now(UTC).isoformat(timespec="milliseconds"),
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
            "request_id": request_id_var.get(),
        }
        for key, value in record.__dict__.items():
            if key not in _RESERVED and not key.startswith("_"):
                payload[key] = value
        if record.exc_info:
            payload["exc"] = self.formatException(record.exc_info)
        return json.dumps(payload, default=str)


def setup_logging(level: str = "INFO") -> None:
    """Route all logging (ours, uvicorn's, sqlalchemy's) through the JSON formatter."""
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter())
    root = logging.getLogger()
    root.handlers = [handler]
    root.setLevel(level)
    for name in ("uvicorn", "uvicorn.error", "uvicorn.access"):
        logging.getLogger(name).handlers = []
        logging.getLogger(name).propagate = True
    # Uvicorn's access log duplicates our request log middleware.
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
