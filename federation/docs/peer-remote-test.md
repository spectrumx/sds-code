# Remote peer sync test (two servers)

CRC lab pair: **sds-dev.crc.nd.edu** (full gateway + sync) ↔ **sds-fed1.crc.nd.edu**
(sync-only: OpenSearch + Redis + federation). Traefik `PathPrefix(/sync)` on both
hosts; do not strip the prefix.

```text
[sds-dev]                                   [sds-fed1]
 gateway + Redis + OpenSearch + sync         OpenSearch + Redis + sync
 publishes real/public FINAL datasets        seed_peer_opensearch.py
 federation.toml [[peers]] → fed1 /sync      federation.peer.toml [[peers]] → sds-dev /sync
```

FQDN must match the real hostname (`sds-fed1`, not `sds-fed-1`).

## Identity

| Field | sds-dev | sds-fed1 |
|-------|---------|----------|
| toml `[site].name` | `crc` (match `FEDERATION_SITE_NAME`) | `fed1` |
| toml `[site].fqdn` / OpenSearch `site_name` | `sds-dev.crc.nd.edu` | `sds-fed1.crc.nd.edu` |
| Public sync URL | `https://sds-dev.crc.nd.edu/sync` | `https://sds-fed1.crc.nd.edu/sync` |
| Redis channel | `federation:events:{name}` | `federation:events:fed1` |

`list-*` and site-hello allowlists use **FQDN**, not the short name. Leave `ca_cert_path`
unset (Let's Encrypt).

## sds-fed1 setup

1. Deploy Traefik (creates `sds-network-local`, TLS for `sds-fed1.crc.nd.edu`):

   ```bash
   cd network
   just up
   ```

   DNS for `sds-fed1.crc.nd.edu` must point at this host (HTTP-01 on :80).

2. Federation config:

   ```bash
   cd federation
   cp federation.peer.remote.example.toml federation.peer.toml
   cp env.peer.example .env.peer
   mkdir -p certs
   ```

3. Start sync + Redis + OpenSearch only (`compose.peer.remote.yaml`, not `just up`):

   ```bash
   docker compose -f compose.peer.remote.yaml --env-file .env.peer up -d --build
   curl -sS https://sds-fed1.crc.nd.edu/sync/health | jq .
   ```

   Gateway export errors to `127.0.0.1:9` are **expected**.

4. Seed peer-owned docs (`--site-name` = `[site].fqdn`):

   ```bash
   uv sync --extra dev
   uv run python scripts/seed_peer_opensearch.py \
     --opensearch-url http://localhost:9200 \
     --site-name sds-fed1.crc.nd.edu
   curl -sS https://sds-fed1.crc.nd.edu/sync/api/v1/webhook/list-datasets/ \
     | jq '.[].site_name'
   # → ["sds-fed1.crc.nd.edu"]
   ```

## sds-dev setup

1. Gateway + federation sync; Traefik toml with `Host(sds-dev.crc.nd.edu) && PathPrefix(/sync)`.
2. In `federation.toml`:

   ```toml
   [site]
   name = "crc"
   fqdn = "sds-dev.crc.nd.edu"
   display_name = "Notre Dame SDS Dev"
   sync_service_url = "https://sds-dev.crc.nd.edu/sync"

   [[peers]]
   name = "fed1"
   fqdn = "sds-fed1.crc.nd.edu"
   display_name = "Fed1 test peer"
   gateway_api_base = "http://peer-gateway-unused:8000/api/v1"
   sync_service_url = "https://sds-fed1.crc.nd.edu/sync"
   ```

3. `SDS_SITE_FQDN=sds-dev.crc.nd.edu` (must match `[site].fqdn`).
4. Restart main sync after toml changes.

## Bring-up order

1. sds-dev gateway + sync healthy; `https://sds-dev.crc.nd.edu/sync/health` is 200.
2. sds-fed1 Traefik + peer stack healthy + seeded.
3. Restart **fed1** sync (site-hello → sds-dev backfill).
4. Restart **sds-dev** sync (bootstrap pull of fed1 `list-*`).

## Verify

```bash
# both public health
curl -sS https://sds-dev.crc.nd.edu/sync/health | jq .
curl -sS https://sds-fed1.crc.nd.edu/sync/health | jq .

# fed1 docs on sds-dev OpenSearch
curl -sS 'http://localhost:9200/fed-datasets/_search?q=site_name:sds-fed1.crc.nd.edu' \
  | jq '.hits.total'
```

Fallback if Traefik/TLS is not ready on fed1: open host **:8000** and use
`http://sds-fed1.crc.nd.edu:8000/sync` in sds-dev `[[peers]]` and
`PEER_SYNC_PUBLIC_URL` (still use `https://sds-dev.crc.nd.edu/sync` the other way).

## Local analogue

Same idea on one machine: `just deploy-local-peer-2-peer` then `just seed-peer`
(see [../README.md](../README.md) and [../scripts/local_e2e/README.md](../scripts/local_e2e/README.md)).
