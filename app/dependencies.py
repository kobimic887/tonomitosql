"""FastAPI dependencies for authentication and common parameters."""
import hashlib

from fastapi import HTTPException, Security
from fastapi.security import APIKeyHeader

from app.db.session import get_db

# FastAPI security scheme — adds "Authorize" button in Swagger UI
api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)


def require_api_key(api_key: str | None = Security(api_key_header)) -> str:
    """Validate API key from X-API-Key header.

    Looks up SHA-256 hash of the provided key in the api_keys table.
    Returns the key name on success for logging/auditing.

    Raises:
        HTTPException 401: Missing or invalid API key
    """
    if api_key is None:
        raise HTTPException(
            status_code=401,
            detail="Missing API key. Include X-API-Key header.",
        )

    key_hash = hashlib.sha256(api_key.encode()).hexdigest()

    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT name FROM api_keys WHERE key_hash = %s AND active = true",
                (key_hash,),
            )
            row = cur.fetchone()

    if row is None:
        raise HTTPException(
            status_code=401,
            detail="Invalid API key.",
        )

    return row[0]  # Return key name for logging
