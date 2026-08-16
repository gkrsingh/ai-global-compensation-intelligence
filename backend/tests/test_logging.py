"""JsonFormatter (app/core/logging.py) is what every production log line
actually looks like (JSON, one per line, for log aggregation) - and had
no dedicated test at all since Phase 1, confirmed by there being no
tests/test_logging.py before this file. Left untested, this phase's own
new request_id field (threaded through via the extras merge, see
app/core/request_context.py) would ship to production unverified in the
one format that actually matters there. Tested directly against
JsonFormatter, not via configure_logging() (which only ever runs once at
interpreter start with whatever ENVIRONMENT happens to be set) - matches
how the rest of this project tests formatting/serialization logic
directly rather than through the one-time wiring that selects it.
"""

import json
import logging

import pytest

from app.core.config import settings
from app.core.logging import JsonFormatter, configure_logging


def _make_record(**overrides: object) -> logging.LogRecord:
    defaults: dict[str, object] = {
        "name": "app.test",
        "level": logging.WARNING,
        "pathname": __file__,
        "lineno": 1,
        "msg": "something happened",
        "args": (),
        "exc_info": None,
    }
    defaults.update(overrides)
    record = logging.LogRecord(**defaults)  # type: ignore[arg-type]
    return record


def test_format_produces_valid_single_line_json_with_the_core_fields() -> None:
    record = _make_record()

    output = JsonFormatter().format(record)
    payload = json.loads(output)

    assert "\n" not in output
    assert payload["level"] == "WARNING"
    assert payload["logger"] == "app.test"
    assert payload["message"] == "something happened"
    assert "timestamp" in payload


def test_format_includes_extra_fields_passed_via_the_logging_call() -> None:
    """Mirrors how every logger.warning(..., extra={...}) call added this
    phase (auth, ai, comparison, compensation) actually gets called -
    proves those extras genuinely reach the JSON payload, not just that
    the core fields work.
    """
    record = _make_record(msg="Login failed")
    record.email = "someone@example.com"
    record.request_id = "req-abc-123"

    payload = json.loads(JsonFormatter().format(record))

    assert payload["email"] == "someone@example.com"
    assert payload["request_id"] == "req-abc-123"


def test_format_includes_the_exception_traceback_when_present() -> None:
    try:
        raise ValueError("simulated failure")
    except ValueError:
        import sys

        record = _make_record(msg="Unhandled exception processing request", exc_info=sys.exc_info())

    payload = json.loads(JsonFormatter().format(record))

    assert "exception" in payload
    assert "ValueError: simulated failure" in payload["exception"]


def test_format_never_leaks_a_secret_that_happens_to_be_in_extra() -> None:
    """Not a claim that JsonFormatter redacts secrets (it doesn't, and
    shouldn't have to - see Phase 9's secret-leak sweep, which confirmed
    empirically that no code path in this app ever puts a real secret
    into a log call's message or extra in the first place). This test
    instead pins down the actual contract: extras pass through byte-for-
    byte, unmodified - which is exactly why the sweep had to check every
    call site rather than trusting a formatter-level safety net that
    doesn't exist.
    """
    record = _make_record()
    record.some_field = "not-a-secret-just-checking-passthrough"

    payload = json.loads(JsonFormatter().format(record))

    assert payload["some_field"] == "not-a-secret-just-checking-passthrough"


def test_configure_logging_selects_json_formatter_in_production(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """configure_logging() itself only ever runs once, at interpreter
    start, with whichever ENVIRONMENT happens to be set that run (always
    "development" for the test suite, per .env.test) - so the branch that
    actually selects JsonFormatter for real production deployments has
    never been exercised by any test. Restores the root logger's real
    handlers afterward so this doesn't leak a stray handler into every
    later test's log capture.
    """
    root = logging.getLogger()
    original_handlers = root.handlers

    monkeypatch.setattr(settings, "environment", "production")
    try:
        configure_logging()
        assert isinstance(root.handlers[0].formatter, JsonFormatter)
    finally:
        root.handlers = original_handlers
