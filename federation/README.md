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

**URLs:** Local debug sync is host **8001** → container `:8000`
(`http://localhost:8001/sync/health`). Peers use **HTTPS :443** via Traefik
`PathPrefix(/sync)` (prefix **not** stripped), e.g. `https://sds.crc.nd.edu/sync/health`.
Set `[site].sync_service_url` / `FEDERATION_SYNC_SERVICE_URL` to that public HTTPS URL
(not `:8001`). Production compose loads sync URL and related vars from gitignored
`site.env` (see `site.example.env`).

See also: [scripts/local_e2e/README.md](scripts/local_e2e/README.md),
[docs/peer-remote-test.md](docs/peer-remote-test.md).

---

## Site identity (critical)

| Setting | Matches | Used for |
|---------|---------|----------|
| `FEDERATION_SITE_NAME` | toml `[site].name` | Short peer id; Redis `federation:events:{name}` |
| `SDS_SITE_FQDN` | toml `[site].fqdn` | OpenSearch **`site_name`**; sync `list-*` filters; Traefik `Host()` |

Do **not** put the short name into OpenSearch docs. Local lab: `name=crc`, `fqdn=sds.localhost`.
Peer lab: `name=peer`, `fqdn=peer.local`.

Config: gitignored `federation.toml`, `site.env` (production compose), repo-root
`federation-shared.env`, gateway `FEDERATION_ENABLED=true` in `django.env`.

---

## Production: start order

