# Feature Research

**Domain:** Cheminformatics molecular search REST API
**Researched:** 2026-03-12
**Confidence:** HIGH (RDKit cartridge docs verified, ChEMBL API docs verified, domain knowledge from authoritative sources)

## Feature Landscape

### Table Stakes (Users Expect These)

Features users assume exist. Missing these = product feels incomplete for any cheminformatics search tool.

| Feature | Why Expected | Complexity | Notes |
|---------|--------------|------------|-------|
| CSV upload with SMILES column | Core ingestion path; every lab exports CSV from Excel/LIMS | MEDIUM | Must auto-detect SMILES column or let user specify. Validate every SMILES on ingest, report row-level errors. RDKit's `mol_from_smiles()` returns NULL for invalid SMILES — use this for validation. |
| SMILES validation on ingest | Invalid SMILES corrupt the database and break downstream searches | LOW | RDKit's `is_valid_smiles()` and `mol_from_smiles()` handle this natively. Report rejected rows with line numbers and reasons. |
| Exact match search | Researchers need "do I already have this molecule?" | LOW | RDKit cartridge `@=` operator. Must canonicalize SMILES before comparison. |
| Tanimoto similarity search | Industry-standard similarity measure; every competitor has it | MEDIUM | RDKit's `morganbv_fp()` with `%` operator and `<%>` for KNN ordering. Configurable threshold (RDKit default 0.5). Must return similarity scores with results. |
| Substructure search (SMILES) | Core workflow: "find all molecules containing this scaffold" | MEDIUM | RDKit `@>` operator with GiST index. Accepts SMILES as substructure query. Performance varies widely by query molecule — some queries scan many rows. |
| Configurable similarity threshold | Different use cases need different cutoffs (0.5 for exploration, 0.9 for close analogs) | LOW | RDKit `rdkit.tanimoto_threshold` parameter. Expose as query parameter. |
| Morgan fingerprints (ECFP-like) | Industry default for similarity searching; most published benchmarks use Morgan/ECFP | MEDIUM | `morganbv_fp(mol, radius)` — default radius 2 (ECFP4 equivalent). Pre-compute and index on ingest for fast search. |
| Similarity scores in results | Researchers need to rank and filter results by relevance | LOW | `tanimoto_sml()` function returns the score. Include in response payload. |
| Canonical SMILES in results | Unambiguous molecular identifier in output | LOW | `mol_to_smiles()` returns canonical form. Always return canonical SMILES regardless of what was uploaded. |
| API key authentication | Protect access to proprietary molecular databases | LOW | Simple header-based API key. No need for JWT/sessions for v1. |
| Pagination | Result sets can be large (substructure search can return thousands) | LOW | Offset/limit pattern. ChEMBL uses `limit` + `offset` with `page_meta` including `total_count`, `next`, `previous`. |
| Error handling with detail | Researchers aren't API experts; need clear messages about what went wrong | LOW | Distinguish: invalid SMILES, no results found, threshold out of range, malformed request. Return HTTP status codes correctly. |
| Health/status endpoint | DevOps need to monitor the service | LOW | Return API version, database status, molecule count. ChEMBL has `/status` endpoint. |

### Differentiators (Competitive Advantage)

Features that set the product apart from running raw SQL against RDKit PostgreSQL. Not expected, but valuable.

