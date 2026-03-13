"""Search service for molecular queries using RDKit cartridge operators.

Uses raw SQL with parameterized queries for all RDKit operations:
- Exact match: @= operator (molecular graph equality)
- Tanimoto similarity: % operator + tanimoto_sml() with SET rdkit.tanimoto_threshold
- Substructure: @> operator (substructure containment)

SMILES validation uses rdkit-pypi when available (x86_64), falls back to
PostgreSQL's RDKit cartridge (mol_from_smiles) on ARM.
All queries use parameterized %s placeholders — never string concatenation.
"""

import logging

from psycopg import sql

from app.chem import validate_query_smiles
from app.db.session import get_db
from app.models.schemas import MoleculeResult, SearchResponse

logger = logging.getLogger(__name__)

# Pagination defaults
DEFAULT_LIMIT = 100
MAX_LIMIT = 1000
MIN_TANIMOTO_THRESHOLD = 0.1  # Floor to prevent full table scans
MAX_TANIMOTO_THRESHOLD = 1.0
DEFAULT_TANIMOTO_THRESHOLD = 0.5

# Guard against runaway queries (broad substructure patterns like 'C' or '[#6]')
SEARCH_TIMEOUT = "30s"


def _clamp_pagination(offset: int, limit: int) -> tuple[int, int]:
    """Clamp pagination parameters to valid ranges."""
    offset = max(0, offset)
    limit = max(1, min(limit, MAX_LIMIT))
    return offset, limit


def exact_match(smiles: str, dataset_id: int | None = None) -> SearchResponse:
    """Search for an exact molecular match using the @= operator.

    Uses canonical SMILES B-tree index for fast lookup, then verifies
    with @= operator for molecular graph equality (handles stereochemistry).

    Args:
        smiles: SMILES string to search for
        dataset_id: Optional dataset filter

    Returns:
        SearchResponse with found=True/False and matching molecule(s)

    Raises:
        ValueError: If SMILES is invalid
    """
    canonical = validate_query_smiles(smiles)

    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                sql.SQL("SET statement_timeout = {}").format(
                    sql.Literal(SEARCH_TIMEOUT)
                )
            )
            # Use canonical_smiles B-tree index for fast lookup
            # Then verify with @= for molecular graph equality
            query = """
                SELECT m.id, m.canonical_smiles, m.metadata
                FROM molecules m
                WHERE m.canonical_smiles = %(smiles)s
                  AND m.mol @= mol_from_smiles(%(smiles)s::cstring)
            """
            params: dict = {"smiles": canonical}

            if dataset_id is not None:
                query += "  AND m.dataset_id = %(dataset_id)s"
                params["dataset_id"] = dataset_id

            cur.execute(query, params)
            rows = cur.fetchall()

    results = [
        MoleculeResult(
            molecule_id=row[0],
            canonical_smiles=row[1],
            metadata=row[2],
        )
        for row in rows
    ]

    return SearchResponse(
        found=len(results) > 0,
        count=len(results),
        results=results,
        query_smiles=canonical,
    )


