"""CSV ingestion service for molecular data.

Pipeline: CSV file → streaming parse → SMILES validation → batch COPY to staging
→ SQL mol_from_smiles conversion → fingerprint computation → cleanup staging.

When rdkit-pypi is available (x86_64), SMILES are validated and canonicalized
Python-side before reaching the database. On ARM where rdkit-pypi is unavailable,
validation is deferred to PostgreSQL's RDKit cartridge (mol_from_smiles).
"""
import csv
import io
import json
import logging
from typing import BinaryIO

from app.chem import validate_smiles, HAS_RDKIT
from app.db.session import get_db
from app.models.schemas import RowError, UploadResponse

logger = logging.getLogger(__name__)

# Batch size for COPY protocol — 5000 rows balances memory vs round-trip overhead.
# At ~3M rows, this means ~600 COPY operations.
BATCH_SIZE = 5000

# Cap error list to prevent OOM on CSVs with millions of invalid rows.
# The total count is always returned; only the detail list is capped.
MAX_ERRORS = 1000

# Columns that map to dedicated molecule table columns (not metadata)
SMILES_COLUMN = "smiles"
CANONICAL_SMILES_COLUMN = "canonical_smiles"
# All other CSV columns go into metadata JSONB


def _detect_smiles_column(headers: list[str]) -> int:
    """Find the SMILES column index. Raises ValueError if not found."""
    lower_headers = [h.strip().lower() for h in headers]
    if SMILES_COLUMN in lower_headers:
        return lower_headers.index(SMILES_COLUMN)
    # Fallback: look for common SMILES column names
    for name in ["smiles", "smi", "smiles_string", "molecule"]:
        if name in lower_headers:
            return lower_headers.index(name)
    raise ValueError(
        f"No SMILES column found in CSV headers: {headers}. "
        f"Expected a column named 'smiles', 'smi', or 'molecule'."
    )


def _build_metadata(headers: list[str], row: list[str], smiles_idx: int) -> dict:
    """Build metadata dict from all CSV columns except the SMILES column.

    The CSV 'id' column goes into metadata (not molecules.id which is SERIAL).
    The CSV 'canonical_smiles' column also goes into metadata (we compute our own).
    """
    metadata = {}
    for i, header in enumerate(headers):
        if i == smiles_idx:
            continue  # Skip the SMILES column — stored in dedicated column
        key = header.strip()
        if key:
            metadata[key] = row[i].strip() if i < len(row) else ""
    return metadata


def _validate_smiles(smiles_str: str) -> tuple[str | None, str | None]:
    """Validate a SMILES string using rdkit-pypi if available, else basic check.

    When rdkit-pypi is available: validates and canonicalizes Python-side.
    When unavailable (ARM): only checks for empty strings; chemical
    validation happens SQL-side via mol_from_smiles().

    Returns (smiles_or_canonical, None) on success or (None, error_reason) on failure.
    """
    return validate_smiles(smiles_str)


def _create_staging_table(conn) -> None:
    """Create a temporary staging table for COPY bulk loading."""
    with conn.cursor() as cur:
        cur.execute("""
            CREATE TEMP TABLE IF NOT EXISTS staging_molecules (
                original_smiles TEXT NOT NULL,
                canonical_smiles TEXT NOT NULL,
                metadata JSONB DEFAULT '{}'::jsonb
            ) ON COMMIT DROP
        """)


def _copy_batch_to_staging(conn, batch: list[tuple[str, str, str]]) -> None:
    """COPY a batch of validated rows into the staging table.

    Each tuple is (original_smiles, canonical_smiles, metadata_json).
    Uses psycopg's COPY protocol for maximum throughput.
    """
    with conn.cursor() as cur:
        with cur.copy(
            "COPY staging_molecules (original_smiles, canonical_smiles, metadata) FROM STDIN"
        ) as copy:
            for original_smiles, canonical_smiles, metadata_json in batch:
                copy.write_row((original_smiles, canonical_smiles, metadata_json))


def _transfer_staging_to_molecules(conn, dataset_id: int) -> int:
    """Move validated molecules from staging into the molecules table.

    Uses mol_from_smiles in SQL to create mol objects and mol_to_smiles
    to compute the canonical SMILES. Rows where mol_from_smiles returns
    NULL are skipped (invalid SMILES rejected by RDKit cartridge).

    When rdkit-pypi validated Python-side, this is a safety net (very few
    rejections expected). When running without rdkit-pypi, this is the
    primary validation step.

    Returns the number of rows inserted.
    """
    with conn.cursor() as cur:
        cur.execute("""
            INSERT INTO molecules (dataset_id, smiles, mol, canonical_smiles, metadata)
            SELECT
                %(dataset_id)s,
                original_smiles,
                mol_from_smiles(canonical_smiles::cstring),
                mol_to_smiles(mol_from_smiles(canonical_smiles::cstring))::text,
                metadata
            FROM staging_molecules
            WHERE mol_from_smiles(canonical_smiles::cstring) IS NOT NULL
        """, {"dataset_id": dataset_id})
        return cur.rowcount


