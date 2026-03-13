"""Dataset management endpoints.

Provides CRUD operations for uploaded datasets:
- GET /datasets — List all datasets
- GET /datasets/{dataset_id} — Get a single dataset
- DELETE /datasets/{dataset_id} — Delete a dataset and all its molecules
"""

import logging

from fastapi import APIRouter, HTTPException

from app.db.session import get_db
from app.models.schemas import DatasetResponse, DatasetListResponse

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/datasets", tags=["Datasets"])


@router.get(
    "",
    response_model=DatasetListResponse,
    summary="List all datasets",
    description="Returns all datasets with their names, filenames, row counts, and creation timestamps.",
)
def list_datasets():
    """List all uploaded datasets."""
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT id, name, filename, row_count, created_at::text
                FROM datasets
                ORDER BY created_at DESC
            """)
            rows = cur.fetchall()

    datasets = [
        DatasetResponse(
            id=row[0],
            name=row[1],
            filename=row[2],
            row_count=row[3],
            created_at=row[4],
        )
        for row in rows
    ]

    return DatasetListResponse(datasets=datasets, count=len(datasets))


@router.get(
    "/{dataset_id}",
    response_model=DatasetResponse,
    summary="Get dataset details",
    description="Returns details for a single dataset by ID.",
)
def get_dataset(dataset_id: int):
    """Get a single dataset by ID."""
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT id, name, filename, row_count, created_at::text
                FROM datasets
                WHERE id = %s
                """,
                (dataset_id,),
            )
            row = cur.fetchone()

    if row is None:
        raise HTTPException(status_code=404, detail=f"Dataset {dataset_id} not found")

    return DatasetResponse(
        id=row[0],
        name=row[1],
        filename=row[2],
        row_count=row[3],
        created_at=row[4],
    )


@router.delete(
    "/{dataset_id}",
    summary="Delete a dataset",
    description=(
        "Deletes a dataset and all associated molecules and fingerprints. "
        "This is irreversible. Uses ON DELETE CASCADE from the schema."
    ),
)
def delete_dataset(dataset_id: int):
    """Delete a dataset and all its molecules (CASCADE)."""
    logger.info("Deleting dataset %d", dataset_id)

    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "DELETE FROM datasets WHERE id = %s RETURNING id",
                (dataset_id,),
            )
            row = cur.fetchone()
        conn.commit()

    if row is None:
        raise HTTPException(status_code=404, detail=f"Dataset {dataset_id} not found")

    return {"deleted": True, "dataset_id": dataset_id}
