# Federation registry deploy (operator runbook)

End-to-end guide: a new peer applies on the **mothership gateway**, proves domain control,
staff approve and publish a **signed registry manifest** on **flagship sync**, and every
member site **polls** the manifest to federate automatically.

---

## Architecture (one page)

```text
Applicant site                         Mothership (e.g. sds.crc.nd.edu)
--------------                         ---------------------------------
sync serves                            gateway: intake UI + RegistryApplication DB
  GET /.well-known/sds-federation.json   staff approve / Publish registry
  (env FEDERATION_REGISTRY_CHALLENGE_TOKEN)     |
         ^                                        v
         |                              flagship sync:
         |                                POST /internal/registry/verify (fetch applicant)
         |                                POST /internal/registry/publish (sign manifest)
         +-- HTTPS well-known ------------- GET /.well-known/sds-registry/sites.json(.sig)

Member sites (existing + new peer): [registry].url → poll manifest → merge peers → bootstrap
```

| Component | Owns |
|-----------|------|
| **Gateway** | Applications, challenges (hash only), staff UI, email to staff, HTTP client to sync |
| **Flagship sync** | Verify fetch, Ed25519 sign, manifest files, public well-known + registry URLs |
| **Applicant sync** | Site identity well-known + challenge token env |
| **All member sync** | Poll registry, trust signature, add peers, site-hello + list backfill |

Internal API: `POST /internal/registry/*` on sync (Docker network + `FEDERATION_SYNC_ADMIN_TOKEN`).
Traefik must **not** route `/internal` on the public hostname.

---

## Roles

| Role | You are… | Main actions |
|------|-----------|----------------|
| **Flagship operator** | Host `FLAGSHIP_GATEWAY_HOST` (default `sds.crc.nd.edu`) | One-time signing key, compose, Traefik, intake env |
| **Applicant operator** | New peer joining the mesh | Apply, set challenge on **your** sync, verify |
| **Flagship staff** | `is_staff` on mothership gateway | Approve, **Publish registry** |
| **Member site** | Already federating | Usually nothing (poll timer); optional `[registry]` bootstrap |

---

## Flagship first-time setup

Prerequisites: Traefik, gateway, federation sync on the mothership host (see
[federation/README.md](../README.md) production start order).

### 1. Registry intake (gateway)

In `gateway/.envs/<env>/django.env` (see `gateway/.envs/example/django.env`):

+ `SDS_SITE_FQDN` = `FLAGSHIP_GATEWAY_HOST` (e.g. `sds.crc.nd.edu`)
+ `FEDERATION_REGISTRY_INTAKE_ENABLED=true`
+ `FEDERATION_SYNC_INTERNAL_URL` — Docker DNS to flagship sync, e.g. `http://sds-federation-prod-sync:8000`
+ `FEDERATION_REGISTRY_STAFF_NOTIFY_EMAILS` — comma-separated staff inboxes (optional; else staff users / `ADMINS`)

`FEDERATION_SYNC_ADMIN_TOKEN` lives in repo-root **`federation-shared.env`** (loaded by gateway + sync compose).

### 2. Publish on sync (flagship only)

| Step | Action |
|------|--------|
| Signing key | `federation/secrets/registry/sign.pem` → mount read-only (see [secrets/registry/README.md](../secrets/registry/README.md)) |
| Config | `[registry.publish] enabled = true` in `federation.toml` / `FEDERATION_REGISTRY_PUBLISH_ENABLED=true` in `site.env` |
| Volume | Named volume for `manifest_dir` (e.g. `sds-federation-prod-registry-publish`) |
| Public key | `federation/certs/sds-registry.pub.pem` + `FEDERATION_REGISTRY_PUBKEY_FINGERPRINT` on sync |
| Traefik | Route flagship host `/.well-known/sds-federation.json` and `/.well-known/sds-registry/*` → sync (see `network/traefik/conf.d/00-federation-sync.toml`) |

Generate keys (from `federation/`):

```bash
uv run sds-federation-registry keygen --out-dir secrets/registry
# Move/sign paths per secrets/registry/README.md; publish .pub.pem to certs/
uv run sds-federation-registry fingerprint --public-key-path certs/sds-registry.pub.pem
```

### 3. Preflight

```bash
cd federation
just federation-doctor
# or: FEDERATION_DOCTOR_CHECK=registry ./scripts/federation-doctor.sh
```

Doctor checks: signing key readable, well-known 200, `/internal` not exposed on public host, fingerprint match.

---

## Applicant onboarding (manual steps)

These steps **require human action**; automation cannot replace them today.

### Checklist

+ [ ] Site is on the public internet with **HTTPS** on the application FQDN
+ [ ] Federation sync (or Traefik→sync) serves `GET https://<fqdn>/.well-known/sds-federation.json`
+ [ ] `[site].fqdn` / `SDS_SITE_FQDN` on applicant sync **equals** the FQDN you will apply with

### 1. Apply (gateway UI)

1. Sign in to mothership gateway → **`/users/federation/registry/`** → **New application**
2. Enter **FQDN**, display name, proposed site id
3. Copy the **verification token** (shown **once** in the modal)

### 2. Publish challenge (applicant sync env)

Set on the **applicant** sync process only (never mothership `django.env` or `federation-shared.env`):

