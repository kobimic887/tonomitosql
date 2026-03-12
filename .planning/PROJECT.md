# TonomitoSQL

## What This Is

A Dockerized REST API that ingests CSV files containing SMILES molecular structures and associated metadata, stores them in PostgreSQL with the RDKit cartridge, and exposes search endpoints for exact match, Tanimoto similarity, and substructure queries. Built for pharmaceutical/cheminformatics workflows where researchers need to find structurally similar compounds from large molecular databases.

## Core Value

Given a SMILES query, return chemically similar molecules ranked by Tanimoto similarity from a user-uploaded molecular database — fast, accurate, and at scale (100K+ molecules).

## Requirements

### Validated

(None yet — ship to validate)

### Active

- [ ] Upload CSV files containing SMILES and metadata columns via API endpoint
- [ ] Parse and validate SMILES strings during ingestion, rejecting invalid molecules
- [ ] Store molecules with RDKit fingerprints in PostgreSQL for indexed searching
- [ ] Search by exact SMILES match
- [ ] Search by Tanimoto similarity with configurable threshold
- [ ] Search by substructure (SMARTS/SMILES pattern)
- [ ] Return SMILES and similarity scores in search results
- [ ] Secure all endpoints with API key authentication
- [ ] Handle 100K+ molecules with acceptable query performance
- [ ] Deploy as Docker containers (API + PostgreSQL/RDKit)

### Out of Scope

- Web frontend — API-only, consumers build their own UI
- Full user auth (JWT, sessions, registration) — simple API key is sufficient
- Molecule visualization/rendering — consumers handle display
- Metadata in search results — v1 returns SMILES + score only
- Real-time streaming ingestion — batch CSV upload only
- Mobile app — API consumed by backend services and web frontends

## Context

- PostgreSQL RDKit cartridge provides native chemical fingerprint indexing and Tanimoto similarity operations at the database level, avoiding application-layer computation
- SMILES (Simplified Molecular Input Line Entry System) is the standard text representation for molecular structures in cheminformatics
- Tanimoto coefficient (Jaccard index applied to molecular fingerprints) is the industry-standard measure of molecular similarity
- The API serves both backend services (automated pipelines) and web frontends (researcher tools)
- CSV files may contain varying metadata columns alongside the required SMILES column

## Constraints

- **Tech stack**: Python (FastAPI) — strongest cheminformatics library ecosystem (RDKit)
- **Database**: PostgreSQL with RDKit cartridge — native molecular operations, fingerprint indexing
- **Deployment**: Docker Compose — API container + PostgreSQL/RDKit container
- **Scale**: Must handle 100K+ molecules with sub-second similarity searches
- **Auth**: API key-based — simple, stateless

## Key Decisions

| Decision | Rationale | Outcome |
|----------|-----------|---------|
| PostgreSQL + RDKit cartridge over in-memory search | Database-level fingerprint indexing scales to 100K+ molecules; GiST indexes on fingerprints enable fast Tanimoto queries | — Pending |
| FastAPI over Flask | Async support, automatic OpenAPI docs, better performance for concurrent requests | — Pending |
| API key auth over JWT | Simpler for service-to-service and developer use; no session management needed | — Pending |
| SMILES + score only in results | Keeps search responses fast and simple; metadata can be fetched separately if needed | — Pending |

---
*Last updated: 2026-03-12 after initialization*
