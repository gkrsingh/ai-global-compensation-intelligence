from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.v1.health import router as health_router
from app.auth.api import router as auth_router
from app.compensation.api import router as compensation_router
from app.core.config import settings
from app.core.exceptions import register_exception_handlers
from app.core.logging import configure_logging
from app.reference_data.api import router as reference_data_router

configure_logging()

app = FastAPI(title="AI Global Compensation Intelligence API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.backend_cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

register_exception_handlers(app)

app.include_router(health_router, prefix="/api/v1")
app.include_router(auth_router, prefix="/api/v1")
app.include_router(reference_data_router, prefix="/api/v1")
app.include_router(compensation_router, prefix="/api/v1")
