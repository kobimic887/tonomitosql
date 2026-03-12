# Architecture Research

**Domain:** Cheminformatics SMILES search API (PostgreSQL + RDKit cartridge)
**Researched:** 2026-03-12
**Confidence:** HIGH

## Standard Architecture

### System Overview

```
┌─────────────────────────────────────────────────────────────────────┐
│                     Docker Compose Environment                       │
│                                                                     │
│  ┌──────────────────────────────┐   ┌────────────────────────────┐  │
│  │     API Container (FastAPI)  │   │   DB Container (PG+RDKit)  │  │
│  │                              │   │                            │  │
│  │  ┌────────────────────────┐  │   │  ┌──────────────────────┐  │  │
│  │  │   HTTP / Auth Layer    │  │   │  │   PostgreSQL 16+     │  │  │
│  │  │   (API key middleware) │  │   │  │                      │  │  │
│  │  └──────────┬─────────────┘  │   │  │  ┌────────────────┐  │  │  │
│  │             │                │   │  │  │ RDKit Cartridge │  │  │  │
│  │  ┌──────────▼─────────────┐  │   │  │  │ (mol, bfp, sfp │  │  │  │
│  │  │   Route Handlers       │  │   │  │  │  GiST indexes) │  │  │  │
│  │  │   /upload, /search/*   │  │   │  │  └────────────────┘  │  │  │
│  │  └──────────┬─────────────┘  │   │  │                      │  │  │
│  │             │                │   │  │  ┌────────────────┐  │  │  │
│  │  ┌──────────▼─────────────┐  │   │  │  │ Tables:        │  │  │  │
│  │  │   Service Layer        │  │   │  │  │  molecules     │  │  │  │
│  │  │   (ingestion, search,  │──┼───┼──▶  │  fingerprints  │  │  │  │
│  │  │    validation)         │  │   │  │  │  datasets      │  │  │  │
│  │  └──────────┬─────────────┘  │   │  │  │  api_keys      │  │  │  │
│  │             │                │   │  │  └────────────────┘  │  │  │
│  │  ┌──────────▼─────────────┐  │   │  └──────────────────────┘  │  │
│  │  │   DB Access Layer      │  │   │                            │  │
│  │  │   (psycopg / asyncpg)  │  │   │  Volume: pgdata           │  │
│  │  └────────────────────────┘  │   └────────────────────────────┘  │
│  └──────────────────────────────┘                                   │
└─────────────────────────────────────────────────────────────────────┘
```

### Component Responsibilities

| Component | Responsibility | Typical Implementation |
|-----------|----------------|------------------------|
| **API Container** | HTTP server, request handling, auth, CSV parsing, SMILES validation | FastAPI + Uvicorn in Python 3.11+ slim image |
| **DB Container** | Molecule storage, fingerprint indexing, similarity/substructure queries | `informaticsmatters/rdkit-cartridge-debian:Release_2025_03_3` |
| **Auth Middleware** | Validate API key on every request | FastAPI dependency injection with `X-API-Key` header |
| **Ingestion Service** | Parse CSV, validate SMILES via RDKit Python, batch insert molecules | Python RDKit + psycopg/asyncpg COPY protocol |
| **Search Service** | Translate search requests into RDKit cartridge SQL queries | SQL using `%` (Tanimoto), `@>` (substructure), `@=` (exact) operators |
| **Database Schema** | Store molecules as `mol` type, fingerprints as `bfp` type, GiST indexes | RDKit cartridge types + standard PostgreSQL |

## Recommended Project Structure

