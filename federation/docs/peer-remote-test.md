# Remote peer sync test (two servers)

Test federation **without** a second full gateway: the peer host runs OpenSearch,
Redis, and the sync service only, then seeds dummy `fed-*` docs. The main host
runs the normal gateway + sync stack.

```text
[Main]                                      [Peer]
 gateway + Redis + OpenSearch + sync         OpenSearch + Redis + sync
 publishes real/public FINAL datasets        seed_peer_opensearch.py
 federation.toml [[peers]] → peer URL        federation.peer.toml [[peers]] → main
```

## Identity

| Field | Main | Peer |
|-------|------|------|
| toml `[site].name` | e.g. `crc` | e.g. `peer` |
| toml `[site].fqdn` / OpenSearch `site_name` | e.g. `sds.example.com` | e.g. `peer.example.com` |
| Redis channel | `federation:events:{name}` | `federation:events:peer` |

`list-*` and search filter by **FQDN**, not the short name.

## Peer host setup

1. Checkout this repo (or deploy the federation image + compose files).
2. Config:

   ```bash
   cd federation
   cp federation.peer.remote.example.toml federation.peer.toml
   # Edit FQDNs + main sync_service_url (reachable from peer)
   cp env.peer.example .env.peer
   # Edit PEER_SYNC_PUBLIC_URL to this host's public sync URL
   ```

3. Start:

   ```bash
   docker compose -f compose.peer.remote.yaml --env-file .env.peer up -d --build
   curl -sS http://localhost:8000/sync/health | jq .
   ```

   Local gateway bootstrap errors (`127.0.0.1:9`) are **expected** on a sync-only peer.
4. Seed peer-owned docs (FQDN must match toml `[site].fqdn`):

   ```bash
   uv sync --extra dev
   uv run python scripts/seed_peer_opensearch.py \
     --opensearch-url http://localhost:9200 \
     --site-name peer.example.com
   ```

5. Open firewall / TLS so the **main** site can reach `https://peer.example.com/sync`
   (and peer can reach main's sync URL).

## Main host setup

1. Normal gateway + federation sync (`compose.local.yaml` or production compose).
2. In `federation.toml` add the peer with a **public** URL (not Docker DNS):

   ```toml
   [[peers]]
   name = "peer"
   fqdn = "peer.example.com"
   display_name = "Remote Peer"
   gateway_api_base = "http://peer-gateway-unused:8000/api/v1"
   sync_service_url = "https://peer.example.com/sync"
   ```

3. Ensure `SDS_SITE_FQDN` matches main `[site].fqdn` (export/OpenSearch `site_name`).
4. Restart main sync after toml changes so bootstrap + site-hello run.

## Bring-up order

1. Main gateway healthy + federation operational.
2. Peer stack healthy + seeded.
3. Restart **main** sync (pulls peer `list-*` / site-hello backfill).
4. Optionally restart **peer** sync (pulls main `list-*`).

Site-hello backfill retries transient connect errors; still prefer peer healthy before main restart.

## Verify

### Peer → main

```bash
# peer
curl -sS https://peer.example.com/sync/api/v1/webhook/list-datasets/ | jq '.[].site_name'
# → ["peer.example.com"]

# main OpenSearch
curl -sS 'http://localhost:9200/fed-datasets/_search?q=site_name:peer.example.com' \
  | jq '.hits.total'
curl -sS 'http://localhost:8001/api/v1/search/datasets?site=peer.example.com' | jq .
```

### Main → peer

```bash
# main: publish a FINAL public dataset, then
curl -sS 'https://peer.example.com/sync/…'  # or query peer OS
curl -sS 'http://PEER_OS:9200/fed-datasets/_search?q=site_name:sds.example.com' \
  | jq '.hits.total'
```

## Safety

- Use a **dedicated** peer OpenSearch; never point peer sync at production `fed-*` by mistake.
- Seed data is synthetic; do not load real user PII onto the peer host.
- Prefer TLS + CA paths in toml (`ca_cert_path`) for non-lab networks.

## Local analogue

Same idea on one machine: `just deploy-local-peer-2-peer` then `just seed-peer`
(see [../README.md](../README.md) and [../scripts/local_e2e/README.md](../scripts/local_e2e/README.md)).
