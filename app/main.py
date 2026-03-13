import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.config import settings
from app.db.session import pool
from app.routers import datasets, health, search, upload

logger = logging.getLogger(__name__)

# Configure root logger from LOG_LEVEL env var
logging.basicConfig(
    level=getattr(logging, settings.log_level.upper(), logging.INFO),
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Manage application lifecycle — clean up connection pool on shutdown."""
    logger.info("Starting TonomitoSQL API v%s", settings.api_version)
    yield
    logger.info("Shutting down — closing connection pool")
    pool.close()


app = FastAPI(
    title=settings.api_title,
    description=settings.api_description,
    version=settings.api_version,
    lifespan=lifespan,
)

# Health check at root — no version prefix (standard for load balancers / orchestrators)
app.include_router(health.router)

# All API endpoints under /v1 prefix
API_V1_PREFIX = "/v1"
app.include_router(upload.router, prefix=API_V1_PREFIX)
app.include_router(search.router, prefix=API_V1_PREFIX)
app.include_router(datasets.router, prefix=API_V1_PREFIX)
