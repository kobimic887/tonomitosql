# Roadmap: TonomitoSQL

## Overview

TonomitoSQL goes from zero to a working molecular search API in three phases: first, stand up the Docker infrastructure with PostgreSQL/RDKit cartridge and a FastAPI skeleton; second, build the CSV ingestion pipeline that validates SMILES, computes fingerprints, and stores molecules at scale; third, implement the three search types (exact, similarity, substructure) with API key auth and production error handling. Each phase delivers a verifiable capability that unblocks the next.

## Phases

**Phase Numbering:**
- Integer phases (1, 2, 3): Planned milestone work
- Decimal phases (2.1, 2.2): Urgent insertions (marked with INSERTED)

Decimal phases appear between their surrounding integers in numeric order.

- [ ] **Phase 1: Infrastructure & API Foundation** - Docker Compose with PostgreSQL/RDKit, FastAPI skeleton, health endpoint, database schema
- [ ] **Phase 2: CSV Ingestion Pipeline** - Upload, validate, canonicalize SMILES, compute fingerprints, store molecules at scale
- [ ] **Phase 3: Search & Authentication** - Exact match, Tanimoto similarity, substructure search with API key auth and error handling

## Phase Details

### Phase 1: Infrastructure & API Foundation
**Goal**: A single `docker compose up` brings up a working FastAPI API connected to PostgreSQL with the RDKit cartridge, schema created, and health endpoint responding
**Depends on**: Nothing (first phase)
**Requirements**: INFR-01, INFR-02, INFR-03, INFR-04, INFR-05, API-02, API-04
**Success Criteria** (what must be TRUE):
  1. Running `docker compose up` starts both containers and the API responds on its configured port
  2. Health endpoint returns API version, database connection status, RDKit cartridge version, and molecule count (zero initially)
  3. Database has `molecules` and `fingerprints` tables with `mol` and `bfp` column types and GiST indexes defined
  4. API auto-generates browsable OpenAPI/Swagger documentation at `/docs`
  5. PostgreSQL memory settings are configured for GiST index builds at 100K+ scale (not default 128MB shared_buffers)
**Plans**: 2 plans

Plans:
- [ ] 01-01-PLAN.md — Docker Compose + PostgreSQL/RDKit container + schema + memory tuning
- [ ] 01-02-PLAN.md — FastAPI skeleton + health endpoint + OpenAPI docs

### Phase 2: CSV Ingestion Pipeline
**Goal**: Users can upload a CSV file containing SMILES and get back a detailed report of what was ingested, what failed validation, and have all valid molecules stored with pre-computed fingerprints ready for search
**Depends on**: Phase 1
**Requirements**: INGT-01, INGT-02, INGT-03, INGT-04, INGT-05, INGT-06
**Success Criteria** (what must be TRUE):
  1. User can POST a CSV file to an upload endpoint and receive a response listing how many molecules were ingested, how many failed, and which rows had invalid SMILES
  2. Invalid SMILES strings are rejected with row-level error details; valid SMILES are canonicalized before storage
  3. Arbitrary metadata columns from the CSV are stored as JSONB alongside each molecule
  4. A 100K-row CSV file completes ingestion without timeout or failure (using COPY protocol)
  5. After ingestion, molecules have Morgan fingerprints (radius 2) stored with GiST indexes ready for similarity search
**Plans**: TBD

Plans:
- [ ] 02-01: TBD
- [ ] 02-02: TBD

### Phase 3: Search & Authentication
**Goal**: Users can query the molecular database by exact match, Tanimoto similarity, or substructure pattern, with all endpoints protected by API key authentication and returning clear error messages
**Depends on**: Phase 2
**Requirements**: SRCH-01, SRCH-02, SRCH-03, SRCH-04, SRCH-05, SRCH-06, API-01, API-03
**Success Criteria** (what must be TRUE):
  1. User can search for an exact SMILES match and get a yes/no result with the matched molecule's canonical SMILES
  2. User can search by Tanimoto similarity with a configurable threshold (default 0.5) and get results ranked by similarity score, with sub-second response on 100K+ molecules
  3. User can search by substructure using a SMILES pattern and get all matching molecules
  4. All search results include canonical SMILES and similarity scores, and support pagination (offset/limit)
  5. All data and search endpoints require a valid API key; requests without a key or with an invalid key get a clear 401/403 error distinguishing auth failures from invalid SMILES, no results, and bad parameters
**Plans**: TBD

Plans:
- [ ] 03-01: TBD
- [ ] 03-02: TBD
- [ ] 03-03: TBD

## Progress

**Execution Order:**
Phases execute in numeric order: 1 → 2 → 3

| Phase | Plans Complete | Status | Completed |
|-------|----------------|--------|-----------|
| 1. Infrastructure & API Foundation | 1/2 | In Progress | - |
| 2. CSV Ingestion Pipeline | 0/2 | Not started | - |
| 3. Search & Authentication | 0/3 | Not started | - |
