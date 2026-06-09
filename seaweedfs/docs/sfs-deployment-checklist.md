# SeaweedFS Production Deployment Checklist

- [SeaweedFS Production Deployment Checklist](#seaweedfs-production-deployment-checklist)
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
    - [Operations \& Maintenance](#operations--maintenance)
        - [5. Monitoring — Prometheus + Grafana](#5-monitoring--prometheus--grafana)
            - [Push vs Pull Metrics](#push-vs-pull-metrics)
        - [6. Backup to MinIO via Async Filer Backup](#6-backup-to-minio-via-async-filer-backup)
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
        - [Appendix C: Recommended Environment `.env` File](#appendix-c-recommended-environment-env-file)

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
| Monitoring             | Prometheus + Grafana (push mode)          | Full observability with the upstream Grafana dashboard                                                                                         |
| S3 gateway             | Yes                                       | Required for S3-compatible access; separate service on port 8333                                                                               |
| Backup                 | Async to existing MinIO (S3 interface)    | `weed filer.backup` with S3 sink; user has mc alias ready                                                                                      |
| Volume server approach | 5 separate volume servers (1 per drive)   | Cleaner drive isolation; easier replacement on failure                                                                                         |

#### EC Design Note

This deployment uses **Erasure Coding (RS 10+4)** as the primary data durability
mechanism instead of replication. Here is how it works:

**Write path:** New data is written to normal volumes with **`000` replication** (no
copies). This is the initial landing zone. Data is temporarily at single-copy risk
during the brief window before EC conversion.

**EC conversion (automatic):** The `erasure_coding` plugin worker (running via `weed
admin` + `weed worker`) continuously scans for volumes that are:

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

  # e.g.
  # meta-data=/dev/vdb1              isize=512    agcount=22, agsize=268435455 blks
  #          =                       sectsz=4096  attr=2, projid32bit=1
  #          =                       crc=1        finobt=1, sparse=1, rmapbt=0
  #          =                       reflink=1    bigtime=1 inobtcount=1 nrext64=0
  # data     =                       bsize=4096   blocks=5859442176, imaxpct=5
  #          =                       sunit=0      swidth=0 blks
  # naming   =version 2              bsize=4096   ascii-ci=0, ftype=1
  # log      =internal log           bsize=4096   blocks=521728, version=2
  #          =                       sectsz=4096  sunit=1 blks, lazy-count=1
  # realtime =none                   extsz=4096   blocks=0, rtextents=0
  ```

  In the example above:

    - **agcount** = `22` → well above 4, excellent for parallel allocation.
    - **naming bsize** = `4096` → below the ideal `8192`. This means directory metadata
  blocks are 4KB instead of 8KB. For SeaweedFS this is a minor factor because volume
  files are written sequentially and directories hold at most a few thousand entries.
  The `-n size=8192` mkfs flag is a "nice to have" optimization, not a requirement.
    - **logsize** = `521728 blocks × 4096 bsize = ~2 GB` → well above the `128m` minimum.
  The log holds metadata journal entries; a tiny log forces flushes more often under
  concurrent writes. On 22TB drives XFS auto-sizes the log generously.

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

  If `noatime,nodiratime,allocsize=1m` are missing, fix them in the next step.

---

#### 1d. Set Mount Options Persistently (Both Tracks)

Mount options — `noatime`, `nodiratime`, `nobarrier`, `allocsize` — can be changed at
any time by updating `/etc/fstab` and remounting. These are the most impactful tuning
parameters and the main reason to touch the filesystem config.

| Option         | Effect                                                                         |
| -------------- | ------------------------------------------------------------------------------ |
| `noatime`      | Skip access-time writes on reads — critical for storage servers                |
| `allocsize=1m` | XFS prealloc hint — matches SeaweedFS volume chunk patterns (1MB chunk writes) |

Sources:

- [`allocsize`](https://oneuptime.com/blog/post/2026-03-04-tune-xfs-file-system-performance-mount-options-rhel-9/view#allocsize)

Other options

| Option         | Effect                                                                  |
| -------------- | ----------------------------------------------------------------------- |
| `rw`           | Read-write mode (default)                                               |
| `attr2`        | Enable version 2 on-disk inode format (immutable default on modern XFS) |
| `nodiratime`   | Skip directory access time updates (`noatime` implies `nodiratime`)     |
| `inode64`      | Support >16TB files (default on modern XFS)                             |
| `logbufs=8`    | More log buffers can improve performance under heavy metadata load      |
| `logbsize=64k` | Larger log buffer size can help with large transactions                 |
| `noquota`      | Disable quota checks (not needed if not using XFS quotas)               |

- [ ] **Add or update fstab entries** for each drive:

  ```text
  /dev/vdb1 /disk1 xfs noatime,allocsize=1m 0 0
  /dev/vdc1 /disk2 xfs noatime,allocsize=1m 0 0
  /dev/vdd1 /disk3 xfs noatime,allocsize=1m 0 0
  /dev/vde1 /disk4 xfs noatime,allocsize=1m 0 0
  /dev/vdf1 /disk5 xfs noatime,allocsize=1m 0 0
  ```

  The trailing `0 0` are for dump and fsck order (`fs_passno`):

  `fs_passno`:
    - 0 means "do not fsck". XFS with journaling rarely needs boot-time fsck, and checking
  22TB drives at boot would add significant startup delay. This setting also avoids
  potential hangs if fsck cannot resolve an issue without human intervention.
    - 1 means "check first" and is reserved for the root filesystem.
    - 2 means "check after root" and is standard for data drives. Use this instead of 0 if
  you want periodic fsck checks at boot (e.g. every 30 mounts via tune2fs on ext4; XFS
  doesn't use mount-count-based fsck).

  > These options are **safe for existing data**. They only change how the kernel
  > interacts with the filesystem going forward; no data rewrite occurs.

- [ ] **Create SeaweedFS data directories** on each drive:

  ```bash
  mkdir -p /disk{1,2,3,4,5}/{data,idx}
  ```

- [ ] **Remount all drives** (non-disruptive — active processes continue; the new mount
  options take effect):

  ```bash
  mount -o remount /disk1
  mount -o remount /disk2
  mount -o remount /disk3
  mount -o remount /disk4
  mount -o remount /disk5
  ```

  Or reboot (cleaner verification that fstab is correct):

  ```bash
  mount -a
  ```

- [ ] **Verify mount options are applied**:

  ```bash
  mount | grep /disk
  # Confirm noatime,nodiratime,allocsize=1m appear in the options column
  ```

- [ ] **Verify disk space**:

  ```bash
  df -h | grep /disk
  ```

- [ ] **Set ulimit** (open file limit):

  ```bash
  echo "* soft nofile 102400" >> /etc/security/limits.conf
  echo "* hard nofile 102400" >> /etc/security/limits.conf
  ulimit -n 102400
  ```

  SeaweedFS can open many network connections under load. Default 1024 is insufficient.
  See the [Optimization wiki
  page](https://github.com/seaweedfs/seaweedfs/wiki/Optimization#increase-user-open-file-limit)
  for details.
- [ ] **Disable swap** or set `vm.swappiness=1` in `/etc/sysctl.conf` — prevents the
  kernel from swapping out SeaweedFS processes under memory pressure:

  ```bash
  echo "vm.swappiness=1" >> /etc/sysctl.conf
  echo "vm.vfs_cache_pressure=50" >> /etc/sysctl.conf
  sysctl -p
  ```

  See the [Linux kernel VM
  documentation](https://www.kernel.org/doc/html/latest/admin-guide/sysctl/vm.html) for
  the rationale behind swappiness tuning. SeaweedFS benefits from keeping page cache hot
  for frequently accessed volume indexes.
- [ ] **Optimize network** (if applicable): net.core.somaxconn, net.ipv4.tcp_tw_reuse
- [ ] **Install Docker Engine** — follow the [official Docker install
  guide](https://docs.docker.com/engine/install/) for your distribution.
- [ ] **Install Docker Compose** (v2 plugin or standalone binary) — see [Docker Compose
  install docs](https://docs.docker.com/compose/install/).
- [ ] **Create Docker network** for SeaweedFS:

  ```bash
  docker network create sds-gateway-prod-seaweedfs-net
  ```

##### Why XFS Settings Matter

The XFS mount options and mkfs parameters above are tuned for large sequential I/O
patterns typical of SeaweedFS volume files. In particular:

| Setting              | Effect                                                                                                      |
| -------------------- | ----------------------------------------------------------------------------------------------------------- |
| `noatime`            | Eliminates metadata writes on reads, including directory atime (`nodiratime` is implied on kernels ≥2.6.30) |
| `allocsize=1m`       | Hints XFS to allocate 1MB extents — matches SeaweedFS volume chunk patterns                                 |
| `agcount=4`          | (mkfs option, not mount) More allocation groups = better parallel allocation under concurrent writes        |
| Volume Preallocation | Master flag `-volumePreallocate` on XFS gives contiguous block allocation, reduces fragmentation            |

See the [Optimization wiki
page](https://github.com/seaweedfs/seaweedfs/wiki/Optimization#preallocate-volume-file-disk-spaces)
for details on `-volumePreallocate` and XFS support.

---

## Core Service Configuration

### 2. Security Configuration

- [ ] **Generate `security.toml` scaffold**:

  ```bash
  docker run --rm docker.io/chrislusf/seaweedfs:4.32_large_disk_full weed scaffold -config=security > security.toml
  ```

- [ ] **Set JWT signing key for volume writes** — prevents unauthorized writes to volume
  servers:

  ```bash
  WEED_JWT_SIGNING_KEY=$(openssl rand -hex 32)
  ```

- [ ] **Set JWT signing key for filer writes** — secures filer HTTP write endpoints:

  ```bash
  WEED_JWT_FILER_SIGNING_KEY=$(openssl rand -hex 32)
  ```

- [ ] **Set SSE-S3 KEK** — required if S3 clients send `x-amz-server-side-encryption:
  AES256`:

  ```bash
  WEED_S3_SSE_KEK=$(openssl rand -hex 32)
  ```

  All S3 API servers must use the same KEK value.
- [ ] **Create `.env` file** — Docker Compose [reads variables from a `.env`
  file](https://docs.docker.com/compose/environment-variables/env-file/) in the same
  directory as `compose.yaml`. Variable names in `.env` are plain (e.g.
  `JWT_SIGNING_KEY`), referenced in the compose file as `${JWT_SIGNING_KEY}`. Add these
  secrets (do NOT commit `.env` to Git):

  ```ini
  # JWT signing key for volume write authorization.
  # Master signs JWTs during /dir/assign; volume servers validate them on write.
  # Generate: openssl rand -hex 32
  JWT_SIGNING_KEY=<value>

  # JWT signing key for filer HTTP write/read authorization.
  # S3 gateway generates these JWTs; filer validates them.
  # Generate: openssl rand -hex 32
  JWT_FILER_SIGNING_KEY=<value>

  # SSE-S3 Key Encryption Key (KEK).
  # Required if S3 clients send x-amz-server-side-encryption: AES256.
  # All S3 API servers in the cluster must use the same value.
  # Generate: openssl rand -hex 32
  S3_SSE_KEK=<value>

  # Grafana admin password.
  GRAFANA_PASSWORD=<choose a strong password>
  ```

- [ ] **Store secrets in a vault/password manager** (Bitwarden, 1Password, pass, etc.)

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

Create `compose.yaml`:

> **Port allocation**: 5 volume servers on ports 8081-8085 (leaving 8080 free if
> needed).
>
> **Image tag choice**: `4.32_large_disk_full` is used for SeaweedFS because:
>
> - `large_disk` variant supports larger volume indexes without memory issues — critical
>     for 22TB drives where default 30GB volumes are not performance-optimal and you may
>     want fewer, larger volumes (e.g. 100GB+).
> - `full` variant includes all optional backends (rclone, MySQL, Postgres, etc.),
>     avoiding surprises if you later need cloud tiering or migrate the filer store.
> - `4.32` (minimal) omits these — it would work but limits future options.
> - Pinning to a specific version instead of `latest` ensures reproducibility: `latest`
>     can change on rebuild and break your deployment.

```yaml
x-logging: &default-logging
  driver: "json-file"
  options:
    max-size: "100m"
    max-file: "3"

networks:
  sds-gateway-prod-seaweedfs-net:
    external: true

volumes:
  prometheus-data:
  grafana-data:

services:
  master:
    image: docker.io/chrislusf/seaweedfs:4.32_large_disk_full
    container_name: seaweedfs-master
    restart: unless-stopped
    networks:
      - sds-gateway-prod-seaweedfs-net
    ports:
      - "9333:9333"
      - "19333:19333"
    environment:
      # JWT key for volume write auth — master signs, volume servers validate
      WEED_JWT_SIGNING_KEY: "${JWT_SIGNING_KEY}"
    volumes:
      - /data/seaweedfs/master:/data
    logging: *default-logging
    command: |
      master
      -mdir=/data
      -ip=master
      -port=9333
      -volumePreallocate
      -volumeSizeLimitMB=30000
      -master.metrics.address=http://pushgateway:9091

  # 5 volume servers — one per XFS drive
  volume1:
    image: docker.io/chrislusf/seaweedfs:4.32_large_disk_full
    container_name: seaweedfs-volume1
    restart: unless-stopped
    networks:
      - sds-gateway-prod-seaweedfs-net
    ports:
      - "8081:8081"
      - "18081:18081"
    environment:
      # JWT key to validate volume write tokens issued by master
      WEED_JWT_SIGNING_KEY: "${JWT_SIGNING_KEY}"
    volumes:
      - /disk1/data:/data
      - /disk1/idx:/idx
    logging: *default-logging
    command: |
      volume
      -master=master:9333
      -ip=volume1
      -port=8081
      -max=0
      -dir=/data
      -dir.idx=/idx
      -index=leveldb
      -dataCenter=dc1
      -rack=rack1
      -compactionMBps=40
      -minFreeSpacePercent=7

  volume2:
    image: docker.io/chrislusf/seaweedfs:4.32_large_disk_full
    container_name: seaweedfs-volume2
    restart: unless-stopped
    networks:
      - sds-gateway-prod-seaweedfs-net
    ports:
      - "8082:8082"
      - "18082:18082"
    environment:
      # JWT key to validate volume write tokens issued by master
      WEED_JWT_SIGNING_KEY: "${JWT_SIGNING_KEY}"
    volumes:
      - /disk2/data:/data
      - /disk2/idx:/idx
    logging: *default-logging
    command: |
      volume
      -master=master:9333
      -ip=volume2
      -port=8082
      -max=0
      -dir=/data
      -dir.idx=/idx
      -index=leveldb
      -dataCenter=dc1
      -rack=rack1
      -compactionMBps=40
      -minFreeSpacePercent=7

  volume3:
    image: docker.io/chrislusf/seaweedfs:4.32_large_disk_full
    container_name: seaweedfs-volume3
    restart: unless-stopped
    networks:
      - sds-gateway-prod-seaweedfs-net
    ports:
      - "8083:8083"
      - "18083:18083"
    environment:
      # JWT key to validate volume write tokens issued by master
      WEED_JWT_SIGNING_KEY: "${JWT_SIGNING_KEY}"
    volumes:
      - /disk3/data:/data
      - /disk3/idx:/idx
    logging: *default-logging
    command: |
      volume
      -master=master:9333
      -ip=volume3
      -port=8083
      -max=0
      -dir=/data
      -dir.idx=/idx
      -index=leveldb
      -dataCenter=dc1
      -rack=rack1
      -compactionMBps=40
      -minFreeSpacePercent=7

  volume4:
    image: docker.io/chrislusf/seaweedfs:4.32_large_disk_full
    container_name: seaweedfs-volume4
    restart: unless-stopped
    networks:
      - sds-gateway-prod-seaweedfs-net
    ports:
      - "8084:8084"
      - "18084:18084"
    environment:
      # JWT key to validate volume write tokens issued by master
      WEED_JWT_SIGNING_KEY: "${JWT_SIGNING_KEY}"
    volumes:
      - /disk4/data:/data
      - /disk4/idx:/idx
    logging: *default-logging
    command: |
      volume
      -master=master:9333
      -ip=volume4
      -port=8084
      -max=0
      -dir=/data
      -dir.idx=/idx
      -index=leveldb
      -dataCenter=dc1
      -rack=rack1
      -compactionMBps=40
      -minFreeSpacePercent=7

  volume5:
    image: docker.io/chrislusf/seaweedfs:4.32_large_disk_full
    container_name: seaweedfs-volume5
    restart: unless-stopped
    networks:
      - sds-gateway-prod-seaweedfs-net
    ports:
      - "8085:8085"
      - "18085:18085"
    environment:
      # JWT key to validate volume write tokens issued by master
      WEED_JWT_SIGNING_KEY: "${JWT_SIGNING_KEY}"
    volumes:
      - /disk5/data:/data
      - /disk5/idx:/idx
    logging: *default-logging
    command: |
      volume
      -master=master:9333
      -ip=volume5
      -port=8085
      -max=0
      -dir=/data
      -dir.idx=/idx
      -index=leveldb
      -dataCenter=dc1
      -rack=rack1
      -compactionMBps=40
      -minFreeSpacePercent=7

  filer:
    image: docker.io/chrislusf/seaweedfs:4.32_large_disk_full
    container_name: seaweedfs-filer
    restart: unless-stopped
    depends_on:
      - master
    networks:
      - sds-gateway-prod-seaweedfs-net
    ports:
      - "8888:8888"
      - "18888:18888"
    environment:
      # JWT key for volume write auth — passed through from master
      WEED_JWT_SIGNING_KEY: "${JWT_SIGNING_KEY}"
      # JWT key for filer HTTP write auth — S3 gateway signs, filer validates
      WEED_JWT_FILER_SIGNING_KEY: "${JWT_FILER_SIGNING_KEY}"
    volumes:
      - /data/seaweedfs/filer:/data
      - ./filer.toml:/etc/seaweedfs/filer.toml:ro
    logging: *default-logging
    command: |
      filer
      -master=master:9333
      -ip=filer
      -port=8888
      -encryptVolumeData=false
      -maxMB=32

  s3:
    image: docker.io/chrislusf/seaweedfs:4.32_large_disk_full
    container_name: seaweedfs-s3
    restart: unless-stopped
    depends_on:
      - filer
    networks:
      - sds-gateway-prod-seaweedfs-net
    ports:
      - "8333:8333"
    environment:
      # JWT key for signing filer HTTP requests — must match filer's WEED_JWT_FILER_SIGNING_KEY
      WEED_JWT_FILER_SIGNING_KEY: "${JWT_FILER_SIGNING_KEY}"
      # SSE-S3 Key Encryption Key — required when clients send x-amz-server-side-encryption: AES256
      WEED_S3_SSE_KEK: "${S3_SSE_KEK}"
    volumes:
      - ./s3-config.json:/etc/seaweedfs/s3.json:ro
    logging: *default-logging
    command: |
      s3
      -filer=filer:8888
      -port=8333
      -config=/etc/seaweedfs/s3.json
      -domain=.s3.example.com

  # Admin server + worker for Erasure Coding and cluster maintenance
  admin:
    image: docker.io/chrislusf/seaweedfs:4.32_large_disk_full
    container_name: seaweedfs-admin
    restart: unless-stopped
    depends_on:
      - master
    networks:
      - sds-gateway-prod-seaweedfs-net
    ports:
      - "23646:23646"
    logging: *default-logging
    command: |
      admin
      -master=master:9333

  worker:
    image: docker.io/chrislusf/seaweedfs:4.32_large_disk_full
    container_name: seaweedfs-worker
    restart: unless-stopped
    depends_on:
      - admin
    networks:
      - sds-gateway-prod-seaweedfs-net
    logging: *default-logging
    command: |
      worker
      -admin=admin:23646

  prometheus:
    image: docker.io/prom/prometheus:v2.53.0
    container_name: seaweedfs-prometheus
    restart: unless-stopped
    networks:
      - sds-gateway-prod-seaweedfs-net
    ports:
      - "9090:9090"
    volumes:
      - prometheus-data:/prometheus
      - ./prometheus.yaml:/etc/prometheus/prometheus.yaml:ro
    command:
      - "--config.file=/etc/prometheus/prometheus.yaml"
      - "--storage.tsdb.path=/prometheus"

  pushgateway:
    image: docker.io/prom/pushgateway:v1.9.0
    container_name: seaweedfs-pushgateway
    restart: unless-stopped
    networks:
      - sds-gateway-prod-seaweedfs-net
    ports:
      - "9091:9091"

  grafana:
    image: docker.io/grafana/grafana:11.1.0
    container_name: seaweedfs-grafana
    restart: unless-stopped
    networks:
      - sds-gateway-prod-seaweedfs-net
    ports:
      - "3000:3000"
    environment:
      GF_SECURITY_ADMIN_PASSWORD: "${GRAFANA_PASSWORD}"
    volumes:
      - grafana-data:/var/lib/grafana
```

- [ ] **Create `filer.toml`** for leveldb2 store (default — file may be empty or
  scaffolded):

  ```bash
  docker run --rm docker.io/chrislusf/seaweedfs:4.32_large_disk_full weed scaffold -config=filer > filer.toml
  ```

- [ ] **Create `prometheus.yaml`** with pushgateway as a target (see section 5 for
  contents)
- [ ] **Set `${GRAFANA_PASSWORD}`** in the same `.env` file (Compose substitutes it into
  the `grafana` service)
- [ ] **Create directories**:

  ```bash
  mkdir -p /data/seaweedfs/{master,filer}
  ```

#### Why 5 Separate Volume Servers Instead of One With 5 Dirs

| Approach                             | Pros                                                                                                                       | Cons                                                      |
| ------------------------------------ | -------------------------------------------------------------------------------------------------------------------------- | --------------------------------------------------------- |
| 5 separate volume servers            | Each drive independent; replacing a failed drive = stop one container; cleaner metrics per-drive; easier to move/rebalance | More containers; more ports                               |
| 1 server with 5 comma-separated dirs | Simpler; fewer ports                                                                                                       | Opaque per-drive health; harder to replace a single drive |

For EC, separate volume servers are equally important. The EC shard placement algorithm
spreads the 14 shards (10 data + 4 parity) across available volume servers. With 5
separate servers (drives), shards are naturally distributed across all drives,
maximizing failure tolerance. A single volume server with 5 dirs is seen as one node by
the EC placement algorithm — losing that one node means losing the volume entirely,
defeating the purpose of EC.

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

- [ ] **Create `s3-config.json`** with an empty identities array — no hardcoded
  credentials. Credentials are set exclusively at deploy time via `deploy.sh`:

  ```json
  {"identities": []}
  ```

- [ ] **S3 credentials** are configured at deploy time by `deploy.sh` using
  `weed shell s3.configure`. Values are read from the `storage.env` file
  (`PRIMARY_ACCESS_KEY_ID`, `PRIMARY_SECRET_ACCESS_KEY`, etc.). The
  `validate_production_credentials()` function in `deploy.sh` prevents accidental
  use of well-known or short keys in production by checking:
    - Access key is not the well-known `admin-access-key` or `backup-access-key`
    - Access key is at least 16 characters
    - Secret key is at least 16 characters
- [ ] **Admin actions** allow bucket creation/deletion. Avoid giving `Admin` to everyday
  users.
- [ ] **Test S3 access**:

  ```bash
  aws s3 --endpoint http://localhost:8333 ls
  aws s3 --endpoint http://localhost:8333 mb s3://test-bucket
  aws s3 --endpoint http://localhost:8333 cp /etc/hostname s3://test-bucket/
  ```

#### S3 Encryption Note

If your S3 clients send `x-amz-server-side-encryption: AES256`, the SSE-S3 KEK must be
configured (already done in step 2). Without it, these requests fail with `400 Bad
Request`.

---

## Operations & Maintenance

### 5. Monitoring — Prometheus + Grafana

- [ ] **Start Prometheus pushgateway** (included in compose as `pushgateway` service)
- [ ] **Master** configured with `-master.metrics.address=http://pushgateway:9091` — all
  other components (volume, filer) inherit this from master's heartbeat and push their
  own metrics.
- [ ] **Configure Prometheus** to scrape the pushgateway:

  ```yaml
  # prometheus.yaml
  global:
    scrape_interval: 15s

  scrape_configs:
    - job_name: "seaweedfs-pushgateway"
      honor_labels: true
      static_configs:
        - targets: ["pushgateway:9091"]
  ```

- [ ] **Import Grafana dashboard** from upstream:

  ```bash
  # Download the dashboard JSON from the SeaweedFS repo
  curl -o grafana-seaweedfs.json \
    https://raw.githubusercontent.com/seaweedfs/seaweedfs/master/other/metrics/grafana_seaweedfs.json
  ```

    - Login to Grafana at `http://<host>:3000` (default admin/admin)
    - Create Prometheus datasource pointing to `http://prometheus:9090`
    - Import `grafana-seaweedfs.json`
- [ ] **Set up alerting** in Grafana for:
    - Volume server down (heartbeat missing)
    - Free volume count = 0 (cluster full)
    - High compaction backlog
    - Disk space < 10% on any volume drive

#### Push vs Pull Metrics

SeaweedFS components push metrics to the pushgateway. This is simpler than configuring
Prometheus to discover dynamic volume server targets. The pushgateway is a lightweight
bridge.

---

### 6. Backup to MinIO via Async Filer Backup

- [ ] **Create backup access key** in your MinIO deployment (via mc or MinIO console)
  with write permissions to a dedicated backup bucket.
- [ ] **Generate `replication.toml`**:

  ```bash
  docker run --rm docker.io/chrislusf/seaweedfs:4.32_large_disk_full weed scaffold -config=replication > replication.toml
  ```

- [ ] **Edit `replication.toml`** to configure the S3 sink targeting your MinIO:

  ```toml
  [sink.s3]
  enabled = true
  aws_access_key_id = "minio-backup-access-key"
  aws_secret_access_key = "minio-backup-secret-key"
  region = "us-east-1"                   # can be anything for MinIO
  bucket = "spectrumx"            # existing bucket in MinIO
  directory = "/spectrumx"        # prefix inside the bucket
  endpoint = "https://minio.example.com" # your MinIO endpoint URL
  is_incremental = false                 # false = continuous mirroring
  ```

- [ ] **Create the backup bucket** in MinIO:

  ```bash
  mc mb --ignore-existing "sds-backup-minio/spectrumx"
  ```

- [ ] **Start backup** as an additional Docker service or standalone process:

  ```yaml
  # Add to compose.yaml
  filer-backup:
    image: docker.io/chrislusf/seaweedfs:4.32_large_disk_full
    container_name: seaweedfs-filer-backup
    restart: unless-stopped
    depends_on:
      - filer
    networks:
      - sds-gateway-prod-seaweedfs-net
    volumes:
      - ./replication.toml:/etc/seaweedfs/replication.toml:ro
    command: |
      filer.backup
      -filer=filer:8888
      -config=/etc/seaweedfs/replication.toml
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
weed backup -server=master:9333 -dir=/backup -volumeId=<id>
```

This is useful for bootstrapping a second cluster but is not continuous.

---

### 7. Startup & Verification

- [ ] **Start all services**:

  ```bash
  docker compose up -d
  ```

- [ ] **Verify cluster status** via master UI:

  ```bash
  curl http://localhost:9333/  # or open in browser
  ```

    - Check that all 5 volume servers appear
    - Check that Free volume count > 0
- [ ] **Verify volume servers**:

  ```bash
  curl http://localhost:8081/   # repeat for 8082-8085
  ```

- [ ] **Verify filer**:

  ```bash
  curl http://localhost:8888/
  ```

- [ ] **Verify S3 gateway**:

  ```bash
  aws s3 --endpoint http://localhost:8333 ls
  ```

- [ ] **Trigger volume allocation** to test write path:

  ```bash
  curl "http://localhost:9333/dir/assign"
  ```

- [ ] **Run the SeaweedFS benchmark** from within the Docker network:

  ```bash
  docker run --rm --network sds-gateway-prod-seaweedfs-net docker.io/chrislusf/seaweedfs:4.32_large_disk_full \
    weed benchmark -master=master:9333 -n 10000
  ```

- [ ] **Verify Prometheus targets** — check pushgateway at `http://localhost:9091`
- [ ] **Verify Grafana dashboard** — open at `http://localhost:3000`, check for data

#### Smoke Test: Drive Failure Scenario

Simulate a drive failure to verify EC durability:

```bash
# Stop one volume server (simulate drive failure)
docker stop seaweedfs-volume1

# Verify data is still accessible via S3/filer
aws s3 --endpoint http://localhost:8333 ls s3://test-bucket/ --recursive
# Read a file to confirm EC reconstruction works
aws s3 --endpoint http://localhost:8333 cp s3://test-bucket/test-file /tmp/test-file

# Check EC shard status via weed shell
docker exec seaweedfs-master weed shell -c "ec.balance"

# Restart the volume server (simulate drive replacement)
docker start seaweedfs-volume1

# After restart, rebalance EC shards to restore optimal distribution
docker exec seaweedfs-master weed shell -c "ec.balance -apply"
```

---

### 8. Volume Growth Tuning

With EC and no replication (`copy_1`), the default growth strategy creates **7 writable
volumes** initially. As these fill up and get EC-encoded, new volumes are automatically
created. Given 22TB drives, this is more than sufficient.

If you need more write concurrency (more simultaneous write streams), pre-create
additional volumes:

```bash
docker run --rm docker.io/chrislusf/seaweedfs:4.32_large_disk_full weed scaffold -config=master > master.toml
```

Edit and mount to master:

```toml
[master.volume_growth]
copy_1 = 16    # 16 writable volumes for no-replication (more write concurrency)
threshold = 0.9
```

**Volume size tuning**: With 22TB drives, the default 30GB volume size means ~733
volumes per drive. With LevelDB mode (`-index=leveldb`), each volume's index occupies
roughly 20-40MB of **disk space** in the `idx` directory (~15-30GB total per drive on
disk). The LevelDB block cache RAM footprint remains fixed at ~4MB per volume server
regardless of volume count — this is the key advantage of LevelDB over memory mode. See
the [Optimization wiki
page](https://github.com/seaweedfs/seaweedfs/wiki/Optimization#use-leveldb) for details
on index types and memory usage.

```text
- volumeSizeLimitMB=100000   # 100GB volumes → ~220 per drive
```

---

### 9. Maintenance Plan

#### Daily / Automated

- [ ] **Admin script plugin** — the `admin` and `worker` Docker services (already in
  `compose.yaml`) automatically run these maintenance tasks. Verify they are running:

  ```bash
  docker ps | grep seaweedfs-admin
  docker ps | grep seaweedfs-worker
  ```

  Default script covers:
    - `ec.balance -apply` — balance EC shards
    - `fs.log.purge -daysAgo=7` — purge old filer logs
    - `volume.deleteEmpty -quietFor=24h -apply` — delete empty volumes
    - `volume.fix.replication -apply` — fix missing replicas
    - `s3.clean.uploads -timeAgo=24h` — clean aborted S3 multipart uploads

- [ ] **Monitor disk usage** on all 5 drives. Alert when any drive exceeds 85% usage.

#### Weekly

- [ ] **Check `weed shell` status**:

  ```bash
  docker exec seaweedfs-master weed shell -c "volume.status"
  docker exec seaweedfs-master weed shell -c "volume.list"
  ```

#### Monthly

- [ ] **Run full cluster health check**:

  ```bash
  weed shell -c "volume.fsck"
  weed shell -c "volume.check.disk"
  ```

- [ ] **Review Grafana dashboards** for trends: compaction rates, write amplification,
  disk growth
- [ ] **Verify backup is running** — check that MinIO bucket has recent files

#### Erasure Coding (Always Active)

EC is the **primary durability mechanism** for this deployment, not an afterthought. The
`erasure_coding` plugin worker runs automatically inside the `worker` container and
continuously converts full/quiet volumes to RS(10,4) EC shards.

**Detection defaults** (configurable from admin UI at `/plugin`):

- Fullness ratio threshold: 80%
- Quiet period: 300 seconds (5 minutes)
- Minimum volume size: 30 MB
- Scan interval: 5 minutes

**What to watch for:**

- Ensure the `worker` container is always running — if it stops, volumes will sit at
  `000` replication (single copy) indefinitely.
- If the cluster runs low on free volume IDs, pre-create volumes manually with `curl
  http://localhost:9333/vol/grow?count=10`.
- Monitor `ec.balance` shard distribution in Grafana after drive replacements.

#### Drive Replacement Procedure

When a drive fails with EC, the procedure differs from a replication-based setup. There
are no volume replicas to "fix" — instead, the surviving EC shards on other drives can
reconstruct missing data once the replacement drive is online.

1. **Do NOT stop the volume container yet** — the volume server may still serve reads
   from its surviving shards (depending on failure mode). Only stop it if the drive is
   fully dead/unresponsive.

2. If the drive is still partially readable, mark maintenance mode:

    ```bash
    docker exec seaweedfs-master weed shell -c "volumeServer.state --nodes volume1:8081 --maintenanceOn"
    ```

3. Replace the physical drive, mkfs.xfs, mount, recreate directory structure:

    ```bash
    # if the drive is new/empty, format with XFS and recommended options for SeaweedFS:
    mkfs.xfs -f -d agcount=4 -l size=128m -n size=8192 /dev/vdb1   # replace with actual new drive

    # if the filesystem already exists (e.g. replaced drive with pre-formatted data):
    #   - check geometry is adequate:
    #     xfs_info /dev/vdb1        (see Track B in §1 for what to look for)
    #   - verify/add fstab entry then mount:
    #     echo '/dev/vdb1 /disk1 xfs noatime,nodiratime,nobarrier,allocsize=1m 0 2' >> /etc/fstab
    #     mount /disk1

    mkdir -p /disk1/{data,idx}
    ```

4. Start the container on the new drive:

    ```bash
    docker start seaweedfs-volume1
    ```

5. **Rebalance EC shards** — the `ec.balance` command detects that some shards are
   missing from the replacement server and moves/reconstructs shards to restore optimal
   distribution:

   ```bash
   docker exec seaweedfs-master weed shell -c "ec.balance -apply"
   ```

   This may take time depending on how many EC volumes need shard reconstruction.
   Monitor progress via the admin UI or Grafana.

6. Re-run volume server state check:

   ```bash
   docker exec seaweedfs-master weed shell -c "volumeServer.state"
   ```

7. Turn off maintenance mode if it was enabled:

   ```bash
   docker exec seaweedfs-master weed shell -c "volumeServer.state --nodes volume1:8081 --maintenanceOff"
   ```

**Note:** Unlike replication (`volume.fix.replication`), EC shard reconstruction
rebuilds only the missing shards from the parity data on surviving drives. This is
network-efficient but computationally intensive (Reed-Solomon encoding). Monitor CPU on
the worker/admin containers during reconstruction.

---

## Appendices

### Appendix A: Volume Size Calculation

| Drive count | Data durability | Volume size | Volumes per drive | Raw storage | Usable capacity |
| ----------- | --------------- | ----------- | ----------------- | ----------- | --------------- |
| 5 × 22TB    | RS(10,4) EC     | 30GB        | ~733 per drive    | 110TB       | ~74.5TB         |
| 5 × 22TB    | RS(10,4) EC     | 100GB       | ~220 per drive    | 110TB       | ~74.5TB         |

**Formula**: `usable = (total_raw / 1.4) × 0.95` (RS 10+4 = 1.4× raw overhead; ~5% for
XFS filesystem overhead, index files, and compaction temp space)

RS(10,4) Erasure Coding: for every 10 data shards, 4 parity shards are created — 14
total. This means 1.4× raw storage consumption vs 2× for `001` replication or 3× for
`002` replication.

| Method          | Raw:Usable ratio | Usable from 110TB raw | # disk failures w/o data loss |
| --------------- | ---------------- | --------------------- | ----------------------------- |
| No redundancy   | 1:1              | 107.8TB               | 0 / 5                         |
| EC RS(10,4)     | 1.4:1            | ~74.5TB               | 2 / 5                         |
| Replication 001 | 2:1              | ~52.3TB               | 1 / 5                         |
| Replication 002 | 3:1              | ~34.8TB               | 2 / 5                         |

### Appendix B: Port Reference

| Service         | HTTP Port | gRPC Port |
| --------------- | --------- | --------- |
| Master          | 9333      | 19333     |
| Volume 1        | 8081      | 18081     |
| Volume 2        | 8082      | 18082     |
| Volume 3        | 8083      | 18083     |
| Volume 4        | 8084      | 18084     |
| Volume 5        | 8085      | 18085     |
| Filer           | 8888      | 18888     |
| S3              | 8333      | —         |
| Prometheus      | 9090      | —         |
| Pushgateway     | 9091      | —         |
| Grafana         | 3000      | —         |
| Admin (if used) | 23646     | —         |

### Appendix C: Recommended Environment `.env` File

This file lives **in the same directory as `compose.yaml`**. Docker Compose reads it
automatically when you run `docker compose up`. Variable names are plain — Compose
substitutes them when referenced as `${VAR_NAME}` in the YAML.

```text
JWT_SIGNING_KEY=<openssl rand -hex 32>
JWT_FILER_SIGNING_KEY=<openssl rand -hex 32>
S3_SSE_KEK=<openssl rand -hex 32>
GRAFANA_PASSWORD=<choose a strong password>
```

**Do not commit `.env` to version control.** remember to add it to `.gitignore`.
