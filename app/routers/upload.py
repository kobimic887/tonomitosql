"""CSV upload endpoint for molecular data ingestion."""
import logging

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from fastapi.responses import JSONResponse

from app.config import settings
from app.dependencies import require_api_key
from app.models.schemas import UploadResponse
from app.services.ingestion import ingest_csv

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Upload"])


@router.post(
    "/upload",
    response_model=UploadResponse,
    summary="Upload a CSV file containing SMILES and metadata",
    description=(
        "Accepts a CSV file via multipart form upload. The CSV must have a column "
        "named 'smiles' containing SMILES strings. All other columns are stored as "
        "JSONB metadata. Each SMILES is validated and canonicalized using RDKit. "
        "Invalid SMILES are rejected with row-level error details. Valid molecules "
        "get Morgan fingerprints (radius 2) computed for similarity search."
    ),
)
async def upload_csv(
    file: UploadFile = File(..., description="CSV file with SMILES column"),
    dataset_name: str | None = None,
    api_key_name: str = Depends(require_api_key),
):
    """Upload a CSV file for molecular ingestion.

    The file is spooled to a temp file on disk (FastAPI default for files >1MB),
    then streamed to the ingestion service. This handles large files (~3M rows)
    without loading the entire file into memory.
    """
    # Validate file type
    if file.filename and not file.filename.lower().endswith(".csv"):
        raise HTTPException(
            status_code=400,
            detail="File must be a CSV file (*.csv)",
        )

    # Validate file size if content_length is available
    if file.size and file.size > settings.max_upload_size:
        raise HTTPException(
            status_code=413,
            detail=f"File too large. Maximum size: {settings.max_upload_size // (1024*1024)}MB",
        )

    try:
        logger.info("Starting CSV upload: %s", file.filename)

        # FastAPI's UploadFile spools large files to disk automatically.
        # We use file.file which is the underlying SpooledTemporaryFile.
        # The ingestion service expects a BinaryIO, which SpooledTemporaryFile satisfies.
        #
        # Important: SpooledTemporaryFile starts in memory (default 1MB threshold)
        # and rolls to disk for larger files. For a ~500MB CSV, it's on disk.
        # We need to ensure the file position is at the start.
        await file.seek(0)

        result = ingest_csv(
            file=file.file,
            filename=file.filename or "unknown.csv",
            dataset_name=dataset_name,
        )

        logger.info(
            "Upload complete (key=%s): dataset_id=%d, valid=%d, invalid=%d",
            api_key_name, result.dataset_id, result.valid_count, result.invalid_count,
        )

        # Return 201 Created for successful ingestion
        return JSONResponse(
            status_code=201,
            content=result.model_dump(),
        )

    except ValueError as e:
        # Raised by ingestion service for CSV parsing errors
        # (empty file, no SMILES column, etc.)
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.exception("Upload failed: %s", str(e))
        raise HTTPException(
            status_code=500,
            detail=f"Ingestion failed: {str(e)}",
        )
    finally:
        await file.close()
