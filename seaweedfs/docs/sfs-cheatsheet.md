# Weed Shell Cheat Sheet

Quick reference for `weed shell` — the interactive maintenance console for SeaweedFS.

## Getting Started

```bash
# Start interactive shell
weed shell

# Pipe commands (suppresses > prompt, good for scripts)
echo "help" | weed shell

# With debug output on stderr
echo "s3.user.list" | weed shell -debug 2>shell.log | jq

# Heredoc for multi-line
weed shell << EOF
lock
volume.fix.replication
unlock
EOF
```

The `fs.` prefix is optional for all `fs.*` commands: `ls` works the same as `fs.ls`.

---

## Navigation & Listing

| Command | Description | Example |
|---------|-------------|---------|
| `fs.cd <path>` | Change directory | `fs.cd /buckets` |
| `fs.pwd` | Print working directory | `fs.pwd` |
| `fs.ls [path]` | List files in a directory | `fs.ls -al /buckets` |
| `fs.tree [path]` | **Recursively** list files + **shows count** at end | `fs.tree /buckets` |
| `fs.du [path]` | Show disk usage (blocks, bytes) | `fs.du /objects` |

### Shortcuts

```bash
ls                    # same as fs.ls
ls -al topics         # with flags
du                    # same as fs.du
du /buckets
```

---

## 📦 Object Counting

| Method | Output | Scope | Cost |
|--------|--------|-------|------|
| `fs.tree /path` | `X directories, Y files` | Recursive filer metadata | **Lightest** — no volume calls |
| `fs.ls -l /path` | `total N` (chunk count) | Single directory | Light — filer metadata only |
| `fs.meta.save /path` | `total X directories, Y files` | Recursive | Medium — serializes all entries |
| `fs.verify /path` | `total X dirs, Y files` + verified count | Recursive | Heavy — verifies chunks on volume servers |
| `collection.list` | `fileCount:N` per collection | Cluster-wide | Light — needle-level count, not logical files |
| `volume.list` | `file_count:N` per volume | Per-volume | Light — same needle-level count |

### Recommended

```bash
# Quick recursive file count (filer metadata only)
> fs.tree /buckets/my-bucket
2 directories, 2 files

# Quick single-directory count
> fs.ls -l /buckets/my-bucket
total 42

# Volume-level needle (chunk) count
> collection.list
  collection       fileCount
  my-bucket        678
```

---

## File Operations

| Command | Description | Example |
|---------|-------------|---------|
| `fs.cat <path>` | Stream file content to stdout | `fs.cat /buckets/log.txt` |
| `fs.rm <path>` | Remove file or directory | `fs.rm /buckets/old.log` |
| `fs.mv <src> <dst>` | Move/rename | `fs.mv /a/file /b/file` |
| `fs.mkdir <path>` | Create directory | `fs.mkdir /buckets/new` |
| `fs.meta.cat <path>` | Print file/dir metadata as JSON | `fs.meta.cat /buckets/file.log` |

---

## Filer Metadata Backup & Restore

| Command | Description |
|---------|-------------|
| `fs.meta.save <path>` | Save filer metadata to a local file |
| `fs.meta.load <path>` | Restore directory/file structure from saved metadata |
| `fs.meta.notify <path>` | Send metadata to notification message queue |
| `fs.meta.changeVolumeId <old> <new>` | Change volume ID in existing metadata |

---

## Volume Management

