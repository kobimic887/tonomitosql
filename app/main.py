from fastapi import FastAPI

from app.config import settings
from app.routers import health

app = FastAPI(
    title=settings.api_title,
    description=settings.api_description,
    version=settings.api_version,
)

app.include_router(health.router)
