# SDS Federation Sync

FastAPI service that indexes federated dataset/capture metadata into OpenSearch
(`fed-datasets`, `fed-captures`), receives peer webhooks, and bootstraps from the
local gateway export API plus peer sync list endpoints.

On startup (unless `FEDERATION_BOOTSTRAP_ON_START=false`):

1. Ensure `fed-*` indices exist
2. Mint or reuse a FederationSync export Api-Key
3. Pull local gateway `/api/v1/federation/export/{datasets,captures}/`
4. Pull each peer’s `/sync/api/v1/webhook/list-{datasets,captures}/`
5. Register with peers via `POST .../webhook/site-hello`
6. Subscribe to Redis `federation:events:{site}` for incremental updates

Local HTTP (this machine only, not the peer path): host **8001** → container `:8000`.
Health: `http://localhost:8001/sync/health`.

Peer sync is **HTTPS :443** via Traefik `PathPrefix(/sync)` (prefix is **not** stripped):

- sds-dev: `https://sds-dev.crc.nd.edu/sync/health`
- sds-fed1: `https://sds-fed1.crc.nd.edu/sync/health`
- prod: `https://sds.crc.nd.edu/sync/health`

Advertise that HTTPS URL in `[site].sync_service_url` / `FEDERATION_SYNC_SERVICE_URL`
(not `:8001`). Prod compose sets `FEDERATION_SYNC_SERVICE_URL=https://sds.crc.nd.edu/sync`.

See also:

- [scripts/local_e2e/README.md](scripts/local_e2e/README.md) — local live test (publish / seed / verify)
- [docs/peer-remote-test.md](docs/peer-remote-test.md) — two-server sync-only peer
- Repo-root `rfc_federation.md` — architecture RFC

---

## Site identity (critical)

| Setting | Matches | Used for |
|---------|---------|----------|
| `FEDERATION_SITE_NAME` | toml `[site].name` | Short peer id; Redis `federation:events:{name}` |
| `SDS_SITE_FQDN` | toml `[site].fqdn` | Export / OpenSearch **`site_name`**; sync `list-*` filters |

Do **not** put the short name into OpenSearch docs. Gateway writes FQDN via `SDS_SITE_FQDN`.

Local lab defaults: `name=crc`, `fqdn=sds.localhost`. Peer lab: `name=peer`, `fqdn=peer.local`.

---

## Prerequisites

- Docker / Compose, `just`, OpenSSL (for secrets)
- Gateway local stack (`sds-network-local`, app, Redis, OpenSearch)
- Python tooling for federation tests (`uv` in this directory)

---

## Local initialization

### 1. Generate shared secrets

From the gateway directory (fills `gateway/.envs/local/*` and repo-root
`federation-shared.env`):

```bash
cd gateway
./scripts/generate-secrets.sh local
```

Confirm the DRF token (40 characters). Leave `FEDERATION_SYNC_SERVER_API_KEY` empty
so sync mints an export key on start.

### 2. Gateway federation env

`gateway/.envs/local/django.env`:

```env
FEDERATION_ENABLED=true
FEDERATION_SITE_NAME=crc
SDS_SITE_FQDN=sds.localhost
FEDERATION_SYNC_HEALTH_URL=http://sds-federation-local-sync:8000/sync/health
FEDERATION_SYNC_USER_EMAIL=federation-sync@internal.local
# Leave FEDERATION_EVENTS_CHANNEL unset → federation:events:crc
```

Optional first boot: `FEDERATION_SKIP_SYNC_HEALTH_PROBE=true` until sync is healthy.

### 3. Federation config

```bash
cd federation
cp federation.example.toml federation.toml
# [site] name/fqdn must match gateway FEDERATION_SITE_NAME / SDS_SITE_FQDN
```

Compose loads OpenSearch from `gateway/.envs/<env>/opensearch.env` and auth from
`federation-shared.env`.

### 4. Start gateway + federation token

