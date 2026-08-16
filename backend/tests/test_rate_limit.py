"""Tests for app/core/rate_limit.py's client-IP resolution specifically -
the part of Phase 9's rate limiting most likely to be silently wrong in
production without ever failing a test: deploy/nginx/comp-intel.conf
proxies to the backend on the same host, so request.client.host (what
slowapi's own get_remote_address reads) is always nginx's loopback
address there, not the real caller's IP. _get_client_ip's X-Forwarded-For
handling is the actual fix for that - untested, it would be exactly the
kind of "looks right, never verified" gap this phase exists to close.
"""

from fastapi import Request
from fastapi.testclient import TestClient

from app.core.rate_limit import _get_client_ip


def _request_with_headers(headers: list[tuple[bytes, bytes]]) -> Request:
    scope = {
        "type": "http",
        "headers": headers,
        "client": ("127.0.0.1", 12345),
    }
    return Request(scope)


def test_uses_the_direct_peer_address_when_no_x_forwarded_for_is_present() -> None:
    request = _request_with_headers([])
    assert _get_client_ip(request) == "127.0.0.1"


def test_uses_the_x_forwarded_for_value_when_present() -> None:
    request = _request_with_headers([(b"x-forwarded-for", b"203.0.113.7")])
    assert _get_client_ip(request) == "203.0.113.7"


def test_uses_the_last_x_forwarded_for_entry_not_the_first() -> None:
    """nginx's `proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for`
    APPENDS the real connecting IP to whatever a client already sent,
    rather than replacing it - so a client trying to spoof its own IP by
    pre-setting the header ends up as an earlier, untrusted entry, with
    nginx's own trusted value always last. Taking the first entry instead
    would let a client's own header claim any address it wants.
    """
    request = _request_with_headers(
        [(b"x-forwarded-for", b"203.0.113.7, 198.51.100.99, 10.0.0.5")]
    )
    assert _get_client_ip(request) == "10.0.0.5"


def test_two_distinct_x_forwarded_for_callers_get_independent_rate_limit_buckets(
    client: TestClient,
) -> None:
    """Full-stack proof, not just the unit-level _get_client_ip check
    above: two callers behind the same direct TestClient connection (same
    request.client.host) but presenting different X-Forwarded-For values
    must be rate-limited independently, exactly as they would be for two
    different real users behind deploy/nginx/comp-intel.conf. If this
    were broken - e.g. still keying on the raw peer address - caller B
    would inherit caller A's exhausted limit despite being a distinct
    real client.
    """
    from tests.test_auth_api import _AUTH_SENSITIVE_PER_MINUTE

    for _ in range(_AUTH_SENSITIVE_PER_MINUTE):
        response = client.post(
            "/api/v1/auth/login",
            json={"email": "xff-a@example.com", "password": "wrong"},
            headers={"X-Forwarded-For": "203.0.113.1"},
        )
        assert response.status_code == 401

    exhausted = client.post(
        "/api/v1/auth/login",
        json={"email": "xff-a@example.com", "password": "wrong"},
        headers={"X-Forwarded-For": "203.0.113.1"},
    )
    assert exhausted.status_code == 429

    # A different caller (different X-Forwarded-For), same direct
    # TestClient connection - must NOT be affected by caller A above.
    still_fine = client.post(
        "/api/v1/auth/login",
        json={"email": "xff-b@example.com", "password": "wrong"},
        headers={"X-Forwarded-For": "203.0.113.2"},
    )
    assert still_fine.status_code == 401
