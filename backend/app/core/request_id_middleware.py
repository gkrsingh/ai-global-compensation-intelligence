"""ASGI middleware pairing with app/core/request_context.py: assigns each
incoming request an id (reusing an inbound X-Request-Id if the reverse
proxy or a calling service already set one, generating a fresh uuid4
otherwise), makes it available to every log line emitted while handling
that request via the ContextVar, and echoes it back on the response so a
caller (or a human reading a bug report) can hand the exact id back to
correlate their one request against server-side logs.
"""

import uuid

from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.core.request_context import request_id_var

_HEADER_NAME = b"x-request-id"


class RequestIdMiddleware:
    def __init__(self, app: ASGIApp) -> None:
        self._app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self._app(scope, receive, send)
            return

        inbound = next(
            (value for key, value in scope.get("headers", []) if key == _HEADER_NAME),
            None,
        )
        request_id = inbound.decode("latin-1") if inbound else str(uuid.uuid4())
        token = request_id_var.set(request_id)

        async def send_with_request_id(message: Message) -> None:
            if message["type"] == "http.response.start":
                headers = list(message.get("headers", []))
                headers.append((_HEADER_NAME, request_id.encode("latin-1")))
                message = {**message, "headers": headers}
            await send(message)

        try:
            await self._app(scope, receive, send_with_request_id)
        finally:
            # Resets rather than leaves set: ASGI can reuse the same task/
            # context for more than one message under some server
            # configurations, and an un-reset ContextVar could otherwise
            # leak this request's id into whatever runs next in the same
            # context.
            request_id_var.reset(token)
