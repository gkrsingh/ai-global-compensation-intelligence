"""Per-request correlation id (Phase 9, original architecture §13).

A contextvars.ContextVar, not a plain module global: ASGI request
handling is concurrent (multiple in-flight requests share one event loop),
so a plain global would let one request's id leak into another's log
lines under real concurrency. ContextVar is per-async-task, which is
exactly the isolation a per-request value needs.
"""

import logging
from contextvars import ContextVar

request_id_var: ContextVar[str | None] = ContextVar("request_id", default=None)


class RequestIdLogFilter:
    """Attaches the active request's id (or "-" outside any request, e.g.
    a management script like fetch_exchange_rates.py) to every log
    record, so JsonFormatter's extras merge picks it up automatically -
    no caller has to remember to pass request_id into every individual
    logger.warning(..., extra={...}) call for it to show up. This is what
    makes "AI insight generation failed" in one log line and "created
    calculation X" in another actually correlatable to the same incoming
    HTTP request, which is the concrete, checkable meaning of "genuinely
    traceable" this phase's own audit asked for - not just "a request id
    exists somewhere."
    """

    def filter(self, record: logging.LogRecord) -> bool:
        record.request_id = request_id_var.get() or "-"
        return True
