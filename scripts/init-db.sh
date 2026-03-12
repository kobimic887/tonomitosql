#!/bin/bash
set -e

psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" <<-EOSQL
    -- Enable RDKit cartridge
    CREATE EXTENSION IF NOT EXISTS rdkit;

    -- Verify RDKit is working
    DO \$\$
    BEGIN
        PERFORM rdkit_version();
        RAISE NOTICE 'RDKit cartridge version: %', rdkit_version();
    END
    \$\$;

    -- Dataset tracking (one per CSV upload)
    CREATE TABLE IF NOT EXISTS datasets (
        id SERIAL PRIMARY KEY,
        name TEXT NOT NULL,
        filename TEXT NOT NULL,
        row_count INTEGER DEFAULT 0,
        created_at TIMESTAMPTZ DEFAULT NOW()
    );

    -- Raw molecule storage with RDKit mol type
    CREATE TABLE IF NOT EXISTS molecules (
        id SERIAL PRIMARY KEY,
        dataset_id INTEGER REFERENCES datasets(id) ON DELETE CASCADE,
        smiles TEXT NOT NULL,
        mol mol NOT NULL,
        canonical_smiles TEXT NOT NULL,
        metadata JSONB DEFAULT '{}'::jsonb,
        created_at TIMESTAMPTZ DEFAULT NOW()
    );

    -- GiST index on mol column for substructure search
    CREATE INDEX IF NOT EXISTS idx_molecules_mol ON molecules USING gist(mol);

    -- B-tree index on canonical SMILES for exact match
    CREATE INDEX IF NOT EXISTS idx_molecules_canonical ON molecules(canonical_smiles);

    -- Index on dataset_id for filtering by dataset
    CREATE INDEX IF NOT EXISTS idx_molecules_dataset ON molecules(dataset_id);

    -- Precomputed fingerprints for similarity search
    CREATE TABLE IF NOT EXISTS fingerprints (
        molecule_id INTEGER PRIMARY KEY REFERENCES molecules(id) ON DELETE CASCADE,
        mfp2 bfp NOT NULL
    );

    -- GiST index on Morgan fingerprint for Tanimoto similarity
    CREATE INDEX IF NOT EXISTS idx_fps_mfp2 ON fingerprints USING gist(mfp2);

    -- Verify schema by testing mol_from_smiles with a known molecule
    DO \$\$
    DECLARE
        test_mol mol;
    BEGIN
        test_mol := mol_from_smiles('c1ccccc1'::cstring);
        IF test_mol IS NULL THEN
            RAISE EXCEPTION 'RDKit mol_from_smiles failed — cartridge not working correctly';
        END IF;
        RAISE NOTICE 'Schema created and RDKit cartridge verified successfully';
    END
    \$\$;
EOSQL
