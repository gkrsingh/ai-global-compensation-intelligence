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
