"""Phase 9: proves the security headers are genuinely present on real
responses, not just that the middleware is registered in main.py. Checked
against a plain, unauthenticated GET so this can't be confused with any
route-specific behavior - these headers are meant to apply universally.
"""

from fastapi.testclient import TestClient


def test_response_includes_the_standard_security_headers(client: TestClient) -> None:
    response = client.get("/api/v1/health")

    assert response.headers["X-Content-Type-Options"] == "nosniff"
    assert response.headers["X-Frame-Options"] == "DENY"
    assert response.headers["Referrer-Policy"] == "no-referrer"


def test_security_headers_are_present_even_on_an_error_response(client: TestClient) -> None:
    """A 404/error response is generated on a different code path than a
    normal 200 (FastAPI's exception handling) - confirming the middleware
    wraps ALL responses, not just the happy path, which is exactly the
    kind of gap a middleware registered too narrowly (or in the wrong
    order relative to exception handling) could have.
    """
    response = client.get("/api/v1/this-route-does-not-exist")

    assert response.status_code == 404
    assert response.headers["X-Content-Type-Options"] == "nosniff"
    assert response.headers["X-Frame-Options"] == "DENY"


# Routes added AFTER the Phase 9 hardening pass. Phase 9 applied rate
# limiting per-route via decorator, so it was worth confirming - by real
# HTTP requests against a running server, not by re-reading main.py -
# that the APP-WIDE middleware genuinely reaches routes registered later.
# It does. These tests pin that down so a route added in some future
# phase cannot quietly miss it: the failure mode is silent, since a
# missing header breaks nothing visible.
_POST_PHASE_9_ROUTES = [
    "/api/v1/job-families",
    "/api/v1/market-context?job_family_id=1&country_code=US",
]


def test_routes_added_after_the_hardening_pass_still_get_the_middleware(
    client: TestClient,
) -> None:
    for path in _POST_PHASE_9_ROUTES:
        response = client.get(path)

        assert response.headers["X-Content-Type-Options"] == "nosniff", path
        assert response.headers["X-Frame-Options"] == "DENY", path
        assert response.headers["Referrer-Policy"] == "no-referrer", path
        # Request-ID tracing must reach them too, or a request through one
        # of these endpoints would be untraceable in the logs.
        assert response.headers.get("X-Request-Id"), path


def test_a_caller_supplied_request_id_is_honoured_on_the_newer_routes(
    client: TestClient,
) -> None:
    response = client.get(
        "/api/v1/market-context?job_family_id=1&country_code=US",
        headers={"X-Request-Id": "polish-probe-123"},
    )

    assert response.headers["X-Request-Id"] == "polish-probe-123"
