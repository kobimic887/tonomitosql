"""Search endpoints for molecular queries.

Provides three search types:
- GET /search/exact — Find exact molecular match
- GET /search/similarity — Find similar molecules by Tanimoto coefficient
- GET /search/substructure — Find molecules containing a substructure pattern

Auth protection is added in Plan 03-03.
"""

import logging

from fastapi import APIRouter, HTTPException, Query

from app.models.schemas import SearchResponse
from app.services import search as search_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/search", tags=["Search"])


@router.get(
    "/exact",
    response_model=SearchResponse,
    summary="Exact molecule match",
    description=(
        "Search for an exact molecular match using the RDKit @= operator. "
        "The query SMILES is canonicalized before comparison. Returns found=true "
        "if the molecule exists in the database, with the matched molecule's "
        "canonical SMILES."
    ),
)
def search_exact(
    smiles: str = Query(
        ...,
        description="SMILES string to search for",
        examples=["c1ccccc1", "CCO", "CC(=O)Oc1ccccc1C(=O)O"],
    ),
):
    """Search for an exact SMILES match."""
    try:
        result = search_service.exact_match(smiles)
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get(
    "/similarity",
    response_model=SearchResponse,
    summary="Tanimoto similarity search",
    description=(
        "Search for molecules similar to the query using Tanimoto coefficient "
        "on Morgan fingerprints (radius 2, ECFP4 equivalent). Results are ranked "
        "by similarity score descending. Uses GiST-indexed fingerprints for "
        "sub-second queries on 100K+ molecules. The threshold controls the "
        "minimum similarity — lower thresholds return more (less similar) results."
    ),
)
def search_similarity(
    smiles: str = Query(
        ...,
        description="Query SMILES string",
        examples=["c1ccccc1", "c1ccc(O)cc1"],
    ),
    threshold: float = Query(
        0.5,
        ge=0.1,
        le=1.0,
        description="Minimum Tanimoto similarity threshold (0.1-1.0, default 0.5)",
    ),
    offset: int = Query(0, ge=0, description="Pagination offset"),
    limit: int = Query(
        100, ge=1, le=1000, description="Maximum results to return (max 1000)"
    ),
):
    """Search by Tanimoto similarity with configurable threshold."""
    try:
        result = search_service.similarity_search(
            smiles=smiles,
            threshold=threshold,
            offset=offset,
            limit=limit,
        )
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get(
    "/substructure",
    response_model=SearchResponse,
    summary="Substructure search",
    description=(
        "Search for molecules containing the query SMILES as a substructure "
        "using the RDKit @> operator with GiST index. For example, searching "
        "for 'c1ccccc1' (benzene) returns all molecules containing a benzene ring. "
        "Note: stereochemistry-aware matching is disabled by default (rdkit.do_chiral_sss=false)."
    ),
)
def search_substructure(
    smiles: str = Query(
        ...,
        description="SMILES substructure pattern to search for",
        examples=["c1ccccc1", "C(=O)O", "c1ccc(N)cc1"],
    ),
    offset: int = Query(0, ge=0, description="Pagination offset"),
    limit: int = Query(
        100, ge=1, le=1000, description="Maximum results to return (max 1000)"
    ),
):
    """Search for molecules containing a substructure pattern."""
    try:
        result = search_service.substructure_search(
            smiles=smiles,
            offset=offset,
            limit=limit,
        )
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
