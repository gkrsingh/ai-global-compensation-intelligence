"""Phase 9 observability audit: the Phase 9 kickoff assumed a request-id
middleware already existed from Phase 1. It didn't - confirmed by
grepping the whole app tree before writing any of this - so these tests
prove the one built for this phase actually does what "genuinely
traceable" requires: a real caller-supplied id gets threaded through and
echoed back, a caller with no id gets a fresh one, and - the part that
actually matters for tracing a request through logs, not just round-
tripping a header - a log line emitted while handling that request
carries the same id.
"""

import logging

import pytest
from fastapi.testclient import TestClient


def test_response_echoes_a_caller_supplied_request_id(client: TestClient) -> None:
    response = client.get("/api/v1/health", headers={"X-Request-Id": "caller-supplied-id-123"})

    assert response.headers["X-Request-Id"] == "caller-supplied-id-123"


def test_response_gets_a_generated_request_id_when_the_caller_sends_none(
    client: TestClient,
) -> None:
    response = client.get("/api/v1/health")

    request_id = response.headers.get("X-Request-Id")
    assert request_id is not None and len(request_id) > 0


def test_two_requests_with_no_caller_supplied_id_get_different_ids(client: TestClient) -> None:
    first = client.get("/api/v1/health").headers["X-Request-Id"]
    second = client.get("/api/v1/health").headers["X-Request-Id"]

    assert first != second


def test_a_log_line_emitted_while_handling_a_request_carries_that_requests_id(
    client: TestClient, caplog: pytest.LogCaptureFixture
) -> None:
    """The actual point of this middleware: proving a request id round-
    trips in the response header is necessary but not sufficient - the
    id also has to show up on log records emitted while handling that
    same request, or there is nothing to actually correlate against in
    production log output. Triggers a real WARNING log line (an invalid
    login) rather than asserting against internal implementation detail.
    """
    with caplog.at_level(logging.WARNING):
        response = client.post(
            "/api/v1/auth/login",
            json={"email": "request-id-trace-probe@example.com", "password": "wrong"},
            headers={"X-Request-Id": "trace-probe-request-id"},
        )

    assert response.status_code == 401
    login_failed_records = [r for r in caplog.records if r.getMessage() == "Login failed"]
    assert len(login_failed_records) == 1
    assert login_failed_records[0].request_id == "trace-probe-request-id"  # type: ignore[attr-defined]