```bash
cd gateway
just up
docker compose -f compose.local.yaml exec sds-gateway-local-app \
  python manage.py init_federation_sync_token
# or: prepare_gateway
```

### 5. Start sync

**Solo (this site only):**

```bash
cd federation
just build && just up
curl -s http://localhost:8001/sync/health | jq .
```

**Local peer mesh (recommended for p2p):**

```bash
cd federation
just deploy-local-peer-2-peer   # gateway check + build + local+peer up
just seed-peer                 # dummy peer.local docs on :9201
docker restart sds-federation-local-sync   # pull peer list / site-hello
```

Tear down both stacks:

```bash
docker compose -f compose.local.yaml -f compose.peer.local.yaml down
# just down   # only stops the primary compose file
```

### 6. Export Api-Key (manual checks)

```bash
TOKEN=$(grep '^FEDERATION_SYNC_DRF_TOKEN=' ../federation-shared.env | cut -d= -f2-)
curl -sS http://localhost:8000/users/get-federation-sync-api-key/ \
  -H "Authorization: Token $TOKEN" | jq -r .api_key
```

Use header: `Authorization: Api-Key: <key>` (note the colon).

---

## Auth model

| Secret | Where | Role |
|--------|--------|------|
| `FEDERATION_SYNC_DRF_TOKEN` | `federation-shared.env` → DB via `init_federation_sync_token` | Mint endpoint auth |
| `FEDERATION_SYNC_SERVER_API_KEY` | Minted by sync (or set in shared env) | Gateway `/federation/export/*` |

There is **no** `create_federation_sync_api_key` command.

---

## Commands

```bash
cd federation
just                          # list recipes
just deploy-local-peer-2-peer # local + peer stacks
just seed-peer                # seed peer OpenSearch (:9201, site peer.local)
just verify-federation-live
just simulate-redis --event-type updated --item-type dataset --uuid <uuid>
just test / just test-regression / just test-integration
```

---

## Publishing local data

```bash
cd gateway
docker compose -f compose.local.yaml exec sds-gateway-local-app \
  python manage.py publish_for_federation \
  --dataset-uuid <uuid> --capture-uuids <uuid>
```

Confirm docs use the FQDN:

```bash
curl -s 'http://localhost:9200/fed-datasets/_search' | jq '.hits.hits[]._source.site_name'
curl -s http://localhost:8001/sync/api/v1/webhook/list-datasets/ | jq 'length'
```

Live-test steps: [scripts/local_e2e/README.md](scripts/local_e2e/README.md).

---

## Peer sync testing

### Same machine

`compose.peer.local.yaml` + `federation.peer.toml` (mutual `[[peers]]` with **container DNS**
URLs). Orchestrated by `just deploy-local-peer-2-peer`.

- Peer has **no gateway** → `GATEWAY_INTERNAL_BASE_URL=http://127.0.0.1:9/...` failures in
  peer logs are expected.
- Peer-owned docs: `just seed-peer` (writes `site_name=peer.local`).
- Then restart local sync so site-hello / list pull ingest peer docs.

### Two servers (sync-only peer)

See **[docs/peer-remote-test.md](docs/peer-remote-test.md)** and
`compose.peer.remote.yaml` / `federation.peer.remote.example.toml`.

---

## Troubleshooting

| Symptom | Check |
|---------|--------|
| Export `503` | Sync health URL, Api-Key, Redis, `FEDERATION_ENABLED` |
| Bootstrap mint fail | DRF token length 40; `init_federation_sync_token`; gateway URL |
| `list-*` empty but OS has docs | Doc `site_name` must be **FQDN** (`SDS_SITE_FQDN`), not short name |
| site-hello connect race | Retries are built in; ensure peer healthy before relying on backfill |
| Redis events missing | Leave `FEDERATION_EVENTS_CHANNEL` unset; channel = `federation:events:{FEDERATION_SITE_NAME}` |
| Gateway code changes not live | App image is not fully bind-mounted — rebuild gateway image |
| Docker build / `sds-opensearch-query` | Build context repo root; `COPY common/` |
