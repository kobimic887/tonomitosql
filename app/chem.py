"""RDKit chemistry utilities with graceful fallback.

Tries to import rdkit-pypi (available on x86_64). If unavailable (ARM/aarch64),
falls back to PostgreSQL RDKit cartridge via SQL for SMILES validation and
canonicalization.

On x86: Python-side validation is faster (no DB round-trip) and catches
invalid SMILES before they reach the database.

On ARM: SQL-side validation via mol_from_smiles() provides identical results,
just with a DB round-trip per call.
"""

import logging

logger = logging.getLogger(__name__)

try:
    from rdkit import Chem

    HAS_RDKIT = True
    logger.info("rdkit-pypi available — using Python-side SMILES validation")
except ImportError:
    HAS_RDKIT = False
    logger.info("rdkit-pypi not available — falling back to SQL-side SMILES validation")


def validate_smiles(smiles: str) -> tuple[str | None, str | None]:
    """Validate and canonicalize a SMILES string.

    Uses rdkit-pypi if available, otherwise returns the raw SMILES
    and defers validation to PostgreSQL's mol_from_smiles().

    Returns:
        (canonical_smiles, None) on success
        (None, error_reason) on failure
    """
    smiles = smiles.strip()
    if not smiles:
        return None, "Empty SMILES string"

    if HAS_RDKIT:
        try:
            mol = Chem.MolFromSmiles(smiles)
            if mol is None:
                return None, "RDKit could not parse SMILES"
            canonical = Chem.MolToSmiles(mol)
            return canonical, None
        except Exception as e:
            return None, f"SMILES validation error: {str(e)}"
    else:
        # No Python RDKit — defer to SQL-side validation
        return smiles, None


def validate_query_smiles(smiles: str) -> str:
    """Validate and canonicalize a query SMILES string.

    Used by search endpoints. Uses rdkit-pypi if available,
    otherwise delegates to PostgreSQL's RDKit cartridge.

    Returns the canonical SMILES on success.
    Raises ValueError with descriptive message on failure.
    """
    smiles = smiles.strip()
    if not smiles:
        raise ValueError("Empty SMILES string")

    if HAS_RDKIT:
        mol = Chem.MolFromSmiles(smiles)
        if mol is None:
            raise ValueError(
                f"Invalid SMILES: '{smiles}' could not be parsed by RDKit"
            )
        return Chem.MolToSmiles(mol)
    else:
        # Fall back to SQL-side validation
        from app.db.session import get_db

        with get_db() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT mol_to_smiles(mol_from_smiles(%s::cstring))::text",
                    (smiles,),
                )
                row = cur.fetchone()

        if row is None or row[0] is None:
            raise ValueError(
                f"Invalid SMILES: '{smiles}' could not be parsed by RDKit"
            )
        result = row[0]
        # mol_to_smiles() can return bytes/memoryview even with ::text cast
        if isinstance(result, (bytes, memoryview)):
            return bytes(result).decode("utf-8")
        return str(result)