| Feature | Value Proposition | Complexity | Notes |
|---------|-------------------|------------|-------|
| SMARTS-based substructure search | More expressive queries than SMILES substructure — wildcards, atom/bond queries, ring specifications | LOW | RDKit `qmol` type handles SMARTS natively with `@>` operator. Slower than SMILES queries but much more powerful. Competitors (ChEMBL) don't expose SMARTS directly via API. |
| Multiple fingerprint types | Different fingerprints excel at different tasks; power users want to choose | MEDIUM | RDKit supports Morgan, FeatMorgan (FCFP-like), RDKit, MACCS, AtomPair, Torsion. Start with Morgan (default), add others later. Each needs its own pre-computed column + GiST index. |
| Molecular descriptors in results | Return MW, LogP, TPSA, formula alongside SMILES — saves researchers a round-trip to compute these | MEDIUM | RDKit has `mol_amw()`, `mol_logp()`, `mol_tpsa()`, `mol_formula()`, `mol_hba()`, `mol_hbd()`, `mol_numrotatablebonds()`. Compute on ingest, store as columns. |
| Metadata preservation and return | Users upload CSV with assay data, vendor IDs, etc. — being able to search and get those back is a killer feature | MEDIUM | Store arbitrary CSV columns as JSONB. Return metadata in search results. This is what PROJECT.md explicitly defers ("v1 returns SMILES + score only") but it's the #1 thing researchers will ask for. |
| Batch SMILES search | Search for multiple molecules at once (common in HTS triage: "which of these 500 hits are novel?") | MEDIUM | Accept array of SMILES, return results grouped by query. ChEMBL supports this via POST with `X-HTTP-Method-Override:GET`. Significant time savings over sequential queries. |
| InChI/InChIKey support | Alternative molecular identifier used in PubChem, patents, and regulatory submissions | LOW | RDKit's `mol_inchi()` and `mol_inchikey()`. Accept as query input, include in results. ChEMBL accepts InChIKey as search input. |
| Configurable Morgan radius | Radius 2 (ECFP4) vs radius 3 (ECFP6) captures different structural neighborhoods | LOW | `morganbv_fp(mol, radius)` already supports this. Expose as query parameter with default=2. |
| Dataset management (multiple uploads) | Researchers work with multiple compound libraries — need to search within or across datasets | MEDIUM | Namespace uploads. Search can target specific dataset or all datasets. Enables multi-project use. |
| Dice similarity metric | Alternative to Tanimoto, preferred for some fingerprint types and fragment-based work | LOW | RDKit `#` operator and `dice_sml()` function. Same index works for both metrics. |
| OpenAPI/Swagger documentation | Self-documenting API reduces support burden, enables client generation | LOW | FastAPI generates this automatically. No extra work needed. List as differentiator because many cheminformatics tools have poor docs. |
| SDF/MOL format export | Standard chemical data exchange format for downstream tools (e.g., docking, visualization) | LOW | RDKit `mol_to_ctab()` generates MOL blocks. Wrap in SDF with metadata. ChEMBL supports `.sdf` format. |
| Upload progress and async processing | Large CSV files (100K+ rows) take minutes to ingest; users need feedback | HIGH | Background job with progress polling endpoint. Return job ID immediately, poll for completion. |

### Anti-Features (Commonly Requested, Often Problematic)

Features that seem good but create problems. Deliberately NOT building these.

| Feature | Why Requested | Why Problematic | Alternative |
|---------|---------------|-----------------|-------------|
| Molecule visualization/rendering (SVG/PNG) | Researchers want to see structures, not just SMILES | Adds image generation dependency, complex rendering config, increases response sizes, and is better handled client-side with existing JS libraries (RDKit.js, SmilesDrawer) | Return SMILES; let consumers render with client-side libraries. Document recommended client-side renderers. |
| Full user management (registration, roles, sessions) | Enterprise use cases need user isolation | JWT/session management adds significant complexity for v1; API key auth covers 90% of use cases (service-to-service, individual researchers) | API key per consumer. Add user management only if multi-tenant demand is proven. |
| Real-time streaming ingestion | "We want to add molecules one at a time from our pipeline" | Creates complex state management, partial-index issues, race conditions with concurrent searches during ingest | Batch CSV upload. If single-molecule add is needed, accept it as a simple POST but don't build streaming infrastructure. |
| Maximum common substructure (MCS) search | Powerful cheminformatics operation, RDKit supports `fmcs()` | MCS is computationally expensive (can take 60+ seconds per query as shown in RDKit docs), hard to set timeouts, and is fundamentally an analytics operation not a search operation | Expose as a separate, explicitly-async endpoint if demand is proven. Not in v1. |
| Tautomer-aware searching | Molecules can exist in multiple tautomeric forms; "shouldn't the search handle this?" | Tautomer enumeration is computationally expensive, increases index size dramatically, and the "right" canonical tautomer is still debated in the field | Canonicalize on ingest using RDKit's tautomer canonicalization. Document the behavior. Don't enumerate all tautomers. |
| 3D similarity / shape search | 3D pharmacophore matching is used in drug discovery | Requires 3D conformer generation, massive compute, entirely different indexing strategy. Out of scope for a SMILES-in/SMILES-out API. | Stay 2D. If 3D is needed, that's a different product. |
| Multi-format upload (SDF, MOL2, PDB) | "We have data in SDF format too" | Each format has parsing edge cases, validation rules, and metadata conventions. Scope creep. | CSV with SMILES only for v1. Provide a conversion script/guide for SDF→CSV using RDKit Python. |
| Custom fingerprint computation via API | "Let me define my own fingerprint parameters" | Exposes internal implementation details, makes indexing strategy impossible to optimize, creates a support nightmare | Offer 2-3 well-chosen presets (Morgan r=2, Morgan r=3, MACCS). Don't expose raw parameters. |
| Stereochemistry-aware substructure by default | "My query has a chiral center, respect it" | RDKit defaults to ignoring stereochemistry in substructure for good reason — most users want structural matches regardless of chirality. Enabling by default surprises users. | Keep RDKit default (ignore chirality). Offer `stereo=true` query parameter for users who need it. Document the behavior clearly. |

## Feature Dependencies