def _compute_fingerprints(conn, dataset_id: int) -> int:
    """Compute Morgan fingerprints (radius 2) for all molecules in the dataset.

    Uses morganbv_fp(mol, 2) which produces ECFP4-equivalent bit vector
    fingerprints stored in the bfp column type with GiST index support.

    Returns the number of fingerprints computed.
    """
    with conn.cursor() as cur:
        cur.execute("""
            INSERT INTO fingerprints (molecule_id, mfp2)
            SELECT m.id, morganbv_fp(m.mol, 2)
            FROM molecules m
            WHERE m.dataset_id = %(dataset_id)s
              AND NOT EXISTS (
                  SELECT 1 FROM fingerprints f WHERE f.molecule_id = m.id
              )
        """, {"dataset_id": dataset_id})
        return cur.rowcount


def _update_dataset_row_count(conn, dataset_id: int, row_count: int) -> None:
    """Update the dataset record with the final molecule count."""
    with conn.cursor() as cur:
        cur.execute(
            "UPDATE datasets SET row_count = %(count)s WHERE id = %(id)s",
            {"count": row_count, "id": dataset_id},
        )


def ingest_csv(
    file: BinaryIO,
    filename: str,
    dataset_name: str | None = None,
) -> UploadResponse:
    """Ingest a CSV file containing SMILES and metadata into the database.

    Pipeline:
    1. Stream-parse CSV to identify SMILES column and metadata columns
    2. Validate each SMILES with RDKit Python if available (row-level error collection)
    3. Batch COPY valid rows into a temporary staging table (5000 rows per batch)
    4. Transfer from staging to molecules table with mol_from_smiles in SQL
       (primary validation on ARM, safety net on x86)
    5. Compute Morgan fingerprints (radius 2) for all new molecules
    6. Update dataset record with final counts

    Args:
        file: Binary file-like object of the CSV
        filename: Original filename for the dataset record
        dataset_name: Optional human-readable name (defaults to filename)

    Returns:
        UploadResponse with counts and row-level errors
    """
    if dataset_name is None:
        dataset_name = filename

    errors: list[RowError] = []
    total_rows = 0
    valid_count = 0
    error_count = 0

    # Wrap binary file in text reader for csv module
    text_stream = io.TextIOWrapper(file, encoding="utf-8", errors="replace")
    reader = csv.reader(text_stream)

    # Read and validate headers
    try:
        headers = next(reader)
    except StopIteration:
        raise ValueError("CSV file is empty — no header row found")

    smiles_idx = _detect_smiles_column(headers)
    logger.info(
        "CSV headers: %s, SMILES column: %s (index %d)",
        headers, headers[smiles_idx], smiles_idx,
    )

    with get_db() as conn:
        # Use a single transaction for the entire ingestion
        with conn.transaction():
            # 1. Create dataset record
            with conn.cursor() as cur:
                cur.execute(
                    """INSERT INTO datasets (name, filename)
                       VALUES (%(name)s, %(filename)s) RETURNING id""",
                    {"name": dataset_name, "filename": filename},
                )
                dataset_id = cur.fetchone()[0]

            # 2. Create staging table (temp, dropped on commit)
            _create_staging_table(conn)

            # 3. Stream CSV, validate SMILES, batch COPY to staging
            batch: list[tuple[str, str, str]] = []

            for row_num, row in enumerate(reader, start=2):  # start=2 because row 1 is header
                total_rows += 1

                # Skip empty rows
                if not row or all(cell.strip() == "" for cell in row):
                    continue

                # Extract SMILES
                if smiles_idx >= len(row):
                    error_count += 1
                    if len(errors) < MAX_ERRORS:
                        errors.append(RowError(
                            row=row_num,
                            smiles="",
                            reason=f"Row has {len(row)} columns, SMILES column is at index {smiles_idx}",
                        ))
                    continue

                raw_smiles = row[smiles_idx].strip()

                # Validate SMILES (rdkit-pypi if available, else basic check)
                canonical, error_reason = _validate_smiles(raw_smiles)
                if error_reason:
                    error_count += 1
                    if len(errors) < MAX_ERRORS:
                        errors.append(RowError(
                            row=row_num,
                            smiles=raw_smiles,
                            reason=error_reason,
                        ))
                    continue

                # Build metadata from all other columns
                metadata = _build_metadata(headers, row, smiles_idx)
                metadata_json = json.dumps(metadata)

                batch.append((raw_smiles, canonical, metadata_json))
                valid_count += 1

                # Flush batch when full
                if len(batch) >= BATCH_SIZE:
                    _copy_batch_to_staging(conn, batch)
                    batch.clear()

            # Flush remaining batch
            if batch:
                _copy_batch_to_staging(conn, batch)
                batch.clear()

            logger.info(
                "CSV parsed: %d total rows, %d valid, %d invalid",
                total_rows, valid_count, error_count,
            )

            # 4. Transfer staging → molecules table (mol_from_smiles in SQL)
            inserted = _transfer_staging_to_molecules(conn, dataset_id)
            logger.info("Inserted %d molecules from staging", inserted)

            # If SQL-side validation rejected additional rows, adjust count
            if inserted < valid_count:
                logger.warning(
                    "SQL-side mol_from_smiles rejected %d additional rows",
                    valid_count - inserted,
                )
                valid_count = inserted

            # 5. Compute Morgan fingerprints (radius 2)
            fp_count = _compute_fingerprints(conn, dataset_id)
            logger.info("Computed %d Morgan fingerprints", fp_count)

            # 6. Update dataset row count
            _update_dataset_row_count(conn, dataset_id, valid_count)

    return UploadResponse(
        dataset_id=dataset_id,
        filename=filename,
        total_rows=total_rows,
        valid_count=valid_count,
        invalid_count=error_count,
        errors=errors,
    )
