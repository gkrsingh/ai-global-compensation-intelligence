from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware

from app.ai.api import router as ai_router
from app.api.v1.health import router as health_router
from app.auth.api import router as auth_router
from app.comparison.api import router as comparison_router
from app.compensation.api import AUTH_WARNING_HEADER
from app.compensation.api import router as compensation_router
from app.core.config import settings
from app.core.exceptions import register_exception_handlers
from app.core.logging import configure_logging
from app.core.rate_limit import limiter, rate_limit_exceeded_handler
from app.core.request_id_middleware import RequestIdMiddleware
from app.core.security_headers import SecurityHeadersMiddleware
from app.market_data.api import router as market_data_router
from app.reference_data.api import router as reference_data_router

configure_logging()

app = FastAPI(title="AI Global Compensation Intelligence API")

app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, rate_limit_exceeded_handler)
# SlowAPIMiddleware is what actually enforces per-route @limiter.limit(...)
# decorators - app.state.limiter alone only makes the Limiter available,
# it doesn't hook request dispatch. Registered before CORSMiddleware (in
# add_middleware's LIFO execution order, that runs CORS's response-header
# injection AFTER a 429 is produced) so a browser-originated request that
# gets rate-limited still receives a CORS-compliant response its own JS
# can read, not one that instead fails as an opaque CORS error masking the
# real 429.
app.add_middleware(SlowAPIMiddleware)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.backend_cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    # Custom response headers aren't readable by browser JS on a
    # cross-origin fetch() unless explicitly exposed here - "*" in
    # allow_headers only covers what the browser is allowed to SEND, not
    # what it's allowed to READ back. Without this, AUTH_WARNING_HEADER
    # would be present in the raw HTTP response (visible in curl / the
    # network tab) but silently invisible to response.headers.get(...) in
    # the frontend.
    expose_headers=[AUTH_WARNING_HEADER],
)

app.add_middleware(SecurityHeadersMiddleware)

# Outermost (added last, so it's the first thing to see the request and
# the last to see the response) - the request id needs to be set in the
# ContextVar before anything else runs, including the rate limiter and
# its own logging, or an early 429/error response would be logged without
# a request id at all.
app.add_middleware(RequestIdMiddleware)

register_exception_handlers(app)

app.include_router(health_router, prefix="/api/v1")
app.include_router(auth_router, prefix="/api/v1")
app.include_router(reference_data_router, prefix="/api/v1")
app.include_router(compensation_router, prefix="/api/v1")
app.include_router(comparison_router, prefix="/api/v1")
app.include_router(ai_router, prefix="/api/v1")
app.include_router(market_data_router, prefix="/api/v1")
