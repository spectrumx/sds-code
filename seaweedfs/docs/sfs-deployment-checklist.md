# SeaweedFS Production Deployment Checklist

Runbook for deploying the SeaweedFS stack defined in `compose.production.yaml` as the
**primary** object store for SDS production. The gateway stack lives in the sibling
`gateway/` directory and connects over the shared Docker network `sds-network-prod`.

For day-2 operations after deploy, see [operations.md](./operations.md). For migrating
existing MinIO data, see
[gateway/docs/migration-minio-to-seaweedfs.md](../../gateway/docs/migration-minio-to-seaweedfs.md).

- [SeaweedFS Production Deployment Checklist](#seaweedfs-production-deployment-checklist)
    - [Overview \& Repository Layout](#overview--repository-layout)
    - [Gateway Integration](#gateway-integration)
    - [Infrastructure \& Pre-Deployment](#infrastructure--pre-deployment)
        - [Single-Server, All-in-One with 5 XFS Drives](#single-server-all-in-one-with-5-xfs-drives)
        - [0. Pre-Deployment Decisions](#0-pre-deployment-decisions)
            - [EC Design Note](#ec-design-note)
        - [1. OS \& Filesystem Preparation](#1-os--filesystem-preparation)
            - [1a. Identify Drives (Both Tracks)](#1a-identify-drives-both-tracks)
            - [1b. Track A — Fresh Drives (Empty, Can Be Formatted)](#1b-track-a--fresh-drives-empty-can-be-formatted)
            - [1c. Track B — Existing Drives (Already Have Data, Cannot Reformat)](#1c-track-b--existing-drives-already-have-data-cannot-reformat)
            - [1d. Set Mount Options Persistently (Both Tracks)](#1d-set-mount-options-persistently-both-tracks)
                - [Why XFS Settings Matter](#why-xfs-settings-matter)
    - [Core Service Configuration](#core-service-configuration)
        - [2. Security Configuration](#2-security-configuration)
            - [Why JWT Security Matters](#why-jwt-security-matters)
            - [gRPC mTLS Note](#grpc-mtls-note)
        - [3. Docker Compose Configuration](#3-docker-compose-configuration)
            - [Why 5 Separate Volume Servers Instead of One With 5 Dirs](#why-5-separate-volume-servers-instead-of-one-with-5-dirs)
            - [Why `-index=leveldb`](#why--indexleveldb)
        - [4. S3 API Setup](#4-s3-api-setup)
            - [S3 Encryption Note](#s3-encryption-note)
    - [Automated Deployment](#automated-deployment)
    - [Operations \& Maintenance](#operations--maintenance)
        - [5. Monitoring — Prometheus + Grafana](#5-monitoring--prometheus--grafana)
            - [Metrics Collection Model](#metrics-collection-model)
        - [6. Backup via Async Filer Backup](#6-backup-via-async-filer-backup)
            - [How Async Backup Works](#how-async-backup-works)
            - [Alternative: Volume-Level Backup](#alternative-volume-level-backup)
        - [7. Startup \& Verification](#7-startup--verification)
            - [Smoke Test: Drive Failure Scenario](#smoke-test-drive-failure-scenario)
        - [8. Volume Growth Tuning](#8-volume-growth-tuning)
        - [9. Maintenance Plan](#9-maintenance-plan)
            - [Daily / Automated](#daily--automated)
            - [Weekly](#weekly)
            - [Monthly](#monthly)
            - [Erasure Coding (Always Active)](#erasure-coding-always-active)
            - [Drive Replacement Procedure](#drive-replacement-procedure)
    - [Appendices](#appendices)
        - [Appendix A: Volume Size Calculation](#appendix-a-volume-size-calculation)
        - [Appendix B: Port Reference](#appendix-b-port-reference)
        - [Appendix C: Environment Files](#appendix-c-environment-files)

---

## Overview & Repository Layout

The SeaweedFS stack is a **separate compose project** checked out beside the gateway:

```text
sds-code/
├── gateway/          # Django app, RustFS secondary, postgres, opensearch, …
└── seaweedfs/        # SeaweedFS primary storage (this repo)
```

| File / path | Purpose |
| ----------- | ------- |
| `compose.production.yaml` | Production service definitions (source of truth) |
| `.envs/production/sfs.env` | JWT keys, Grafana password (git-ignored) |
| `.envs/example/seaweedfs.env` | Template for `sfs.env` |
| `config/*.toml`, `config/s3-config.json` | Checked-in SeaweedFS config |
| `prometheus/prometheus.yaml` | Prometheus scrape targets |
| `scripts/deploy.sh` | Start stack, configure S3 creds, create bucket |
| `scripts/prod-hostnames.env` | Hostnames allowed to run production deploy |
| `justfile` | `just deploy`, `just up`, `just health`, `just shell`, … |

**Image:** `docker.io/chrislusf/seaweedfs:4.32_large_disk_full` — pinned in
`compose.production.yaml`. Do not use `latest`.

**Tools required:** Docker Engine, Docker Compose v2, `just`, and (for data migration)
`mc` (MinIO Client).

---

## Gateway Integration

In production the gateway treats SeaweedFS as **PRIMARY** storage and RustFS as optional
**SECONDARY** redundancy.

| Concern | SeaweedFS side | Gateway side |
| ------- | -------------- | ------------ |
| S3 credentials | Configured by `deploy.sh` via `weed shell s3.configure` | `gateway/.envs/production/storage.env` (`PRIMARY_*` vars) |
| S3 endpoint (in-cluster) | Container `sds-gateway-prod-sfs-s3:8333` or compose service `sfs-s3:8333` on `sds-network-prod` | `PRIMARY_ENDPOINT_URL` / `PRIMARY_S3_ENDPOINT_URL` in `storage.env` |
| Bucket name | Created by deploy script | `PRIMARY_STORAGE_BUCKET_NAME` (default `spectrumx`) |
| Shared network | `sfs-s3` joins `sds-network-prod` | App, celery, rustfs join the same network |
| Dual-write / fallback | N/A | `OBJECT_STORE_*` flags in `storage.env` (off by default) |

Generate gateway storage secrets first:

```bash
cd gateway
./scripts/generate-secrets.sh production
# review gateway/.envs/production/storage.env
```

Ensure `PRIMARY_ACCESS_KEY_ID` is **at least 16 characters** — production deploy
validation rejects shorter or well-known keys.

The gateway deploy script orchestrates both stacks:

```bash
cd gateway
./scripts/deploy.sh production
```

That calls `seaweedfs/scripts/deploy.sh` with
`--sfs-env gateway/.envs/production/storage.env` unless you pass `--skip-sfs`.

---

## Infrastructure & Pre-Deployment

### Single-Server, All-in-One with 5 XFS Drives

---

### 0. Pre-Deployment Decisions

Answers to scoping questions gathered before writing this checklist:

| Question               | Decision                                  | Rationale                                                                                                                                      |
| ---------------------- | ----------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------- |
| Topology               | Single server, all-in-one                 | One machine runs master, volume servers, filer, S3, monitoring                                                                                 |
| Master HA              | Single master                             | Acceptable for single-node; master load is light; restartable                                                                                  |
| Filer store            | leveldb2 (embedded)                       | Simplest for single filer; no external dependency                                                                                              |
| Data durability        | Erasure Coding (RS 10+4) via admin worker | Writes go to `000` volumes; EC worker auto-converts full/quiet volumes to EC shards; survives up to 4 shard losses with ~1.4x storage overhead |
| Drive size             | 5 × 22TB                                  | ~110TB raw, ~74.5TB usable after EC overhead (RS 10+4 = 1.4x)                                                                                  |
| Drive failure target   | Up to 4 drives (theoretical max)          | RS(10,4) can lose any 4 of 14 shards; with 5 drives, EC shards are spread across all drives — losing 1-2 drives is fully survivable            |
| Monitoring             | Prometheus + Grafana                      | Pull-based scrape of per-component `/metrics` ports; pushgateway retained for batch metrics                                                    |
| S3 gateway             | Yes                                       | Required for S3-compatible access; service `sfs-s3` on port 8333                                                                               |
| Backup                 | Async filer backup (S3 sink)              | `sfs-filer-backup` service; configure `config/replication.toml`                                                                                |
| Volume server approach | 5 separate volume servers (1 per drive)   | Cleaner drive isolation; easier replacement on failure                                                                                         |

#### EC Design Note

This deployment uses **Erasure Coding (RS 10+4)** as the primary data durability
mechanism instead of replication. Here is how it works:

**Write path:** New data is written to normal volumes with **`000` replication** (no
copies). This is the initial landing zone. Data is temporarily at single-copy risk
during the brief window before EC conversion.

**EC conversion (automatic):** The `erasure_coding` plugin worker (running via `sfs-admin`

- `sfs-worker`) continuously scans for volumes that are:
- ≥80% full (fullness ratio threshold, configurable)
- Unmodified for ≥300 seconds (quiet period, configurable)
- Larger than 30MB

When a volume qualifies, the worker encodes it into **14 EC shards** (10 data + 4
parity) using Reed-Solomon coding. The 14 shards are spread across available volume
servers (drives). After successful encoding, the original volume file is deleted,
freeing space.

**Failure tolerance:** RS(10,4) can reconstruct data from any **10 of 14 shards**. With
5 drives and shards spread evenly, this means:

- **1-2 drive failures:** Fully survivable — at most ~3 shards lost per volume
- **3-4 drive failures:** Potentially survivable depending on shard distribution
- All 5 drives can have some shards on each; losing any single drive never takes down
  more than ~3 shards per volume (well within the 4-shard recovery limit)

**Storage efficiency:** RS(10,4) requires only **1.4×** raw storage (vs 2× for 001
replication, 3× for 002). For 5 × 22TB = 110TB raw, this yields ~74.5TB usable.

**Trade-offs:**

- Write amplification: EC reads the entire volume to encode it (one-time cost)
- Read penalty: EC reads may require an extra network hop to reconstruct data from
  multiple shards (~50% throughput vs normal volumes in benchmarks)
- Deletes only: EC shards are append-only; updates require re-compaction
- Temporary risk window: Before EC conversion, data lives on a single volume with 000
  replication — conversion happens within minutes of volume filling up

---

### 1. OS & Filesystem Preparation

This section splits into two tracks depending on whether the XFS drives are **fresh** or
**already formatted with data**. Mount options can be fixed on either track; mkfs-level
geometry cannot be changed without reformatting.

#### 1a. Identify Drives (Both Tracks)

- [ ] **Identify 5 drives** — confirm device paths:

  ```bash
  lsblk -o NAME,SIZE,TYPE,MOUNTPOINT,FSTYPE
  ```

- [ ] **Note mount points** — decide on a consistent scheme, e.g. `/disk1` … `/disk5`.
  Create them:

  ```bash
  mkdir -p /disk{1,2,3,4,5}
  ```

---

#### 1b. Track A — Fresh Drives (Empty, Can Be Formatted)

> Use this if the drives are new or contain nothing you need to keep.

- [ ] **XFS mkfs on each drive** with optimal settings:

  ```bash
  mkfs.xfs -f -d agcount=4 -l size=128m -n size=8192 /dev/vdb1   # repeat for vdc1, vdd1, vde1, vdf1
  ```

  | Flag      | Value | Why                                                                    |
  | --------- | ----- | ---------------------------------------------------------------------- |
  | `agcount` | 4     | More allocation groups → parallel allocation under concurrent writes   |
  | `l size`  | 128m  | Larger journal → smoother write bursts                                 |
  | `n size`  | 8192  | Larger dir blocks → better perf for directories with many volume files |

  > **On 22TB drives** the defaults are often already close to these values (XFS
  > auto-tunes based on device size). Run `xfs_info /dev/vdb1` after mkfs to confirm.

---

#### 1c. Track B — Existing Drives (Already Have Data, Cannot Reformat)

> Use this when the drives are already in use or carry data you need to preserve.

- [ ] **Check current XFS geometry** — some mkfs-time settings affect performance but
  **cannot be changed without reformatting**. Run on each drive:

  ```bash
  xfs_info /dev/vdb1   # repeat for vdc1, vdd1, vde1, vdf1
  ```

  Pay attention to:

  | Parameter | Ideal  | Impact if suboptimal                                             | Can fix?               |
  | --------- | ------ | ---------------------------------------------------------------- | ---------------------- |
  | `agcount` | ≥ 4    | Fewer AGs → less parallel allocation; minor perf hit             | **No** — requires mkfs |
  | `logsize` | ≥ 64m  | Small log → more frequent log rotation under write load          | **No** — requires mkfs |
  | `naming`  | ≥ 8192 | Small dir blocks → slower directory scans with many volume files | **No** — requires mkfs |

- [ ] **Check current mount options**:

  ```bash
  mount | grep /disk
  # or
  findmnt /disk1
  ```

  If `noatime,allocsize=1m` are missing, fix them in the next step.

---

#### 1d. Set Mount Options Persistently (Both Tracks)

Mount options — `noatime`, `allocsize=1m` — can be changed at any time by updating
`/etc/fstab` and remounting.

| Option         | Effect                                                                         |
| -------------- | ------------------------------------------------------------------------------ |
| `noatime`      | Skip access-time writes on reads — critical for storage servers                |
| `allocsize=1m` | XFS prealloc hint — matches SeaweedFS volume chunk patterns (1MB chunk writes) |

- [ ] **Add or update fstab entries** for each drive:

  ```text
  /dev/vdb1 /disk1 xfs noatime,allocsize=1m 0 0
  /dev/vdc1 /disk2 xfs noatime,allocsize=1m 0 0
  /dev/vdd1 /disk3 xfs noatime,allocsize=1m 0 0
  /dev/vde1 /disk4 xfs noatime,allocsize=1m 0 0
  /dev/vdf1 /disk5 xfs noatime,allocsize=1m 0 0
  ```

- [ ] **Create SeaweedFS data directories** on each drive:

  ```bash
  mkdir -p /disk{1,2,3,4,5}/{data,idx}
  mkdir -p /data/seaweedfs/{master,filer}
  ```

- [ ] **Remount all drives** (non-disruptive):

  ```bash
  mount -a
  mount | grep /disk   # confirm noatime,allocsize=1m
  df -h | grep /disk
  ```

- [ ] **Set ulimit** (open file limit):

  ```bash
  echo "* soft nofile 102400" >> /etc/security/limits.conf
  echo "* hard nofile 102400" >> /etc/security/limits.conf
  ulimit -n 102400
  ```

- [ ] **Disable swap** or set `vm.swappiness=1`:

  ```bash
  echo "vm.swappiness=1" >> /etc/sysctl.conf
  echo "vm.vfs_cache_pressure=50" >> /etc/sysctl.conf
  sysctl -p
  ```

- [ ] **Install Docker Engine** and **Docker Compose** v2.
- [ ] **Create the shared gateway network** (required before `compose.production.yaml`
  starts — `sds-s3` attaches to it):

  ```bash
  docker network create sds-network-prod --driver=bridge
  ```

  The internal SeaweedFS network `sds-gateway-prod-seaweed-net` is **created
  automatically** by compose — do not create it manually.
- [ ] **Register production hostnames** in both repos:

  ```bash
  cp scripts/prod-hostnames.example.env scripts/prod-hostnames.env
  echo "$(hostname)" >> scripts/prod-hostnames.env
  # repeat in gateway/scripts/
  ```

  Deploy scripts abort if the current hostname is not listed when deploying to
  production.

##### Why XFS Settings Matter

| Setting              | Effect                                                                                                      |
| -------------------- | ----------------------------------------------------------------------------------------------------------- |
| `noatime`            | Eliminates metadata writes on reads                                                                         |
| `allocsize=1m`       | Hints XFS to allocate 1MB extents — matches SeaweedFS volume chunk patterns                                 |
| `agcount=4`          | (mkfs option) More allocation groups = better parallel allocation under concurrent writes                   |
| Volume Preallocation | Master flag `-volumePreallocate` on XFS gives contiguous block allocation, reduces fragmentation            |

See the [Optimization wiki
page](https://github.com/seaweedfs/seaweedfs/wiki/Optimization#preallocate-volume-file-disk-spaces).

---

## Core Service Configuration

### 2. Security Configuration

JWT and SSE secrets live in **`.envs/production/sfs.env`**, loaded by compose via
`just dc` / `scripts/env-selection.sh`. S3 access keys live in the **gateway**
`storage.env` and are applied at deploy time — see [§4](#4-s3-api-setup).

- [ ] **Review checked-in config** under `config/`:
    - `security.toml` — JWT / security scaffold (already in repo)
    - `master.toml` — volume growth and maintenance scripts
    - `filer.toml` — leveldb2 filer store enabled
    - `s3-config.json` — empty identities array (credentials added at deploy)
    - `replication.toml` — backup sink template (edit before enabling backup)

- [ ] **Create `.envs/production/sfs.env`** from the example (never commit):

  ```bash
  cp .envs/example/seaweedfs.env .envs/production/sfs.env
  chmod 600 .envs/production/sfs.env
  ```

- [ ] **Set required secrets** in `sfs.env`:

  ```ini
  JWT_SIGNING_KEY=<openssl rand -hex 32>
  JWT_FILER_SIGNING_KEY=<openssl rand -hex 32>
  S3_SSE_KEK=<openssl rand -hex 32>
  GRAFANA_PASSWORD=<choose a strong password>
  ```

  `scripts/deploy.sh` validates that all three JWT/SSE keys are non-empty before
  starting production.

- [ ] **Store secrets in a vault/password manager** and snapshot env files:

  ```bash
  ../gateway/scripts/create-snapshot.sh production
  ```

#### Why JWT Security Matters

Without JWT signing keys, any client that can reach the volume servers can write data.
The JWT is generated by the master during `/dir/assign`, so only clients that first
authenticate with the master (or go through the filer/S3 gateway) can write. This
prevents direct unauthorized writes to volume server HTTP endpoints.

#### gRPC mTLS Note

For a single-server deployment, gRPC mTLS is **optional**. The gRPC traffic stays within
the Docker network and does not leave the host. Skip unless you need FIPS compliance or
defense-in-depth.

---

### 3. Docker Compose Configuration

The production stack is defined in **`compose.production.yaml`**. Do not maintain a
separate hand-written `compose.yaml` — edit the checked-in file or add a
`compose.override.yaml` for site-specific bind mounts.

- [ ] **Review `compose.production.yaml`** matches your hardware (disk paths, resource
  limits).
- [ ] **Confirm bind mounts exist** on the host:

  ```bash
  ls -la /disk{1,2,3,4,5}/{data,idx} /data/seaweedfs/{master,filer}
  ```

- [ ] **Optional: override disk layout** — for non-5-drive hosts, use
  `compose.override.yaml` to adjust volume server `volumes:` and `command:` blocks.

#### Production services (current)

| Compose service | Container | Role |
| --------------- | --------- | ---- |
| `sfs-master` | `sds-gateway-prod-sfs-master` | Cluster coordinator |
| `sfs-volume1` … `sfs-volume5` | `sds-gateway-prod-sfs-volume1` … `volume5` | One volume server per XFS drive (8081–8085) |
| `sfs-filer` | `sds-gateway-prod-sfs-filer` | Metadata (leveldb2) |
| `sfs-s3` | `sds-gateway-prod-sfs-s3` | S3 API — **only service on `sds-network-prod`** |
| `sfs-webdav` | `sds-gateway-prod-sfs-webdav` | WebDAV (internal network only) |
| `sfs-admin` | `sds-gateway-prod-sfs-admin` | EC / maintenance admin |
| `sfs-worker` | `sds-gateway-prod-sfs-worker` | EC encoding worker |
| `sfs-prometheus` | `sds-gateway-prod-sfs-prometheus` | Metrics (internal) |
| `sfs-pushgateway` | `sds-gateway-prod-sfs-pushgateway` | Batch / push metrics |
| `sfs-grafana` | `sds-gateway-prod-sfs-grafana` | Dashboards (`127.0.0.1:3000` only) |
| `sfs-filer-backup` | `sds-gateway-prod-sfs-filer-backup` | Async replication (configure sink first) |

Internal DNS names (`sfs-master`, `sfs-filer`, …) resolve on
`sds-gateway-prod-seaweed-net`. Gateway containers reach SeaweedFS S3 via
`sds-gateway-prod-sfs-s3:8333` or `sfs-s3:8333` on `sds-network-prod`.

#### Why 5 Separate Volume Servers Instead of One With 5 Dirs

| Approach                             | Pros                                                                                                                       | Cons                                                      |
| ------------------------------------ | -------------------------------------------------------------------------------------------------------------------------- | --------------------------------------------------------- |
| 5 separate volume servers            | Each drive independent; replacing a failed drive = stop one container; cleaner metrics per-drive; easier to move/rebalance | More containers; more ports                               |
| 1 server with 5 comma-separated dirs | Simpler; fewer ports                                                                                                       | Opaque per-drive health; harder to replace a single drive |

For EC, separate volume servers are equally important. The EC shard placement algorithm
spreads the 14 shards (10 data + 4 parity) across available volume servers. With 5
separate servers (drives), shards are naturally distributed across all drives,
maximizing failure tolerance.

| EC shard distribution (5 drives)       | Max survivable failures             |
| -------------------------------------- | ----------------------------------- |
| 14 shards spread across 5 servers      | 4 shards = any 2-3 drives           |
| 14 shards on 1 server (5 dirs, 1 node) | 0 drives (server loss = total loss) |

#### Why `-index=leveldb`

- **Memory mode** (default): Fast but loads full index into RAM on startup — slow
  restart with large volumes.
- **LevelDB mode**: ~4MB fixed memory footprint per volume server, faster startup,
  minimal performance impact since index lookups are dwarfed by network latency.
- For 5 volume servers with large volumes, leveldb saves significant RAM.

---

### 4. S3 API Setup

- [ ] **Confirm `config/s3-config.json`** has an empty identities array — credentials
  are never hardcoded:

  ```json
  {"identities": []}
  ```

- [ ] **Prepare gateway `storage.env`** with PRIMARY credentials (see
  [Gateway Integration](#gateway-integration)):

  ```ini
  PRIMARY_ACCESS_KEY_ID=<min 16 chars>
  PRIMARY_SECRET_ACCESS_KEY=<min 16 chars>
  PRIMARY_STORAGE_BUCKET_NAME=spectrumx
  PRIMARY_ENDPOINT_URL=sds-gateway-prod-sfs-s3:8333
  PRIMARY_S3_ENDPOINT_URL=http://sds-gateway-prod-sfs-s3:8333
  ```

- [ ] **Deploy configures S3 automatically** — `scripts/deploy.sh` runs
  `weed shell s3.configure` and `s3.bucket.create` using those PRIMARY vars.
  Production validation rejects:
    - Well-known keys (`admin-access-key`, `backup-access-key`)
    - Access or secret keys shorter than 16 characters

- [ ] **Test S3 access** after deploy:

  ```bash
  ACCESS_KEY=$(grep PRIMARY_ACCESS_KEY_ID ../gateway/.envs/production/storage.env | cut -d= -f2)
  SECRET=$(grep PRIMARY_SECRET_ACCESS_KEY ../gateway/.envs/production/storage.env | cut -d= -f2)

  AWS_ACCESS_KEY_ID="${ACCESS_KEY}" AWS_SECRET_ACCESS_KEY="${SECRET}" \
    aws s3 --endpoint http://localhost:8333 ls s3://spectrumx/
  ```

#### S3 Encryption Note

If S3 clients send `x-amz-server-side-encryption: AES256`, `S3_SSE_KEK` must be set in
`sfs.env`. Without it, these requests fail with `400 Bad Request`.

---

## Automated Deployment

Preferred path — from the **gateway** directory (deploys SeaweedFS then gateway):

```bash
cd gateway
./scripts/deploy.sh production
```

SeaweedFS-only deploy — from this directory:

```bash
cd seaweedfs
./scripts/deploy.sh --sfs-env ../gateway/.envs/production/storage.env production
# or:
just deploy production
```

What `seaweedfs/scripts/deploy.sh` does:

1. Validates hostname against `scripts/prod-hostnames.env`
2. Validates JWT secrets in `.envs/production/sfs.env`
3. Starts the stack (`just build && just up`)
4. Waits for S3 health on `sds-gateway-prod-sfs-s3`
5. Runs `weed shell s3.configure` with PRIMARY credentials
6. Creates the `spectrumx` bucket (or value of `PRIMARY_STORAGE_BUCKET_NAME`)

Useful flags:

| Flag / env | Effect |
| ---------- | ------ |
| `--skip-setup` / `SFS_SKIP_SETUP=true` | Start stack only; skip credential/bucket setup |
| `--auto-gen-prod-env` | Generate empty `sfs.env` with JWT keys (new deployments only) |
| `SDS_SKIP_SFS=true` (gateway deploy) | Skip SeaweedFS entirely |

Check selected environment:

```bash
just env
```

Run cluster health check:

```bash
just health
just health-json   # machine-readable
```

---

## Operations & Maintenance

### 5. Monitoring — Prometheus + Grafana

Monitoring services are included in `compose.production.yaml`. Prometheus config is
**checked in** at `prometheus/prometheus.yaml`.

- [ ] **Confirm scrape targets** — Prometheus pulls metrics directly from each
  component's `-metricsPort`:

  | Job | Target |
  | --- | ------ |
  | master | `sds-gateway-prod-sfs-master:9324` |
  | filer | `sds-gateway-prod-sfs-filer:9326` |
  | s3 | `sds-gateway-prod-sfs-s3:9327` |
  | volume1–5 | `sds-gateway-prod-sfs-volume{N}:950{N}` |
  | pushgateway | `sds-gateway-prod-sfs-pushgateway:9091` |

- [ ] **Access Grafana** — bound to localhost only:

  ```bash
  # on the production host
  curl -fsS http://127.0.0.1:3000/api/health
  ```

  Use SSH port-forward or a reverse proxy for remote access. Login with admin /
  `GRAFANA_PASSWORD` from `sfs.env`.

- [ ] **Import Grafana dashboard** from upstream:

  ```bash
  curl -o grafana-seaweedfs.json \
    https://raw.githubusercontent.com/seaweedfs/seaweedfs/master/other/metrics/grafana_seaweedfs.json
  ```

  Create a Prometheus datasource pointing to `http://sds-gateway-prod-sfs-prometheus:9090`
  (from inside the Docker network).

- [ ] **Set up alerting** for:
    - Volume server down (heartbeat missing)
    - Free volume count = 0 (cluster full)
    - High compaction backlog
    - Disk space < 10% on any volume drive

The gateway admin dashboard also TCP-checks `PRIMARY_ENDPOINT_URL` as `primary-storage`.

#### Metrics Collection Model

Components expose `/metrics` on dedicated ports (`-metricsPort` in compose). Prometheus
**scrapes** these endpoints on the internal network. Pushgateway remains available for
batch or short-lived job metrics but is no longer the primary collection path.

---

### 6. Backup via Async Filer Backup

The `sfs-filer-backup` service is **already defined** in `compose.production.yaml`.
Configure the sink before relying on it.

- [ ] **Create backup credentials** in your remote S3-compatible store (MinIO, RustFS,
  etc.) with write access to a dedicated bucket.
- [ ] **Edit `config/replication.toml`** — set `[sink.s3]` endpoint, bucket, and
  credentials. Optionally set `MINIO_BACKUP_ACCESS_KEY` / `MINIO_BACKUP_SECRET_KEY` in
  `sfs.env` if using env substitution.
- [ ] **Create the remote backup bucket**:

  ```bash
  mc mb --ignore-existing "backup-alias/spectrumx"
  ```

- [ ] **Restart the backup service** after config changes:

  ```bash
  just dc restart sfs-filer-backup
  just logs sfs-filer-backup
  ```

#### How Async Backup Works

- `weed filer.backup` subscribes to the filer's metadata change log (CDC).
- When files are created/updated/deleted, it reads the content from SeaweedFS and
  replicates to the configured sink.
- Progress is checkpointed on the filer — safe to restart.
- In `is_incremental = false` mode, the remote mirror keeps the same directory structure
  as the source.

#### Alternative: Volume-Level Backup

For a full-clone backup (not just file-level), use `weed backup` per volume:

```bash
docker exec sds-gateway-prod-sfs-filer \
  weed backup -server=sfs-master:9333 -dir=/backup -volumeId=<id>
```

This is useful for bootstrapping a second cluster but is not continuous.

---

### 7. Startup & Verification

- [ ] **Deploy** (see [Automated Deployment](#automated-deployment)) or start manually:

  ```bash
  just up
  just dc ps
  ```

- [ ] **Verify S3 gateway**:

  ```bash
  curl -fsS http://localhost:8333/healthz
  ```

- [ ] **Verify cluster status** (master HTTP is internal — use exec or internal curl):

  ```bash
  docker exec sds-gateway-prod-sfs-master \
    curl -fsS http://localhost:9333/cluster/status
  ```

  Confirm all 5 volume servers appear and free volume count > 0.
- [ ] **Verify volume servers** (host ports 8081–8085):

  ```bash
  curl -fsS http://localhost:8081/healthz   # repeat for 8082–8085
  ```

- [ ] **Verify filer**:

  ```bash
  curl -fsS http://localhost:8888/
  ```

- [ ] **Verify bucket and write path**:

  ```bash
  just shell
  # inside weed shell:
  #   s3.bucket.list
  ```

- [ ] **Run benchmark** from the internal network:

  ```bash
  docker run --rm --network sds-gateway-prod-seaweed-net \
    docker.io/chrislusf/seaweedfs:4.32_large_disk_full \
    weed benchmark -master=sfs-master:9333 -n 10000
  ```

- [ ] **Verify Prometheus** — from a container on the seaweed network, check targets
  are up.
- [ ] **Verify Grafana** — `http://127.0.0.1:3000`

#### Smoke Test: Drive Failure Scenario

Simulate a drive failure to verify EC durability:

```bash
docker stop sds-gateway-prod-sfs-volume1

# verify data still accessible via S3
aws s3 --endpoint http://localhost:8333 ls s3://spectrumx/ --recursive

docker exec -it sds-gateway-prod-sfs-filer weed shell -master=sfs-master:9333 \
  -c "ec.balance"

docker start sds-gateway-prod-sfs-volume1

docker exec -it sds-gateway-prod-sfs-filer weed shell -master=sfs-master:9333 \
  -c "ec.balance -apply"
```

---

### 8. Volume Growth Tuning

Default growth is configured in **`config/master.toml`** (`[master.volume_growth]`,
currently `copy_1 = 7`). The master command sets `-volumeSizeLimitMB=30000` (30 GB
volumes).

To increase write concurrency, edit `config/master.toml`:

```toml
[master.volume_growth]
copy_1 = 16
threshold = 0.9
```

For larger volumes on 22TB drives, adjust the master command in
`compose.production.yaml`:

```text
-volumeSizeLimitMB=100000   # 100GB volumes → ~220 per drive
```

With LevelDB index mode, each volume's on-disk index is ~20–40 MB in the `idx`
directory; RAM per volume server stays ~4 MB regardless of volume count.

---

### 9. Maintenance Plan

#### Daily / Automated

- [ ] **Verify admin + worker are running**:

  ```bash
  docker ps --filter name=sds-gateway-prod-sfs-admin
  docker ps --filter name=sds-gateway-prod-sfs-worker
  ```

  `config/master.toml` defines periodic maintenance (EC encode/rebuild/balance, log
  purge, empty volume cleanup, S3 multipart cleanup) via `[master.maintenance]`.

- [ ] **Monitor disk usage** on all 5 drives. Alert when any drive exceeds 85% usage.

- [ ] **Quick health check**:

  ```bash
  just health
  ```

#### Weekly

- [ ] **Check volume status via weed shell**:

  ```bash
  just shell
  # volume.status
  # volume.list
  ```

#### Monthly

- [ ] **Run cluster health checks**:

  ```bash
  just shell
  # volume.fsck
  # volume.check.disk
  ```

- [ ] **Review Grafana dashboards** for compaction rates, write amplification, disk growth
- [ ] **Verify backup** — confirm remote bucket has recent objects

#### Erasure Coding (Always Active)

EC is the **primary durability mechanism**. The `sfs-worker` container runs the
`erasure_coding` plugin and continuously converts full/quiet volumes to RS(10,4) shards.

**Detection defaults** (configurable from admin UI):

- Fullness ratio threshold: 80%
- Quiet period: 300 seconds
- Minimum volume size: 30 MB
- Scan interval: 5 minutes

**What to watch for:**

- Ensure `sds-gateway-prod-sfs-worker` is always running — if it stops, volumes remain
  at `000` replication (single copy) indefinitely.
- If free volume IDs run low: `curl http://localhost:9333/vol/grow?count=10` (via exec)
- Monitor EC shard distribution after drive replacements.

#### Drive Replacement Procedure

1. **Do NOT stop the volume container yet** unless the drive is fully dead.

2. If partially readable, mark maintenance mode:

   ```bash
   docker exec -it sds-gateway-prod-sfs-filer weed shell -master=sfs-master:9333 \
     -c "volumeServer.state --nodes sfs-volume1:8081 --maintenanceOn"
   ```

3. Replace the drive, mkfs/mount, recreate dirs:

   ```bash
   mkdir -p /disk1/{data,idx}
   ```

4. Start the container:

   ```bash
   docker start sds-gateway-prod-sfs-volume1
   ```

5. Rebalance EC shards:

   ```bash
   docker exec -it sds-gateway-prod-sfs-filer weed shell -master=sfs-master:9333 \
     -c "ec.balance -apply"
   ```

6. Turn off maintenance mode if enabled:

   ```bash
   docker exec -it sds-gateway-prod-sfs-filer weed shell -master=sfs-master:9333 \
     -c "volumeServer.state --nodes sfs-volume1:8081 --maintenanceOff"
   ```

---

## Appendices

### Appendix A: Volume Size Calculation

| Drive count | Data durability | Volume size | Volumes per drive | Raw storage | Usable capacity |
| ----------- | --------------- | ----------- | ----------------- | ----------- | --------------- |
| 5 × 22TB    | RS(10,4) EC     | 30GB        | ~733 per drive    | 110TB       | ~74.5TB         |
| 5 × 22TB    | RS(10,4) EC     | 100GB       | ~220 per drive    | 110TB       | ~74.5TB         |

**Formula**: `usable = (total_raw / 1.4) × 0.95` (RS 10+4 = 1.4× raw overhead; ~5% for
XFS filesystem overhead, index files, and compaction temp space)

| Method          | Raw:Usable ratio | Usable from 110TB raw | # disk failures w/o data loss |
| --------------- | ---------------- | --------------------- | ----------------------------- |
| No redundancy   | 1:1              | 107.8TB               | 0 / 5                         |
| EC RS(10,4)     | 1.4:1            | ~74.5TB               | 2 / 5                         |
| Replication 001 | 2:1              | ~52.3TB               | 1 / 5                         |
| Replication 002 | 3:1              | ~34.8TB               | 2 / 5                         |

### Appendix B: Port Reference

Host-exposed ports (production). Metrics ports are internal-only unless you add port
mappings.

| Service | Container | HTTP / API | gRPC | Metrics |
| ------- | --------- | ---------- | ---- | ------- |
| Master | `sds-gateway-prod-sfs-master` | 9333 (internal) | 19333 | 9324 |
| Volume 1–5 | `sds-gateway-prod-sfs-volume{N}` | 8081–8085 | 18081–18085 | 9501–9505 |
| Filer | `sds-gateway-prod-sfs-filer` | 8888 | 18888 | 9326 |
| S3 | `sds-gateway-prod-sfs-s3` | **8333** | — | 9327 |
| Admin | `sds-gateway-prod-sfs-admin` | 23646 (internal) | — | — |
| Prometheus | `sds-gateway-prod-sfs-prometheus` | 9090 (internal) | — | — |
| Pushgateway | `sds-gateway-prod-sfs-pushgateway` | 9091 (internal) | — | — |
| Grafana | `sds-gateway-prod-sfs-grafana` | **127.0.0.1:3000** | — | — |

### Appendix C: Environment Files

**SeaweedFS stack** — `.envs/production/sfs.env` (loaded by `just dc`):

```ini
JWT_SIGNING_KEY=<openssl rand -hex 32>
JWT_FILER_SIGNING_KEY=<openssl rand -hex 32>
S3_SSE_KEK=<openssl rand -hex 32>
GRAFANA_PASSWORD=<strong password>

# optional — for filer.backup S3 sink in replication.toml
MINIO_BACKUP_ACCESS_KEY=
MINIO_BACKUP_SECRET_KEY=
```

**Gateway stack** — `gateway/.envs/production/storage.env` (PRIMARY = SeaweedFS):

```ini
PRIMARY_ACCESS_KEY_ID=<min 16 chars>
PRIMARY_SECRET_ACCESS_KEY=<min 16 chars>
PRIMARY_STORAGE_BUCKET_NAME=spectrumx
PRIMARY_ENDPOINT_URL=sds-gateway-prod-sfs-s3:8333
PRIMARY_S3_ENDPOINT_URL=http://sds-gateway-prod-sfs-s3:8333
PRIMARY_STORAGE_USE_HTTPS=false

# SECONDARY (RustFS) — optional redundancy
SECONDARY_ACCESS_KEY_ID=...
SECONDARY_SECRET_ACCESS_KEY=...
SECONDARY_ENDPOINT_URL=rustfs:9000
SECONDARY_S3_ENDPOINT_URL=http://rustfs:9000
SECONDARY_STORAGE_BUCKET_NAME=spectrumx

OBJECT_STORE_WRITE_BOTH_ENABLED=false
OBJECT_STORE_READ_FALLBACK_TO_SECONDARY_ENABLED=false
OBJECT_STORE_DUAL_WRITE_STRICT=false
```

**Do not commit either file to version control.** Snapshot with
`gateway/scripts/create-snapshot.sh production` after initial generation.