def similarity_search(
    smiles: str,
    threshold: float = DEFAULT_TANIMOTO_THRESHOLD,
    offset: int = 0,
    limit: int = DEFAULT_LIMIT,
    dataset_id: int | None = None,
) -> SearchResponse:
    """Search by Tanimoto similarity using Morgan fingerprints (ECFP4).

    Uses the % operator with GiST index on mfp2 column. The
    rdkit.tanimoto_threshold session variable MUST be set before the query
    to ensure the GiST index filters correctly.

    Uses <%> KNN operator for ORDER BY to leverage GiST index ordering
    instead of a full sort.

    The query fingerprint is computed once in a CTE to avoid redundant
    mol_from_smiles + morganbv_fp calls (previously computed 3x per row).

    Args:
        smiles: Query SMILES string
        threshold: Tanimoto similarity threshold (0.1-1.0, default 0.5)
        offset: Pagination offset
        limit: Number of results (max 1000)
        dataset_id: Optional dataset filter

    Returns:
        SearchResponse with results ranked by similarity score descending

    Raises:
        ValueError: If SMILES is invalid or threshold out of range
    """
    canonical = validate_query_smiles(smiles)

    # Clamp threshold to valid range
    if threshold < MIN_TANIMOTO_THRESHOLD or threshold > MAX_TANIMOTO_THRESHOLD:
        raise ValueError(
            f"Threshold must be between {MIN_TANIMOTO_THRESHOLD} and {MAX_TANIMOTO_THRESHOLD}, "
            f"got {threshold}"
        )

    offset, limit = _clamp_pagination(offset, limit)

    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                sql.SQL("SET statement_timeout = {}").format(
                    sql.Literal(SEARCH_TIMEOUT)
                )
            )
            # CRITICAL: Set tanimoto_threshold per-query for correct GiST index usage.
            # This is a session-level variable. The connection pool returns connections
            # to the pool after use, so we must set it every time.
            # NOTE: SET does not support parameterized $1 placeholders, so we use
            # sql.Literal for safe value interpolation.
            cur.execute(
                sql.SQL("SET rdkit.tanimoto_threshold = {}").format(
                    sql.Literal(threshold)
                )
            )

            # CTE computes the query fingerprint once, avoiding 3x redundant
            # mol_from_smiles + morganbv_fp calls in SELECT/WHERE/ORDER BY.
            dataset_filter = ""
            params: dict = {"smiles": canonical, "offset": offset, "limit": limit}

            if dataset_id is not None:
                dataset_filter = "AND m.dataset_id = %(dataset_id)s"
                params["dataset_id"] = dataset_id

            cur.execute(
                f"""
                WITH q AS (
                    SELECT morganbv_fp(mol_from_smiles(%(smiles)s::cstring), 2) AS qfp
                )
                SELECT
                    m.id,
                    m.canonical_smiles,
                    m.metadata,
                    tanimoto_sml(q.qfp, f.mfp2) AS similarity
                FROM q, fingerprints f
                JOIN molecules m ON m.id = f.molecule_id
                WHERE q.qfp %% f.mfp2
                {dataset_filter}
                ORDER BY q.qfp <%%> f.mfp2
                OFFSET %(offset)s
                LIMIT %(limit)s
                """,
                params,
            )
            rows = cur.fetchall()

    results = [
        MoleculeResult(
            molecule_id=row[0],
            canonical_smiles=row[1],
            metadata=row[2],
            similarity=round(float(row[3]), 4),
        )
        for row in rows
    ]

    return SearchResponse(
        found=len(results) > 0,
        count=len(results),
        results=results,
        query_smiles=canonical,
    )


def substructure_search(
    smiles: str,
    offset: int = 0,
    limit: int = DEFAULT_LIMIT,
    dataset_id: int | None = None,
) -> SearchResponse:
    """Search for molecules containing the query as a substructure.

    Uses the @> operator with GiST index on mol column.
    Note: rdkit.do_chiral_sss defaults to false (v1 behavior — matches
    both enantiomers).

    Args:
        smiles: SMILES pattern to search for
        offset: Pagination offset
        limit: Number of results (max 1000)
        dataset_id: Optional dataset filter

    Returns:
        SearchResponse with all molecules containing the substructure

    Raises:
        ValueError: If SMILES pattern is invalid
    """
    canonical = validate_query_smiles(smiles)
    offset, limit = _clamp_pagination(offset, limit)

    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                sql.SQL("SET statement_timeout = {}").format(
                    sql.Literal(SEARCH_TIMEOUT)
                )
            )

            query = """
                SELECT m.id, m.canonical_smiles, m.metadata
                FROM molecules m
                WHERE m.mol @> mol_from_smiles(%(smiles)s::cstring)
            """
            params: dict = {"smiles": canonical, "offset": offset, "limit": limit}

            if dataset_id is not None:
                query += "  AND m.dataset_id = %(dataset_id)s"
                params["dataset_id"] = dataset_id

            query += """
                OFFSET %(offset)s
                LIMIT %(limit)s
            """

            cur.execute(query, params)
            rows = cur.fetchall()

    results = [
        MoleculeResult(
            molecule_id=row[0],
            canonical_smiles=row[1],
            metadata=row[2],
        )
        for row in rows
    ]

    return SearchResponse(
        found=len(results) > 0,
        count=len(results),
        results=results,
        query_smiles=canonical,
    )
