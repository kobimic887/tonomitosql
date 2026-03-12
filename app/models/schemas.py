from pydantic import BaseModel


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


class SearchResponse(BaseModel):
    """Response for all search endpoints."""

    found: bool
    count: int
    results: list[MoleculeResult]
    query_smiles: str