| Command | Description |
|---------|-------------|
| `volume.list` | List all volumes across the cluster |
| `volume.grow` | Grow (create new) volumes |
| `volume.balance [-force]` | Generate (and execute with `-force`) a volume balancing plan |
| `volume.fix.replication [-n]` | Fix under/over-replicated volumes (`-n` = dry run) |
| `volume.vacuum` | Compact volumes (remove deleted entries) |
| `volume.vacuum.disable` | Disable auto-vacuum from master |
| `volume.vacuum.enable` | Re-enable auto-vacuum |
| `volume.delete <volumeId>` | Delete a live volume |
| `volume.deleteEmpty` | Delete empty volumes from all servers |
| `volume.mark <volumeId> <node>` | Mark volume writable or readonly |
| `volume.mount <volumeId> <node>` | Mount a volume |
| `volume.unmount <volumeId> <node>` | Unmount a volume |
| `volume.copy <volumeId> <srcNode> <dstNode>` | Copy a volume between servers |
| `volume.move <volumeId> <srcNode> <dstNode>` | Move a volume between servers |
| `volume.check.disk [-apply] [-slow]` | Check replicated volumes for inconsistencies |
| `volume.fsck [-findMissingChunksInFiler]` | Find filer entries with no chunks on volume servers |
| `volume.scrub` | Scrub volume contents on volume servers |
| `volume.configure.replication <volumeId> <replication>` | Change replication value for a volume |
| `volume.tier.upload <volumeId>` | Upload .dat file to remote tier |
| `volume.tier.download <volumeId>` | Download .dat file from remote tier |
| `volume.tier.move <volumeId> <diskType>` | Move volume to different disk type |

### Typical workflow

```text
> lock
> volume.fix.replication
> volume.balance -force
> unlock
```

### Volume Server State

```text
> volumeServer.state
> volumeServer.state --nodes 192.168.10.111:9009 --maintenanceOn
> volumeServer.evacuate <node>
> volumeServer.leave <node>
```

### Collection Management

```text
> collection.list
> collection.delete <name>
```

---

## 🔒 Locking for Exclusive Operations

Some volume operations require exclusive cluster access:

```bash
> lock          # acquire cluster-wide lock
> unlock        # release lock

# Scripted:
echo "lock; volume.fix.replication; unlock" | weed shell
```

---

## Erasure Coding

| Command | Description |
|---------|-------------|
| `ec.encode [-force]` | Apply erasure coding to volumes |
| `ec.decode <volumeId>` | Decode an EC volume back to a normal volume |
| `ec.rebuild` | Find and rebuild missing EC shards |
| `ec.balance [-apply]` | Balance EC shards across racks/servers |
| `ec.scrub [-mode checksum]` | Scrub EC volumes for bitrot |

```bash
ec.scrub -mode checksum
ec.scrub -mode checksum -volumeId 7 -node 127.0.0.1:8080
```

---

## Cluster Management

| Command | Description |
|---------|-------------|
| `cluster.status` | Quick overview of cluster status |
| `cluster.ps` | Check cluster process status |
| `cluster.check` | Check network connectivity between nodes |
| `cluster.raft.ps` | Check Raft cluster status |
| `cluster.raft.add <server>` | Add server to Raft cluster |
| `cluster.raft.remove <server>` | Remove server from Raft cluster |
| `cluster.raft.transferLeader <server>` | Transfer Raft leadership |

---

## S3 IAM Management

### Users

```text
> s3.user.create -name alice
> s3.user.list
> s3.user.show -name alice
> s3.user.disable -name alice
> s3.user.enable -name alice
> s3.user.delete -name alice
> s3.user.provision -name alice -bucket photos -role readwrite   # one-step create + policy
```

### Access Keys

```text
> s3.accesskey.create -user alice
> s3.accesskey.list -user alice
> s3.accesskey.rotate -user alice -access_key AKID...
> s3.accesskey.delete -user alice -access_key AKID...
```

### Policies

```text
> s3.policy -put -name=photos-rw -file=photos-policy.json
> s3.policy.attach -policy photos-rw -user alice
> s3.policy.detach -policy photos-rw -user alice
```

### Buckets

```text
> s3.bucket.create -name my-bucket
> s3.bucket.list
> s3.bucket.delete -name my-bucket
> s3.bucket.lock -name my-bucket                    # view/enable Object Lock
> s3.bucket.owner -name my-bucket -owner alice       # view/change owner
> s3.bucket.quota -bucket my-bucket -quota 1GB       # set quota
> s3.bucket.quota.enforce                             # enforce quotas cluster-wide
```

### Anonymous Access

```text
> s3.anonymous.set -bucket photos -access Read,List
> s3.anonymous.get -bucket photos
> s3.anonymous.list
```

### Service Accounts

```text
> s3.serviceaccount.create -user alice -description "CI" -actions Read,List
> s3.serviceaccount.create -user alice -expiry 24h
> s3.serviceaccount.list -user alice
> s3.serviceaccount.show -id sa:alice:<uuid>
> s3.serviceaccount.delete -id sa:alice:<uuid>
```

