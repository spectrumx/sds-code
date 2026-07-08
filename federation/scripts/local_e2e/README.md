# Local federation live test (gateway + sync + OpenSearch)

End-to-end flow: pull real RF data from CRC → load into **local** gateway → publish for federation → index in `fed-*` → query sync search.

**Never commit API tokens.** Use `env.example` → copy to `.env` in this directory.

## Prerequisites

1. Gateway stack up (`gateway` compose local): app, Redis, OpenSearch, MinIO.
2. Federation sync up (`federation/compose.local.yaml`) on port **8001**.
3. Gateway env (e.g. `django.env`):
   - `FEDERATION_ENABLED=true`
   - `FEDERATION_SITE_NAME=crc` (short id)
   - `SDS_SITE_FQDN=localhost` (must match `federation.toml` `[site].fqdn` for local)
   - `FEDERATION_EXPORT_ALLOWED_CIDRS` includes your sync container / dev machine
4. Federation sync env: `FEDERATION_GATEWAY_API_KEY` from:
   ```bash
   docker compose exec sds-gateway-local-app python manage.py create_federation_sync_api_key
   ```
5. OpenSearch capture indices: `python manage.py init_indices` (gateway).

## 1. Download from CRC (read-only)

```bash
cd sdk
cp ../federation/scripts/local_e2e/env.example ../federation/scripts/local_e2e/.env
# Edit .env: SDS_SECRET_TOKEN=... (your user token; rotate if exposed)

set -a && source ../federation/scripts/local_e2e/.env && set +a
uv run python ../federation/scripts/local_e2e/download_crc_dataset.py \
  --dataset-uuid 50e979bd-8018-415c-8212-c08c3dc98654 \
  --to ../federation/data/downloaded_dataset
```

To mimic a Haystack-style folder (one time slice), discover `top_level_dir` on CRC with the SDK (`list_dataset_captures`) then pass `--top-level-dir`.

**Size warning:** full datasets can be huge; prefer `--top-level-dir` or `--skip-contents` for metadata-only federation tests.

## 2. Upload to local gateway

Use a **local** user token (`LOCAL_SDS_SECRET_TOKEN` in `.env`).

```bash
uv run python ../federation/scripts/local_e2e/upload_capture_to_local.py \
  --local-path ../federation/data/downloaded_dataset \
  --sds-path federation-fixture/starlink-sample
```

Note the printed **capture UUID**.

## 3. Create / publish dataset

Create a dataset in the UI or API, attach the capture, then:

```bash
docker compose exec sds-gateway-local-app python manage.py publish_for_federation \
  --dataset-uuid <your-local-dataset-uuid> \
  --capture-uuids <capture-uuid>
```

This sets `FINAL` + `is_public` and marks captures public (fires `federation:events` when enabled).

## 4. Re-index federation

Restart sync (bootstrap on start) or trigger an update:

```bash
cd federation
just simulate-redis --event-type updated --item-type dataset --uuid <dataset-uuid>
```

## 5. Verify

```bash
cd federation
uv run python scripts/local_e2e/verify_federation_live.py --q starlink
```

Or:

```bash
curl -s 'http://localhost:8001/api/v1/search/datasets?site=localhost&q=fixture' | jq .
curl -s 'http://localhost:8000/api/v1/federation/export/datasets/' \
  -H "Authorization: Api-Key $FEDERATION_GATEWAY_API_KEY" | jq .
```

## Haystack public HTTP (optional)

Apollo directory listings (e.g. `rf@*.h5` under `Vpol_11.325GHz/...`) are the same kind of DigitalRF files CRC stores. You can `wget`/`curl` a **small** subset into `federation/data/apollo_sample/` and upload with the same `upload_capture_to_local.py` script instead of using `download_dataset`.
