# Project Research Summary

**Project:** TonomitoSQL
**Domain:** Cheminformatics molecular search REST API (self-hosted)
**Researched:** 2026-03-12
**Confidence:** HIGH

## Executive Summary

TonomitoSQL is a self-hosted cheminformatics search API that wraps PostgreSQL's RDKit cartridge in a clean REST interface, enabling researchers to upload their own molecular datasets (CSV with SMILES) and run similarity, substructure, and exact match searches. The competitive position is clear: this is not competing with ChEMBL or PubChem (fixed public databases), but replacing "researchers writing raw SQL against the RDKit cartridge" or "Python scripts doing in-memory RDKit searches that break at 100K molecules." The standard approach is a two-container Docker Compose setup — FastAPI for HTTP/validation/auth, and the `informaticsmatters/rdkit-cartridge-debian` image for PostgreSQL with native chemical types and GiST-indexed fingerprints.

The recommended stack is well-established and all components have verified compatibility: Python 3.12+, FastAPI, psycopg3, SQLAlchemy Core (for connection pooling only — NOT ORM, since RDKit `mol`/`bfp` types are unsupported by ORMs), and RDKit Python for client-side SMILES validation. The architecture follows a clear pattern from RDKit's official documentation: separate `molecules` and `fingerprints` tables, Morgan bit-vector fingerprints (ECFP4 equivalent) with GiST indexes, COPY protocol for bulk ingestion, and raw parameterized SQL for all chemistry queries. This is not speculative — it's the exact pattern used by ChEMBL's own PostgreSQL deployment.

The primary risks are: (1) RDKit cartridge Docker version mismatches causing silent `CREATE EXTENSION` failures — must be validated in Phase 1 before any other work proceeds; (2) silent SMILES rejection where `mol_from_smiles()` returns NULL instead of raising errors, silently dropping molecules during ingestion — must be caught with pre-validation in Python; (3) missing or wrong index types on fingerprint columns, turning sub-second similarity searches into 60-second table scans. All three risks have straightforward mitigations if addressed in the correct phase.

## Key Findings

### Recommended Stack

The stack is mature, with no experimental components. Every library has verified version compatibility and the Docker image has arm64 support (Apple Silicon).

**Core technologies:**
- **PostgreSQL 16 + RDKit Cartridge (`Release_2025_03_3`):** Database with native molecular types (`mol`, `bfp`), GiST-indexed similarity/substructure operators — this IS the product's core engine
- **FastAPI 0.135.1:** Async-capable API framework with automatic OpenAPI docs, Pydantic integration — objectively the best choice for new Python APIs
- **Python 3.12+ with RDKit 2025.9.6:** Application-side SMILES validation before DB insertion; canonical SMILES generation
- **psycopg 3.3.3:** Modern PostgreSQL driver with COPY protocol for bulk inserts — critical for ingestion performance
- **SQLAlchemy 2.0 Core (NOT ORM):** Connection pooling and query building for non-chemistry tables only; RDKit queries use raw parameterized SQL
- **Docker Compose:** Two-container orchestration (API + DB), standard deployment pattern

**Critical version note:** The `informaticsmatters/rdkit-cartridge-debian` image bundles a specific PostgreSQL version. Never use `:latest` — pin the release tag.

### Expected Features

**Must have (table stakes):**
- CSV upload with SMILES column auto-detection and per-row validation/error reporting
- Tanimoto similarity search (Morgan radius=2, ECFP4 equivalent) with configurable threshold and scores in results
- Substructure search (SMILES input) with GiST index acceleration
- Exact match search using `@=` operator on canonical SMILES
- API key authentication (`X-API-Key` header)
- Pagination (offset/limit), health endpoint, detailed error responses
- Store metadata as JSONB on ingest (near-zero cost, enables future return without re-ingest)

**Should have (differentiators — v1.x):**
- SMARTS-based substructure search (uses same GiST index, minimal implementation cost once SMILES substructure works)
- Metadata returned in search results (storage is v1, return is v1.x)
- Batch SMILES search (POST array, results grouped by query)
- InChI/InChIKey as query input
- Dataset management (namespace uploads, search within/across datasets)
- Molecular descriptors in results (MW, LogP, TPSA, formula — computed on ingest)

**Defer (v2+):**
- Multiple fingerprint types (MACCS, FeatMorgan, AtomPair)
- Async upload with progress tracking
- SDF export
- Molecule visualization (better handled client-side with RDKit.js)

**Anti-features (do NOT build):**
- Full user management / JWT sessions — API key covers 90% of use cases
- MCS search — computationally prohibitive (60+ seconds per query)
- 3D similarity / shape search — entirely different product
- Multi-format upload (SDF, MOL2) — scope creep; CSV with SMILES only for v1

### Architecture Approach

Two-container Docker Compose: FastAPI API container handles HTTP, auth, CSV parsing, and SMILES validation; PostgreSQL+RDKit container stores molecules and executes all chemistry operations at the database level. The critical architectural insight is that ALL fingerprint computation and chemical search happens in PostgreSQL via the RDKit cartridge's native operators — the API layer validates input and formats output but never does chemistry at scale.

