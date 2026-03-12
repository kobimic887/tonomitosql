from contextlib import contextmanager

from psycopg_pool import ConnectionPool

from app.config import settings

pool = ConnectionPool(conninfo=settings.database_url, min_size=2, max_size=10)


@contextmanager
def get_db():
    """Get a database connection from the pool."""
    with pool.connection() as conn:
        yield conn
