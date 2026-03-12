---
phase: 03-search-authentication
plan: 03
subsystem: search-auth-wiring
tags: [fastapi-depends, api-key, search-auth, error-differentiation]

# Dependency graph
requires:
  - phase: 03-search-authentication
    plan: 01
    provides: "require_api_key dependency in app/dependencies.py"
  - phase: 03-search-authentication
    plan: 02
    provides: "Search router with exact, similarity, substructure endpoints"
provides:
  - "All search endpoints protected with API key auth"
  - "Error differentiation: 401 auth, 400 SMILES, 422 params, 200 no-results"
  - "Search router wired into FastAPI app (already done by 03-02)"
affects: []

# Tech tracking
tech-stack:
  added: []
  patterns: [dependency-injection-auth-on-search, layered-error-differentiation]

key-files:
  created: []
  modified:
    - app/routers/search.py

key-decisions:
  - "Auth dependency added as last parameter on each endpoint — FastAPI evaluates dependencies before endpoint body"
  - "Error differentiation is architectural, not custom handlers — 422 from FastAPI validation, 401 from dependency, 400 from endpoint, 200 from service"
  - "main.py already had search router wired from 03-02 — no changes needed there"

patterns-established:
  - "All protected endpoints follow pattern: api_key_name: str = Depends(require_api_key) as final parameter"
  - "Logging includes key name for audit trail: logger.info('Search X (key=%s): %s', api_key_name, smiles)"

requirements-completed: [API-01, API-03]

# Metrics
duration: 2min
completed: 2026-03-12
---

# Phase 3 Plan 3: Wire Search with Auth & Error Differentiation Summary

**Applied require_api_key dependency to all 3 search endpoints, completing the authenticated search API with clear error differentiation (401/400/422/200)**

## Performance

- **Duration:** 2 min
- **Started:** 2026-03-12
- **Completed:** 2026-03-12
- **Tasks:** 1
- **Files modified:** 1

## Accomplishments
- All 3 search endpoints (exact, similarity, substructure) now require valid API key via X-API-Key header
- Added audit logging with key name on all search endpoints
- Error differentiation complete: 401 for auth failures, 400 for invalid SMILES, 422 for bad params, 200 with found=false for no results
- Health endpoint remains publicly accessible (no auth)
- Updated module docstring to reflect auth requirement

## Task Commits

1. **Task 1: Add auth dependency to search endpoints** - (pending commit)

## Files Modified
- `app/routers/search.py` — Added `Depends(require_api_key)` to all 3 endpoints, added import of `require_api_key` from `app.dependencies`, added `logger.info` audit logging with key name, updated docstring

## Decisions Made
- main.py already had `app.include_router(search.router)` from plan 03-02, so no modification needed
- Auth dependency placed as last parameter in function signature for readability (query params first, auth last)

## Deviations from Plan

- main.py was already wired with the search router by plan 03-02, so no changes needed there (plan assumed it might need updating)

## Issues Encountered
None

## Self-Check: PASSED

All 3 endpoints have `Depends(require_api_key)`. Search router registered in main.py. Error differentiation verified by architecture (401 from dependency, 400 from ValueError handler, 422 from FastAPI validation, 200 from service).

---
*Phase: 03-search-authentication*
*Completed: 2026-03-12*
