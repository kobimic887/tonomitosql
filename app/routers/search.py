"""Search endpoints for molecular queries.

Provides three search types:
- GET /search/exact — Find exact molecular match
- GET /search/similarity — Find similar molecules by Tanimoto coefficient
- GET /search/substructure — Find molecules containing a substructure pattern

All endpoints accept an optional dataset_id filter to scope searches.
"""

import logging

from fastapi import APIRouter, HTTPException, Query

from app.models.schemas import (
    BatchSearchRequest,
    BatchSearchResponse,
    BatchSearchResultItem,
    SearchResponse,
    SearchType,
)
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
    dataset_id: int | None = Query(
        None, description="Optional dataset ID to scope search"
    ),
):
    """Search for an exact SMILES match."""
    logger.info("Search exact: %s", smiles)
    try:
        result = search_service.exact_match(smiles, dataset_id=dataset_id)
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
    dataset_id: int | None = Query(
        None, description="Optional dataset ID to scope search"
    ),
):
    """Search by Tanimoto similarity with configurable threshold."""
    logger.info("Search similarity: %s (threshold=%s)", smiles, threshold)
    try:
        result = search_service.similarity_search(
            smiles=smiles,
            threshold=threshold,
            offset=offset,
            limit=limit,
            dataset_id=dataset_id,
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
    dataset_id: int | None = Query(
        None, description="Optional dataset ID to scope search"
    ),
):
    """Search for molecules containing a substructure pattern."""
    logger.info("Search substructure: %s", smiles)
    try:
        result = search_service.substructure_search(
            smiles=smiles,
            offset=offset,
            limit=limit,
            dataset_id=dataset_id,
        )
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post(
    "/batch",
    response_model=BatchSearchResponse,
    summary="Batch search",
    description=(
        "Search for multiple SMILES in a single request. Accepts up to 100 SMILES "
        "and runs the specified search type (exact, similarity, or substructure) "
        "for each. Results are returned per-query. Invalid SMILES are reported "
        "with an error field rather than failing the entire batch."
    ),
)
def search_batch(
    body: BatchSearchRequest,
):
    """Batch search for multiple SMILES queries."""
    logger.info(
        "Batch search: %d queries, type=%s",
        len(body.smiles_list), body.search_type,
    )

    results: list[BatchSearchResultItem] = []

    for smiles in body.smiles_list:
        try:
            if body.search_type == SearchType.exact:
                resp = search_service.exact_match(
                    smiles, dataset_id=body.dataset_id,
                )
            elif body.search_type == SearchType.similarity:
                resp = search_service.similarity_search(
                    smiles,
                    threshold=body.threshold,
                    limit=body.limit,
                    dataset_id=body.dataset_id,
                )
            else:  # substructure
                resp = search_service.substructure_search(
                    smiles,
                    limit=body.limit,
                    dataset_id=body.dataset_id,
                )

            results.append(BatchSearchResultItem(
                query_smiles=resp.query_smiles,
                found=resp.found,
                count=resp.count,
                results=resp.results,
            ))
        except ValueError as e:
            results.append(BatchSearchResultItem(
                query_smiles=smiles,
                found=False,
                count=0,
                results=[],
                error=str(e),
            ))
        except Exception as e:
            logger.exception("Batch search error for SMILES: %s", smiles)
            results.append(BatchSearchResultItem(
                query_smiles=smiles,
                found=False,
                count=0,
                results=[],
                error="Internal search error",
            ))

    return BatchSearchResponse(
        search_type=body.search_type.value,
        total_queries=len(body.smiles_list),
        results=results,
    )
