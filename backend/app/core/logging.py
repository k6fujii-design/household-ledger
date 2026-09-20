import json
import logging
import traceback
from datetime import datetime, timezone, timedelta
from typing import Any

JST = timezone(timedelta(hours=9))


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "timestamp": datetime.now(JST).isoformat(),
            "level": record.levelname,
            "event": getattr(record, "event", record.getMessage()),
        }
        for key in (
            "request_id",
            "conversation_id",
            "line_user_hash",
            "user_id",
            "ticket_id",
            "action",
            "intent",
            "pending_intent",
            "tool",
            "duration_ms",
            "details",
        ):
            value = getattr(record, key, None)
            if value is not None:
                payload[key] = value
        if record.exc_info:
            payload["exception"] = "".join(traceback.format_exception(*record.exc_info)).rstrip()
        return json.dumps(payload, ensure_ascii=False, default=str)


def setup_logging() -> None:
    handler = logging.StreamHandler()
    handler.setFormatter(JsonFormatter())
    logging.basicConfig(level=logging.INFO, handlers=[handler], force=True)
