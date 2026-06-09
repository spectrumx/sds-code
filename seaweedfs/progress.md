# SeaweedFS Production Deployment Progress

## Mission: Checklist-Compliant Production Deployment

**Target:** 5 × 22TB drives, Erasure Coding RS(10+4), push-based monitoring, JWT security.

## Audit Results

### Current State vs Checklist Requirements

| Area                | Before                                        | After                                          |
| ------------------- | --------------------------------------------- | ---------------------------------------------- |
| Image tag           | `4.17_large_disk`                             | `4.23-large_disk_full`                         |
| Volume servers      | 1 (named Docker volume)                       | 5 (bind mount to /disk{1-5}/{data,idx})        |
| Index               | memory (default)                              | leveldb on all 5 volumes                       |
| EC (admin+worker)   | Not present                                   | admin + worker containers added                |
| Monitoring          | Prometheus (direct scrape)                    | Pushgateway + Prometheus (push mode) + Grafana |
| S3 config           | No s3-config.json                             | s3-config.json with identities                 |
| Security (JWT)      | security.toml keys empty                      | Env var JWT keys in compose + .env             |
| Backup              | Not present                                   | filer-backup service + replication.toml S3 sink|
| Logging config      | Not defined                                   | x-logging with json-file driver                |
| Network             | `sds-gateway-prod-seaweed-net` (bridge)       | External network (created before deploy)       |
| WebDAV              | Present                                       | Preserved (image bumped to 4.23)               |
| Healthchecks        | Present on volume, s3                         | Retained on all 5 volumes + s3                 |
| Env file refs       | `.envs/*/seaweedfs.env` (wrong name)          | Fixed to `sfs.env` in env-selection.sh         |

## Changes Made

### 1. `compose.production.yaml` — Full rewrite

- Image: `4.23-large_disk_full` (supports large volumes, includes all backends)
- x-logging defaults for all services
- External network `sds-gateway-prod-seaweed-net` (created before deploy)
- Master: JWT env var, volumePreallocate, volumeSizeLimitMB=30000, push metrics
- 5 volume services (volume1-5): bind mounts, leveldb index, compactionMBps=40, minFreeSpacePercent=7, per-drive healthchecks
- Filer: JWT filer signing, leveldb2, encryptVolumeData=false, maxMB=32
- S3: JWT filer signing, SSE KEK, s3-config.json, healthcheck, dual-network
- WebDAV: preserved, image bumped
- Admin: EC management, cluster maintenance
- Worker: erasure_coding plugin runner
- Prometheus: v2.53.0, pushgateway scrape target, web.enable-lifecycle
- Pushgateway: v1.9.0
- Grafana: 11.1.0, admin password from env
- filer-backup: async S3 replication to MinIO

### 2. `prometheus/prometheus.yaml` — Pushgateway mode

- Changed from direct service scrape (4 targets) to single pushgateway target with `honor_labels: true`

### 3. `config/security.toml` — Env var documentation

- Added comments: `PRODUCTION: Set via WEED_JWT_SIGNING_KEY env var`

### 4. `config/s3-config.json` — NEW

- Admin identity (Admin, Read, Write, List, Tagging)
- Backup-user identity (Read, List)

### 5. `config/replication.toml` — S3 sink enabled

- Uncommented `[sink.s3]` section, set `enabled = true`
- Credentials use `${MINIO_BACKUP_ACCESS_KEY}` / `${MINIO_BACKUP_SECRET_KEY}` env vars
- Target: `spectrumx` bucket, `/spectrumx` prefix

### 6. `.envs/production/sfs.env` — Secrets scaffolding

- Added: `JWT_SIGNING_KEY`, `JWT_FILER_SIGNING_KEY`, `S3_SSE_KEK`, `GRAFANA_PASSWORD`, `MINIO_BACKUP_ACCESS_KEY`, `MINIO_BACKUP_SECRET_KEY`

### 7. `.envs/example/seaweedfs.env` — Updated template

- Mirrors production env structure with secrets placeholders

### 8. `scripts/env-selection.sh` — Bug fix

- Fixed: `seaweedfs.env` → `sfs.env` (all actual env files use `sfs.env` naming)

## Final Compliance Review

| Checklist Section       | Status | Notes                                            |
| ----------------------- | ------ | ------------------------------------------------ |
| §0 Pre-Deployment       | ✅     | EC RS(10+4), 5×22TB, leveldb2, push monitoring   |
| §1 OS & Filesystem      | 🟡     | Documented; mkfs/fstab are host-level ops         |
| §2 Security             | ✅     | JWT env vars, security.toml scaffold, .env        |
| §3 Docker Compose       | ✅     | Full compose with all checklist services          |
| §4 S3 API               | ✅     | s3-config.json with admin + backup identities     |
| §5 Monitoring           | ✅     | Pushgateway + Prometheus + Grafana               |
| §6 Backup               | ✅     | filer-backup + replication.toml S3 sink          |
| §7 Startup & Verify     | 🟡     | Documented in checklist; commands ready to run    |
| §8 Volume Growth        | ✅     | master.toml volume_growth config present          |
| §9 Maintenance          | ✅     | master.toml scripts + admin+worker services      |

### Items requiring host-level ops (not in compose scope)

- XFS filesystem creation with mkfs.xfs
- /etc/fstab mount options (noatime,allocsize=1m)
- /disk{1-5}/{data,idx} directory creation
- Docker network creation
- Docker Engine installation
- ulimit and sysctl tuning
- MinIO backup bucket creation
- Grafana dashboard import
- S3 credential configuration via `s3.configure` in weed shell

## Progress Log

### 2026-05-05

- [x] Audited all existing compose files, config files, .env files, scripts
- [x] Documented gap analysis
- [x] Rewrote compose.production.yaml — full checklist compliance + merged existing features
- [x] Updated prometheus.yaml for pushgateway mode
- [x] Updated security.toml with env var documentation
- [x] Created s3-config.json with admin + backup identities
- [x] Updated replication.toml with S3 sink enabled
- [x] Updated .envs/production/sfs.env with JWT secrets scaffolding
- [x] Updated .envs/example/seaweedfs.env with secrets placeholders
- [x] Fixed env-selection.sh bug (seaweedfs.env → sfs.env)
- [x] Final review against checklist sections 0-9 — all covered
