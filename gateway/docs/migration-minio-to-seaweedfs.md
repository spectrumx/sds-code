# Migration: MinIO → SeaweedFS

Runbook for migrating the gateway's object storage from MinIO to SeaweedFS (SFS).

Both stacks remain **separate compose projects**. They communicate over a shared
Docker network (`sds-network-local` for local, `sds-network-prod` for production).

---

## Prerequisites

| Tool                                | Purpose                              |
| ----------------------------------- | ------------------------------------ |
| `mc` (MinIO Client)                 | data transfer + verification         |
| Docker / Docker Compose             | running both stacks                  |
| `weed shell` (inside SFS container) | S3 credential setup, bucket creation |

Install `mc` from <https://min.io/docs/minio/linux/reference/minio-mc.html>.

---

## 1. Start both compose stacks

The gateway stack (with MinIO still running) and the SeaweedFS stack must be up at the
same time during migration.

```bash
# from gateway/
docker compose -f compose.local.yaml up -d

# from seaweedfs/
docker compose up -d
```

Verify both are healthy:

```bash
docker compose -f compose.local.yaml ps   # gateway services + minio
docker compose ps                          # seaweedfs services
```

Confirm the SFS S3 endpoint responds:

```bash
curl -s http://localhost:8333/healthz
# expected: empty 200
```

---

## 2. Configure SFS S3 credentials

SFS manages S3 credentials via `weed shell`, not environment variables.

```bash
docker compose exec sds-gateway-local-sfs-master \
  weed shell
```

Inside the shell:

```text
# create an admin identity (use real secrets in production)
s3.configure -apply \
  -user admin \
  -access_key admin \
  -secret_key admin \
  -actions Admin \
  -buckets *

# verify
s3.configure
```

For **production**, generate strong credentials and update
`gateway/.envs/production/sfs.env` accordingly:

```text
AWS_ACCESS_KEY_ID=<generated-key>
AWS_SECRET_ACCESS_KEY=<generated-secret>
```

---

## 3. Create the target bucket in SFS

Still inside `weed shell`:

```text
s3.bucket.create -name spectrumx
s3.bucket.list
```

Or from the host using `mc`:

```bash
mc alias set sfs http://localhost:8333 admin admin
mc mb sfs/spectrumx
```

---

## 4. Configure `mc` aliases

```bash
# MinIO (source)
mc alias set minio http://localhost:9000 minioadmin '<minio-secret>'

# SeaweedFS (target)
mc alias set sfs http://localhost:8333 admin admin
```

Verify connectivity:

```bash
mc ls minio/spectrumx
mc ls sfs/spectrumx
```

---

## 5. Migrate data

Mirror all objects from MinIO into SFS:

```bash
mc mirror --preserve minio/spectrumx sfs/spectrumx
```

For large datasets, consider:

```bash
# dry run first
mc mirror --preserve --dry-run minio/spectrumx sfs/spectrumx

# parallel transfer (adjust workers to available bandwidth)
mc mirror --preserve --active-active minio/spectrumx sfs/spectrumx
```

---

## 6. Verify migration

### Object count

```bash
echo "MinIO:     $(mc ls --recursive minio/spectrumx | wc -l) objects"
echo "SeaweedFS: $(mc ls --recursive sfs/spectrumx   | wc -l) objects"
```

### Checksums (sample or full)

```bash
# full diff — reports any missing or different objects
mc diff minio/spectrumx sfs/spectrumx
```

If `mc diff` reports no differences, migration is verified.

### Spot check from the application

```bash
# from gateway/
docker compose -f compose.local.yaml exec sds-gateway-local-app \
  python manage.py shell -c "
from sds_gateway.api_methods.utils.minio_client import get_minio_client
client = get_minio_client()
objs = list(client.list_objects('spectrumx', recursive=True))
print(f'{len(objs)} objects found via app client')
"
```

---

## 7. Switch the application to SFS

The local and production compose files already replaced `minio.env` with `sfs.env` in
all service `env_file` lists. The CI compose keeps both files (with `minio.env` marked
as legacy) so that `sfs.env` values take precedence.

To revert to MinIO temporarily, replace `sfs.env` with `minio.env` in the `env_file`
lists.

Restart the gateway to pick up any env changes:

```bash
docker compose -f compose.local.yaml up -d
```

Run a quick smoke test:

```bash
curl -s http://localhost:8000/api/v1/files/ | head
```

---

## 8. Tear down MinIO

Once migration is verified and the application runs correctly on SFS:

1. Stop the MinIO container:

```bash
docker compose -f compose.local.yaml stop minio
```

1. Remove `minio.env` from `env_file` lists in the compose file (remove the
   `# legacy` lines).

2. Comment out or delete the `minio:` service block from the compose file.

3. Remove the MinIO network (`sds-gateway-local-minio-net`) from the `networks:`
   section and from all services that reference it.

4. Remove the MinIO volume from the `volumes:` section:

```yaml
# remove this line
sds-gateway-local-minio-files: {}
```

1. Bring the stack back up to confirm nothing breaks:

```bash
docker compose -f compose.local.yaml up -d
docker compose -f compose.local.yaml ps
```

---

## 9. Delete MinIO data (future — irreversible)

> **Warning:** Only do this after confirming all data is accessible via SFS and
> backups exist.

```bash
# remove the docker volume
docker volume rm sds-gateway-local-minio-files

# if MinIO used bind-mounted host directories, remove those too
# rm -rf /path/to/minio/data
```

---

## Production notes

- Replace `compose.local.yaml` with `compose.production.yaml` throughout.
- Replace `sds-network-local` with `sds-network-prod` (already external).
- Use strong, unique credentials in `gateway/.envs/production/sfs.env`.
- Production SFS S3 endpoint: `sds-gateway-prod-sfs-s3:8333`.
- Production MinIO ports are remapped (`19000`/`19001`): adjust `mc alias` accordingly.
- Consider a maintenance window to avoid writes during step 5.
- After migration, update CI (`compose.ci.yaml`) following the same steps — env files
  and network references are already in place.

---

## Rollback

If issues arise after switching to SFS:

1. Replace `sfs.env` with `minio.env` in the `env_file` lists of the compose file.
2. Restart the gateway stack.
3. MinIO data is untouched — the application will resume using MinIO.
