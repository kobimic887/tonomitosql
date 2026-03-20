#!/bin/bash
# Migration: Add new fingerprint columns to existing fingerprints table.
# Run this inside the PostgreSQL container for existing databases.
#
# Usage:
#   docker compose exec db bash /path/to/migrate-add-fingerprints.sh
#
# For NEW deployments, init-db.sh already includes all columns.
# This script is only needed for databases created before multi-FP support.
set -e

psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" <<-EOSQL
    -- Step 1: Add new columns (nullable first for backfill)
    ALTER TABLE fingerprints ADD COLUMN IF NOT EXISTS maccs bfp;
    ALTER TABLE fingerprints ADD COLUMN IF NOT EXISTS ffp2 bfp;
    ALTER TABLE fingerprints ADD COLUMN IF NOT EXISTS apfp bfp;
    ALTER TABLE fingerprints ADD COLUMN IF NOT EXISTS ttfp bfp;
    ALTER TABLE fingerprints ADD COLUMN IF NOT EXISTS rdfp bfp;

    -- Step 2: Backfill from molecules.mol
    UPDATE fingerprints f
    SET
        maccs = maccs_fp(m.mol),
        ffp2  = featmorganbv_fp(m.mol, 2),
        apfp  = atompairbv_fp(m.mol),
        ttfp  = torsionbv_fp(m.mol),
        rdfp  = rdkit_fp(m.mol)
    FROM molecules m
    WHERE f.molecule_id = m.id
      AND f.maccs IS NULL;

    -- Step 3: Set NOT NULL constraints
    ALTER TABLE fingerprints ALTER COLUMN maccs SET NOT NULL;
    ALTER TABLE fingerprints ALTER COLUMN ffp2 SET NOT NULL;
    ALTER TABLE fingerprints ALTER COLUMN apfp SET NOT NULL;
    ALTER TABLE fingerprints ALTER COLUMN ttfp SET NOT NULL;
    ALTER TABLE fingerprints ALTER COLUMN rdfp SET NOT NULL;

    -- Step 4: Create GiST indexes
    CREATE INDEX IF NOT EXISTS idx_fps_maccs ON fingerprints USING gist(maccs);
    CREATE INDEX IF NOT EXISTS idx_fps_ffp2 ON fingerprints USING gist(ffp2);
    CREATE INDEX IF NOT EXISTS idx_fps_apfp ON fingerprints USING gist(apfp);
    CREATE INDEX IF NOT EXISTS idx_fps_ttfp ON fingerprints USING gist(ttfp);
    CREATE INDEX IF NOT EXISTS idx_fps_rdfp ON fingerprints USING gist(rdfp);

    -- Verify
    DO \$\$
    DECLARE
        col_count INTEGER;
    BEGIN
        SELECT count(*) INTO col_count
        FROM information_schema.columns
        WHERE table_name = 'fingerprints'
          AND column_name IN ('mfp2', 'maccs', 'ffp2', 'apfp', 'ttfp', 'rdfp');
        IF col_count != 6 THEN
            RAISE EXCEPTION 'Expected 6 fingerprint columns, found %', col_count;
        END IF;
        RAISE NOTICE 'Migration complete: 6 fingerprint columns verified';
    END
    \$\$;
EOSQL