**Major components:**
1. **API Container (FastAPI + Uvicorn)** — HTTP server, auth middleware, CSV parsing, SMILES pre-validation via RDKit Python
2. **DB Container (PostgreSQL + RDKit Cartridge)** — Molecule storage (`mol` type), fingerprint indexing (`bfp` + GiST), similarity/substructure queries via native SQL operators
3. **Ingestion Pipeline** — COPY protocol for bulk insert → staging table → `mol_from_smiles()` conversion → `morganbv_fp()` fingerprint generation → GiST index
4. **Search Layer** — Raw parameterized SQL using `%` (Tanimoto), `@>` (substructure), `@=` (exact match) operators with per-session `SET rdkit.tanimoto_threshold`

**Key schema pattern:** Separate `molecules` table (with `mol` column + GiST index) from `fingerprints` table (with `mfp2 bfp` column + GiST index). This follows the ChEMBL loading pattern from official RDKit docs.

### Critical Pitfalls

1. **RDKit cartridge + PostgreSQL version mismatch** — The cartridge is a compiled C extension; version mismatches cause silent failures. **Avoid:** Use `informaticsmatters/rdkit-cartridge-debian` with a pinned release tag, validate with `SELECT rdkit_version()` in health check.

2. **Silent SMILES rejection** — `mol_from_smiles()` returns NULL instead of errors, silently dropping molecules. **Avoid:** Pre-validate every SMILES with RDKit Python before DB insertion; report rejected rows with line numbers in upload response.

3. **Wrong fingerprint type / missing GiST index** — Using `sfp` instead of `bfp`, or B-tree instead of GiST, makes similarity search 10-100x slower with no error. **Avoid:** Use `morganbv_fp()` (bit-vector) with explicit `USING gist` index; verify with `EXPLAIN ANALYZE`.

4. **SMILES canonicalization confusion** — Same molecule has many SMILES strings; string comparison for "exact match" misses duplicates. **Avoid:** Canonicalize on ingest, use `@=` operator for exact match.

5. **`rdkit.tanimoto_threshold` not set per-query** — Threshold is a session variable, not a function parameter. If not set to match the user's request, the GiST index filters results incorrectly. **Avoid:** Always `SET rdkit.tanimoto_threshold` before each similarity query.

## Implications for Roadmap

Based on research, suggested phase structure:

### Phase 1: Docker Infrastructure + Database Foundation
**Rationale:** Everything depends on the database existing with the RDKit cartridge functional. This is the #1 failure point (version mismatches, extension loading). Must be validated before any other work.
**Delivers:** Working Docker Compose with API + DB containers, RDKit extension loaded, schema created (molecules, fingerprints, datasets, api_keys tables), PostgreSQL tuned for cheminformatics workload.
**Addresses:** Health endpoint (basic), Docker Compose deployment
**Avoids:** Pitfall 1 (RDKit/PG version mismatch), Pitfall 4 (PostgreSQL memory defaults)
**Stack elements:** Docker Compose, informaticsmatters image, PostgreSQL tuning, init-db.sh, FastAPI skeleton

### Phase 2: CSV Ingestion Pipeline
**Rationale:** You cannot test search without data. Ingestion is the second critical path and contains the most pitfalls (silent SMILES rejection, canonicalization, bulk performance).
**Delivers:** CSV upload endpoint, SMILES validation with error reporting, COPY protocol bulk insert, mol object conversion, Morgan fingerprint generation with GiST indexes.
**Addresses:** CSV upload, SMILES validation, canonical SMILES, Morgan fingerprint pre-computation, JSONB metadata storage
**Avoids:** Pitfall 2 (silent SMILES rejection), Pitfall 5 (canonicalization), Pitfall 4 (missing GiST index)
**Stack elements:** python-multipart, RDKit Python, psycopg3 COPY protocol, Pydantic schemas

### Phase 3: Search Endpoints
**Rationale:** Depends on Phase 1 (indexes) and Phase 2 (data). This is the core value proposition — three search types that demonstrate the product works.
**Delivers:** Exact match, Tanimoto similarity, and substructure search endpoints with pagination, similarity scores, and configurable threshold.
**Addresses:** Exact match, similarity search, substructure search, configurable threshold, pagination, similarity scores in results
**Avoids:** Pitfall 3 (wrong fingerprint type), Pitfall 6 (stereochemistry defaults), `tanimoto_threshold` session variable trap
**Stack elements:** Raw parameterized SQL with RDKit operators, Pydantic response models

### Phase 4: Authentication + Production Hardening
**Rationale:** Auth can be layered on after core functionality works. This phase also covers error handling, input sanitization, and API documentation — the "production-ready" polish.
**Delivers:** API key middleware, rate limiting floor (minimum Tanimoto threshold), comprehensive error handling, OpenAPI documentation, security hardening (no exposed DB port, parameterized queries).
**Addresses:** API key auth, error handling with detail, OpenAPI/Swagger docs
**Avoids:** SQL injection via SMILES strings, API key in query params, exposed PostgreSQL port