Prerequisites: Docker, `just`, DNS A/AAAA for your FQDN, ports 80/443 (Let's Encrypt).

| Step | Directory | Command |
|------|-----------|---------|
| 1. Traefik | `network/` | `just up` — routes in `traefik/conf.d/` (`00-federation-sync.toml` for ND sites; wizard adds `<site>-sync.toml` for new hosts) |
| 2. Gateway | `gateway/` | `./scripts/generate-secrets.sh production` then `just up` |
| 3. Federation | `federation/` | `SDS_ENV=production just federation-onboard` (below) |

### Onboard a new site (recommended)

Gateway and Traefik must already be up.

```bash
cd federation
SDS_ENV=production just federation-onboard
```

The wizard prompts for FQDN, short site id, display name, bootstrap peer FQDN, optional
peer CA path; renders `site.env`, `federation.toml`, gateway federation block in
`django.env`, and Traefik drop-in when needed; runs `federation-doctor`; ensures secrets;
`init_federation_sync_token`; builds and starts sync; waits for `"status":"ok"` on
`/sync/health`, restarts sync once; prints a `[[peers]]` block for the peer operator.

**Non-interactive** — export variables, then the same command:

```bash
export SDS_SITE_FQDN=your-site.example.edu
export SDS_SITE_NAME=your-site
export SDS_SITE_DISPLAY_NAME="Your Site"
export FEDERATION_PEER_FQDN=sds.crc.nd.edu
# optional: FEDERATION_PEER_CA_PATH=/path/to/ca.pem
SDS_ENV=production just federation-onboard
```

**Render only** (no container changes): set `SDS_SITE_*`, then
`SDS_ENV=production just federation-render-config` (templates in `templates/`).
Skip Traefik: `RENDER_TRAEFIK_SYNC=0`. **Preflight:** `just federation-doctor`
(`FEDERATION_DOCTOR_SKIP_DNS=1` / `FEDERATION_DOCTOR_SKIP_DB=1` as needed).

**Add a peer** on this host:

```bash
SDS_ENV=production just federation-add-peer \
  --name peer-id --fqdn peer.example.edu \
  --sync-url https://peer.example.edu/sync/ \
  --gateway-api-base https://peer.example.edu/api/v1
```

Optional `--ca-cert-path` (file under `federation/certs/` in the sync container).
Reciprocal `[[peers]]` on the remote site is still manual.

**Manual production** (debugging): copy `site.example.env` → `site.env`,
`federation.example.toml` → `federation.toml`, align `[site]` with `django.env`,
`init_federation_sync_token` on `sds-gateway-prod-app`, then
`SDS_ENV=production just build && just up`. Verify:
`curl -sS https://<fqdn>/sync/health | jq .` (`"status":"ok"`).

---

## Local development

Lab sync URL for health checks: `http://localhost:8001/sync` (not Traefik).

### Option A — same wizard as production

```bash
cd gateway && ./scripts/generate-secrets.sh local && just up
cd ../federation
SDS_ENV=local just federation-onboard
```

Defaults: `crc` / `sds.localhost`, site sync URL `http://localhost:8001/sync`, peer
`peer.local` with `sync_service_url = http://sds-federation-peer-sync:8000/sync` for
`just deploy-local-peer-2-peer`. Keep `federation.peer.toml` reciprocal (see wizard output).

### Option B — manual

```bash
cd gateway
./scripts/generate-secrets.sh local
# django.env: FEDERATION_ENABLED=true, FEDERATION_SITE_NAME=crc, SDS_SITE_FQDN=sds.localhost,
#   FEDERATION_SYNC_HEALTH_URL=http://sds-federation-local-sync:8000/sync/health,
#   FEDERATION_SYNC_USER_EMAIL=federation-sync@internal.local
just up
docker compose -f compose.local.yaml exec sds-gateway-local-app \
  uv run manage.py init_federation_sync_token

cd ../federation
cp federation.example.toml federation.toml   # [site] matches gateway
just build && just up
curl -s http://localhost:8001/sync/health | jq .
```

Leave `FEDERATION_SYNC_SERVER_API_KEY` empty in `federation-shared.env` so sync mints
the export key. Optional: `FEDERATION_SKIP_SYNC_HEALTH_PROBE=true` until sync is up.

**Local peer mesh:**

```bash
just deploy-local-peer-2-peer
just seed-peer
docker restart sds-federation-local-sync
```

Tear down: `just down-peer-2-peer` or
`docker compose -f compose.local.yaml -f compose.peer.local.yaml down`.

Two-server peer: [docs/peer-remote-test.md](docs/peer-remote-test.md).

---

## Verify

| Check | Command |
|-------|---------|
| Sync health | `curl -sS http://localhost:8001/sync/health \| jq .` (local) or `https://<fqdn>/sync/health` (prod) — need `"status":"ok"` |
| Export Api-Key | `TOKEN=$(grep '^FEDERATION_SYNC_DRF_TOKEN=' ../federation-shared.env \| cut -d= -f2-)` then `curl -sS http://localhost:8000/users/get-federation-sync-api-key/ -H "Authorization: Token $TOKEN"` — use `Authorization: Api-Key: <key>` |
| Indexed FQDN | `curl -s 'http://localhost:9200/fed-datasets/_search' \| jq '.hits.hits[]._source.site_name'` |
| List API | `curl -s http://localhost:8001/sync/api/v1/webhook/list-datasets/ \| jq 'length'` |

Publish test data:

```bash
cd gateway
docker compose -f compose.local.yaml exec sds-gateway-local-app \
  python manage.py publish_for_federation --dataset-uuid <uuid> --capture-uuids <uuid>
```

---

## Auth model

| Secret | Where | Role |
|--------|--------|------|
| `FEDERATION_SYNC_DRF_TOKEN` | `federation-shared.env` → DB via `init_federation_sync_token` | Mint endpoint auth (40 chars) |
| `FEDERATION_SYNC_SERVER_API_KEY` | Minted by sync (or shared env) | Gateway `/federation/export/*` |

There is **no** `create_federation_sync_api_key` command.

---

## Commands (`cd federation`)

| Recipe | Purpose |
|--------|---------|
| `just federation-onboard` | Site onboarding wizard |
| `just federation-render-config` | Render `site.env`, `federation.toml`, django block, Traefik |
| `just federation-doctor` | Identity, token, URL, network checks |
| `just federation-add-peer` | Append `[[peers]]`, restart sync |
| `just build` / `just up` / `just down` | Sync container (`SDS_ENV=local\|production`) |
| `just deploy-local-peer-2-peer` | Local + peer stacks |
| `just seed-peer` | Dummy peer docs on :9201 |
| `just verify-federation-live` | Live pipeline check |
| `just simulate-redis` | Inject federation Redis events |
| `just test` / `just test-regression` / `just test-integration` | Pytest |
| `just env` | Selected env; warns if `site.env` missing |

---

## Troubleshooting

| Symptom | Check |
|---------|--------|
| Export `503` | Sync health URL, Api-Key, Redis, `FEDERATION_ENABLED` |
| Bootstrap mint fail | DRF token length 40; `init_federation_sync_token`; gateway URL |
| Identity drift | `just federation-doctor` |
| `list-*` empty but OS has docs | Doc `site_name` must be **FQDN**, not short name |
| `/sync` 404 at edge | Traefik `conf.d` for your FQDN; restart `network` after route changes |
| site-hello race | Wizard restarts sync; or `docker restart <sync-container>` |
| Redis events missing | Unset `FEDERATION_EVENTS_CHANNEL` → `federation:events:{FEDERATION_SITE_NAME}` |
| Gateway code not live | Rebuild gateway image (not fully bind-mounted) |
| Docker build / `sds-opensearch-query` | Build context repo root; `COPY common/` |

Peer mesh notes: peer stack has no gateway — `GATEWAY_INTERNAL_BASE_URL` errors in peer
logs are expected. Peer-owned docs use `just seed-peer` (`site_name=peer.local`).
