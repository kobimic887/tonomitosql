"""FastAPI dependencies for authentication and common parameters."""
import hashlib
import logging
import time
from collections import defaultdict
from threading import Lock

from fastapi import HTTPException, Request, Security
from fastapi.security import APIKeyHeader

from app.db.session import get_db

logger = logging.getLogger(__name__)

# FastAPI security scheme — adds "Authorize" button in Swagger UI
api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)


# ---------- Rate limiter (brute-force protection) ----------
# Sliding window per IP: max AUTH_RATE_LIMIT failures within AUTH_RATE_WINDOW seconds.
# Successful authentications are NOT counted — only failures.
# Thread-safe via Lock (multi-worker uvicorn spawns threads per-worker).

AUTH_RATE_LIMIT = 20       # max failed auth attempts per window
AUTH_RATE_WINDOW = 60      # window in seconds
_fail_log: dict[str, list[float]] = defaultdict(list)
_fail_lock = Lock()


def _check_rate_limit(client_ip: str) -> None:
    """Raise 429 if client_ip exceeded failed auth rate limit."""
    now = time.monotonic()
    with _fail_lock:
        # Prune expired timestamps
        timestamps = _fail_log[client_ip]
        cutoff = now - AUTH_RATE_WINDOW
        _fail_log[client_ip] = [t for t in timestamps if t > cutoff]

        if len(_fail_log[client_ip]) >= AUTH_RATE_LIMIT:
            logger.warning("Rate limit exceeded for %s", client_ip)
            raise HTTPException(
                status_code=429,
                detail="Too many failed authentication attempts. Try again later.",
            )


def _record_failure(client_ip: str) -> None:
    """Record a failed auth attempt for rate limiting."""
    with _fail_lock:
        _fail_log[client_ip].append(time.monotonic())


def require_api_key(
    request: Request,
    api_key: str | None = Security(api_key_header),
) -> str:
    """Validate API key from X-API-Key header.

    Looks up SHA-256 hash of the provided key in the api_keys table.
    Returns the key name on success for logging/auditing.

    Rate-limited: after AUTH_RATE_LIMIT failed attempts within
    AUTH_RATE_WINDOW seconds from the same IP, returns 429.

    Raises:
        HTTPException 401: Missing or invalid API key
        HTTPException 429: Rate limit exceeded
    """
    client_ip = request.client.host if request.client else "unknown"

    # Check rate limit BEFORE doing any work
    _check_rate_limit(client_ip)

    if api_key is None:
        _record_failure(client_ip)
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
        _record_failure(client_ip)
        raise HTTPException(
            status_code=401,
            detail="Invalid API key.",
        )

    return row[0]  # Return key name for logging
