#!/usr/bin/env python3
"""Generate an API key and store its SHA-256 hash in the database.

Usage:
    python scripts/create-api-key.py [--name KEY_NAME]
    docker compose exec api python scripts/create-api-key.py --name "my-app"

The script prints the raw API key to stdout (this is the only time it's visible).
The SHA-256 hash is stored in the api_keys table.
"""
import argparse
import hashlib
import os
import secrets

import psycopg


def create_api_key(name: str) -> str:
    """Generate a random API key, store its hash, return the raw key."""
    database_url = os.environ.get(
        "DATABASE_URL",
        "postgresql://tonomito:tonomito_dev@db:5432/tonomitosql",
    )

    # Generate a 32-byte (256-bit) random key, URL-safe base64 encoded
    raw_key = secrets.token_urlsafe(32)
    key_hash = hashlib.sha256(raw_key.encode()).hexdigest()

    with psycopg.connect(database_url) as conn:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO api_keys (key_hash, name) VALUES (%s, %s) RETURNING id",
                (key_hash, name),
            )
            key_id = cur.fetchone()[0]
        conn.commit()

    return raw_key


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Generate an API key")
    parser.add_argument(
        "--name",
        default="default",
        help="Human-readable name for the key (default: 'default')",
    )
    args = parser.parse_args()

    key = create_api_key(args.name)
    print(f"API Key (save this — it won't be shown again): {key}")