```
tonomitosql/
├── docker-compose.yml          # Orchestrates API + DB containers
├── Dockerfile                  # API container build
├── .env.example                # Environment variable template
├── alembic/                    # Database migrations
│   ├── alembic.ini
│   └── versions/
├── app/                        # FastAPI application
│   ├── __init__.py
│   ├── main.py                 # FastAPI app factory, lifespan
│   ├── config.py               # Settings via pydantic-settings
│   ├── dependencies.py         # Auth, DB session dependencies
│   ├── models/                 # SQLAlchemy / Pydantic models
│   │   ├── database.py         # SQLAlchemy table definitions
│   │   └── schemas.py          # Pydantic request/response schemas
│   ├── routers/                # Route handlers
│   │   ├── upload.py           # CSV upload endpoint
│   │   ├── search.py           # Search endpoints (exact, similarity, substructure)
│   │   └── health.py           # Health check
│   ├── services/               # Business logic
│   │   ├── ingestion.py        # CSV parsing, SMILES validation, batch insert
│   │   └── search.py           # Query building, result formatting
│   └── db/                     # Database utilities
│       ├── session.py          # Connection pool / session factory
│       └── init_rdkit.sql      # CREATE EXTENSION rdkit; schema setup
├── scripts/                    # Utility scripts
│   └── init-db.sh              # DB initialization on first run
├── tests/
│   ├── conftest.py
│   ├── test_upload.py
│   ├── test_search.py
│   └── fixtures/               # Sample CSV files for testing
├── requirements.txt
└── pyproject.toml
```

### Structure Rationale

- **`app/routers/`:** Separates HTTP concerns (upload vs. search vs. health) into focused modules. FastAPI's `APIRouter` makes this clean.
- **`app/services/`:** Business logic lives here, not in route handlers. Ingestion and search are distinct domains with different concerns (batch processing vs. query optimization).
- **`app/models/`:** Database models and API schemas separated. The database layer uses raw SQL for RDKit cartridge operations (SQLAlchemy has no native `mol`/`bfp` type support), while Pydantic handles API validation.
- **`app/db/`:** Connection management is centralized. The init SQL script runs `CREATE EXTENSION rdkit` and sets up the schema.
- **`alembic/`:** Database migrations for schema evolution. RDKit cartridge extension must be created before molecule tables.

## Database Schema Design

This is the critical architectural decision. Based on the RDKit cartridge documentation, the standard pattern uses separate tables for molecules and fingerprints.

### Core Schema

```sql
-- Enable the RDKit cartridge
CREATE EXTENSION IF NOT EXISTS rdkit;

-- Dataset tracking (one per CSV upload)
CREATE TABLE datasets (
    id SERIAL PRIMARY KEY,
    name TEXT NOT NULL,
    filename TEXT NOT NULL,
    row_count INTEGER DEFAULT 0,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Raw molecule storage with RDKit mol type
CREATE TABLE molecules (
    id SERIAL PRIMARY KEY,
    dataset_id INTEGER REFERENCES datasets(id) ON DELETE CASCADE,
    smiles TEXT NOT NULL,               -- Original SMILES string
    mol mol NOT NULL,                   -- RDKit molecule object (for substructure search)
    canonical_smiles TEXT NOT NULL       -- Canonical SMILES (for exact match)
);

-- GiST index on mol column for substructure search
CREATE INDEX idx_molecules_mol ON molecules USING gist(mol);

-- B-tree index on canonical SMILES for exact match
CREATE INDEX idx_molecules_canonical ON molecules(canonical_smiles);

-- Precomputed fingerprints for similarity search
CREATE TABLE fingerprints (
    molecule_id INTEGER PRIMARY KEY REFERENCES molecules(id) ON DELETE CASCADE,
    mfp2 bfp NOT NULL                  -- Morgan fingerprint radius=2 (ECFP4 equivalent)
);

-- GiST index on Morgan fingerprint for Tanimoto similarity
CREATE INDEX idx_fps_mfp2 ON fingerprints USING gist(mfp2);

-- API key storage
CREATE TABLE api_keys (
    id SERIAL PRIMARY KEY,
    key_hash TEXT NOT NULL UNIQUE,      -- SHA-256 hash of the API key
    name TEXT NOT NULL,                 -- Human-readable label
    active BOOLEAN DEFAULT true,
    created_at TIMESTAMPTZ DEFAULT NOW()
);
```

### Why This Schema

