FROM python:3.12-slim

WORKDIR /app

# libxrender1, libxext6 needed by rdkit-pypi (available on x86_64 only)
RUN apt-get update && apt-get install -y --no-install-recommends \
    libxrender1 libxext6 && \
    rm -rf /var/lib/apt/lists/*

COPY requirements.txt .

# Install rdkit-pypi separately so ARM builds don't fail.
# On x86_64: installs normally, enables Python-side SMILES validation.
# On aarch64: pip install fails (no wheel), skipped gracefully.
# Core deps (FastAPI, psycopg, etc.) are always installed.
RUN pip install --no-cache-dir -r requirements.txt || \
    (echo "rdkit-pypi failed (likely ARM) — installing without it" && \
     grep -v rdkit-pypi requirements.txt | pip install --no-cache-dir -r /dev/stdin)

COPY app/ ./app/
COPY scripts/ ./scripts/

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
