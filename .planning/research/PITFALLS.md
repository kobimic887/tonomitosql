# Pitfalls Research

**Domain:** Cheminformatics SMILES Search API (PostgreSQL + RDKit Cartridge + FastAPI)
**Researched:** 2026-03-12
**Confidence:** HIGH (RDKit official docs, cartridge reference, installation guides)

## Critical Pitfalls

### Pitfall 1: RDKit Cartridge + PostgreSQL Version Mismatch in Docker

**What goes wrong:**
The RDKit PostgreSQL cartridge is a compiled C extension (`rdkit.so` / `rdkit.dll`) that must be built against the exact major version of PostgreSQL it will run in. Using `pip install rdkit` does NOT install the cartridge — it only gives you the Python bindings. The cartridge requires either building from source with `-DRDK_BUILD_PGSQL=ON` or using a pre-built Docker image like `informaticsmatters/rdkit-cartridge-debian`. Mixing PostgreSQL versions (e.g., building against PG15 headers but running in PG16) causes `CREATE EXTENSION rdkit` to fail silently or crash.

**Why it happens:**
Developers assume `pip install rdkit` or `conda install rdkit` gives them the full cartridge. They don't realize the PostgreSQL extension is a separate artifact that requires native compilation against PostgreSQL server headers. The `informaticsmatters/rdkit-cartridge-debian` Docker image pins specific PG + RDKit version combinations — the latest tag may not match your target PG version.

**How to avoid:**
- Use `informaticsmatters/rdkit-cartridge-debian` as your base PostgreSQL image. The most recent tag is `Release_2024_09_3`. Verify the PostgreSQL major version inside the image matches your expectations before building on top of it.
- Test `CREATE EXTENSION rdkit` and `SELECT rdkit_version()` in your Docker entrypoint or health check.
- Pin both the RDKit release tag AND PostgreSQL major version explicitly in your Dockerfile. Never use `:latest`.
- If building from source, ensure the `PostgreSQL_CONFIG_DIR`, `PostgreSQL_INCLUDE_DIR`, and `PostgreSQL_TYPE_INCLUDE_DIR` CMake flags all point to the correct PostgreSQL installation.

**Warning signs:**
- `ERROR: could not load library "...rdkit.so"` at `CREATE EXTENSION` time
- `GLIBCXX_3.4.XX not found` errors (shared library mismatch between build and runtime environments)
- `CREATE EXTENSION rdkit` succeeds but `mol_from_smiles()` returns errors about missing functions
- Docker build succeeds but container crashes on startup

**Phase to address:**
Phase 1 (Infrastructure/Docker Setup) — this must work before anything else. Validate with an integration test that creates the extension and runs `SELECT mol_from_smiles('C')`.

---

### Pitfall 2: Silent SMILES Rejection Without Error Propagation

**What goes wrong:**
`mol_from_smiles()` returns `NULL` for invalid SMILES instead of raising an error. If your ingestion pipeline uses `INSERT INTO ... mol_from_smiles(smiles::cstring)` without filtering, you get NULL molecules in your table that silently corrupt search results. Worse, `mol_from_smiles()` issues `WARNING` log messages (not errors) for rejected SMILES, so in a batch insert of 100K rows, you may never see them.

The RDKit Python layer has the same behavior: `Chem.MolFromSmiles('invalid')` returns `None` and prints a warning to stderr, not an exception.

**Why it happens:**
RDKit was designed for batch processing of large chemical databases where 100% parse success is not expected (real-world chemical datasets commonly have 0.1-2% invalid SMILES). The library prioritizes continuing over failing. Developers coming from other domains expect parsing functions to throw exceptions on bad input.