**Separate `molecules` and `fingerprints` tables:** The RDKit cartridge documentation (ChEMBL loading example) consistently uses this pattern. The `mol` column is needed for substructure search (`@>` operator) while `bfp` columns are needed for similarity search (`%` operator). Separating them allows independent indexing and avoids bloating the molecule table with multiple fingerprint columns.

**Morgan fingerprint radius=2 (`morganbv_fp(mol, 2)`):** This is the ECFP4 equivalent, the most widely used fingerprint in pharmaceutical cheminformatics for similarity searching. The RDKit cartridge docs use this as the primary example.

**GiST indexes:** The RDKit cartridge uses GiST (Generalized Search Tree) for both molecule substructure and fingerprint similarity indexes. This is mandatory for the `%` and `@>` operators to use index scans instead of sequential scans.

**Canonical SMILES column:** Stored separately from the `mol` object for fast exact-match lookups via B-tree index. `mol_to_smiles(mol)` produces canonical SMILES, which is deterministic for the same molecule regardless of input SMILES notation.

**Confidence:** HIGH -- directly derived from RDKit cartridge official documentation examples.

## Architectural Patterns

### Pattern 1: Batch Ingestion via COPY Protocol

**What:** Use PostgreSQL's COPY protocol for bulk loading molecules, not individual INSERT statements.
**When to use:** CSV upload ingestion -- always. Individual inserts are orders of magnitude slower for bulk data.
**Trade-offs:** Requires staging table approach (load raw SMILES, then convert to mol objects), but 10-100x faster than row-by-row inserts.

**Example flow:**
```python
# 1. Upload CSV, parse with Python csv/pandas
# 2. Validate SMILES with RDKit Python (rdkit.Chem.MolFromSmiles)
# 3. Bulk insert valid SMILES into a staging table via COPY
# 4. Convert to mol objects in SQL:
#    INSERT INTO molecules (dataset_id, smiles, mol, canonical_smiles)
#    SELECT dataset_id, smiles, mol_from_smiles(smiles::cstring),
#           mol_to_smiles(mol_from_smiles(smiles::cstring))
#    FROM staging WHERE mol_from_smiles(smiles::cstring) IS NOT NULL;
# 5. Generate fingerprints in SQL:
#    INSERT INTO fingerprints (molecule_id, mfp2)
#    SELECT id, morganbv_fp(mol) FROM molecules WHERE dataset_id = ?;
```

### Pattern 2: Tanimoto Similarity Search Function

**What:** Encapsulate similarity search as a PostgreSQL function for clean API integration and query plan reuse.
**When to use:** Every similarity search request.
**Trade-offs:** Slightly less flexible than dynamic SQL, but safer and faster due to plan caching.

**Example:**
```sql
-- From RDKit cartridge docs, adapted for our schema
CREATE OR REPLACE FUNCTION search_similar(
    query_smiles TEXT,
    threshold DOUBLE PRECISION DEFAULT 0.5,
    max_results INTEGER DEFAULT 100
)
RETURNS TABLE(smiles TEXT, similarity DOUBLE PRECISION) AS $$
BEGIN
    -- Set the Tanimoto threshold for index usage
    EXECUTE format('SET rdkit.tanimoto_threshold = %L', threshold);

    RETURN QUERY
    SELECT m.canonical_smiles,
           tanimoto_sml(morganbv_fp(mol_from_smiles(query_smiles::cstring)), f.mfp2)
    FROM fingerprints f
    JOIN molecules m ON m.id = f.molecule_id
    WHERE morganbv_fp(mol_from_smiles(query_smiles::cstring)) % f.mfp2
    ORDER BY morganbv_fp(mol_from_smiles(query_smiles::cstring)) <%> f.mfp2
    LIMIT max_results;
END;
$$ LANGUAGE plpgsql STABLE;
```

### Pattern 3: Client-Side SMILES Validation Before Database

