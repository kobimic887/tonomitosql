from fastapi import APIRouter, HTTPException

from app.config import settings
from app.db.session import get_db
from app.models.schemas import HealthResponse

router = APIRouter(tags=["Health"])


@router.get("/health", response_model=HealthResponse)
def health_check():
    """
    Health check endpoint.

    Returns API version, database connection status, RDKit cartridge version,
    and current molecule count.
    """
    try:
        with get_db() as conn:
            with conn.cursor() as cur:
                # Check RDKit cartridge version
                cur.execute("SELECT rdkit_version();")
                rdkit_ver = cur.fetchone()[0]

                # Approximate molecule count — uses pg_class statistics instead of
                # COUNT(*) which does a full sequential scan on every call.
                # Accurate after ANALYZE runs (autovacuum does this periodically).
                cur.execute(
                    "SELECT reltuples::bigint FROM pg_class WHERE relname = 'molecules';"
                )
                mol_count = cur.fetchone()[0]

        return HealthResponse(
            status="healthy",
            api_version=settings.api_version,
            database="connected",
            rdkit_version=rdkit_ver,
            molecule_count=mol_count,
        )
    except Exception as e:
        raise HTTPException(
            status_code=503,
            detail={
                "status": "unhealthy",
                "api_version": settings.api_version,
                "database": f"error: {str(e)}",
                "rdkit_version": None,
                "molecule_count": 0,
            },
        )