```bash
FEDERATION_REGISTRY_CHALLENGE_TOKEN=<paste-token-here>
```

Helper (writes env + prints recreate command):

```bash
cd federation
chmod +x scripts/set-registry-challenge.sh
./scripts/set-registry-challenge.sh --token "<paste-token>" --peer
# or: --env-file .env.local | --site-env
```

| Deployment | Env file | Recreate |
|------------|----------|----------|
| Local lab sync | `federation/.env.local` (from `env.local.example`; loaded by `compose.local.yaml` `env_file`) | `docker compose -f compose.local.yaml up -d --force-recreate sds-federation-local-sync` |
| Sync-only peer (e.g. fed1) | `federation/.env.peer` from `env.peer.example` | `compose.peer.local.yaml` / `compose.peer.remote.yaml` |
| Production applicant | `federation/site.env` | production compose for that host |

Sync injects `registry_challenge` into well-known JSON (`well_known.py`); you do **not** edit JSON by hand.

Confirm:

```bash
docker compose ... exec <sync-container> printenv FEDERATION_REGISTRY_CHALLENGE_TOKEN
curl -sS "https://<fqdn>/.well-known/sds-federation.json" | jq '{fqdn, registry_challenge}'
```

### 3. Verify (applicant UI)

On the application detail page → **Verify domain**. On success: **`pending_approval`**; staff get email.

### 4. Wait for staff

No applicant action until approved and manifest published.

---

## Flagship staff workflow

Requires **`is_staff`**. Open **`/users/federation/registry/`**.

| Status | Action |
|--------|--------|
| `pending_approval` | Open application → **Approve** (confirm site id) or **Reject** |
| `approved` (+ any already `published` peers) | **Publish registry** on list page (enabled when sync reports `publish_enabled`) |

**Publish registry** builds the site list from approved/published applications, calls sync internal publish, and marks rows **`published`** with the new manifest serial.

Optional: `FEDERATION_REGISTRY_AUTO_PUBLISH_ON_APPROVE=true` on the gateway runs publish immediately after each **Approve** (default `false`).

Break-glass (no UI): `sds-federation-registry publish --sites-json ...` on flagship sync; then reconcile DB manually if needed.

---

## New peer after publish (join the mesh)

After staff publish, the applicant (and all members) should trust the mothership manifest.

### On the new peer sync

1. **`[registry]`** in `federation.toml` (or render via onboard):

   ```toml
   [registry]
   url = "https://sds.crc.nd.edu/.well-known/sds-registry"
   public_key_path = "/etc/sds/certs/sds-registry.pub.pem"
   refresh_secs = 900
   required = false
   ```

2. Copy **`sds-registry.pub.pem`** from flagship (`federation/certs/`) into peer `federation/certs/` (compose mount).
3. Set **`FEDERATION_REGISTRY_PUBKEY_FINGERPRINT`** on peer sync (optional in well-known; use for operator verification).
4. Set **`FEDERATION_REGISTRY_WELL_KNOWN_URL`** on peer if you want identity JSON to advertise the registry URL.
5. Restart sync; confirm poll in logs (`registry added peer …`) or:

   ```bash
   curl -sS "https://sds.crc.nd.edu/.well-known/sds-registry/sites.json" | jq '.sites[].fqdn'
   ```

Existing members pick up the new peer on their **`registry.refresh_secs`** timer without editing `[[peers]]` (unless they use static overrides).

---

## Manual-only checklist (summary)

| Who | Manual step |
|-----|-------------|
| Applicant | Copy one-time token; set `FEDERATION_REGISTRY_CHALLENGE_TOKEN`; **recreate** sync container |
| Applicant | Click **Verify domain** |
| Staff | **Approve** / **Reject** |
| Staff | **Publish registry** |
| Flagship (once) | Signing key, Traefik routes, doctor green |
| New peer (once) | Registry URL, public key, `[registry]` in toml |

---

## Troubleshooting

Use the full table in [gateway/docs/federation-registry-verify.md#troubleshooting](../../gateway/docs/federation-registry-verify.md#troubleshooting).

Quick hits:

| Symptom | Fix |
|---------|-----|
| `registry_challenge` null | Token missing on **applicant** sync or container not recreated |
| Staff email missing | Celery worker up; `FEDERATION_REGISTRY_STAFF_NOTIFY_EMAILS` or staff accounts |
| **Publish registry** hidden | Sync `publish_enabled` false — key + `[registry.publish]` |
| Peers never see new site | Staff did not publish; wrong `registry.url`; signature / serial trust failure in sync logs |

---

## Local lab pointer

Mothership lab: `SDS_SITE_FQDN` = `FLAGSHIP_GATEWAY_HOST` = `sds.localhost`, gateway `:8000`, sync `:8001`.
Same flow as above; verify doc covers loopback curls and `FEDERATION_REGISTRY_LOCAL_LAB` on sync when applicable.

Registry intake is **separate** from two-peer sync E2E: [scripts/local_e2e/README.md](../scripts/local_e2e/README.md).

---

## Related

+ [gateway/docs/federation-registry-verify.md](../../gateway/docs/federation-registry-verify.md) — verify UI and troubleshooting
+ [peer-remote-test.md](./peer-remote-test.md) — remote sync-only peer
