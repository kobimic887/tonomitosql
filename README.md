# TonomitoSQL

Molecular search API powered by PostgreSQL + RDKit. Upload CSV datasets of molecules, then run substructure and similarity searches using the RDKit cartridge — all through a REST API.

## Stack

- **API:** FastAPI + Uvicorn (Python 3.12)
- **Database:** PostgreSQL with [RDKit cartridge](https://www.rdkit.org/docs/Cartridge.html)
- **Connection:** psycopg3 connection pool (sync, no ORM)
- **Containers:** Docker Compose

## Quick Start

```bash
cp .env.example .env    # edit credentials if needed
docker compose up
```

The API starts at `http://localhost:8000`. The database initializes automatically on first run (RDKit extension, schema, indexes).

## Endpoints

| Method | Path | Description |
|--------|------|-------------|
| GET | `/health` | API version, DB status, RDKit version, molecule count |
| GET | `/docs` | Swagger UI (auto-generated) |
| GET | `/openapi.json` | OpenAPI spec |

## Database Schema

Three tables created automatically by `scripts/init-db.sh`:

- **datasets** — tracks CSV uploads (name, filename, row count)
- **molecules** — SMILES strings stored as RDKit `mol` type with GiST index for substructure search
- **fingerprints** — precomputed Morgan fingerprints (`bfp` type) with GiST index for Tanimoto similarity

## Project Structure

```
app/
  main.py          # FastAPI app factory
  config.py        # Settings via pydantic-settings
  db/session.py    # psycopg connection pool
  routers/health.py
  models/schemas.py
scripts/
  init-db.sh       # Schema + RDKit extension setup
  postgresql.conf  # Tuned for 100K+ molecules
docker-compose.yml
Dockerfile
```

## Configuration

Environment variables (see `.env.example`):

| Variable | Default | Description |
|----------|---------|-------------|
| `POSTGRES_USER` | `tonomito` | Database user |
| `POSTGRES_PASSWORD` | `changeme` | Database password |
| `POSTGRES_DB` | `tonomitosql` | Database name |
| `DATABASE_URL` | composed from above | psycopg connection string |

PostgreSQL is tuned for cheminformatics workloads in `scripts/postgresql.conf` (shared_buffers=2048MB, work_mem=128MB, maintenance_work_mem=512MB).

## License

MIT
