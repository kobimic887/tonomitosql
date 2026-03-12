from fastapi import FastAPI

from app.config import settings
from app.routers import health, search, upload

app = FastAPI(
    title=settings.api_title,
    description=settings.api_description,
    version=settings.api_version,
)

app.include_router(health.router)
app.include_router(upload.router)
app.include_router(search.router)
