#!/usr/bin/env python3
"""Regression: >1000 equal-score hits must page deterministically past offset 1000.

Creates a disposable dataset of identical structures (similarity 1.0 for all),
pages across the 1000 boundary, asserts global id order, then deletes the
dataset. Requires DATABASE_URL (e.g. docker compose exec api …).

Exits 0 on pass, 1 on fail. Also asserts the search.py contract: global
ORDER BY similarity DESC, id ASC (no KNN LIMIT candidate cap).
"""

from __future__ import annotations

import inspect
import os
import sys
import time

DATASET_NAME = "__tie_pagination_regression__"
N_HITS = 1105
QUERY = "CCO"  # ethanol — every inserted row shares this structure


def _assert_query_contract() -> None:
    # Import after path setup when run from container /app
    from app.services import search as search_mod

    src = inspect.getsource(search_mod.similarity_search)
    if "candidates AS" in src and "LIMIT %(cap)s" in src:
        raise AssertionError(
            "similarity_search must not KNN-LIMIT candidates before the id "
            "tie-breaker (silent cap / non-global ties)"
        )
    if "max_parallel_workers_per_gather = 0" not in src:
        raise AssertionError(
            "similarity_search must disable parallel gather (Docker shm DiskFull)"
        )
    if "m.id ASC" not in src:
        raise AssertionError("similarity_search must ORDER BY …, m.id ASC")
    print("contract: OK (global ORDER BY + noparallel, no KNN cap)")


def _cleanup(cur, dataset_id: int | None) -> None:
    if dataset_id is not None:
        cur.execute("DELETE FROM datasets WHERE id = %s", (dataset_id,))
    cur.execute("DELETE FROM datasets WHERE name = %s", (DATASET_NAME,))


def _run_db_regression() -> None:
    from psycopg import connect

    from app.models.schemas import FingerprintType, SimilarityMetric
    from app.services.search import similarity_search

    url = os.environ.get("DATABASE_URL")
    if not url:
        raise SystemExit("DATABASE_URL is required for the DB portion of this test")

    dataset_id: int | None = None
    with connect(url) as conn:
        conn.autocommit = False
        with conn.cursor() as cur:
            _cleanup(cur, None)
            cur.execute(
                """
                INSERT INTO datasets (name, filename, row_count)
                VALUES (%s, %s, %s) RETURNING id
                """,
                (DATASET_NAME, "tie-pagination-regression.csv", N_HITS),
            )
            dataset_id = cur.fetchone()[0]

            # Same structure → identical fingerprints → similarity 1.0 to QUERY.
            # Distinct metadata only so rows are distinguishable.
            cur.execute(
                """
                WITH params AS (
                    SELECT %(smiles)s::text AS smiles,
                           %(dataset_id)s::int AS dataset_id,
                           %(n)s::int AS n
                ),
                ins AS (
                    INSERT INTO molecules (dataset_id, smiles, mol, canonical_smiles, metadata)
                    SELECT
                        p.dataset_id,
                        p.smiles,
                        mol_from_smiles(p.smiles::cstring),
                        mol_to_smiles(mol_from_smiles(p.smiles::cstring)),
                        jsonb_build_object('tie_i', g)
                    FROM params p, generate_series(0, (SELECT n FROM params) - 1) AS g
                    RETURNING id
                )
                INSERT INTO fingerprints (molecule_id, mfp2, maccs, ffp2, apfp, ttfp, rdfp)
                SELECT
                    ins.id,
                    morganbv_fp(mol_from_smiles(p.smiles::cstring), 2),
                    maccs_fp(mol_from_smiles(p.smiles::cstring)),
                    featmorganbv_fp(mol_from_smiles(p.smiles::cstring), 2),
                    atompairbv_fp(mol_from_smiles(p.smiles::cstring)),
                    torsionbv_fp(mol_from_smiles(p.smiles::cstring)),
                    rdkit_fp(mol_from_smiles(p.smiles::cstring))
                FROM ins, params p
                """,
                {"dataset_id": dataset_id, "smiles": QUERY, "n": N_HITS},
            )

            cur.execute(
                "SELECT id FROM molecules WHERE dataset_id = %s ORDER BY id ASC",
                (dataset_id,),
            )
            all_ids = [r[0] for r in cur.fetchall()]
            assert len(all_ids) == N_HITS
            conn.commit()

    # Page across the 1000 cutoff using the real search service.
    t0 = time.perf_counter()
    page_near = similarity_search(
        QUERY,
        threshold=0.99,
        offset=995,
        limit=10,
        dataset_id=dataset_id,
        fingerprint_type=FingerprintType.morgan,
        similarity_metric=SimilarityMetric.tanimoto,
    )
    page_past = similarity_search(
        QUERY,
        threshold=0.99,
        offset=1000,
        limit=10,
        dataset_id=dataset_id,
        fingerprint_type=FingerprintType.morgan,
        similarity_metric=SimilarityMetric.tanimoto,
    )
    ms = (time.perf_counter() - t0) * 1000

    near_ids = [r.molecule_id for r in page_near.results]
    past_ids = [r.molecule_id for r in page_past.results]
    expected_near = all_ids[995:1005]
    expected_past = all_ids[1000:1010]

    if near_ids != expected_near:
        raise AssertionError(
            f"offset=995 page mismatch:\n  got {near_ids}\n  want {expected_near}"
        )
    if past_ids != expected_past:
        raise AssertionError(
            f"offset=1000 page mismatch (KNN cap would drop these):\n"
            f"  got {past_ids}\n  want {expected_past}"
        )
    if not all(r.similarity == 1.0 for r in page_near.results + page_past.results):
        raise AssertionError("expected all equal-score hits at similarity 1.0")
    if near_ids[-5:] != past_ids[:5]:
        raise AssertionError("overlapping pages must share the five tied boundary ids")

    print(
        f"db: OK pages across 1000 ({N_HITS} ties) in {ms:.0f}ms "
        f"near={near_ids[:2]}… past={past_ids[:2]}…"
    )

    with connect(url) as conn:
        with conn.cursor() as cur:
            _cleanup(cur, dataset_id)
            conn.commit()
    print("cleanup: OK")


def main() -> int:
    # Allow `python scripts/…` from repo root or `/app` in the API image.
    repo = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    if repo not in sys.path:
        sys.path.insert(0, repo)

    try:
        _assert_query_contract()
        _run_db_regression()
    except Exception as exc:
        print(f"FAIL: {exc}", file=sys.stderr)
        return 1
    print("PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
