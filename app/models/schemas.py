from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class HealthResponse(BaseModel):
    status: str
    api_version: str
    database: str
    rdkit_version: str | None = None
    molecule_count: int


class RowError(BaseModel):
    row: int
    smiles: str
    reason: str


class UploadResponse(BaseModel):
    dataset_id: int
    filename: str
    total_rows: int
    valid_count: int
    invalid_count: int
    errors: list[RowError]


class MoleculeResult(BaseModel):
    """A single molecule in search results."""

    molecule_id: int
    canonical_smiles: str
    similarity: float | None = None  # Only populated for similarity search
    metadata: dict[str, Any] | None = None


class SearchResponse(BaseModel):
    """Response for all search endpoints."""

    found: bool
    count: int
    results: list[MoleculeResult]
    query_smiles: str


class DatasetResponse(BaseModel):
    """A single dataset record."""

    id: int
    name: str
    filename: str
    row_count: int
    created_at: str


class DatasetListResponse(BaseModel):
    """Response for listing datasets."""

    datasets: list[DatasetResponse]
    count: int


class SearchType(str, Enum):
    """Search type for batch operations."""

    exact = "exact"
    similarity = "similarity"
    substructure = "substructure"


class BatchSearchRequest(BaseModel):
    """Request body for batch search."""

    smiles_list: list[str] = Field(
        ..., min_length=1, max_length=100,
        description="List of SMILES strings to search (max 100)",
    )
    search_type: SearchType = Field(
        SearchType.similarity,
        description="Type of search to perform",
    )
    threshold: float = Field(
        0.5, ge=0.1, le=1.0,
        description="Tanimoto threshold (similarity search only)",
    )
    limit: int = Field(
        10, ge=1, le=100,
        description="Max results per SMILES query (max 100)",
    )
    dataset_id: int | None = Field(
        None, description="Optional dataset ID to scope search",
    )


class BatchSearchResultItem(BaseModel):
    """Result for a single SMILES in a batch search."""

    query_smiles: str
    found: bool
    count: int
    results: list[MoleculeResult]
    error: str | None = None


class BatchSearchResponse(BaseModel):
    """Response for batch search endpoint."""

    search_type: str
    total_queries: int
    results: list[BatchSearchResultItem]
