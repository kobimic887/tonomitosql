from contextlib import contextmanager

from psycopg_pool import ConnectionPool

from app.config import settings

pool = ConnectionPool(
    conninfo=settings.database_url,
    min_size=2,
    max_size=10,
    timeout=30,        # Seconds to wait for a connection before raising PoolTimeout
    max_waiting=20,    # Max queued requests — fail fast instead of unbounded queue
    max_idle=300,      # Close idle connections after 5 minutes
)


@contextmanager
def get_db():
    """Get a database connection from the pool."""
    with pool.connection() as conn:
        yield conn