**How to avoid:**
- Always use `is_valid_smiles(smiles)` to pre-validate before calling `mol_from_smiles()`.
- In your ingestion pipeline, validate each SMILES in Python with `Chem.MolFromSmiles()` and check for `None` before inserting.
- Track rejected SMILES count and return it in the API response. A CSV upload that silently drops 5% of rows will confuse users.
- In your `SELECT ... INTO` for creating molecule tables, always include `WHERE m IS NOT NULL` (as shown in the official cartridge tutorial).
- Consider canonicalizing SMILES in Python before insertion: `Chem.MolToSmiles(Chem.MolFromSmiles(input_smiles))` — this normalizes input and catches invalids.

**Warning signs:**
- Row count in molecule table < row count in raw data table (without explanation)
- Users report "missing compounds" after upload
- PostgreSQL log files full of `WARNING: could not create molecule from SMILES` messages
- NULL values appearing in molecule columns

**Phase to address:**
Phase 2 (CSV Ingestion) — validation and error reporting must be built into the upload pipeline from day one.

---

### Pitfall 3: Wrong Fingerprint Type for Tanimoto Similarity Searches

**What goes wrong:**
Developers pick a fingerprint type without understanding the tradeoffs. The RDKit cartridge offers many options: `morganbv_fp` (ECFP-like), `featmorganbv_fp` (FCFP-like), `rdkit_fp` (Daylight-like), `torsionbv_fp`, `atompairbv_fp`, `maccs_fp`. Each produces fundamentally different similarity rankings for the same query molecule. Choosing the wrong one means your similarity search returns chemically irrelevant results — and this won't be caught by functional tests (the search "works," it just returns bad answers).

**Why it happens:**
Most tutorials use Morgan fingerprints (radius 2) by default, which is a reasonable general choice. But developers don't realize that:
- Morgan radius 2 (`morganbv_fp(m, 2)`) = ECFP4 equivalent. Radius 3 = ECFP6. These are different fingerprints.
- `rdkit_fp` (Daylight path-based) is better for certain scaffold-level comparisons.
- The default fingerprint bit size (2048 for Morgan in the cartridge) affects collision rates and thus similarity scores.
- Using count-based fingerprints (`morgan_fp`, type `sfp`) with Tanimoto doesn't work with GiST index acceleration — you need bit vector fingerprints (`morganbv_fp`, type `bfp`) for indexed Tanimoto searches.

**How to avoid:**
- Use `morganbv_fp(mol, 2)` (Morgan bit vector, radius 2) as the default. This is ECFP4-equivalent and the most widely used in pharma virtual screening. The official ChEMBL cartridge tutorial uses this.
- Always use `bfp` (bit vector) fingerprints for Tanimoto similarity, not `sfp` (sparse count vectors). The GiST index and `%` operator work on `bfp` type.
- Pre-compute fingerprints into a separate `fps` table (as shown in the cartridge docs) rather than computing them at query time. A query like `WHERE morganbv_fp(mol_from_smiles('query'))%mfp2` uses the pre-computed `mfp2` column.
- Document your fingerprint choice in the API docs. Researchers need to know what ECFP variant is being used.

**Warning signs:**
- Tanimoto scores seem "too high" or "too low" for known compound pairs
- Similarity search returns structurally unrelated compounds in top hits
- Queries are slow despite having a GiST index (may be using sfp instead of bfp)
- Changing fingerprint radius drastically changes result sets

**Phase to address:**
Phase 3 (Search Endpoints) — fingerprint selection is an early design decision that affects data storage. Changing fingerprint type later requires re-computing all fingerprints and rebuilding indexes.

---

### Pitfall 4: Missing GiST Index or Using B-tree Instead of GiST for Fingerprints

**What goes wrong:**
Tanimoto similarity searches do a full table scan instead of using an index. At 100K+ molecules, this means queries take 10-60 seconds instead of sub-second. The `%` (Tanimoto threshold) operator and `<%>` (Tanimoto KNN) operator ONLY use GiST indexes. A B-tree index on a fingerprint column is useless for similarity search.

