---
phase: 02-csv-ingestion-pipeline
plan: 01
subsystem: ingestion
tags: [rdkit, csv, smiles, copy-protocol, psycopg, streaming, fingerprints, morgan, pydantic]

# Dependency graph
requires:
  - phase: 01-infrastructure-api-foundation
    provides: Docker compose with RDKit cartridge, psycopg connection pool, database schema (datasets, molecules, fingerprints)
provides:
  - rdkit-pypi installed in API container for Python-side SMILES validation
  - CSV ingestion service with streaming parse, batch COPY, staging table pipeline
  - UploadResponse and RowError Pydantic schemas for upload results
  - Morgan fingerprint computation (radius 2) via SQL
affects: [02-csv-ingestion-pipeline, 03-search-api-auth]

# Tech tracking
tech-stack:
  added: [rdkit-pypi, libxrender1, libxext6]
  patterns: [streaming-csv-parse, batch-copy-protocol, staging-table-pipeline, double-validation]

key-files:
  created:
    - app/services/ingestion.py
  modified:
    - requirements.txt
    - Dockerfile
    - app/models/schemas.py

key-decisions:
  - "Batch size 5000 rows for COPY protocol — balances ~5MB memory per batch vs round-trip overhead"
  - "Double validation: Python-side Chem.MolFromSmiles + SQL-side mol_from_smiles WHERE NOT NULL safety net"
  - "ON COMMIT DROP staging table for automatic cleanup"
  - "rdkit-pypi unpinned — let pip resolve latest compatible wheel for Python 3.12"

patterns-established:
  - "Staging table pattern: COPY raw data → SQL transformation → production table"
  - "Row-level error collection: RowError list returned in UploadResponse"
  - "JSONB metadata: all non-SMILES CSV columns stored as metadata dict"

requirements-completed: [INGT-02, INGT-03, INGT-04, INGT-05, INGT-06]

# Metrics
duration: 2min
completed: 2026-03-12
---

# Phase 2 Plan 1: CSV Ingestion Service Summary

**Streaming CSV ingestion service with RDKit SMILES validation, psycopg COPY protocol batch loading, staging table pipeline, and Morgan fingerprint computation**

## Performance

- **Duration:** 2 min
- **Started:** 2026-03-12T19:41:31Z
- **Completed:** 2026-03-12T19:43:41Z
- **Tasks:** 2
- **Files modified:** 4

## Accomplishments
- Added rdkit-pypi dependency with required system libs (libxrender1, libxext6) for python:3.12-slim
- Created UploadResponse and RowError Pydantic schemas for structured upload result reporting
- Built full ingestion pipeline: streaming CSV parse → SMILES validation → batch COPY (5000 rows) → staging table → mol_from_smiles → morganbv_fp fingerprints
- All non-SMILES CSV columns collected into JSONB metadata (including CSV's own id and canonical_smiles columns)

## Task Commits

Each task was committed atomically:

1. **Task 1: Add rdkit-pypi dependency and create upload response schemas** - `fa8c8f4` (feat)
2. **Task 2: Create ingestion service with streaming CSV parsing, SMILES validation, batch COPY, and fingerprint computation** - `dea7af1` (feat)

## Files Created/Modified
- `app/services/ingestion.py` - Core ingestion service: streaming CSV parse, SMILES validation, batch COPY, staging→production pipeline, fingerprint computation (299 lines)
- `app/models/schemas.py` - Added RowError and UploadResponse Pydantic schemas alongside existing HealthResponse
- `requirements.txt` - Added rdkit-pypi dependency
- `Dockerfile` - Added apt-get layer for libxrender1 and libxext6 required by rdkit-pypi on slim image

## Decisions Made
- Batch size 5000 rows for COPY protocol — balances ~5MB memory per batch vs round-trip overhead at ~3M rows (~600 COPY operations)
- Double validation strategy: Python-side Chem.MolFromSmiles for row-level error reporting + SQL-side mol_from_smiles WHERE NOT NULL as safety net
- ON COMMIT DROP staging table for automatic cleanup — no manual cleanup needed
- rdkit-pypi unpinned — let pip resolve latest compatible wheel for Python 3.12 (prebuilt wheels, no compilation)
- Single transaction for entire ingestion — rollback-safe for ~3M rows with tuned work_mem (256MB from Phase 1)

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered
- Docker not available in execution environment — verification limited to AST parsing, pattern checking, and schema import testing. Full Docker-based verification (rdkit import in container, COPY protocol test) deferred to next plan execution or manual verification.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness
- Ingestion service ready for HTTP endpoint wiring in Plan 02-02
- rdkit-pypi will be available in container after next `docker compose build`
- UploadResponse schema ready for FastAPI endpoint return type

## Self-Check: PASSED

- All 4 created/modified files verified on disk
- Both task commits (fa8c8f4, dea7af1) verified in git history

---
*Phase: 02-csv-ingestion-pipeline*
*Completed: 2026-03-12*
