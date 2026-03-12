# Project State

## Project Reference

See: .planning/PROJECT.md (updated 2026-03-12)

**Core value:** Given a SMILES query, return chemically similar molecules ranked by Tanimoto similarity from a user-uploaded molecular database — fast, accurate, and at scale (100K+ molecules).
**Current focus:** Phase 1: Infrastructure & API Foundation

## Current Position

Phase: 1 of 3 (Infrastructure & API Foundation) — COMPLETE
Plan: 2 of 2 in current phase
Status: Phase Complete
Last activity: 2026-03-12 — Completed 01-02-PLAN.md

Progress: [███░░░░░░░] 29%

## Performance Metrics

**Velocity:**
- Total plans completed: 2
- Average duration: 2.5 min
- Total execution time: 0.08 hours

**By Phase:**

| Phase | Plans | Total | Avg/Plan |
|-------|-------|-------|----------|
| 01-infrastructure | 2 | 5 min | 2.5 min |

**Recent Trend:**
- Last 5 plans: 01-01 (3 min), 01-02 (2 min)
- Trend: Stable

*Updated after each plan completion*

## Accumulated Context

### Decisions

Decisions are logged in PROJECT.md Key Decisions table.
Recent decisions affecting current work:

- [Roadmap]: 3-phase quick-depth structure — Infrastructure → Ingestion → Search+Auth
- [Roadmap]: API auth (API-01) merged into Phase 3 with search rather than standalone phase
- [01-01]: Used informaticsmatters/rdkit-cartridge-debian:Release_2024_09_3 (verified latest tag)
- [01-01]: Port 5432 not exposed to host — API connects via Docker network only
- [01-01]: Separate fingerprints table with mfp2 bfp column (ChEMBL pattern)
- [01-01]: metadata JSONB column on molecules for arbitrary CSV column storage
- [01-02]: Sync psycopg (not async) — RDKit queries CPU-bound at DB, async adds complexity with no benefit
- [01-02]: psycopg ConnectionPool min=2, max=10 for connection reuse
- [01-02]: No SQLAlchemy — raw psycopg for all RDKit queries per research
- [01-02]: No rdkit-pypi yet — defer to Phase 2 to keep image small

### Pending Todos

None yet.

### Blockers/Concerns

- ~~[Research]: RDKit cartridge Docker image tag needs verification during Phase 1 (Release_2025_03_3 vs actual latest)~~ → Resolved: using Release_2024_09_3
- [Research]: Connection pooling + `tanimoto_threshold` session variable isolation — verify during Phase 3 planning
- [Research]: Large CSV upload may timeout at 100K+ rows — validate during Phase 2 implementation

## Session Continuity

Last session: 2026-03-12
Stopped at: Completed 01-02-PLAN.md (Phase 1 complete)
Resume file: None
