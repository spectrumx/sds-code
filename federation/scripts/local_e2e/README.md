# Local federation live test

Exercise gateway → sync → OpenSearch without depending on any remote production site.

**Never commit API tokens.** Copy `env.example` → `.env` in this directory (gitignored).

## Identity (do not mix these up)

| Setting | Role |
|---------|------|
| `FEDERATION_SITE_NAME` / toml `[site].name` | Short peer id; Redis channel `federation:events:{name}` |
| `SDS_SITE_FQDN` / toml `[site].fqdn` | OpenSearch + export `site_name`; sync `list-*` filters |

Local compose defaults (see `federation.toml`): name `crc`, fqdn `sds.localhost`.

## Prerequisites

1. Gateway stack up (`gateway` compose local): app, Redis, OpenSearch, object store.
2. Federation sync up — either:
   - Solo: `cd federation && just up` (port **8001**)
   - Peer mesh: `just deploy-local-peer-2-peer` (local **8001**, peer **8002**)
3. Gateway `django.env`:
   - `FEDERATION_ENABLED=true`
   - `FEDERATION_SITE_NAME` / `SDS_SITE_FQDN` match `federation.toml` `[site]`
4. Mint export Api-Key (no `create_federation_sync_api_key` command):

   ```bash
   TOKEN=$(grep '^FEDERATION_SYNC_DRF_TOKEN=' ../../../federation-shared.env | cut -d= -f2-)
   curl -sS http://localhost:8000/users/get-federation-sync-api-key/ \
     -H "Authorization: Token $TOKEN" | jq -r .api_key
   # save as FEDERATION_GATEWAY_API_KEY in .env
   ```

   Header form: `Authorization: Api-Key: <key>` (colon after `Api-Key`).
5. Gateway capture indices: `python manage.py init_indices` (inside app container).

## Recommended: peer seed (no RF files)

For peer→local backfill / `list-*` without a second gateway:

```bash
cd federation
just seed-peer
docker restart sds-federation-local-sync
curl -s 'http://localhost:9200/fed-datasets/_search' \
  | jq '.hits.hits[]._source | {site: .site_name, name}'
```

## Local-owned data: publish any capture

Create a public FINAL dataset in the UI or API (attach any local capture), then:

```bash
cd gateway
docker compose -f compose.local.yaml exec sds-gateway-local-app \
  python manage.py publish_for_federation \
  --dataset-uuid <dataset-uuid> \
  --capture-uuids <capture-uuid>
```

Optional Redis fan-out:

```bash
cd federation
just simulate-redis --event-type updated --item-type dataset --uuid <dataset-uuid>
```

Confirm OpenSearch `site_name` is the FQDN:

```bash
curl -s 'http://localhost:9200/fed-datasets/_search' \
  | jq '.hits.hits[]._source.site_name'
# → matches SDS_SITE_FQDN / [site].fqdn
```

## Verify

```bash
cd federation
set -a && source scripts/local_e2e/.env && set +a
just verify-federation-live --q <search-term>
```

Or:

```bash
curl -s "http://localhost:8001/api/v1/search/datasets?site=${LOCAL_SITE_FQDN}&q=<search-term>" | jq .
curl -s http://localhost:8000/api/v1/federation/export/datasets/ \
  -H "Authorization: Api-Key: $FEDERATION_GATEWAY_API_KEY" | jq 'length'
curl -s http://localhost:8001/sync/api/v1/webhook/list-datasets/ | jq 'length'
```

## Optional: import a capture via SDK

Federation does **not** ship remote download/upload helpers. Use the SpectrumX SDK from
`sdk/` against whatever host you choose (`SDS_HOST`, `SDS_SECRET_TOKEN`), then upload
to local gateway (`LOCAL_SDS_HOST` / `LOCAL_SDS_SECRET_TOKEN`). See `sdk/docs` for
`download_dataset` / `upload_capture`. Ensure channel layout and `drf_properties.h5`
match what the local gateway expects before `publish_for_federation`.

## Remote peer (two servers)

See [../../docs/peer-remote-test.md](../../docs/peer-remote-test.md).