**Why it happens:**
- Developers forget to create the GiST index: `CREATE INDEX fps_mfp2_idx ON fps USING gist(mfp2)`.
- They create a B-tree index out of habit: `CREATE INDEX ... ON fps(mfp2)` — which PostgreSQL accepts without complaint but never uses for similarity operators.
- The GiST index build is SLOW (can take 10+ minutes for 100K molecules) and requires significant `maintenance_work_mem`. If the index build fails silently (e.g., OOM in a Docker container with memory limits), queries fall back to sequential scan.

**How to avoid:**
- Always create GiST indexes explicitly: `CREATE INDEX fps_mfp2_idx ON fps USING gist(mfp2)`.
- Verify index usage with `EXPLAIN ANALYZE` on a similarity query before declaring search "working."
- In Docker, set `maintenance_work_mem` to at least 512MB for index builds on 100K+ molecule datasets. The official cartridge docs recommend `work_mem = 128MB` and `shared_buffers = 2048MB` for good performance.
- Build indexes AFTER bulk data load, not during. Set `synchronous_commit = off` and `full_page_writes = off` during loading (as recommended in the official cartridge docs), then re-enable after.

**Warning signs:**
- `EXPLAIN ANALYZE` shows "Seq Scan" instead of "Bitmap Index Scan" for similarity queries
- Similarity queries take >1 second on datasets under 1M molecules
- Index creation takes unusually long or fails
- Docker container OOM-killed during bulk ingestion + indexing

**Phase to address:**
Phase 2/3 (Ingestion + Search) — index creation strategy must be designed alongside the ingestion pipeline.

---

### Pitfall 5: SMILES Canonicalization and Equivalence Confusion

**What goes wrong:**
The same molecule can be represented by many different SMILES strings. `C(=O)O` and `OC=O` and `O=CO` all represent formic acid. If you store the user's raw SMILES and use string comparison for "exact match" search, you'll miss equivalent molecules. Worse, if your CSV has duplicate molecules with different SMILES representations, you'll store them as separate entries.

**Why it happens:**
Developers treat SMILES as plain strings. They implement "exact match" as `WHERE smiles = 'query'` instead of using the RDKit molecule equality operator `@=`. They don't realize that RDKit internally canonicalizes SMILES, so `mol_to_smiles(mol_from_smiles('C(=O)O'))` produces `O=CO` (canonical form).

**How to avoid:**
- Always convert to canonical SMILES on ingestion: store `mol_to_smiles(mol_from_smiles(input))` as your SMILES column.
- Use the `@=` operator for exact match searches, not string comparison. `@=` compares by molecular graph, not string.
- Deduplicate on canonical SMILES during CSV ingestion if duplicates are not desired.
- Decide and document whether stereochemistry is considered in exact matches. By default, `@=` considers stereochemistry. Different canonical SMILES are generated with and without `isomericSmiles=True`.

**Warning signs:**
- "Exact match" misses molecules that are chemically identical
- Duplicate molecules in database with different SMILES strings
- Users confused by "no results" when searching with non-canonical SMILES

**Phase to address:**
Phase 2 (CSV Ingestion) — canonicalization must happen at ingestion time.

---

### Pitfall 6: Ignoring Stereochemistry Defaults in Substructure Search

**What goes wrong:**
By default, the RDKit cartridge does NOT use stereochemistry in substructure matching (`rdkit.do_chiral_sss` defaults to `false`). This means a substructure query with a specific chirality center will match both R and S enantiomers. For pharmaceutical applications, this can return clinically different compounds as "matches."

Conversely, if you enable `do_chiral_sss`, a non-chiral query against a chiral molecule behaves differently than expected: a non-chiral query DOES match a chiral molecule, but a chiral query does NOT match a non-chiral molecule.

**Why it happens:**
The default is designed for broad substructure screening where stereochemistry filtering is a later step. Developers either don't realize it's off, or turn it on without understanding the asymmetric matching behavior.

**How to avoid:**
- Document the stereochemistry behavior in your API response or docs.
- Consider making stereochemistry-aware search an optional parameter (e.g., `?chiral=true`).
- Set `rdkit.do_chiral_sss` at the session level per-query if you need both behaviors, not globally in `postgresql.conf`.

