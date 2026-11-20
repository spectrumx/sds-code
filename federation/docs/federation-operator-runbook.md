# Federation operator runbook

Single guide for **mesh sync**, **signed registry**, and **registry intake** (apply → verify → staff publish).

Technical sync service reference (compose, auth, pytest): [federation/README.md](../README.md).

Registry signing key paths: [secrets/registry/README.md](../secrets/registry/README.md).

---

## 1. Concept

**Federation sync** shares *metadata* (datasets/captures in OpenSearch `fed-*` indexes), not file blobs. When a site publishes a public asset, it indexes locally, signals Redis, and sync notifies peers; peers index a read-only copy for search.

**Signed registry** is a separate mesh bootstrap: the mothership publishes `sites.json` + signature; member sync containers poll `/.well-known/sds-registry/` and merge peers without hand-editing every `[[peers]]` block.

**Registry intake** is gateway UI + DB on the flagship host: applicants prove DNS via well-known JSON; staff approve and publish the manifest on flagship sync.

---

## 2. Architecture

```text
Applicant site                         Mothership (e.g. sds.crc.nd.edu)
--------------                         ---------------------------------
sync serves                            gateway: intake UI + RegistryApplication DB
  GET /.well-known/sds-federation.json   staff approve / Publish registry
  (FEDERATION_REGISTRY_CHALLENGE_TOKEN)        |
         ^                                       v
         |                              flagship sync:
         |                                POST /internal/registry/verify
         |                                POST /internal/registry/publish (sign)
         +-- HTTPS well-known ------------- GET /.well-known/sds-registry/
                                              sites.json, .sig, sds-registry.pub.pem

Members: [registry] url → poll manifest → verify sig → merge peers → bootstrap
```

| Component | Owns |
|-----------|------|
| **Gateway** | Applications, challenge hash, staff UI, applicant email on **published**, HTTP client to sync |
| **Flagship sync** | Verify fetch, Ed25519 sign, manifest files, public well-known + registry URLs |
| **Applicant sync** | Site identity well-known + challenge token env |
| **All member sync** | Poll registry, trust signature, auto-add peers |

Internal API: `POST /internal/registry/*` on sync (Docker network + `FEDERATION_SYNC_ADMIN_TOKEN`). Traefik must **not** expose `/internal` on the public hostname.

---

## 3. Flagship first-time setup

Prerequisites: Traefik, gateway, federation sync on the mothership host ([federation/README.md](../README.md) production start order).

### Gateway (intake)

In `gateway/.envs/<env>/django.env`:

| Variable | Notes |
|----------|--------|
| `SDS_SITE_FQDN` | Must equal `FLAGSHIP_GATEWAY_HOST` (e.g. `sds.crc.nd.edu`) |
| `FEDERATION_REGISTRY_INTAKE_ENABLED` | `true` on flagship only |
| `FEDERATION_SYNC_INTERNAL_URL` | e.g. `http://sds-federation-prod-sync:8000` |
| `FEDERATION_REGISTRY_AUTO_PUBLISH_ON_APPROVE` | Optional; default `false` |
| `FEDERATION_REGISTRY_PREFLIGHT_PUBLISH_HEALTH` | Optional; warn if applicant `/sync/health` fails at publish; default `false` |

`FEDERATION_SYNC_ADMIN_TOKEN` lives in repo-root **`federation-shared.env`** (gateway + sync compose).

### Sync (publish)

| Step | Action |
|------|--------|
| Signing key | `federation/secrets/registry/sign.pem` (see [secrets/registry/README.md](../secrets/registry/README.md)) |
| Config | `[registry.publish] enabled = true` / `FEDERATION_REGISTRY_PUBLISH_ENABLED=true` |
| Volume | Named volume for `manifest_dir` |
| Public key | `federation/certs/sds-registry.pub.pem`; optional fingerprint in `site.env` |
| Traefik | `Host()` + `/.well-known/sds-federation.json` and `/.well-known/sds-registry/*` → sync |

```bash
cd federation
uv run sds-federation-registry keygen --out-dir secrets/registry
uv run sds-federation-registry fingerprint --public-key-path certs/sds-registry.pub.pem
just federation-doctor
# or: FEDERATION_DOCTOR_CHECK=registry ./scripts/bin/federation-doctor.sh
```

---

## 4. New peer setup

Production order: **network (Traefik)** → **gateway secrets** → **`federation-onboard`** → **`federation-preflight-apply`**.

```bash
cd federation
SDS_ENV=production just federation-onboard
SDS_ENV=production just federation-preflight-apply
```

Preflight prints:

```text
Registry application FQDN (use exactly): <SDS_SITE_FQDN>
```

Use that FQDN on the mothership application form.

Onboard/render sets consumer `[registry]` when not flagship publish (`site.example.env`):

- `FEDERATION_REGISTRY_URL` — mothership registry well-known base
- Fetch verifying PEM: `just federation-fetch-registry-pubkey` (or automatic during render)
- Optional OOB pin: `FEDERATION_REGISTRY_PUBKEY_FINGERPRINT`

---

## 5. Registry join (applicant)

### Apply

1. Mothership gateway → `/users/federation/registry/` → **New application**
2. **FQDN** must match applicant `SDS_SITE_FQDN` / well-known `fqdn` (doctor enforces alignment)
3. Copy the **verification token** (shown once)

### Challenge + preflight

```bash
cd federation
just federation-join-registry --token "$TOKEN" --site-env
# recreate sync per printed command
just federation-join-registry --preflight --site-env
```

