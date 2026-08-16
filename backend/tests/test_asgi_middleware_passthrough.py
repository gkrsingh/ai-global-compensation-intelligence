"""RequestIdMiddleware and SecurityHeadersMiddleware both special-case
non-"http" ASGI scopes (lifespan startup/shutdown, websocket) by passing
straight through untouched - neither request ids nor security headers
mean anything for those. TestClient(app) used throughout the rest of the
suite never actually triggers a lifespan scope (it's constructed without
the `with TestClient(app) as client:` form that would), so that passthrough
branch is otherwise never exercised - tested directly here rather than
left as an unverified "should work" assumption.

Plain asyncio.run(), not pytest-asyncio/anyio test infrastructure: this
project has no async tests anywhere else, and standing up that
infrastructure for two one-line passthrough branches would be exactly the
kind of disproportionate abstraction this project avoids elsewhere.
"""

import asyncio

from app.core.request_id_middleware import RequestIdMiddleware
from app.core.security_headers import SecurityHeadersMiddleware


async def _noop_receive() -> dict[str, object]:
    return {}


async def _never_called_send(message: dict[str, object]) -> None:
    raise AssertionError("send should never be called for a passthrough scope")


def test_request_id_middleware_passes_through_a_non_http_scope_untouched() -> None:
    calls: list[dict[str, object]] = []

    async def downstream(scope: dict[str, object], receive: object, send: object) -> None:
        calls.append(scope)

    middleware = RequestIdMiddleware(downstream)  # type: ignore[arg-type]
    scope: dict[str, object] = {"type": "lifespan"}

    asyncio.run(middleware(scope, _noop_receive, _never_called_send))  # type: ignore[arg-type]

    assert calls == [scope]


def test_security_headers_middleware_passes_through_a_non_http_scope_untouched() -> None:
    calls: list[dict[str, object]] = []

    async def downstream(scope: dict[str, object], receive: object, send: object) -> None:
        calls.append(scope)

    middleware = SecurityHeadersMiddleware(downstream)  # type: ignore[arg-type]
    scope: dict[str, object] = {"type": "lifespan"}

    asyncio.run(middleware(scope, _noop_receive, _never_called_send))  # type: ignore[arg-type]

    assert calls == [scope]