```
CSV Upload + SMILES Validation
    └──requires──> Molecule Storage (RDKit mol type + fingerprint columns)
                       └──enables──> Exact Match Search
                       └──enables──> Similarity Search (requires fingerprint index)
                       └──enables──> Substructure Search (requires GiST index on mol)

Similarity Search
    └──requires──> Morgan Fingerprint Pre-computation + GiST Index
    └──enhances──> Batch SMILES Search (search N molecules at once)

Substructure Search (SMILES)
    └──enhances──> SMARTS-based Substructure (same index, different query type)

Multiple Fingerprint Types
    └──requires──> Similarity Search (baseline Morgan must work first)
    └──requires──> Additional pre-computed columns + indexes (storage/ingest cost)

Molecular Descriptors
    └──requires──> Molecule Storage (compute from stored mol objects)
    └──independent of──> Search features (can add without changing search)

Dataset Management
    └──requires──> CSV Upload (namespaced storage)
    └──enhances──> All search types (filter by dataset)

Metadata Return
    └──requires──> CSV Upload (metadata stored on ingest)
    └──conflicts with──> "SMILES + score only" simplicity goal (adds response complexity)

Async Upload Processing
    └──requires──> CSV Upload
    └──requires──> Background job infrastructure (Celery/ARQ or similar)
```

### Dependency Notes

- **Similarity Search requires Morgan Fingerprint Index:** Without pre-computed fingerprints and GiST indexes, Tanimoto queries do full table scans. This is the single most important performance dependency.
- **SMARTS enhances Substructure Search:** Uses the same `@>` operator and GiST index but with `qmol` type. Minimal additional implementation once SMILES substructure works.
- **Multiple Fingerprint Types require storage trade-off:** Each additional fingerprint type adds ~100-200 bytes per molecule + index build time. With 100K molecules, this is manageable. At 1M+, it matters.
- **Metadata Return conflicts with simplicity goal:** PROJECT.md says "v1 returns SMILES + score only" — but storing metadata on ingest (in JSONB) costs almost nothing. Deferring the *return* is fine, but the *storage* should be v1.
- **Dataset Management enhances all search types:** Adding a `dataset_id` filter to queries is trivial once the data model supports it. The complexity is in the management (create, list, delete datasets).

## MVP Definition

### Launch With (v1)

Minimum viable product — what's needed to validate the concept with real researchers.

- [ ] CSV upload with SMILES validation — Core ingestion, without this nothing works
- [ ] Exact match search — "Do I have this molecule?"
- [ ] Tanimoto similarity search (Morgan r=2) with configurable threshold — Core value proposition
- [ ] Substructure search (SMILES input) — Second most-requested search type
- [ ] Canonical SMILES + similarity score in results — Minimum useful output
- [ ] API key authentication — Basic access control
- [ ] Pagination (offset/limit) — Handle large result sets
- [ ] Health/status endpoint — Operational visibility
- [ ] Error responses with detail — Usable by non-expert API consumers
- [ ] Docker Compose deployment — API + PostgreSQL/RDKit in one command
- [ ] Store metadata as JSONB on ingest — Near-zero cost, enables future metadata return without re-ingest

### Add After Validation (v1.x)

Features to add once core is working and users are providing feedback.

- [ ] Metadata in search results — Add when first user asks "where are my other columns?"
- [ ] SMARTS substructure search — Add when power users request more expressive queries
- [ ] InChI/InChIKey as query input — Add when users working with patent/regulatory data arrive
- [ ] Batch SMILES search — Add when users demonstrate sequential-query pain (>10 queries at a time)
- [ ] Dataset management (multiple named uploads) — Add when second user/project onboards
- [ ] Molecular descriptors in results (MW, LogP, formula) — Add when users request filtering/sorting by properties
- [ ] Dice similarity as alternative metric — Add when fragment-based drug discovery users arrive

### Future Consideration (v2+)

Features to defer until product-market fit is established.

- [ ] Multiple fingerprint types (MACCS, FeatMorgan, AtomPair) — Only after validating that Morgan r=2 isn't sufficient for most users
- [ ] Configurable Morgan radius as query parameter — Power user feature, low demand expected
- [ ] Async upload with progress tracking — Only needed at scale (500K+ molecules)
- [ ] SDF export format — Only if downstream tools can't consume SMILES
- [ ] Stereochemistry-aware substructure (`stereo=true` flag) — Niche use case

## Feature Prioritization Matrix

