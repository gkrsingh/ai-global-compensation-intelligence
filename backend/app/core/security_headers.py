"""Standard security response headers (Phase 9, original architecture
§14). A pure-JSON API has a narrower attack surface than an HTML-serving
app, but this API also serves interactive Swagger/Redoc docs at /docs and
/redoc, and every response is still a page a browser can be tricked into
framing or MIME-sniffing regardless of content type - these headers cost
nothing and close that off explicitly rather than relying on "we only
return JSON" as an implicit, unverified assumption.

Deliberately NOT setting Strict-Transport-Security: deploy/nginx/comp-
intel.conf listens on plain :80 with TLS explicitly out of scope for now
(see its own comment). HSTS is meaningless without TLS, and forcing it at
the app layer - which has no way to know whether it's actually being
served over HTTPS - would be building for infrastructure that doesn't
exist yet, which this phase's own instructions rule out. Add it at the
reverse-proxy layer once TLS termination exists there.

Deliberately NOT setting X-XSS-Protection: deprecated, ignored by every
current browser, and its legacy behavior in old browsers could actually
introduce an XSS vector in some cases - modern guidance (MDN, OWASP) is to
omit it entirely and rely on CSP instead, not to set it defensively.
"""

from starlette.types import ASGIApp, Message, Receive, Scope, Send


class SecurityHeadersMiddleware:
    def __init__(self, app: ASGIApp) -> None:
        self._app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self._app(scope, receive, send)
            return

        async def send_with_headers(message: Message) -> None:
            if message["type"] == "http.response.start":
                headers = list(message.get("headers", []))
                headers.extend(
                    (key.encode("latin-1"), value.encode("latin-1"))
                    for key, value in _SECURITY_HEADERS.items()
                )
                message = {**message, "headers": headers}
            await send(message)

        await self._app(scope, receive, send_with_headers)


_SECURITY_HEADERS: dict[str, str] = {
    # Stops a browser from MIME-sniffing a response into executing as
    # something other than its declared Content-Type (e.g. treating a
    # JSON error body as HTML/JS because it starts with something the
    # browser's sniffer misreads).
    "X-Content-Type-Options": "nosniff",
    # Blocks this API's responses (including /docs and /redoc) from being
    # rendered inside a <frame>/<iframe> on another site - clickjacking
    # defense. DENY, not SAMEORIGIN: nothing in this app legitimately
    # frames itself.
    "X-Frame-Options": "DENY",
    # Never send this origin's URL (which can include auth-adjacent path
    # segments) as a Referer header to a third party a response might link
    # to. no-referrer, not a same-origin-permissive policy: an API has no
    # legitimate reason to leak referrer information anywhere.
    "Referrer-Policy": "no-referrer",
}