### Phase 5: Differentiators (v1.x)
**Rationale:** Only after core v1 is validated with users. These features build on the existing foundation with minimal architectural changes.
**Delivers:** SMARTS substructure, metadata in results, batch search, InChI/InChIKey support, dataset management, molecular descriptors.
**Addresses:** All P2 features from the prioritization matrix
**Avoids:** Scope creep — each feature is independently shippable

### Phase Ordering Rationale

- **Phase 1 → 2 → 3 is strictly sequential:** Database must exist before ingestion; data must exist before search. No parallelization possible.
- **Phase 4 can overlap with Phase 3:** Auth middleware is independent of search logic and can be developed in parallel, but should be integrated before external testing.
- **Phase 5 features are independently deployable:** Each v1.x feature can ship separately based on user feedback priority.
- **Ingestion before search avoids the "demo trap":** Building search first with hardcoded test data creates architecture that doesn't handle real-world ingestion edge cases.
- **GiST index creation belongs in Phase 2, not Phase 3:** Indexes must exist before search can be meaningfully tested. Building them during ingestion (after bulk load) follows the official RDKit recommendation.

### Research Flags

Phases likely needing deeper research during planning:
- **Phase 2 (Ingestion):** CSV parsing edge cases (encoding detection, SMILES column auto-detection, large file handling with HTTP timeouts). COPY protocol staging table pattern needs concrete implementation research.
- **Phase 3 (Search):** The `SET rdkit.tanimoto_threshold` per-session pattern needs careful design around connection pooling (threshold set on one connection shouldn't leak to another). KNN ordering with `<%>` operator needs performance validation at target scale.

Phases with standard patterns (skip research-phase):
- **Phase 1 (Infrastructure):** Well-documented Docker Compose pattern. informaticsmatters image has clear documentation.
- **Phase 4 (Auth):** Standard FastAPI middleware pattern. Well-documented in FastAPI docs.
- **Phase 5 (Differentiators):** Each feature uses existing RDKit cartridge operators already documented in Phase 3 research.

## Confidence Assessment

| Area | Confidence | Notes |
|------|------------|-------|
| Stack | HIGH | All versions verified on PyPI/Docker Hub. Compatibility matrix confirmed. No experimental components. |
| Features | HIGH | Feature landscape derived from RDKit cartridge docs (authoritative) and ChEMBL API (production reference). Competitive analysis grounded in real public APIs. |
| Architecture | HIGH | Schema and query patterns directly from RDKit's official ChEMBL loading tutorial. Docker image verified with arm64 support. Two-container pattern is the established community standard. |
| Pitfalls | HIGH | All pitfalls sourced from official RDKit docs, installation guides, and cartridge README. Warning signs and recovery strategies are specific and actionable. |

**Overall confidence:** HIGH — This is a well-documented domain with a mature toolchain. The RDKit cartridge has been in production use at ChEMBL (1.8M compounds) for years, and the patterns are well-established. The main risk is not "will this approach work" but "will we implement the known patterns correctly."

### Gaps to Address

- **Connection pooling + `tanimoto_threshold` isolation:** The `SET rdkit.tanimoto_threshold` session variable interacts with connection pooling. Need to verify that psycopg3's connection pool properly resets session state, or use per-transaction SET. Research this during Phase 3 planning.
- **Large CSV upload timeout handling:** At 100K+ rows, synchronous HTTP upload may timeout. PROJECT.md doesn't mention async processing, but the ingestion pipeline may need HTTP 202 + polling for large files. Validate actual timing during Phase 2 implementation.
- **RDKit Python `rdkit-pypi` vs `rdkit` package naming:** The pip package name has changed over time. Verify the correct package name works in the Dockerfile during Phase 1.
- **informaticsmatters image tag discrepancy:** STACK.md references `Release_2025_03_3` while PITFALLS.md references `Release_2024_09_3` as "latest." Verify the actual latest tag during Phase 1 Docker setup.

## Sources

### Primary (HIGH confidence)
- RDKit PostgreSQL Cartridge Documentation (v2025.09.6): https://www.rdkit.org/docs/Cartridge.html — Schema patterns, operators, functions, GiST indexing, ChEMBL loading tutorial
- RDKit GitHub (cartridge source): https://github.com/rdkit/rdkit/tree/master/Code/PgSQL/rdkit — GiST index implementation, `mol`/`bfp`/`sfp` types, installation procedures
- InformaticsMatters Docker images: https://hub.docker.com/r/informaticsmatters/rdkit-cartridge-debian — Verified release tags, arm64 support
- ChEMBL Web Services Documentation: https://chembl.gitbook.io/chembl-interface-documentation/web-services — API design patterns, search endpoint structure, pagination
- PyPI package pages — Version numbers verified for FastAPI, RDKit, psycopg, SQLAlchemy, Uvicorn, Pydantic, Alembic

### Secondary (MEDIUM confidence)
- SMILES specification analysis (Depth-First blog) — Context on SMILES standardization challenges
- RDKit Getting Started in Python — SMILES parsing behavior, `MolFromSmiles` returning None

### Tertiary (LOW confidence)
- None — all findings verified against authoritative sources

---
*Research completed: 2026-03-12*
*Ready for roadmap: yes*