| Feature | User Value | Implementation Cost | Priority |
|---------|------------|---------------------|----------|
| CSV upload + SMILES validation | HIGH | MEDIUM | P1 |
| Tanimoto similarity search (Morgan) | HIGH | MEDIUM | P1 |
| Substructure search (SMILES) | HIGH | MEDIUM | P1 |
| Exact match search | HIGH | LOW | P1 |
| Configurable similarity threshold | HIGH | LOW | P1 |
| Pagination | HIGH | LOW | P1 |
| API key auth | MEDIUM | LOW | P1 |
| Canonical SMILES + scores in results | HIGH | LOW | P1 |
| Health/status endpoint | MEDIUM | LOW | P1 |
| Error handling with detail | MEDIUM | LOW | P1 |
| Store metadata as JSONB | MEDIUM | LOW | P1 |
| Metadata in search results | HIGH | LOW | P2 |
| SMARTS substructure search | MEDIUM | LOW | P2 |
| InChI/InChIKey support | MEDIUM | LOW | P2 |
| Batch SMILES search | MEDIUM | MEDIUM | P2 |
| Dataset management | MEDIUM | MEDIUM | P2 |
| Molecular descriptors in results | MEDIUM | MEDIUM | P2 |
| Dice similarity | LOW | LOW | P2 |
| Multiple fingerprint types | LOW | HIGH | P3 |
| Async upload with progress | LOW | HIGH | P3 |
| SDF export | LOW | LOW | P3 |
| Configurable Morgan radius | LOW | LOW | P3 |
| Stereo-aware substructure flag | LOW | LOW | P3 |

**Priority key:**
- P1: Must have for launch
- P2: Should have, add when possible (driven by user feedback)
- P3: Nice to have, future consideration

## Competitor Feature Analysis

| Feature | ChEMBL API | PubChem PUG REST | TonomitoSQL Approach |
|---------|------------|------------------|----------------------|
| Exact match | Yes (connectivity search) | Yes (by CID, SMILES, InChIKey) | Yes — `@=` operator on canonical SMILES |
| Similarity search | Yes (Tanimoto, threshold in URL path `/SMILES/80`) | Yes (Tanimoto, 2D fingerprints) | Yes — Morgan FP with configurable threshold as query param |
| Substructure search | Yes (SMILES and InChIKey input) | Yes (SMILES, SMARTS) | Yes — SMILES input, SMARTS as differentiator |
| Query input types | SMILES, InChIKey, ChEMBL ID | SMILES, InChI, InChIKey, name, CID | SMILES (v1), InChIKey (v1.x) |
| Data ingestion | No — fixed ChEMBL database | No — fixed PubChem database | **Yes — user uploads own CSV. This is the core differentiator.** |
| Output formats | JSON, XML, YAML, SDF, SVG | JSON, XML, CSV, SDF, PNG | JSON (v1). SDF possible in v2. |
| Pagination | Yes (limit/offset with page_meta) | Yes (listkey-based async) | Yes — limit/offset |
| Filtering by properties | Yes (MW, LogP, etc. via query params) | Yes (via PUG REST compound property endpoint) | v1.x — molecular descriptors stored, filterable |
| Batch search | Yes (POST with override header) | Yes (up to ~100 CIDs per request) | v1.x — POST array of SMILES |
| API auth | None (public database) | None (public, rate-limited) | API key — required because user data is private |
| Self-hosted | No (EBI-hosted only) | No (NCBI-hosted only) | **Yes — Docker Compose. Second core differentiator.** |
| Custom data | No | No | **Yes — arbitrary metadata columns preserved** |
| Rate limiting | Yes (implied) | Yes (5 requests/second) | Not initially — API key controls access |

**Key competitive insight:** ChEMBL and PubChem are fixed public databases with sophisticated APIs. TonomitoSQL is a *self-hosted molecular search engine for your own data*. The competitor is not ChEMBL — it's "researchers writing raw SQL against the RDKit cartridge" or "Python scripts using RDKit in-memory." The differentiator is wrapping the RDKit cartridge in a usable, deployable, self-service API.

## Sources

- **RDKit PostgreSQL Cartridge Documentation (v2025.09.6):** https://www.rdkit.org/docs/Cartridge.html — [HIGH confidence] Primary reference for all fingerprint types, search operators, descriptor functions, and PostgreSQL configuration. Verified current (2025 release).
- **ChEMBL Web Services Documentation:** https://chembl.gitbook.io/chembl-interface-documentation/web-services/chembl-data-web-services — [HIGH confidence] API design patterns, search endpoint structure, pagination, filtering, chemical searching. Official documentation from EBI.
- **ChEMBL API Interactive Docs:** https://www.ebi.ac.uk/chembl/ws — [HIGH confidence] Resource list, supported formats, CORS/JSONP support.
- **SMILES specification analysis (Depth-First blog):** https://depth-first.com/articles/2022/06/01/protosmiles/ — [MEDIUM confidence] Context on SMILES standardization challenges affecting validation strategies.

---
*Feature research for: Cheminformatics molecular search REST API (TonomitoSQL)*
*Researched: 2026-03-12*
