# Stack Research

**Domain:** Cheminformatics SMILES Search API
**Researched:** 2026-03-12
**Confidence:** HIGH

## Recommended Stack

### Core Technologies

| Technology | Version | Purpose | Why Recommended |
|------------|---------|---------|-----------------|
| Python | 3.12+ | API runtime | Required for RDKit wheel support (3.10-3.14); 3.12 offers best performance/stability balance |
| FastAPI | 0.135.1 | API framework | Async-capable, automatic OpenAPI docs generation, native Pydantic integration, best Python API framework for 2025+ |
| PostgreSQL | 16 (via Docker image) | Molecular database | Bundled in the RDKit cartridge Docker image; RDKit cartridge requires PostgreSQL 9.1+ |
| RDKit Cartridge | Release_2025_03_3 | Chemical search engine | Native `mol`/`bfp` column types, GiST-indexed Tanimoto similarity, substructure matching at database level |
| RDKit Python | 2025.9.6 | SMILES validation & processing | Application-side SMILES validation before DB insertion; canonical SMILES generation |
| Docker Compose | 2.x | Container orchestration | Multi-container setup: API + PostgreSQL/RDKit; standard deployment pattern |

### Supporting Libraries

| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| Uvicorn | 0.41.0 | ASGI server | Always — production FastAPI server with --workers for concurrency |
| Pydantic | 2.12.5 | Data validation | Always — request/response models, settings validation |
| pydantic-settings | 2.13.1 | Configuration | Always — environment variable management, .env file support |
| psycopg | 3.3.3 | PostgreSQL driver | Always — modern successor to psycopg2, supports COPY protocol for bulk inserts |
| SQLAlchemy | 2.0.48 | SQL toolkit (Core only) | For connection pooling and query building — use Core, NOT ORM (RDKit types unsupported by ORM) |
| Alembic | 1.18.4 | Database migrations | For schema versioning — may need raw SQL migrations for `mol`/`bfp` columns |
| python-multipart | latest | File uploads | Required for FastAPI file upload endpoints (CSV ingestion) |
| httpx | 0.28.1 | HTTP client | For testing — async test client for FastAPI |
| pytest | 9.0.2 | Testing | Always — test runner with async support via pytest-asyncio |

### Development Tools

| Tool | Purpose | Notes |
|------|---------|-------|
| Docker Desktop | Local development | Required for PostgreSQL + RDKit cartridge container |
| ruff | Linting + formatting | Fast Python linter, replaces black + isort + flake8 |
| mypy | Type checking | Optional but recommended with FastAPI's type-heavy patterns |

## Installation

```bash
# Core (requirements.txt or pyproject.toml)
fastapi==0.135.1
uvicorn==0.41.0
pydantic==2.12.5
pydantic-settings==2.13.1
psycopg[binary]==3.3.3
sqlalchemy==2.0.48
alembic==1.18.4
rdkit==2025.9.6
python-multipart

# Dev dependencies
pytest==9.0.2
httpx==0.28.1
ruff
```

```yaml
# Docker: PostgreSQL + RDKit cartridge
services:
  db:
    image: informaticsmatters/rdkit-cartridge-debian:Release_2025_03_3
```

## Alternatives Considered

| Recommended | Alternative | When to Use Alternative |
|-------------|-------------|-------------------------|
| psycopg 3 | psycopg2 | Only if a dependency hard-requires psycopg2; psycopg3 is the maintained successor |
| psycopg 3 | asyncpg | If you need maximum concurrent throughput; asyncpg is faster for pure async but has different API patterns and less ecosystem support |
| SQLAlchemy Core | Raw psycopg | If queries are simple enough that connection pooling via psycopg pool suffices; SQLAlchemy adds complexity but provides connection management |
| FastAPI | Flask | Only if the team is deeply invested in Flask; FastAPI is objectively better for new API projects (async, auto-docs, typing) |
| informaticsmatters image | Custom RDKit build | Only if you need a specific PostgreSQL version not in the pre-built image; building RDKit from source takes 30-60 min |

## What NOT to Use

| Avoid | Why | Use Instead |
|-------|-----|-------------|
| Django | ORM-centric framework; RDKit cartridge requires raw SQL for `mol`/`bfp` types. Django's ORM adds overhead with no benefit. | FastAPI |
| Flask | No async support, no auto-generated API docs, manual request validation | FastAPI |
| psycopg2 | Legacy driver, no longer actively developed. psycopg3 is the maintained successor with COPY protocol support | psycopg 3 |
| SQLAlchemy ORM | ORM cannot map RDKit custom types (`mol`, `bfp`). ORM sessions add complexity for what is essentially raw SQL queries | SQLAlchemy Core (for connection pooling) or raw psycopg |
| MongoDB / NoSQL | No chemical search primitives. Would require application-level fingerprint computation and similarity scoring — unusable at 100K+ scale | PostgreSQL + RDKit cartridge |
| In-memory RDKit search | Loads all molecules into memory. Works for <10K but OOMs at 100K+. No persistence, no concurrent access | PostgreSQL + RDKit cartridge with GiST indexes |
| Async SQLAlchemy | RDKit cartridge queries are CPU-bound at the database level; async adds complexity with no throughput benefit for this workload | Sync psycopg with Uvicorn workers for concurrency |

## Stack Patterns

**For this project (100K+ molecules, API key auth):**
- Use sync psycopg + SQLAlchemy Core for database access
- Use Uvicorn with `--workers N` for concurrency (process-based, not async)
- Use COPY protocol via psycopg for bulk CSV ingestion
- Use `informaticsmatters/rdkit-cartridge-debian` as the database container

**If scaling to 1M+ molecules:**
- Add read replicas for search queries
- Consider asyncpg for connection multiplexing
- Add Redis for query result caching
- Partition molecules table by dataset/upload batch

## Version Compatibility

| Package A | Compatible With | Notes |
|-----------|-----------------|-------|
| rdkit 2025.9.6 | Python 3.10-3.14 | pip wheel; no arm64 issues reported |
| informaticsmatters/rdkit-cartridge-debian:Release_2025_03_3 | PostgreSQL 16 (bundled) | arm64 support confirmed (Apple Silicon) |
| psycopg 3.3.3 | PostgreSQL 9.1+ | Binary wheels available; use `psycopg[binary]` for easiest install |
| FastAPI 0.135.1 | Python 3.10+ | Requires Pydantic v2 |
| SQLAlchemy 2.0.48 | psycopg 3.x | Use `create_engine("postgresql+psycopg://...")` connection string |

## Sources

- PyPI package pages — version numbers verified (FastAPI, RDKit, psycopg, SQLAlchemy, Uvicorn, Pydantic, Alembic, httpx, pytest)
- Docker Hub informaticsmatters — verified `Release_2025_03_3` tag exists with arm64 support
- RDKit PostgreSQL cartridge documentation — verified `mol`/`bfp` types, GiST indexing, Tanimoto operators
- RDKit GitHub — confirmed cartridge compatibility with PostgreSQL 9.1+

---
*Stack research for: Cheminformatics SMILES Search API*
*Researched: 2026-03-12*
