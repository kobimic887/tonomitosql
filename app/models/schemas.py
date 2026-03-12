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
