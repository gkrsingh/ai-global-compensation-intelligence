import json
import logging
import sys
from datetime import UTC, datetime

from app.core.config import settings
from app.core.request_context import RequestIdLogFilter

_SAMPLE_RECORD = logging.LogRecord(
    name="", level=0, pathname="", lineno=0, msg="", args=(), exc_info=None
)
_RESERVED_ATTRS = set(_SAMPLE_RECORD.__dict__.keys()) | {"message"}


class JsonFormatter(logging.Formatter):
    """Structured single-line JSON formatter for production log aggregation."""

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, object] = {
            "timestamp": datetime.fromtimestamp(record.created, tz=UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)

        extras = {
            key: value for key, value in record.__dict__.items() if key not in _RESERVED_ATTRS
        }
        payload.update(extras)

        return json.dumps(payload, default=str)


def configure_logging() -> None:
    handler = logging.StreamHandler(sys.stdout)
    if settings.environment == "production":
        handler.setFormatter(JsonFormatter())
    else:
        # request_id included here too (not just JsonFormatter's automatic
        # extras merge) - a request id that's only traceable in
        # production, and invisible in the dev console where most actual
        # debugging happens, would defeat the point of adding it.
        handler.setFormatter(
            logging.Formatter("%(asctime)s %(levelname)s %(name)s [%(request_id)s]: %(message)s")
        )
    # Attached to the handler, not the logger: a filter on the logger
    # itself only runs for records created through that specific logger,
    # but every module's own `logging.getLogger(__name__)` needs
    # request_id populated the same way - putting it on the shared root
    # handler covers all of them from one place.
    handler.addFilter(RequestIdLogFilter())

    root = logging.getLogger()
    root.handlers = [handler]
    root.setLevel(settings.log_level)