**What:** Validate SMILES strings using RDKit Python library (`Chem.MolFromSmiles`) in the API layer before sending to the database.
**When to use:** During CSV ingestion. Reject invalid molecules early with clear error messages.
**Trade-offs:** Requires RDKit Python in the API container (adds ~200MB to image size), but prevents database errors and provides better error reporting.

```python
from rdkit import Chem

def validate_smiles(smiles: str) -> bool:
    """Returns True if SMILES is valid and parseable by RDKit."""
    mol = Chem.MolFromSmiles(smiles)
    return mol is not None
```

## Data Flow

### CSV Upload Flow

```
Client (CSV file)
    │
    ▼
FastAPI /upload endpoint
    │ (multipart file upload)
    ▼
Auth Middleware ── reject if invalid API key
    │
    ▼
Ingestion Service
    │
    ├── 1. Parse CSV (identify SMILES column)
    ├── 2. Validate each SMILES (RDKit Python)
    ├── 3. Create dataset record
    ├── 4. Bulk insert valid rows (COPY protocol)
    ├── 5. Convert SMILES → mol objects (SQL)
    ├── 6. Generate fingerprints (SQL)
    │
    ▼
Response: { dataset_id, total_rows, valid_rows, invalid_rows }
```

### Similarity Search Flow

```
Client (query SMILES + threshold)
    │
    ▼
FastAPI /search/similarity endpoint
    │
    ▼
Auth Middleware ── reject if invalid API key
    │
    ▼
Search Service
    │
    ├── 1. Validate query SMILES (RDKit Python)
    ├── 2. SET rdkit.tanimoto_threshold = <threshold>
    ├── 3. Execute similarity query (GiST index scan on fingerprints)
    ├── 4. Results: [(smiles, score), ...] ordered by similarity DESC
    │
    ▼
Response: { results: [{ smiles, similarity }], count }
```

### Substructure Search Flow

```
Client (SMILES or SMARTS pattern)
    │
    ▼
FastAPI /search/substructure endpoint
    │
    ▼
Auth Middleware
    │
    ▼
Search Service
    │
    ├── 1. Validate pattern
    ├── 2. Execute: SELECT ... FROM molecules WHERE mol @> pattern
    ├── 3. GiST index on mol column accelerates the search
    │
    ▼
Response: { results: [{ smiles }], count }
```

### Exact Match Flow

```
Client (SMILES string)
    │
    ▼
FastAPI /search/exact endpoint
    │
    ▼
Auth Middleware
    │
    ▼
Search Service
    │
    ├── 1. Canonicalize query SMILES (RDKit Python)
    ├── 2. B-tree lookup on canonical_smiles column
    │
    ▼
Response: { results: [{ smiles }], found: bool }
```

## Docker Architecture

### Container 1: PostgreSQL + RDKit Cartridge

**Base image:** `informaticsmatters/rdkit-cartridge-debian:Release_2025_03_3`
- Pre-built Debian image with PostgreSQL and the RDKit cartridge compiled and installed
- Available for both amd64 and arm64 (works on Apple Silicon)
- ~400MB compressed
- Latest stable tag as of research date

**Initialization:**
- Custom `init-db.sh` mounted to `/docker-entrypoint-initdb.d/` runs on first container start
- Creates database, runs `CREATE EXTENSION rdkit`, creates schema
- PostgreSQL tuning via environment variables or custom `postgresql.conf`

**Key tuning parameters (from RDKit docs):**
```
shared_buffers = 2048MB          # Default is too conservative
work_mem = 128MB                 # Needed for fingerprint operations
synchronous_commit = off         # Faster bulk loading (acceptable for non-financial data)
full_page_writes = off           # Faster bulk loading
```

### Container 2: FastAPI Application

**Base image:** `python:3.11-slim` + RDKit installed via `pip install rdkit-pypi`
- RDKit Python bindings needed for client-side SMILES validation
- `rdkit-pypi` is the pip-installable wheel (no conda required)
- FastAPI + Uvicorn for the HTTP server

