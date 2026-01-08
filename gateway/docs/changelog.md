# SpectrumX Gateway Changelog

## 2026-01-08

+ Fixes:
    + [**Added M2M relationships for assets to datasets**](https://github.com/spectrumx/sds-code/pull/226): Currently the foreign key (FK) relationships only allow assets to be connected to a single dataset. This PR expands the schema (with future contraction planned) to correct the schema issues.
        + Requires a data migration for existing datasets (and captures) from the FK field to M2M field. Run management command `migrate_fk_to_m2m` to transfer foreign key model relationship to many-to-many field (only adds, does NOT nullify FK).
        + This is meant to be run on systems with data under the current schema that require migrations to new schema.
