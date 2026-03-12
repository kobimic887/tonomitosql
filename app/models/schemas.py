from pydantic import BaseModel


class HealthResponse(BaseModel):
    status: str
    api_version: str
    database: str
    rdkit_version: str | None = None
    molecule_count: int
