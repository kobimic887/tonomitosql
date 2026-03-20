"""Search service for molecular queries using RDKit cartridge operators.

Uses raw SQL with parameterized queries for all RDKit operations:
- Exact match: @= operator (molecular graph equality)
- Similarity: Tanimoto (%) or Dice (#) with configurable fingerprint type
- Substructure: @> operator (substructure containment)

SMILES validation uses rdkit-pypi when available (x86_64), falls back to
PostgreSQL's RDKit cartridge (mol_from_smiles) on ARM.
All queries use parameterized %s placeholders — never string concatenation.
"""

import logging

from psycopg import sql

from app.chem import validate_query_smiles
from app.db.session import get_db
from app.models.schemas import (
    FingerprintType,
    MoleculeResult,
    SearchResponse,
    SimilarityMetric,
)

logger = logging.getLogger(__name__)

# Pagination defaults
DEFAULT_LIMIT = 100
MAX_LIMIT = 1000
MIN_TANIMOTO_THRESHOLD = 0.1  # Floor to prevent full table scans
MAX_TANIMOTO_THRESHOLD = 1.0
DEFAULT_TANIMOTO_THRESHOLD = 0.5

# Guard against runaway queries (broad substructure patterns like 'C' or '[#6]')
SEARCH_TIMEOUT = "30s"

# ── Fingerprint / Similarity mappings ──────────────────────────────────

# Map FingerprintType enum → (DB column name, SQL function to compute query FP)
FP_CONFIG: dict[FingerprintType, tuple[str, str]] = {
    FingerprintType.morgan:       ("mfp2",  "morganbv_fp(mol_from_smiles(%(smiles)s::cstring), 2)"),
    FingerprintType.maccs:        ("maccs", "maccs_fp(mol_from_smiles(%(smiles)s::cstring))"),
    FingerprintType.feat_morgan:  ("ffp2",  "featmorganbv_fp(mol_from_smiles(%(smiles)s::cstring), 2)"),
    FingerprintType.atom_pair:    ("apfp",  "atompairbv_fp(mol_from_smiles(%(smiles)s::cstring))"),
    FingerprintType.torsion:      ("ttfp",  "torsionbv_fp(mol_from_smiles(%(smiles)s::cstring))"),
    FingerprintType.rdkit:        ("rdfp",  "rdkit_fp(mol_from_smiles(%(smiles)s::cstring))"),
}

# Map SimilarityMetric enum → (sml function, filter operator, KNN operator, threshold variable)
SIM_CONFIG: dict[SimilarityMetric, tuple[str, str, str, str]] = {
    SimilarityMetric.tanimoto: ("tanimoto_sml", "%%",  "<%%>", "rdkit.tanimoto_threshold"),
    SimilarityMetric.dice:     ("dice_sml",     "#",   "<#>",  "rdkit.dice_threshold"),
}


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
    fingerprint_type: FingerprintType = FingerprintType.morgan,
    similarity_metric: SimilarityMetric = SimilarityMetric.tanimoto,
) -> SearchResponse:
    """Search by similarity using configurable fingerprint type and metric.

    Supports 6 fingerprint types and 2 similarity metrics, all using
    GiST-indexed bit vector fingerprints for sub-second queries.

    Args:
        smiles: Query SMILES string
        threshold: Similarity threshold (0.1-1.0, default 0.5)
        offset: Pagination offset
        limit: Number of results (max 1000)
        dataset_id: Optional dataset filter
        fingerprint_type: Which fingerprint to compare (default: morgan/ECFP4)
        similarity_metric: Which similarity function (default: tanimoto)

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

    # Look up FP and similarity config
    fp_column, fp_sql_func = FP_CONFIG[fingerprint_type]
    sml_func, filter_op, knn_op, threshold_var = SIM_CONFIG[similarity_metric]

    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                sql.SQL("SET statement_timeout = {}").format(
                    sql.Literal(SEARCH_TIMEOUT)
                )
            )
            # Set the per-session threshold variable for the GiST index filter.
            # Must be set every time because connections are pooled.
            cur.execute(
                sql.SQL("SET {} = {}").format(
                    sql.Identifier(*threshold_var.split(".")),
                    sql.Literal(threshold),
                )
            )

            dataset_filter = ""
            params: dict = {"smiles": canonical, "offset": offset, "limit": limit}

            if dataset_id is not None:
                dataset_filter = "AND m.dataset_id = %(dataset_id)s"
                params["dataset_id"] = dataset_id

            # CTE computes the query fingerprint once.
            # Dynamic column/function/operator selection based on FP type and metric.
            query = f"""
                WITH q AS (
                    SELECT {fp_sql_func} AS qfp
                )
                SELECT
                    m.id,
                    m.canonical_smiles,
                    m.metadata,
                    {sml_func}(q.qfp, f.{fp_column}) AS similarity
                FROM q, fingerprints f
                JOIN molecules m ON m.id = f.molecule_id
                WHERE q.qfp {filter_op} f.{fp_column}
                {dataset_filter}
                ORDER BY q.qfp {knn_op} f.{fp_column}
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
