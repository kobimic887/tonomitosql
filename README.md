# TonomitoSQL

Molecular search API powered by PostgreSQL + RDKit. Upload CSV datasets of molecules, then run exact, substructure, and similarity searches using the RDKit cartridge — all through a REST API.

## Stack

- **API:** FastAPI + Uvicorn (Python 3.12, multi-worker)
- **Database:** PostgreSQL with [RDKit cartridge](https://www.rdkit.org/docs/Cartridge.html)
- **Connection:** psycopg3 connection pool (sync, no ORM)
- **Containers:** Docker Compose

## Quick Start

```bash
cp .env.example .env    # edit credentials — no defaults, required
docker compose up -d
```

The API starts at `http://localhost:8000`. The database initializes automatically on first run (RDKit extension, schema, indexes).

## API Endpoints (v1.1)

| Method | Path | Description |
|--------|------|-------------|
| GET | `/health` | API version, DB status, RDKit version, molecule count |
| GET | `/docs` | Swagger UI (auto-generated) |
| POST | `/v1/upload` | Upload a CSV file with SMILES column |
| GET | `/v1/search/exact` | Exact molecular match (`@=` operator) |
| GET | `/v1/search/similarity` | Tanimoto similarity search (Morgan FP, ECFP4) |
| GET | `/v1/search/substructure` | Substructure containment search (`@>` operator) |
| POST | `/v1/search/batch` | Batch search (up to 100 SMILES per request) |
| GET | `/v1/datasets` | List all datasets |
| GET | `/v1/datasets/{id}` | Get dataset details |
| DELETE | `/v1/datasets/{id}` | Delete dataset + molecules (CASCADE) |

### Search Parameters

**Exact:** `?smiles=CCO`

**Similarity:** `?smiles=CCO&threshold=0.5&offset=0&limit=100`
- `threshold` (0.1-1.0): Minimum Tanimoto coefficient

**Substructure:** `?smiles=c1ccccc1&offset=0&limit=100`

**All search endpoints:** `?dataset_id=N` to scope to a specific dataset.

### Batch Search

```bash
curl -X POST http://localhost:8000/v1/search/batch \
  -H "Content-Type: application/json" \
  -d '{
    "smiles_list": ["CCO", "c1ccccc1"],
    "search_type": "similarity",
    "threshold": 0.7,
    "limit": 10
  }'
```

## Database Schema

Three tables created automatically by `scripts/init-db.sh`:

- **datasets** — tracks CSV uploads (name, filename, row count, timestamp)
- **molecules** — SMILES strings stored as RDKit `mol` type with GiST index
- **fingerprints** — Morgan fingerprints (radius 2, `bfp` type) with GiST index

## Project Structure

```
app/
  main.py              # FastAPI app with lifespan, /v1 prefix routing
  config.py            # Settings via pydantic-settings (no defaults for secrets)
  chem.py              # RDKit Python wrapper with ARM fallback
  db/session.py        # psycopg connection pool (min=2, max=10)
  routers/
    health.py          # GET /health
    upload.py          # POST /v1/upload
    search.py          # GET /v1/search/*, POST /v1/search/batch
    datasets.py        # GET/DELETE /v1/datasets/*
  models/schemas.py    # Pydantic request/response models
  services/
    ingestion.py       # CSV → staging → mol_from_smiles → fingerprints
    search.py          # RDKit cartridge queries (@=, %, @>)
scripts/
  init-db.sh           # Schema + RDKit extension setup
  postgresql.conf      # Tuned for cheminformatics (shared_buffers=2GB, work_mem=64MB)
docker-compose.yml
Dockerfile
```

## Configuration

Environment variables (see `.env.example`):

| Variable | Required | Description |
|----------|----------|-------------|
| `POSTGRES_USER` | Yes | Database user |
| `POSTGRES_PASSWORD` | Yes | Database password |
| `POSTGRES_DB` | Yes | Database name |
| `DATABASE_URL` | Yes | psycopg connection string |
| `WEB_WORKERS` | No (default: 4) | Uvicorn worker count |
| `LOG_LEVEL` | No (default: INFO) | Python logging level |

**No hardcoded credential defaults.** The app fails fast at startup if `DATABASE_URL` is missing.

PostgreSQL is tuned for cheminformatics workloads in `scripts/postgresql.conf`:
- `shared_buffers` = 2048MB
- `work_mem` = 64MB
- `maintenance_work_mem` = 2048MB

## Safety

- Database port (5432) not exposed to host — API-only access via Docker network
- No default credentials — `.env` is required and gitignored
- 30s statement timeout on all search queries (prevents runaway queries)
- Generic error messages on 500 (no SQL/connection detail leaks)

## Architecture Notes

- **RDKit lives in two places:** (1) PostgreSQL RDKit cartridge does all heavy lifting — `mol_from_smiles`, `morganbv_fp`, `tanimoto_sml`, `@=`, `@>`, `%%`. (2) Optional `rdkit-pypi` Python package for pre-validation on x86.
- **ARM compatibility:** On ARM (aarch64), `rdkit-pypi` is unavailable. SMILES validation falls back to SQL-side `mol_from_smiles()`. All code paths work on both architectures.
- **No SQLAlchemy** — raw psycopg for RDKit cartridge operator compatibility.
- **Sync psycopg** — RDKit queries are CPU-bound at the DB level; async provides no benefit.

## License

MIT
