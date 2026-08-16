"""In-process rate limiting (Phase 9, original architecture §14).

An in-process limiter (slowapi, backed by an in-memory counter) is
deliberately sufficient here - this project runs a small, fixed number of
Gunicorn/Uvicorn worker processes on a single host (see
deploy/systemd/comp-intel-backend.service), not a horizontally-scaled
fleet, so there is no shared state to coordinate across instances. Redis-
backed or otherwise distributed limiting would be real infrastructure this
project has deliberately excluded since Phase 1 for a project at this
scale, not a missing piece.

Keyed uniformly by remote IP address (get_remote_address), including on
the authenticated POST /ai-insights endpoint. The alternative - keying by
authenticated user id there - would need the limiter's key_func to decode
the caller's JWT itself, duplicating app.auth.tokens.decode_access_token's
logic in a second place a future bug could hide, just to save sharing one
limit bucket across users behind the same NAT/office IP. That's a real,
accepted tradeoff, not an oversight: IP-based limiting still bounds the
cost/abuse exposure this endpoint cares about (a single caller hammering
it), which is the actual risk being defended against.
"""

import logging

from fastapi import Request
from slowapi import Limiter
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address
from starlette.responses import JSONResponse

logger = logging.getLogger(__name__)


def _get_client_ip(request: Request) -> str:
    """slowapi's own get_remote_address reads request.client.host - the
    direct TCP peer. That's correct for local dev/tests (uvicorn or
    TestClient hit directly), but WRONG in production: deploy/nginx/
    comp-intel.conf proxies to 127.0.0.1:8000 on the same host, so every
    request's direct peer is nginx itself. Using raw get_remote_address in
    production would key every real user into the same shared bucket -
    confirmed by reading get_remote_address's source, not assumed - which
    is either "one abusive caller locks out everyone" or "the per-IP limit
    is meaningless," depending which direction you look at it from.

    nginx's own `proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for`
    APPENDS the real connecting IP to any X-Forwarded-For a client already
    sent, rather than replacing it - so a spoofed client-supplied value
    ends up as an earlier entry in the list, with nginx's own trusted value
    always last. Taking the last entry (not the first, and not a naive
    single-value read) is what makes this safe against a client trying to
    fake its own IP by pre-setting the header.
    """
    forwarded_for = request.headers.get("x-forwarded-for")
    if forwarded_for:
        return forwarded_for.split(",")[-1].strip()
    return get_remote_address(request)


limiter = Limiter(key_func=_get_client_ip)

# Auth endpoints: tight enough to make automated credential-stuffing/
# registration-spam impractical, loose enough that a real user mistyping a
# password a few times, or a browser silently refreshing across a couple
# of open tabs, never notices. Refresh/logout get a higher ceiling than
# login/register because legitimate clients call them automatically and
# more frequently during ordinary use, not just when a human is typing.
AUTH_SENSITIVE_LIMIT = "5/minute"
AUTH_ROUTINE_LIMIT = "20/minute"

# AI insight generation makes a real, externally-billed API call
# (Anthropic or Gemini) on a cache miss - this is the direct mitigation
# for Phase 8's live billing exposure. 10/minute per IP is well above any
# realistic legitimate usage (a user generates an insight per calculation/
# comparison, not repeatedly - and a repeat call for the same target is
# served from cache without hitting the provider at all, see
# app/ai/orchestration.py's caching), while still bounding worst-case
# spend from a single abusive caller.
AI_INSIGHT_LIMIT = "10/minute"


def rate_limit_exceeded_handler(request: Request, exc: Exception) -> JSONResponse:
    """Matches app.core.exceptions._error_envelope's shape, so a 429 looks
    like every other error this API returns instead of slowapi's own
    default response shape. A trip is a security-relevant event (a caller
    hammering an auth or cost-sensitive endpoint) worth a real log line,
    not just a silent 429 - the same "logs should be genuinely useful for
    tracing what happened" standard as the rest of this phase.
    """
    assert isinstance(exc, RateLimitExceeded)
    logger.warning(
        "Rate limit exceeded",
        extra={
            "path": request.url.path,
            "client_ip": _get_client_ip(request),
            "limit": str(exc.detail),
        },
    )
    return JSONResponse(
        status_code=429,
        content={
            "error": {
                "code": "rate_limit_exceeded",
                "message": "Too many requests. Please try again later.",
                "details": None,
            }
        },
    )