**Dockerfile pattern:**
```dockerfile
FROM python:3.11-slim
RUN pip install --no-cache-dir rdkit-pypi fastapi uvicorn[standard] \
    psycopg[binary] python-multipart pydantic-settings
COPY ./app /app
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

### Docker Compose Topology

```yaml
services:
  api:
    build: .
    ports: ["8000:8000"]
    depends_on:
      db:
        condition: service_healthy
    environment:
      - DATABASE_URL=postgresql://user:pass@db:5432/tonomitosql
      - API_KEY_HASH=...

  db:
    image: informaticsmatters/rdkit-cartridge-debian:Release_2025_03_3
    volumes:
      - pgdata:/var/lib/postgresql/data
      - ./scripts/init-db.sh:/docker-entrypoint-initdb.d/init-db.sh
    environment:
      - POSTGRES_USER=user
      - POSTGRES_PASSWORD=pass
      - POSTGRES_DB=tonomitosql
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U user -d tonomitosql"]
      interval: 5s
      retries: 5

volumes:
  pgdata:
```

**Confidence:** HIGH -- `informaticsmatters/rdkit-cartridge-debian` is the standard community Docker image for RDKit+PostgreSQL, with 100K+ pulls and active maintenance through 2025.

## Scaling Considerations

| Scale | Architecture Adjustments |
|-------|--------------------------|
| 0-100K molecules | Single Docker Compose as designed. GiST indexes provide sub-second Tanimoto queries. No changes needed. |
| 100K-1M molecules | Increase `shared_buffers` and `work_mem`. Consider adding `torsionbv_fp` or `featmorganbv_fp` columns for alternative similarity measures. Bulk ingestion must use COPY protocol. |
| 1M-10M molecules | Consider partitioning molecules table by dataset. Connection pooling (PgBouncer). May need to move to dedicated PostgreSQL host rather than Docker volume. |
| 10M+ molecules | Beyond project scope. Would require read replicas, materialized fingerprint views, or dedicated cheminformatics search engines (e.g., chemfp). |

### Scaling Priorities

1. **First bottleneck: Ingestion speed.** At 100K+ molecules, row-by-row INSERT becomes unusable. The COPY protocol + staging table pattern is mandatory. RDKit's `mol_from_smiles()` conversion in SQL is ~10x faster than converting in Python and sending mol objects over the wire.

2. **Second bottleneck: Similarity search latency.** The GiST index on `mfp2` is critical. Without it, Tanimoto queries do sequential scans. With the index, ChEMBL-scale (1.8M compounds) similarity searches return in 30-180ms per the official docs. At 100K molecules, expect <50ms.

3. **Third bottleneck: Connection pool exhaustion.** FastAPI's async nature can open many concurrent DB connections. Use connection pooling (asyncpg pool or PgBouncer) from the start.

## Anti-Patterns

### Anti-Pattern 1: Computing Fingerprints in Application Code

**What people do:** Generate fingerprints using RDKit Python and store them as binary blobs in generic columns.
**Why it's wrong:** Loses all GiST index capabilities. The RDKit cartridge's entire value is that fingerprint types (`bfp`, `sfp`) and their indexes are native PostgreSQL types with built-in operator support. Storing fingerprints as bytea columns means every similarity search becomes a sequential scan.
**Do this instead:** Use cartridge functions (`morganbv_fp()`) to generate fingerprints in SQL and store them in `bfp` typed columns with GiST indexes.

### Anti-Pattern 2: Using SQLAlchemy ORM for RDKit Queries

**What people do:** Try to map `mol` and `bfp` columns to SQLAlchemy models and use ORM query building.
**Why it's wrong:** SQLAlchemy has no native support for RDKit custom types (`mol`, `bfp`, `sfp`) or operators (`%`, `@>`, `<%>`). Attempting to wrap these in custom types creates fragile, hard-to-debug code.
**Do this instead:** Use raw SQL (via `psycopg` or `asyncpg`) for all RDKit-specific queries. Use SQLAlchemy/Pydantic only for non-chemistry tables (datasets, api_keys) if desired, or use raw SQL throughout for consistency.

### Anti-Pattern 3: Validating SMILES Only at the Database Level

**What people do:** Skip Python-side SMILES validation and rely on `mol_from_smiles()` returning NULL for invalid SMILES.
**Why it's wrong:** Database-level validation during bulk COPY doesn't provide per-row error reporting. The user gets no feedback about which SMILES failed or why. Also, invalid SMILES in a COPY batch can cause the entire batch to fail depending on error handling.
**Do this instead:** Validate SMILES with RDKit Python first, collect invalid rows with line numbers, report them back to the user, and only send valid SMILES to the database.

### Anti-Pattern 4: Skipping `rdkit.tanimoto_threshold` Configuration

**What people do:** Run Tanimoto queries without setting the threshold, relying on the default 0.5.
**Why it's wrong:** The threshold controls which rows the GiST index considers. If a user requests threshold=0.3, but `rdkit.tanimoto_threshold` is still at 0.5, the index will filter out results between 0.3 and 0.5 before they reach the application.
**Do this instead:** Always `SET rdkit.tanimoto_threshold` to match the user's requested threshold before executing the query. Use per-session or per-transaction SET.

## Integration Points

### Internal Boundaries

| Boundary | Communication | Notes |
|----------|---------------|-------|
| API Container <-> DB Container | TCP via Docker internal network, port 5432 | psycopg or asyncpg driver. Connection pooling recommended. |
| Route Handlers <-> Services | Direct Python function calls | No network boundary. Services return Pydantic models. |
| Ingestion Service <-> DB | COPY protocol for bulk, standard SQL for schema ops | COPY is critical for performance at scale. |
| Search Service <-> DB | Parameterized SQL queries using RDKit operators | Raw SQL, not ORM. SET tanimoto_threshold per query. |

### External Boundaries

| Boundary | Communication | Notes |
|----------|---------------|-------|
| Client <-> API | HTTP REST, JSON responses | API key in `X-API-Key` header. Multipart for file upload. |

## Suggested Build Order

Components have clear dependencies that dictate build order:

```
Phase 1: Database Foundation
   └── Docker Compose + DB container + schema + RDKit extension
       (Everything depends on the database existing)