### IAM Backup & Restore

```text
> s3.iam.export -file iam-backup.json
> s3.iam.import -file iam-backup.json -apply
> s3.config.show
```

### Circuit Breaker (Rate Limiting)

```text
> s3.circuitBreaker -global -type count -actions Read,Write -values 500,200 -apply
> s3.circuitBreaker -buckets mybucket -type count -actions Read -values 50 -apply
> s3.circuitBreaker -global -actions Read -type count -delete -apply
```

### Multipart Upload Cleanup

```text
> s3.clean.uploads -timeAgo=24h
```

---

## S3 Tables

```text
> s3tables.bucket create my-test-bucket
> s3tables.bucket list
> s3tables.bucket delete my-test-bucket
> s3tables.namespace create my-test-bucket my-namespace
> s3tables.namespace list my-test-bucket
> s3tables.table create my-test-bucket my-namespace my-table
> s3tables.table list my-test-bucket my-namespace
> s3tables.tag set my-test-bucket environment=prod
> s3tables.tag list my-test-bucket
```

---

## Remote Storage (Cloud Tier / Cloud Drive)

```text
> remote.configure -name=cloud1 -type=s3 -s3.access_key=xxx -s3.secret_key=yyy
> remote.configure -name=cloud1 -type=gcs -gcs.appCredentialsFile=~/service-account.json
> remote.mount -dir=/mnt/cloud -remote=cloud1/bucket
> remote.mount.buckets -dir=/mnt/cloud -remote=cloud1
> remote.unmount -dir=/mnt/cloud
> remote.cache -dir=/mnt/cloud
> remote.uncache -dir=/mnt/cloud
> remote.copy.local -dir=/mnt/cloud
> remote.meta.sync -dir=/mnt/cloud

# Mount strategies:
# - metadataStrategy=sync   (default, pull all metadata upfront — fast local listing)
# - metadataStrategy=lazy   (on-demand — best for huge buckets with known paths)
```

---

## Message Queue (SMQ)

```text
> mq.topic.list
> mq.topic.create -topic <name> -partitions 6
> mq.topic.describe -topic <name>
> mq.topic.configure -topic <name> [-partitions 6] [-replication 001]
> mq.topic.compact -topic <name>
> mq.topic.truncate -topic <name>
> mq.balance
```

---

## Filer Configuration

```text
> fs.configure -locationPrefix=/buckets/foo -volumeGrowthCount=3 -replication=002 -apply
> fs.log.purge -daysAgo=7
> fs.mergeVolumes                                            # re-locate chunks to target volumes
> fs.verify -v -modifyTimeAgo 1h                             # verify chunks, prints file count
```

---

## Mount Configuration

```text
> mount.configure -mountPoint=/mnt/sfs -cacheCapacity=1024 -cacheDir=/tmp/cache -apply
```

---

## Deprecated / Legacy

```text
# These are now handled by the admin script plugin worker:
# ec.encode      → erasure_coding plugin worker
# volume.balance → volume_balance plugin worker
# See [[Worker]] for details.
```

---

## Scripting Tips

```bash
# Pipe JSON output to jq
echo "s3.user.list" | weed shell | jq '.[] | select(.keys > 0)'

# Suppress logs (automatic when piped)
echo 'fs.tree /buckets' | weed shell

# Debug mode (re-enables logs on stderr)
echo 'fs.verify' | weed shell -debug 2>shell.log

# Docker
docker run --rm \
  -e SHELL_FILER=localhost:8888 \
  -e SHELL_MASTER=localhost:9333 \
  chrislusf/seaweedfs:local \
  "shell" \
  "fs.configure -locationPrefix=/buckets/foo -volumeGrowthCount=3 -replication=002 -apply"
```

## See Also

- [Weed Shell Reference](sfs-wiki/weed-shell.md) — full command list and examples
- [Volume Management](sfs-wiki/Volume-Management.md) — maintenance workflows
- [File Operations Quick Reference](sfs-wiki/File-Operations-Quick-Reference.md) — HTTP API
- [SQL Quick Reference](sfs-wiki/SQL-Quick-Reference.md) — `weed sql` / `weed db`