Lower-level: `./scripts/bin/set-registry-challenge.sh --token "$TOKEN" --site-env`

| Deployment | Env file | Recreate |
|------------|----------|----------|
| Local lab | `.env.local` | `compose.local.yaml` sync service |
| Sync-only peer | `.env.peer` | `compose.peer.*.yaml` |
| Production | `site.env` | production compose sync |

Confirm:

```bash
curl -sS "https://<fqdn>/.well-known/sds-federation.json" | jq '{fqdn, registry_challenge}'
```

### Verify (UI)

Application detail → **Verify domain**. Success → **`pending_approval`** (no email). Staff approve and publish separately.

### After publish

Applicant receives email when status becomes **`published`**. Sync polls the registry; confirm peers in logs or:

```bash
curl -sS "https://sds.crc.nd.edu/.well-known/sds-registry/sites.json" | jq '.sites[].fqdn'
```

---

## 6. Staff workflow

Requires `is_staff` on flagship gateway. List: `/users/federation/registry/`.

| Status | Action |
|--------|--------|
| `pending_approval` | **Approve** (site id) or **Reject** |
| `approved` (+ existing `published`) | **Publish registry** (when sync reports `publish_enabled`) |

Publish builds the site list, signs on sync, marks rows `published`, emails applicants for newly published rows.

Optional: `FEDERATION_REGISTRY_AUTO_PUBLISH_ON_APPROVE=true` publishes immediately after each approve.

Break-glass: `sds-federation-registry publish` on flagship sync; reconcile DB manually.

---

## 7. Commands and troubleshooting

### Just recipes (`cd federation`)

| Recipe | Purpose |
|--------|---------|
| `just federation-onboard` | Site wizard |
| `just federation-preflight-apply` | Pre-apply gate (Traefik, public URLs, registry consumer) |
| `just federation-join-registry` | Challenge token + post-recreate preflight |
| `just federation-doctor` | Identity, token, registry, optional checks |
| `just federation-fetch-registry-pubkey` | Pull `sds-registry.pub.pem` from mothership |
| `just federation-render-config` | Templates → `site.env`, `federation.toml`, Traefik |
| `just federation-add-peer` | Static `[[peers]]` (non-registry path) |

Doctor profiles: `FEDERATION_DOCTOR_CHECK=preflight_apply`, `registry`, `identity`, etc. Skips: `FEDERATION_DOCTOR_SKIP_DNS`, `FEDERATION_DOCTOR_SKIP_PUBLIC`, `FEDERATION_PREFLIGHT_SKIP=1` (local only).

### Registry troubleshooting

| Symptom | What to check |
|---------|----------------|
| `registry_challenge` null | Token on **applicant** sync; container **recreated** after env edit |
| Challenge mismatch | Env token ≠ apply token; re-issue or re-apply |
| `fqdn` mismatch | Application FQDN ≠ `SDS_SITE_FQDN` / well-known `fqdn` |
| Verify fetch error | HTTPS/DNS/TLS from **sync** container to applicant |
| **Publish registry** disabled | Signing key, `[registry.publish]`, doctor `registry` |
| Peers missing new site | Staff did not publish; wrong `registry.url`; signature/fingerprint |
| Applicant no email | Celery worker; status must be `published` (not approve alone) |
| Pubkey fetch fail | `GET …/sds-registry/sds-registry.pub.pem` on mothership; fingerprint pin |

Sync mesh troubleshooting: [federation/README.md#troubleshooting](../README.md#troubleshooting).

---

## 8. Local lab

**Single machine:** `just deploy-local-peer-2-peer`, `just seed-peer` — [scripts/local_e2e/README.md](../scripts/local_e2e/README.md).

**Registry lab:** Align `SDS_SITE_FQDN` with `FLAGSHIP_GATEWAY_HOST` (`sds.localhost`). Same join flow; optional `FEDERATION_REGISTRY_LOCAL_LAB` on sync for verify fetch.

**Two-server peer (sync-only remote host):**

1. Remote: Traefik TLS for peer FQDN → `compose.peer.remote.yaml` + `federation.peer.toml` + `.env.peer`
2. Dev host: gateway + sync; reciprocal `[[peers]]` using public `https://<fqdn>/sync`
3. Order: both `/sync/health` OK → restart peer sync (site-hello) → restart dev sync (bootstrap `list-*`)
4. OpenSearch `site_name` in docs = **FQDN**, not short `name`

| Field | Dev (example) | Remote peer (example) |
|-------|---------------|------------------------|
| `[site].name` | `crc` | `fed1` |
| `[site].fqdn` | `sds-dev.example.edu` | `sds-fed1.example.edu` |

Use `env.peer.example` → `.env.peer`; not `peer.env`.

---

## Settings quick reference

| Setting | Where | Purpose |
|---------|--------|---------|
| `FEDERATION_REGISTRY_CHALLENGE_TOKEN` | Applicant sync env only | Well-known challenge |
| `FEDERATION_REGISTRY_URL` | Peer `site.env` | Registry poll base URL |
| `FEDERATION_REGISTRY_PUBLISH_ENABLED` | Flagship `site.env` | Signing on sync |
| `FEDERATION_REGISTRY_AUTO_PUBLISH_ON_APPROVE` | Gateway django.env | Publish on each approve |
| `FEDERATION_REGISTRY_PREFLIGHT_PUBLISH_HEALTH` | Gateway django.env | Warn on unhealthy peer at publish |