**Warning signs:**
- Pharma users report substructure search returning wrong enantiomers
- Setting chiral SSS to true causes expected matches to disappear

**Phase to address:**
Phase 3 (Search Endpoints) — design the API parameter before implementing substructure search.

---

## Technical Debt Patterns

| Shortcut | Immediate Benefit | Long-term Cost | When Acceptable |
|----------|-------------------|----------------|-----------------|
| Computing fingerprints at query time instead of pre-computing | Simpler schema, no fps table | Every similarity query is 10-100x slower; no index acceleration | Never at 100K+ scale. Pre-compute always. |
| Storing raw SMILES without canonicalization | Faster ingestion, simpler code | Duplicate molecules, broken exact match, inconsistent data | Never. Canonicalize on ingest. |
| Single-table design (molecules + fingerprints + metadata in one table) | Fewer JOINs | Bloated rows slow down sequential scans; harder to rebuild fingerprints when changing type | Acceptable for <10K molecules, not at scale |
| Skipping `is_valid_smiles()` pre-validation | Faster ingestion loop | Silent data loss, NULLs in molecule column, corrupted search results | Never. Always validate. |
| Using default PostgreSQL memory settings in Docker | Works out of the box | OOM on index builds, slow queries, Docker container restarts | Never for production. Tune `shared_buffers`, `work_mem`, `maintenance_work_mem`. |

## Integration Gotchas

| Integration | Common Mistake | Correct Approach |
|-------------|----------------|------------------|
| RDKit Python (`rdkit` pip package) + RDKit Cartridge | Assuming `pip install rdkit` gives you the PostgreSQL cartridge | The pip package only provides Python bindings. The cartridge is a PostgreSQL extension that must be installed separately (via Docker image or source build with `-DRDK_BUILD_PGSQL=ON`). |
| Docker memory limits + GiST index builds | Setting a 512MB container memory limit | GiST index builds on fingerprint columns are memory-intensive. Allow at least 2GB for the PostgreSQL container during bulk operations. Set `maintenance_work_mem` to 512MB+. |
| psycopg2 + mol type | Expecting `psycopg2` to auto-serialize RDKit mol objects | Use `mol_send(m)` in SQL to get binary representation, then `Chem.Mol(row.tobytes())` in Python. Or just `SELECT mol_to_smiles(m)` and work with SMILES strings. |
| CSV upload with arbitrary encodings | Assuming CSV is UTF-8 | Chemical databases often come from legacy systems with Latin-1 or Windows-1252 encoding. Detect and convert encoding before parsing. SMILES themselves are ASCII, but metadata columns may not be. |
| `rdkit.tanimoto_threshold` session variable | Setting threshold globally in `postgresql.conf` | This is a session-level GUC. Set it per-query with `SET rdkit.tanimoto_threshold=X` before the similarity query. API endpoints with different threshold parameters need separate `SET` calls. This is NOT a function parameter — it's a PostgreSQL session variable. |

## Performance Traps

| Trap | Symptoms | Prevention | When It Breaks |
|------|----------|------------|----------------|
| No pre-computed fingerprint table | Similarity queries >5s | Create a separate `fps` table with pre-computed `morganbv_fp` columns and GiST indexes (follow the ChEMBL loading pattern in official docs) | >1K molecules |
| Default PostgreSQL `shared_buffers` (128KB) | Every query hits disk, even repeated ones | Set `shared_buffers = 25% of RAM`, minimum 512MB. Set `work_mem = 128MB` for complex queries. | >10K molecules |
| Full result set before pagination | API returns all 500 similarity matches, client shows 10 | Use `LIMIT` in SQL. The cartridge docs show that adding `LIMIT 100` to substructure queries drops time from 1922ms to 97ms on 1.7M compounds. | >100 results |
| Computing `mol_from_smiles()` on every query instead of caching the query molecule | Each similarity call re-parses the query SMILES | For the similarity function pattern, the query fingerprint `morganbv_fp(mol_from_smiles($1::cstring))` is computed once per SQL function call but be aware of query plan caching in prepared statements. | High query volume |
| Loading molecules and building indexes simultaneously | Container runs out of memory, index build takes 10x longer | Load raw data first, then create molecule table with `SELECT INTO`, then build GiST indexes. Official docs recommend `synchronous_commit = off` and `full_page_writes = off` during loading. | >50K molecules |
| Not using the `<%>` KNN operator for ordered results | `ORDER BY tanimoto_sml(...)` does a full sort instead of using index | Use `ORDER BY query_fp <%> column_fp` which leverages the GiST index for KNN ordering. This is the pattern shown in the official `get_mfp2_neighbors` function. | >10K molecules |

