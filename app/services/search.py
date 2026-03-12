"""Search service for molecular queries using RDKit cartridge operators.

Uses raw SQL with parameterized queries for all RDKit operations:
- Exact match: @= operator (molecular graph equality)
- Tanimoto similarity: % operator + tanimoto_sml() with SET rdkit.tanimoto_threshold
- Substructure: @> operator (substructure containment)

All SMILES inputs are validated with RDKit Python before querying.
All queries use parameterized %s placeholders — never string concatenation.
"""

import logging

from rdkit import Chem

from app.db.session import get_db
from app.models.schemas import MoleculeResult, SearchResponse

logger = logging.getLogger(__name__)

# Pagination defaults
DEFAULT_LIMIT = 100
MAX_LIMIT = 1000
MIN_TANIMOTO_THRESHOLD = 0.1  # Floor to prevent full table scans
MAX_TANIMOTO_THRESHOLD = 1.0
DEFAULT_TANIMOTO_THRESHOLD = 0.5


def _validate_query_smiles(smiles: str) -> str:
    """Validate and canonicalize a query SMILES string.

    Returns the canonical SMILES on success.
    Raises ValueError with descriptive message on failure.
    """
    smiles = smiles.strip()
    if not smiles:
        raise ValueError("Empty SMILES string")

    mol = Chem.MolFromSmiles(smiles)
    if mol is None:
        raise ValueError(f"Invalid SMILES: '{smiles}' could not be parsed by RDKit")

    return Chem.MolToSmiles(mol)


def _clamp_pagination(offset: int, limit: int) -> tuple[int, int]:
    """Clamp pagination parameters to valid ranges."""
    offset = max(0, offset)
    limit = max(1, min(limit, MAX_LIMIT))
    return offset, limit


def exact_match(smiles: str) -> SearchResponse:
    """Search for an exact molecular match using the @= operator.

    Uses canonical SMILES B-tree index for fast lookup, then verifies
    with @= operator for molecular graph equality (handles stereochemistry).

    Args:
        smiles: SMILES string to search for

    Returns:
        SearchResponse with found=True/False and matching molecule(s)

    Raises:
        ValueError: If SMILES is invalid
    """
    canonical = _validate_query_smiles(smiles)

    with get_db() as conn:
        with conn.cursor() as cur:
            # Use canonical_smiles B-tree index for fast lookup
            # Then verify with @= for molecular graph equality
            cur.execute(
                """
                SELECT m.id, m.canonical_smiles
                FROM molecules m
                WHERE m.canonical_smiles = %s
                  AND m.mol @= mol_from_smiles(%s::cstring)
                """,
                (canonical, canonical),
            )
            rows = cur.fetchall()

    results = [
        MoleculeResult(molecule_id=row[0], canonical_smiles=row[1])
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
) -> SearchResponse:
    """Search by Tanimoto similarity using Morgan fingerprints (ECFP4).

    Uses the % operator with GiST index on mfp2 column. The
    rdkit.tanimoto_threshold session variable MUST be set before the query
    to ensure the GiST index filters correctly.

    Uses <%> KNN operator for ORDER BY to leverage GiST index ordering
    instead of a full sort.

    Args:
        smiles: Query SMILES string
        threshold: Tanimoto similarity threshold (0.1-1.0, default 0.5)
        offset: Pagination offset
        limit: Number of results (max 1000)

    Returns:
        SearchResponse with results ranked by similarity score descending

    Raises:
        ValueError: If SMILES is invalid or threshold out of range
    """
    canonical = _validate_query_smiles(smiles)

    # Clamp threshold to valid range
    if threshold < MIN_TANIMOTO_THRESHOLD or threshold > MAX_TANIMOTO_THRESHOLD:
        raise ValueError(
            f"Threshold must be between {MIN_TANIMOTO_THRESHOLD} and {MAX_TANIMOTO_THRESHOLD}, "
            f"got {threshold}"
        )

    offset, limit = _clamp_pagination(offset, limit)

    with get_db() as conn:
        with conn.cursor() as cur:
            # CRITICAL: Set tanimoto_threshold per-query for correct GiST index usage.
            # This is a session-level variable. The connection pool returns connections
            # to the pool after use, so we must set it every time.
            cur.execute("SET rdkit.tanimoto_threshold = %s", (threshold,))

            cur.execute(
                """
                SELECT
                    m.id,
                    m.canonical_smiles,
                    tanimoto_sml(morganbv_fp(mol_from_smiles(%(smiles)s::cstring), 2), f.mfp2) AS similarity
                FROM fingerprints f
                JOIN molecules m ON m.id = f.molecule_id
                WHERE morganbv_fp(mol_from_smiles(%(smiles)s::cstring), 2) %% f.mfp2
                ORDER BY morganbv_fp(mol_from_smiles(%(smiles)s::cstring), 2) <%%> f.mfp2
                OFFSET %(offset)s
                LIMIT %(limit)s
                """,
                {"smiles": canonical, "offset": offset, "limit": limit},
            )
            rows = cur.fetchall()

    results = [
        MoleculeResult(
            molecule_id=row[0],
            canonical_smiles=row[1],
            similarity=round(float(row[2]), 4),
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
) -> SearchResponse:
    """Search for molecules containing the query as a substructure.

    Uses the @> operator with GiST index on mol column.
    Note: rdkit.do_chiral_sss defaults to false (v1 behavior — matches
    both enantiomers).

    Args:
        smiles: SMILES pattern to search for
        offset: Pagination offset
        limit: Number of results (max 1000)

    Returns:
        SearchResponse with all molecules containing the substructure

    Raises:
        ValueError: If SMILES pattern is invalid
    """
    canonical = _validate_query_smiles(smiles)
    offset, limit = _clamp_pagination(offset, limit)

    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT m.id, m.canonical_smiles
                FROM molecules m
                WHERE m.mol @> mol_from_smiles(%(smiles)s::cstring)
                OFFSET %(offset)s
                LIMIT %(limit)s
                """,
                {"smiles": canonical, "offset": offset, "limit": limit},
            )
            rows = cur.fetchall()

    results = [
        MoleculeResult(molecule_id=row[0], canonical_smiles=row[1])
        for row in rows
    ]

    return SearchResponse(
        found=len(results) > 0,
        count=len(results),
        results=results,
        query_smiles=canonical,
    )
