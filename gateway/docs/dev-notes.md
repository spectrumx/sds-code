# Gateway Development Notes

+ [Gateway Development Notes](#gateway-development-notes)
    + [Production Backups](#production-backups)
        + [Backups Restoration](#backups-restoration)
    + [MinIO Configuration](#minio-configuration)
    + [OpenSearch Cluster Maintenance](#opensearch-cluster-maintenance)
        + [Cluster health](#cluster-health)
        + [Cluster stats](#cluster-stats)
        + [Disk allocation](#disk-allocation)
        + [Cluster settings](#cluster-settings)
    + [OpenSearch Snapshots](#opensearch-snapshots)
        + [Register the snapshots repository](#register-the-snapshots-repository)
        + [Verify the snapshot repository](#verify-the-snapshot-repository)
        + [Take a snapshot](#take-a-snapshot)
        + [Get a snapshot status](#get-a-snapshot-status)
    + [OpenSearch Indices and Documents](#opensearch-indices-and-documents)
        + [List OpenSearch indices](#list-opensearch-indices)
        + [List all documents of an index](#list-all-documents-of-an-index)
        + [Get a specific document by ID](#get-a-specific-document-by-id)
    + [Handling migration conflicts](#handling-migration-conflicts)
        + [Rebasing the migration](#rebasing-the-migration)
        + [Workflow](#workflow)
    + [Troubleshooting](#troubleshooting)
        + [Running Postgres commands](#running-postgres-commands)
        + [Postgres collation version mismatch](#postgres-collation-version-mismatch)
            + [Solution](#solution)

## Production Backups

This procedure might be useful for daily backups, before major database changes such
as migrations, or before upgrading Postgres versions.

1. `cp scripts/.env.sh.example scripts/.env.sh`.
2. `$EDITOR scripts/.env.sh` to set the variables in it.
3. Run `make snapshot` to create a daily backup snapshot of Postgres database.
    + See `scripts/create-snapshot.sh` for details of what is executed.
    + Database credentials are automatically loaded from the postgres container, so
        the user running the snapshot must have privileges to manage the database
        container, and the container must be running with those env variables set.
    + The Postgres snapshot is created with `pg_dumpall`. See the docs for details:
        [Postgres docs](https://postgresql.org/docs/current/app-pg-dumpall.html).
    + The snapshot creation is non-interactive, so it can be run from automated scripts; but interaction might be required for backup exfiltration.
4. Access the created files in `./data/backups/`.

### Backups Restoration

> [!WARNING]
> This is a destructive operation that will overwrite the existing database.
>
> Unless in exceptional data recovery circumstances, do not restore a backup to a live
> production environment. If doing that anyway, create a recent snapshot and export
> it to a different machine first. See [production backups](#production-backups) above.

See `scripts/restore-snapshot.sh` to restore the most recent snapshot.

This is an interactive script with some safeguards to prevent accidental overwriting of
data. Read the script before running it to make sure it does the expected, since this
is a destructive operation.

## MinIO Configuration

+ [MinIO reference document](https://github.com/minio/minio/blob/master/docs/config/README.md)

## OpenSearch Cluster Maintenance

### [Cluster health](https://docs.opensearch.org/docs/latest/api-reference/cluster-api/cluster-health/)

See [cluster API](https://docs.opensearch.org/docs/latest/api-reference/cluster-api/index/) for other methods.

```bash
docker exec -it sds-gateway-prod-opensearch bash -c "curl -k -u "'"'"\$OPENSEARCH_USER:\$OPENSEARCH_PASSWORD"'"'" https://localhost:9200/_cluster/health" | jq .
```

### Cluster stats

```bash
docker exec -it sds-gateway-prod-opensearch bash -c "curl -k -u "'"'"\$OPENSEARCH_USER:\$OPENSEARCH_PASSWORD"'"'" https://localhost:9200/_cluster/stats" | jq .
```

### [Disk allocation](https://docs.opensearch.org/docs/latest/api-reference/cat/cat-allocation/)

See [CAT API](https://docs.opensearch.org/docs/latest/api-reference/cat/index/) for other stats.

```bash
docker exec -it sds-gateway-prod-opensearch bash -c "curl -k -u "'"'"\$OPENSEARCH_USER:\$OPENSEARCH_PASSWORD"'"'" https://localhost:9200/_cat/allocation?v"
```

### Cluster settings

```bash
docker exec -it sds-gateway-prod-opensearch bash -c "curl -k -u "'"'"\$OPENSEARCH_USER:\$OPENSEARCH_PASSWORD"'"'" https://localhost:9200/_cluster/settings?include_defaults=false" | jq .
```

## OpenSearch Snapshots

### Register the snapshots repository

See [Snapshot APIs](https://docs.opensearch.org/latest/api-reference/snapshots/create-repository/#example-requests) for more details.

```bash
docker exec -it sds-gateway-prod-opensearch bash -c "curl -k -u "'"'"\$OPENSEARCH_ADMIN_USER:\$OPENSEARCH_INITIAL_ADMIN_PASSWORD"'"'" -X PUT https://localhost:9200/_snapshot/my-fs-repository -H 'Content-Type: application/json' -d '{\"type\": \"fs\",\"settings\": {\"location\": \"/mnt/snapshots\"}}'" | jq .
```

### Verify the snapshot repository

```bash
docker exec -it sds-gateway-prod-opensearch bash -c "curl -k -u "'"'"\$OPENSEARCH_ADMIN_USER:\$OPENSEARCH_INITIAL_ADMIN_PASSWORD"'"'" https://localhost:9200/_snapshot/my-fs-repository/" | jq .
```

### Take a snapshot

```bash
docker exec -it sds-gateway-prod-opensearch bash -c "curl -k -u "'"'"\$OPENSEARCH_ADMIN_USER:\$OPENSEARCH_INITIAL_ADMIN_PASSWORD"'"'" -X PUT https://localhost:9200/_snapshot/my-fs-repository/snapshot_1?wait_for_completion=true" | jq .
```

Output example

```json
{
  "snapshot": {
    "snapshot": "snapshot_1",
    "uuid": "FvqZA8zeRcCfvTUq7J32sA",
    "version_id": 136397827,
    "version": "2.18.0",
    "remote_store_index_shallow_copy": false,
    "indices": [
      ".opensearch-sap-log-types-config",
      ".opensearch-observability",
      "captures-rh",
      ".plugins-ml-config",
      ".opendistro_security",
      "captures-drf"
    ],
    "data_streams": [],
    "include_global_state": true,
    "state": "SUCCESS",
    "start_time": "2025-10-21T13:02:35.193Z",
    "start_time_in_millis": 1761051755193,
    "end_time": "2025-10-21T13:02:35.393Z",
    "end_time_in_millis": 1761051755393,
    "duration_in_millis": 200,
    "failures": [],
    "shards": {
      "total": 10,
      "failed": 0,
      "successful": 10
    }
  }
}
```

### Get a snapshot status

See [snapshot status](https://docs.opensearch.org/latest/api-reference/snapshots/get-snapshot-status/).

```bash
docker exec -it sds-gateway-prod-opensearch bash -c "curl -k -u "'"'"\$OPENSEARCH_ADMIN_USER:\$OPENSEARCH_INITIAL_ADMIN_PASSWORD"'"'" https://localhost:9200/_snapshot/my-fs-repository/snapshot_1/_status" | jq .
```

## OpenSearch Indices and Documents

### List OpenSearch indices

```bash
docker exec -it sds-gateway-prod-opensearch bash -c "curl -k -u "'"'"\$OPENSEARCH_USER:\$OPENSEARCH_PASSWORD"'"'" https://localhost:9200/_cat/indices?v" | jq .
```

### List all documents of an index

+ Replace `captures-drf` with the targeted index name.

```bash
docker exec -it sds-gateway-prod-opensearch bash -c "curl -k -u "'"'"\$OPENSEARCH_USER:\$OPENSEARCH_PASSWORD"'"'" -X GET 'https://localhost:9200/captures-drf/_search?size=10000&_source=false' -H 'Content-Type: application/json' -d '{\"query\": {\"match_all\": {}}, \"stored_fields\": []}'" | jq .
```

### Get a specific document by ID

+ Replace `captures-drf` with the targeted index name.
+ Replace `966...19a` with the targeted document ID.

```bash
docker exec -it sds-gateway-prod-opensearch bash -c "curl -k -u "'"'"\$OPENSEARCH_USER:\$OPENSEARCH_PASSWORD"'"'" https://localhost:9200/captures-drf/_doc/966074cf-644f-4598-8ea6-dae217ea719a" | jq .
```

## Handling migration conflicts

At times, you might need to merge two branches with conflicting changes to
`max_migrations.txt`. This file is created by
[`django-linear-migrations`](https://github.com/adamchainz/django-linear-migrations),
which we use to help manage and resolve migration conflicts.

This installed app will nudge you to rebase the migrations, linearizing them in the
process. This is done to prevent problems with running migrations in different order and
complicated rollbacks.

### Rebasing the migration

```bash
# docker exec -it sds-gateway-<local/prod>-app python manage.py rebase_migration <app_name>
docker exec -it sds-gateway-local-app python manage.py rebase_migration users
docker exec -it sds-gateway-local-app python manage.py rebase_migration api_methods
```

Then, manually check the altered files look right and continue the rebase.

The command uses the conflict information in the `max_migration.txt` file to determine
which migration to rebase. It automatically detects whether a Git merge or rebase
operation is in progress, assuming rebase if a Git repository cannot be found. The
command then:

1. Renames the migration
2. Edits it to depend on the new migration from your main branch
3. Updates `max_migration.txt`.

> [!NOTE]
> Rebasing the migration might not always be the correct thing to do. If the
> migrations in your default and feature branches have both affected the same models,
> rebasing the migration to the end may not make sense. However, such parallel changes
> would normally cause conflicts in your model files or other parts of the source code
> as well.

### Workflow

Below is a workflow example with `users` as the app with migration conflicts between
the default branch and the feature branch.

```bash
# bring the default branch up-to-date:
git switch master
git pull

# switch to the feature branch that has a new migration:
git switch feat-branch
docker exec -it sds-gateway-local-app python manage.py migrate users

# rebase branches and migrations
git rebase origin/master
# if no conflict, you're set; otherwise, you might see a conflict on max_migration.txt:
# CONFLICT (content): Merge conflict in users/migrations/max_migration.txt
# ...

# so on conflict, rebase the migrations too:
docker exec -it sds-gateway-local-app python manage.py rebase_migration users

# then CHECK THE FILES, making manual changes if needed
git diff users/migrations/

# if ok, add them, and continue the migration
git add users/migrations/
git rebase --continue

# finally, migrate your local env to continue development
docker exec -it sds-gateway-local-app python manage.py migrate users
```

## Troubleshooting

### Running Postgres commands

```bash
docker exec -it sds-gateway-local-postgres bash -c "psql -U \${POSTGRES_USER}"
```

### Postgres collation version mismatch

```txt
WARNING:  database "<DB_NAME>" has a collation version mismatch
DETAIL:  The database was created using collation version X, but the operating system provides version Y.
```

#### Solution

To refresh the collation version for all databases, you can iterate over them:

```bash
docker exec -it sds-gateway-local-postgres bash -c "
    for db in \$(psql -U \${POSTGRES_USER} -tAc 'SELECT datname FROM pg_database;'); do
        psql -U \${POSTGRES_USER} -c \"ALTER DATABASE \\\"\$db\\\" REFRESH COLLATION VERSION;\"
    done
"
```

Or one-by-one:

```bash
docker exec -it sds-gateway-local-postgres bash -c "psql -U \${POSTGRES_USER} -c \"ALTER DATABASE \"spectrumx\" REFRESH COLLATION VERSION;\""
```