## Security Mistakes

| Mistake | Risk | Prevention |
|---------|------|------------|
| Accepting SMILES strings directly in SQL without parameterized queries | SQL injection via crafted SMILES strings. SMILES can contain characters like `'`, `\`, `(`, `)` that have SQL meaning. | Always use parameterized queries (`%s` with psycopg2, never f-strings or string concatenation). FastAPI + SQLAlchemy or psycopg2 parameterized queries handle this. |
| Exposing PostgreSQL port from Docker container | Direct database access bypassing API auth | Only expose PostgreSQL on Docker internal network. API container connects via Docker network, not published ports. |
| No rate limiting on similarity search | A single query with low Tanimoto threshold scans the entire fingerprint table. An attacker can DOS the database with expensive queries. | Rate limit API endpoints. Set a minimum Tanimoto threshold floor (e.g., 0.3) to prevent extremely broad searches. |
| API key in query parameters | Keys logged in web server access logs, browser history | Use `X-API-Key` header, not query parameter. |

## UX Pitfalls

| Pitfall | User Impact | Better Approach |
|---------|-------------|-----------------|
| Not returning rejected SMILES in upload response | Users don't know which compounds failed. They re-upload the entire file trying to fix it. | Return a structured response: `{accepted: 95000, rejected: 5000, errors: [{row: 42, smiles: "bad", reason: "kekulization failed"}]}` |
| Returning raw Tanimoto scores without context | Users don't know if 0.7 is "high" or "low" similarity | Include guidance: thresholds >0.85 typically indicate same scaffold, 0.5-0.7 indicates related compounds. Or return a ranked list with clear ordering. |
| Undocumented fingerprint/threshold defaults | Users get different results than they expect from other tools | Document in API: "Similarity search uses Morgan fingerprint radius 2 (ECFP4 equivalent). Default Tanimoto threshold: 0.5." |
| Slow feedback on large CSV uploads | User uploads 100K-row CSV, waits 5 minutes with no progress indication | Return HTTP 202 with a job ID for large uploads. Provide a status endpoint. Or use chunked processing with progress callbacks. |

## "Looks Done But Isn't" Checklist

- [ ] **CSV Ingestion:** Often missing encoding detection — verify CSV files with non-ASCII metadata characters parse correctly
- [ ] **Similarity Search:** Often missing threshold documentation — verify API docs state the fingerprint type, radius, and default threshold
- [ ] **Exact Match:** Often missing canonicalization — verify `@=` operator is used, not SMILES string comparison
- [ ] **Substructure Search:** Often missing stereochemistry documentation — verify API docs state whether chiral SSS is on/off and how to toggle it
- [ ] **GiST Index:** Often missing verification — run `EXPLAIN ANALYZE` on a similarity query and verify "Bitmap Index Scan" appears
- [ ] **Docker Setup:** Often missing health check — verify `CREATE EXTENSION rdkit` runs successfully in container startup
- [ ] **Error Handling:** Often missing molecule validation — verify `mol_from_smiles()` NULL results are caught and reported
- [ ] **PostgreSQL Tuning:** Often using defaults — verify `shared_buffers`, `work_mem`, and `maintenance_work_mem` are tuned for dataset size
- [ ] **Bulk Upload:** Often missing async handling — verify 100K-row uploads don't timeout the HTTP connection

## Recovery Strategies

| Pitfall | Recovery Cost | Recovery Steps |
|---------|---------------|----------------|
| Wrong fingerprint type chosen | MEDIUM | Recompute fingerprints: `DROP TABLE fps; SELECT molregno, morganbv_fp(m, 2) as mfp2 INTO fps FROM mols;` then rebuild GiST index. Data is preserved, only derived columns change. |
| No canonicalization on ingest | MEDIUM | Run `UPDATE mols SET canonical_smiles = mol_to_smiles(m)` to regenerate canonical SMILES from stored mol objects. Deduplicate afterward. |
| Missing GiST index | LOW | `CREATE INDEX CONCURRENTLY` can add the index without locking the table. Takes time but no data loss. |
| Silent SMILES rejection (NULLs in mol column) | HIGH | Must re-ingest the CSV with validation. Determine which rows were lost by comparing raw data to molecule table. Users may need to re-upload. |
| PostgreSQL version mismatch with cartridge | HIGH | Must rebuild Docker image with correct version pairing. Database files may be incompatible across PG major versions — may need `pg_dump` / `pg_restore`. |
| Default PostgreSQL memory settings | LOW | Update `postgresql.conf` or Docker environment variables. Restart container. No data loss. |

## Pitfall-to-Phase Mapping

| Pitfall | Prevention Phase | Verification |
|---------|------------------|--------------|
| RDKit/PG version mismatch in Docker | Phase 1 (Infrastructure) | `docker compose up` succeeds + `CREATE EXTENSION rdkit` + `SELECT rdkit_version()` returns expected version |
| Silent SMILES rejection | Phase 2 (CSV Ingestion) | Upload a CSV with known-bad SMILES, verify rejected count in response matches expected |
| Wrong fingerprint type | Phase 3 (Search) | Run known similarity queries against reference compounds with published Tanimoto scores, verify results match |
| Missing GiST index | Phase 2/3 (Ingestion + Search) | `EXPLAIN ANALYZE` on similarity query shows Bitmap Index Scan |
| SMILES canonicalization missing | Phase 2 (CSV Ingestion) | Insert two different SMILES for the same molecule, verify exact match finds both via `@=` |
| Stereochemistry defaults | Phase 3 (Search) | Document behavior in API docs. Test with chiral and achiral queries. |
| PostgreSQL memory settings | Phase 1 (Infrastructure) | Load 100K molecules and verify query performance <1s. No OOM during index build. |
| No async for bulk uploads | Phase 2 (CSV Ingestion) | Upload 100K-row CSV, verify HTTP response within 30s (either completed or 202 with job ID) |
| SQL injection via SMILES | Phase 3 (Search) | Send SMILES strings containing SQL metacharacters (`'`, `;`, `--`), verify no SQL errors |

## Sources

- RDKit PostgreSQL Cartridge Documentation (v2025.09.6): https://www.rdkit.org/docs/Cartridge.html — HIGH confidence (official docs, verified functions, operators, and configuration variables)
- RDKit Cartridge PostgreSQL README (GitHub master): https://github.com/rdkit/rdkit/blob/master/Code/PgSQL/rdkit/README.md — HIGH confidence (official installation procedures, known errors with `GLIBCXX` and `LD_LIBRARY_PATH`)
- RDKit Installation Guide (v2025.09.6): https://www.rdkit.org/docs/Install.html — HIGH confidence (official, covers conda/pip/source, cartridge installation)
- RDKit Getting Started in Python (v2025.09.6): https://www.rdkit.org/docs/GettingStartedInPython.html — HIGH confidence (official, SMILES parsing behavior, MolFromSmiles returning None)
- `informaticsmatters/rdkit-cartridge-debian` Docker Hub: https://hub.docker.com/r/informaticsmatters/rdkit-cartridge-debian — HIGH confidence (official pre-built images, latest tag Release_2024_09_3)

---
*Pitfalls research for: Cheminformatics SMILES Search API*
*Researched: 2026-03-12*
