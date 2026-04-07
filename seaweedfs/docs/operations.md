# SeaweedFS Operations Guide

Reference guide for managing this deployment. All commands target the Docker Compose stack
defined in `compose.yaml`.

+ [SeaweedFS Operations Guide](#seaweedfs-operations-guide)
    + [Architecture](#architecture)
        + [Data flow](#data-flow)
    + [Deployment](#deployment)
        + [Start](#start)
        + [Stop (preserve data)](#stop-preserve-data)
        + [Full teardown (destroy all data)](#full-teardown-destroy-all-data)
        + [Restart a single service](#restart-a-single-service)
        + [View logs](#view-logs)
        + [Check status](#check-status)
    + [Web UIs](#web-uis)
    + [S3 API](#s3-api)
        + [AWS CLI setup](#aws-cli-setup)
        + [Common operations](#common-operations)
    + [Filer HTTP API](#filer-http-api)
    + [Maintenance](#maintenance)
        + [Open the admin shell](#open-the-admin-shell)
        + [Garbage collection (reclaim space from deleted files)](#garbage-collection-reclaim-space-from-deleted-files)
        + [Delete empty / orphaned volumes](#delete-empty--orphaned-volumes)
        + [Check volume filesystem integrity](#check-volume-filesystem-integrity)
        + [Fix replication](#fix-replication)
        + [Balance volume distribution across servers](#balance-volume-distribution-across-servers)
    + [Backup and Restore](#backup-and-restore)
        + [Save filer metadata to a file](#save-filer-metadata-to-a-file)
        + [Restore filer metadata from a file](#restore-filer-metadata-from-a-file)
        + [Backup volume data incrementally](#backup-volume-data-incrementally)
    + [Troubleshooting](#troubleshooting)
        + [Filer metadata not persisting after restart](#filer-metadata-not-persisting-after-restart)
        + [Disk space used but files not visible](#disk-space-used-but-files-not-visible)
        + [Volume server not registering with master](#volume-server-not-registering-with-master)
        + [No free volumes error](#no-free-volumes-error)

## Architecture

| Component  | Container                          | Default Port | Purpose                              |
| ---------- | ---------------------------------- | ------------ | ------------------------------------ |
| Master     | `sds-gateway-local-sfs-master`     | 9333         | Cluster coordination, volume routing |
| Volume     | `sds-gateway-local-sfs-volume`     | 8080         | Raw file chunk storage               |
| Filer      | `sds-gateway-local-sfs-filer`      | 8888         | Metadata + path-based file access    |
| S3 Gateway | `sds-gateway-local-sfs-s3`         | 8333         | AWS S3-compatible API                |
| WebDAV     | `sds-gateway-local-sfs-webdav`     | 7333         | WebDAV mount access                  |
| Prometheus | `sds-gateway-local-sfs-prometheus` | 9000         | Metrics scraping                     |

### Data flow

```text
Client → S3/WebDAV/Filer HTTP → Filer (metadata in /data/filer/filerldb2)
                                      ↓
                               Volume Server (chunks in ./data/volumes)
```

The **Filer** stores only metadata (file paths, sizes, chunk IDs). The **Volume Server**
stores the actual bytes. Both must persist across restarts — see the `volumes` section in
`compose.yaml`.

---

## Deployment

### Start

```bash
cd seaweedfs/
docker compose up -d
```

### Stop (preserve data)

```bash
docker compose down
```

### Full teardown (destroy all data)

```bash
docker compose down -v
rm -rf data/volumes/* data/filer/*
```

### Restart a single service

```bash
docker compose restart sds-gateway-local-sfs-filer
```

### View logs

```bash
# all services
docker compose logs -f

# single service
docker compose logs -f sds-gateway-local-sfs-filer
```

### Check status

```bash
docker compose ps
```

---

## Web UIs

| UI                    | URL                                   |
| --------------------- | ------------------------------------- |
| Master cluster status | <http://localhost:9333>               |
| Volume server status  | <http://localhost:8080/ui/index.html> |
| Filer browser         | <http://localhost:8888>               |
| Prometheus targets    | <http://localhost:9000/targets>       |

---

## S3 API

The S3 gateway is compatible with the AWS CLI and any S3 SDK.

### AWS CLI setup

```bash
aws configure set aws_access_key_id any
aws configure set aws_secret_access_key any
aws configure set default.region us-east-1
aws configure set default.s3.signature_version s3v4

export S3=http://localhost:8333
```

### Common operations

```bash
# list buckets
aws --endpoint-url $S3 s3 ls

# create a bucket
aws --endpoint-url $S3 s3 mb s3://my-bucket

# upload a file
aws --endpoint-url $S3 s3 cp local-file.txt s3://my-bucket/

# list bucket contents
aws --endpoint-url $S3 s3 ls s3://my-bucket

# download a file
aws --endpoint-url $S3 s3 cp s3://my-bucket/file.txt .

# delete a file
aws --endpoint-url $S3 s3 rm s3://my-bucket/file.txt

# delete a bucket (must be empty)
aws --endpoint-url $S3 s3 rb s3://my-bucket

# sync a local directory to a bucket
aws --endpoint-url $S3 s3 sync ./local-dir s3://my-bucket/prefix/
```

---

## Filer HTTP API

```bash
# upload a file
curl -F file=@report.pdf "http://localhost:8888/path/to/dir/"

# upload with a specific name
curl -F file=@report.pdf "http://localhost:8888/path/to/dir/renamed.pdf"

# download
curl "http://localhost:8888/path/to/dir/renamed.pdf" -o renamed.pdf

# list directory (JSON)
curl -H "Accept: application/json" "http://localhost:8888/path/to/dir/?pretty=y"

# delete a file
curl -X DELETE "http://localhost:8888/path/to/dir/renamed.pdf"

# server-side copy (no client data transfer)
curl -X POST "http://localhost:8888/dest/dir/?cp.from=/source/path/file.pdf"
```

---

## Maintenance

### Open the admin shell

All maintenance operations go through `weed shell`. Always `unlock` before exiting.

```bash
docker exec -it sds-gateway-local-sfs-master weed shell -master=localhost:9333
```

### Garbage collection (reclaim space from deleted files)

Deleted file chunks are not immediately removed. Run vacuum to compact volumes and free
disk space. The master also runs this automatically every 15 minutes when free space
exceeds 30%.

```bash
# trigger immediately via HTTP (no shell needed)
curl "http://localhost:9333/vol/vacuum"

# or with a custom threshold (40% free space to trigger)
curl "http://localhost:9333/vol/vacuum?garbageThreshold=0.4"
```

### Delete empty / orphaned volumes

Volumes that contain no live data (e.g. left over from previous runs with missing metadata)
can be removed. Run inside `weed shell`:

```bash
lock
volume.deleteEmpty -quietFor=24h -apply
unlock
```

`-quietFor=24h` skips volumes that have been written to within the last 24 hours, to avoid
racing with active writes.

### Check volume filesystem integrity

```bash
lock
volume.fsck -findMissingChunks
unlock
```

### Fix replication

```bash
lock
volume.fix.replication -apply
unlock
```

### Balance volume distribution across servers

```bash
lock
volume.balance -apply
unlock
```

---

## Backup and Restore

### Save filer metadata to a file

Run inside `weed shell` on the source cluster:

```bash
lock
fs.cd /
fs.meta.save -o /tmp/filer-backup.meta
unlock
```

Then copy it out:

```bash
docker cp sds-gateway-local-sfs-filer:/tmp/filer-backup.meta ./filer-backup.meta
```

### Restore filer metadata from a file

```bash
docker cp ./filer-backup.meta sds-gateway-local-sfs-filer:/tmp/filer-backup.meta
```

Then inside `weed shell`:

```bash
fs.meta.load /tmp/filer-backup.meta
```

### Backup volume data incrementally

Run on any machine with enough disk space. SeaweedFS fetches only the delta since the
last backup.

```bash
weed backup -server=localhost:9333 -dir=/backup/volumes -volumeId=1
```

Loop over all known volume IDs in a script — non-existent IDs are a no-op, so iterating
`1..N` is safe.

---

## Troubleshooting

### Filer metadata not persisting after restart

Verify the filer process is writing to the bind-mounted path:

```bash
docker exec sds-gateway-local-sfs-filer find / -maxdepth 4 -name "filerldb2" -type d 2>/dev/null
# Expected: /data/filer/filerldb2

docker exec sds-gateway-local-sfs-filer ls /data/filer/
# Expected: filerldb2/
```

If `filerldb2` appears outside `/data/filer/`, the `dir` setting in `config/filer.toml`
is wrong. It must use an absolute path that falls inside the volume mount:

```toml
[leveldb2]
    dir     = "/data/filer/filerldb2"
    enabled = true
```

### Disk space used but files not visible

This means orphaned volume chunks exist without filer metadata (e.g. the filer metadata
was lost in a previous session). The data is unrecoverable. Reclaim the space with:

```bash
# inside weed shell
lock
volume.deleteEmpty -quietFor=24h -apply
unlock
```

Or wipe `data/volumes/` entirely if you have no data to preserve.

### Volume server not registering with master

Check the master address in `compose.yaml` matches the master container name and port.
The filer and volume services must be able to reach the master by its container name on
the internal Docker network.

```bash
docker exec sds-gateway-local-sfs-volume ping sds-gateway-local-sfs-master
```

### No free volumes error

The default setup creates 8 volumes of 30 GB each. If you need more (e.g. many S3 buckets
each use their own collection):

```bash
# pre-allocate 4 more volumes
curl "http://localhost:9333/vol/grow?count=4"
```

Or reduce the volume size limit in the master command to allow more volumes from the same
disk budget (requires restart):

```bash
# in compose.yaml master command, add:
-volumeSizeLimitMB=1024
```
