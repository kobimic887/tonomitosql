# Requirements: TonomitoSQL

**Defined:** 2026-03-12
**Core Value:** Given a SMILES query, return chemically similar molecules ranked by Tanimoto similarity from a user-uploaded molecular database — fast, accurate, and at scale (100K+ molecules).

## v1 Requirements

Requirements for initial release. Each maps to roadmap phases.

### Infrastructure

- [x] **INFR-01**: System deploys via Docker Compose with a single `docker compose up` command
- [x] **INFR-02**: PostgreSQL container runs RDKit cartridge with `mol` and `bfp` column types available
- [ ] **INFR-03**: API container runs FastAPI with Uvicorn, connects to PostgreSQL/RDKit
- [x] **INFR-04**: Database schema supports molecule storage with RDKit mol type and Morgan fingerprint columns with GiST indexes
- [x] **INFR-05**: PostgreSQL memory settings tuned for GiST index builds at 100K+ molecule scale

### Data Ingestion

- [ ] **INGT-01**: User can upload a CSV file via API endpoint containing SMILES and optional metadata columns
- [ ] **INGT-02**: System validates every SMILES string on ingest and reports row-level errors for invalid molecules
- [ ] **INGT-03**: System canonicalizes SMILES on ingest for consistent storage and matching
- [ ] **INGT-04**: System pre-computes Morgan fingerprints (radius 2) and stores them with GiST indexes on ingest
- [ ] **INGT-05**: System stores arbitrary CSV metadata columns as JSONB alongside molecules
- [ ] **INGT-06**: Ingestion handles 100K+ rows efficiently using PostgreSQL COPY protocol

### Search

- [ ] **SRCH-01**: User can search for an exact SMILES match and get a yes/no result with the matched molecule
- [ ] **SRCH-02**: User can search by Tanimoto similarity with a configurable threshold (default 0.5) and get results ranked by similarity score
- [ ] **SRCH-03**: User can search by substructure using a SMILES pattern and get all molecules containing that substructure
- [ ] **SRCH-04**: Search results include canonical SMILES and similarity score
- [ ] **SRCH-05**: Search results support pagination with offset/limit parameters
- [ ] **SRCH-06**: Similarity search performs sub-second queries on 100K+ molecules using GiST-indexed fingerprints

### API

- [ ] **API-01**: API key authentication required on all data and search endpoints
- [ ] **API-02**: Health/status endpoint returns API version, database status, and molecule count
- [ ] **API-03**: Error responses include descriptive messages distinguishing invalid SMILES, no results, bad parameters, and auth failures
- [ ] **API-04**: API auto-generates OpenAPI/Swagger documentation via FastAPI

## v2 Requirements

Deferred to future release. Tracked but not in current roadmap.

### Enhanced Search

- **SRCH-07**: User can search by substructure using SMARTS patterns for more expressive queries
- **SRCH-08**: User can search multiple SMILES in a single batch request
- **SRCH-09**: User can search by InChI or InChIKey as alternative molecular identifiers
- **SRCH-10**: User can use Dice similarity as an alternative to Tanimoto

### Enhanced Results

- **RSLT-01**: Search results include stored metadata from the original CSV upload
- **RSLT-02**: Search results include molecular descriptors (MW, LogP, TPSA, formula)

### Data Management

- **DATA-01**: User can manage multiple named datasets (create, list, delete)
- **DATA-02**: User can scope searches to a specific dataset or search across all datasets

### Advanced

- **ADVN-01**: Multiple fingerprint types available (MACCS, FeatMorgan, AtomPair)
- **ADVN-02**: Configurable Morgan radius as search parameter
- **ADVN-03**: Async upload processing with progress tracking for large files
- **ADVN-04**: Export search results in SDF format

## Out of Scope

Explicitly excluded. Documented to prevent scope creep.

| Feature | Reason |
|---------|--------|
| Molecule visualization/rendering (SVG/PNG) | Better handled client-side with RDKit.js or SmilesDrawer; adds complex dependency |
| Full user management (registration, roles, sessions) | API key auth covers 90% of use cases; unnecessary complexity for v1 |
| Real-time streaming ingestion | Complex state management, race conditions; batch CSV upload sufficient |
| Maximum common substructure (MCS) search | 60+ second queries, fundamentally an analytics operation not search |
| Tautomer enumeration | Computationally expensive, debated canonical forms; canonicalize on ingest instead |
| 3D similarity / shape search | Requires entirely different indexing, massive compute; different product |
| Multi-format upload (SDF, MOL2, PDB) | Each format has parsing edge cases; CSV with SMILES for v1 |
| Custom fingerprint parameters via API | Exposes internals, breaks optimization; offer well-chosen presets instead |
| Web frontend | API-only product; consumers build their own UI |
| Mobile app | API consumed by services and web frontends |

## Traceability

Which phases cover which requirements. Updated during roadmap creation.

| Requirement | Phase | Status |
|-------------|-------|--------|
| INFR-01 | Phase 1 | ✅ Complete |
| INFR-02 | Phase 1 | ✅ Complete |
| INFR-03 | Phase 1 | Pending |
| INFR-04 | Phase 1 | ✅ Complete |
| INFR-05 | Phase 1 | ✅ Complete |
| INGT-01 | Phase 2 | Pending |
| INGT-02 | Phase 2 | Pending |
| INGT-03 | Phase 2 | Pending |
| INGT-04 | Phase 2 | Pending |
| INGT-05 | Phase 2 | Pending |
| INGT-06 | Phase 2 | Pending |
| SRCH-01 | Phase 3 | Pending |
| SRCH-02 | Phase 3 | Pending |
| SRCH-03 | Phase 3 | Pending |
| SRCH-04 | Phase 3 | Pending |
| SRCH-05 | Phase 3 | Pending |
| SRCH-06 | Phase 3 | Pending |
| API-01 | Phase 3 | Pending |
| API-02 | Phase 1 | Pending |
| API-03 | Phase 3 | Pending |
| API-04 | Phase 1 | Pending |

**Coverage:**
- v1 requirements: 21 total
- Mapped to phases: 21 ✓
- Unmapped: 0

---
*Requirements defined: 2026-03-12*
*Last updated: 2026-03-12 after roadmap creation*
