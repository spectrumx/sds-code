# Gateway Development Notes

+ [Gateway Development Notes](#gateway-development-notes)
    + [Production Backups](#production-backups)
        + [What is backed up](#what-is-backed-up)
        + [What is NOT backed up](#what-is-not-backed-up)
        + [Creating Backups](#creating-backups)
        + [Backups Restoration](#backups-restoration)
    + [MinIO Configuration](#minio-configuration)
    + [OpenSearch Cluster Maintenance](#opensearch-cluster-maintenance)
        + [Cluster health](#cluster-health)
        + [Cluster stats](#cluster-stats)
        + [Disk allocation](#disk-allocation)
        + [Cluster settings](#cluster-settings)
        + [Change disk watermark levels](#change-disk-watermark-levels)
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
        + [Basic PostgreSQL Commands](#basic-postgresql-commands)
            + [List Databases](#list-databases)
            + [List Tables in Current Database](#list-tables-in-current-database)
            + [List Schemas in Current Database](#list-schemas-in-current-database)
            + [List Users](#list-users)
        + [Postgres collation version mismatch](#postgres-collation-version-mismatch)
            + [Solution](#solution)

## Production Backups

This procedure might be useful for daily backups, before major database changes such as
migrations, or before upgrading Postgres versions.

### What is backed up

Up to one snapshot per day of:

+ [x] **PostgreSQL database** - Complete database dump via `pg_dumpall` (all schemas,
    tables, and data)
+ [x] **OpenSearch indices** - Snapshots of all indices and their data
+ [x] **Gateway secrets** - Environment files (`.envs/`, `.env.sh`, etc.) and
    configuration files
+ [x] **Git repository state** - Branch info, commit SHA, uncommitted changes, staged
    changes, and commit archive.

### What is NOT backed up

+ ❌ **MinIO objects** - S3-compatible storage data is not included in snapshots (see
    warning below). When configuring MinIO, you can configure erasure coding for data
    redundancy across multiple drives or nodes. Consider using MinIO's own backup and
    replication features for protecting this data instead of this snapshot procedure.
+ ❌ **Docker volumes** - Any data stored in Docker volumes outside of the database
    container is not included, such as temporary zip files, `uv` cache, virtual
    environments, generated static files.

### Creating Backups

1. `cp scripts/.env.sh.example scripts/.env.sh`.
2. `$EDITOR scripts/.env.sh` to set the variables in it.
3. Run `just snapshot` to create a _daily_ backup snapshot of Postgres database.
    + See `scripts/create-snapshot.sh` for details of what is executed.
    + Database credentials are automatically loaded from the postgres container, so the
        user running the snapshot must have privileges to manage the database container,
        and the container must be running with those env variables set.
    + The Postgres snapshot is created with `pg_dumpall`. See the docs for details:
        [Postgres docs](https://postgresql.org/docs/current/app-pg-dumpall.html).
    + The snapshot creation is non-interactive, so it can be run from automated scripts;
      but interaction might be required for backup exfiltration.
    + **Note:** MinIO objects are not included in this snapshot. See [What is NOT backed
      up](#what-is-not-backed-up) above.
4. Access the created files in `./data/backups/`.
    + Note you can set up a remote server in `.env.sh` to automatically copy the backups
    there after creation using `rsync` over `ssh`.

### Backups Restoration

READ THIS ENTIRE SECTION BEFORE RESTORING A BACKUP.

> [!WARNING]
> This is a destructive operation that will overwrite the existing database.
>
> Unless in exceptional data recovery circumstances, do not restore a backup to a live
> production environment. If doing that anyway, create a recent snapshot and export
> it to a different machine first. See [creating backups](#creating-backups) above.

What can be automatically restored:

+ [x] **PostgreSQL database** - Full restoration of the database from the latest
    snapshot. See [Backups Restoration](#backups-restoration) below.

Everything else (OpenSearch indices, secrets, git state) can be manually restored from
the snapshot files, but there is no automated restoration procedure for them yet.

Note that, while the database can be restored, it will contain references to other data
sources that might exist or not. Most notably:

+ OpenSearch indices - The restored database might contain references to documents in
    OpenSearch that do not exist if those indices were not manually restored.
+ MinIO objects - The restored database might contain references to objects in MinIO
    that do not exist if those objects were not manually restored. This is the main
    challenge when restoring a production backup to a staging/QA machine, as most
    objects will not exist there due to the commonly large size of object data.

Run `scripts/restore-snapshot.sh` when you are ready to restore the most recent snapshot.

> [!IMPORTANT]
> This is an interactive script. Read the instructions carefully before interacting with
> it, as this is a destructive operation.

The script has some safeguards to prevent accidental overwriting of data. Read the
script before running it to make sure it does what you expect before running it in a
production environment.

## MinIO Configuration

+ MinIO config for SDS: [see the production deploy
    instructions](./detailed-deploy.md#production-deploy).
+ [MinIO reference
    document](https://github.com/minio/minio/blob/master/docs/config/README.md).

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

### Change disk watermark levels

```bash
docker exec -it sds-gateway-prod-opensearch bash -c "curl -k -u "'"'"\$OPENSEARCH_ADMIN_USER:\$OPENSEARCH_INITIAL_ADMIN_PASSWORD"'"'" -X PUT https://localhost:9200/_cluster/settings -H 'Content-Type: application/json' -d '{\"transient\": {\"cluster.routing.allocation.disk.watermark.low\": \"85%\", \"cluster.routing.allocation.disk.watermark.high\": \"90%\", \"cluster.routing.allocation.disk.watermark.flood_stage\": \"95%\", \"cluster.info.update.interval\": \"1m\"}}'" | jq .
```

```json
{
    "acknowledged": true,
    "persistent": {},
    "transient": {
        "cluster": {
            "routing": {
                "allocation": {
                    "disk": {
                        "watermark": {
                            "low": "85%",
                            "flood_stage": "95%",
                            "high": "90%"
                        }
                    }
                }
            },
            "info": {
                "update": {
                    "interval": "1m"
                }
            }
        }
    }
}
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

### Basic PostgreSQL Commands

Here are some basic commands for interacting with PostgreSQL:

#### List Databases

```sql
\l
```

#### List Tables in Current Database

```sql
\dt
```

#### List Schemas in Current Database

```sql
\dn
```

#### List Users

```sql
\du
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
