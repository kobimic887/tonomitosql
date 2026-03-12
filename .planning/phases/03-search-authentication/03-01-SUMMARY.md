---
phase: 03-search-authentication
plan: 01
subsystem: auth
tags: [api-key, sha256, fastapi-security, psycopg]

# Dependency graph
requires:
  - phase: 01-infrastructure
    provides: "PostgreSQL + RDKit database, init-db.sh schema"
  - phase: 02-csv-ingestion
    provides: "/upload endpoint and ingestion pipeline"
provides:
  - "api_keys table in PostgreSQL for storing hashed API keys"
  - "require_api_key FastAPI dependency for X-API-Key header validation"
  - "create-api-key.py CLI script for key generation"
  - "/upload endpoint protected with API key auth"
affects: [03-search-authentication]

# Tech tracking
tech-stack:
  added: [fastapi.security.APIKeyHeader, hashlib.sha256, secrets.token_urlsafe]
  patterns: [dependency-injection-auth, sha256-key-hashing, header-based-api-key]

key-files:
  created:
    - app/dependencies.py
    - scripts/create-api-key.py
  modified:
    - scripts/init-db.sh
    - app/routers/upload.py

key-decisions:
  - "SHA-256 hash stored in DB, raw key never persisted — standard API key security pattern"
  - "APIKeyHeader with auto_error=False for custom 401 messages instead of FastAPI default 403"
  - "401 Unauthorized (not 403 Forbidden) — semantically correct for missing/invalid credentials"
  - "create-api-key.py uses psycopg.connect() directly, not pool — CLI script runs once"

patterns-established:
  - "Auth dependency pattern: Depends(require_api_key) on any endpoint needing auth"
  - "API key management: generate with secrets.token_urlsafe(32), store SHA-256 hash"

requirements-completed: [API-01]

# Metrics
duration: 1min
completed: 2026-03-12
---

# Phase 3 Plan 1: API Key Authentication Summary

**SHA-256 hashed API key auth via FastAPI dependency injection, protecting /upload with X-API-Key header validation against the api_keys table**

## Performance

- **Duration:** 1 min
- **Started:** 2026-03-12T19:56:07Z
- **Completed:** 2026-03-12T19:57:24Z
- **Tasks:** 2
- **Files modified:** 4

## Accomplishments
- api_keys table added to database schema (key_hash UNIQUE, name, active, created_at)
- require_api_key FastAPI dependency validates X-API-Key header via SHA-256 hash lookup
- /upload endpoint protected — returns 401 for missing or invalid API keys
- create-api-key.py script generates cryptographically secure keys and stores hashes

## Task Commits

Each task was committed atomically:

1. **Task 1: Add api_keys table and key management script** - `50859aa` (feat)
2. **Task 2: Create auth dependency and protect /upload** - `490ad1f` (feat)

## Files Created/Modified
- `scripts/init-db.sh` - Added api_keys table definition after fingerprints table
- `app/dependencies.py` - FastAPI auth dependency with APIKeyHeader and SHA-256 validation
- `scripts/create-api-key.py` - CLI script for generating and storing API keys
- `app/routers/upload.py` - Added Depends(require_api_key) and key name logging

## Decisions Made
- Used SHA-256 hashing (not bcrypt) — API keys are high-entropy random tokens, not user passwords; SHA-256 is the standard pattern
- Used APIKeyHeader with auto_error=False — allows custom 401 error messages instead of FastAPI's default 403
- Used 401 (not 403) status code — semantically correct for "not authenticated" vs "not authorized"
- create-api-key.py uses psycopg.connect() directly — CLI script doesn't need connection pooling

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered
None

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- Auth infrastructure ready for Plan 03-02 (search endpoints) and Plan 03-03 (search + auth integration)
- require_api_key dependency can be added to any future endpoint via Depends(require_api_key)
- API key can be generated after database init with: `docker compose exec api python scripts/create-api-key.py --name "my-app"`

## Self-Check: PASSED

All key files verified on disk. All task commits verified in git history.

---
*Phase: 03-search-authentication*
*Completed: 2026-03-12*
