import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.config import settings
from app.db.session import pool
from app.routers import health, search, upload

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Manage application lifecycle — clean up connection pool on shutdown."""
    logger.info("Starting TonomitoSQL API")
    yield
    logger.info("Shutting down — closing connection pool")
    pool.close()


app = FastAPI(
    title=settings.api_title,
    description=settings.api_description,
    version=settings.api_version,
    lifespan=lifespan,
)

app.include_router(health.router)
app.include_router(upload.router)
app.include_router(search.router)