Phase 2: Ingestion Pipeline
   └── CSV upload + SMILES validation + bulk insert + fingerprint generation
       (Depends on: Phase 1 schema)
       (Search requires data to exist)

Phase 3: Search Endpoints
   └── Exact match + Tanimoto similarity + substructure search
       (Depends on: Phase 1 indexes, Phase 2 data)

Phase 4: Auth + Production Hardening
   └── API key middleware + error handling + health checks
       (Can be built incrementally alongside Phases 2-3)
```

**Why this order:** You cannot test search without data. You cannot ingest data without a schema. The database with RDKit cartridge is the foundation everything else depends on. Auth can be added as middleware at any point but is lower priority for initial development.

## Sources

- RDKit Cartridge Official Documentation (v2025.09.6): https://www.rdkit.org/docs/Cartridge.html -- HIGH confidence (authoritative primary source for all schema patterns, operators, functions, and query examples)
- InformaticsMatters Docker RDKit Repository: https://github.com/InformaticsMatters/docker-rdkit -- HIGH confidence (standard community Docker images, 100K+ pulls, active through 2025)
- Docker Hub `informaticsmatters/rdkit-cartridge-debian` tags: https://hub.docker.com/r/informaticsmatters/rdkit-cartridge-debian/tags -- HIGH confidence (verified `Release_2025_03_3` tag exists with amd64+arm64 support)
- RDKit PostgreSQL Cartridge Source (GitHub): https://github.com/rdkit/rdkit/tree/master/Code/PgSQL/rdkit -- HIGH confidence (confirms GiST index implementation, `mol`/`bfp`/`sfp` types)

---
*Architecture research for: Cheminformatics SMILES Search API*
*Researched: 2026-03-12*
