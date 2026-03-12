---
phase: 03-search-authentication
plan: 02
subsystem: search
tags: [rdkit, tanimoto, fingerprints, postgresql, gist, smiles, fastapi]

# Dependency graph
requires:
  - phase: 02-csv-ingestion
    provides: molecules and fingerprints tables with data for searching
  - phase: 01-infrastructure
    provides: PostgreSQL/RDKit cartridge with GiST indexes, psycopg connection pool
provides:
  - Search service with exact_match, similarity_search, substructure_search functions
  - GET /search/exact, /search/similarity, /search/substructure endpoints
  - MoleculeResult and SearchResponse Pydantic schemas
affects: [03-search-authentication]

# Tech tracking
tech-stack:
  added: []
  patterns: [parameterized-sql-for-rdkit-operators, set-tanimoto-threshold-per-query, knn-gist-ordering]

key-files:
  created:
    - app/services/search.py
    - app/routers/search.py
  modified:
    - app/models/schemas.py
    - app/main.py

key-decisions:
  - "Parameterized queries for all SMILES inputs — never string concatenation"
  - "SET rdkit.tanimoto_threshold per-query before every similarity search"
  - "<%> KNN operator for ORDER BY to leverage GiST index ordering"
  - "Tanimoto threshold floor at 0.1 to prevent full table scans"
  - "MAX_LIMIT=1000 to prevent unbounded result sets"
  - "Sync handlers consistent with existing project pattern (psycopg sync)"

patterns-established:
  - "Search service pattern: validate SMILES in Python, execute parameterized SQL, return Pydantic models"
  - "Router pattern: Query params with FastAPI validation, ValueError→400, service call, response model"

requirements-completed: [SRCH-01, SRCH-02, SRCH-03, SRCH-04, SRCH-05, SRCH-06]

# Metrics
duration: 3min
completed: 2026-03-12
---

# Phase 3 Plan 2: Search Service & Endpoints Summary

**Search service with exact match (@= operator), Tanimoto similarity (% operator + <%> KNN ordering + SET tanimoto_threshold), and substructure (@> operator) search — all with parameterized SQL and pagination**

## Performance

- **Duration:** 3 min
- **Started:** 2026-03-12T19:56:13Z
- **Completed:** 2026-03-12T19:59:03Z
- **Tasks:** 2
- **Files modified:** 4

## Accomplishments
- Search service with three search functions using RDKit cartridge SQL operators
- Tanimoto similarity search with per-query threshold setting, GiST-indexed KNN ordering, and configurable threshold (0.1-1.0)
- REST endpoints under /search/ prefix with FastAPI Query validation and descriptive error messages
- SMILES validation with canonicalization before all database queries

## Task Commits

Each task was committed atomically:

1. **Task 1: Create search Pydantic schemas and search service** - `f3e49b7` (feat)
2. **Task 2: Create search router with GET endpoints** - `745bea9` (feat)

## Files Created/Modified
- `app/services/search.py` - Search service with exact_match, similarity_search, substructure_search using RDKit cartridge operators
- `app/routers/search.py` - HTTP endpoints for GET /search/exact, /search/similarity, /search/substructure
- `app/models/schemas.py` - Added MoleculeResult and SearchResponse Pydantic schemas
- `app/main.py` - Wired search router into FastAPI app

## Decisions Made
- Parameterized queries for all SMILES inputs — never string concatenation (SQL injection prevention)
- SET rdkit.tanimoto_threshold per-query before every similarity search (connection pool returns connections with potentially stale threshold)
- <%> KNN operator for ORDER BY to leverage GiST index ordering instead of full sort (critical for sub-second performance at 100K+)
- Tanimoto threshold floor at 0.1 to prevent extremely broad searches that scan entire table
- MAX_LIMIT=1000 safety cap to prevent unbounded result sets
- %% and <%%> escape sequences for psycopg parameterized query syntax (% is special in psycopg)
- Sync handlers consistent with existing project pattern (psycopg sync, FastAPI runs in thread pool)

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered
None

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- Search service and endpoints complete, ready for auth wiring in Plan 03-03
- Endpoints currently unprotected — auth dependency will be added in Plan 03-03
- Error response differentiation (400 vs 401 vs 422) ready to be consolidated in Plan 03-03

---
*Phase: 03-search-authentication*
*Completed: 2026-03-12*

## Self-Check: PASSED

- [x] app/services/search.py exists
- [x] app/routers/search.py exists
- [x] Commit f3e49b7 found
- [x] Commit 745bea9 found
- [x] SUMMARY file exists
