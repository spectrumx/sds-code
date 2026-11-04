# Federation registry: domain verification

How to apply for federation registry membership on the gateway (mothership intake),
publish a domain-control challenge on the applicant site, and click **Verify domain** in the gateway UI (verification runs on **federation sync**).

+ [Federation registry: domain verification](#federation-registry-domain-verification)
    + [Overview](#overview)
    + [Roles](#roles)
    + [Prerequisites](#prerequisites)
    + [Step-by-step](#step-by-step)
        + [1. Start the gateway](#1-start-the-gateway)
        + [2. Create a registry application](#2-create-a-registry-application)
        + [3. Publish the challenge on the applicant site](#3-publish-the-challenge-on-the-applicant-site)
        + [4. Preflight the well-known document](#4-preflight-the-well-known-document)
        + [5. Verify domain (UI)](#5-verify-domain-ui)
    + [Local development](#local-development)
    + [Automated tests](#automated-tests)
    + [Troubleshooting](#troubleshooting)
    + [Not implemented yet](#not-implemented-yet)
    + [Related docs](#related-docs)

## Overview

Registry **domain verification** proves that the applicant controls the hostname they
registered. The mothership gateway:

1. Stores a **hashed** challenge when the user applies (raw token shown once in the UI).
2. On **Verify domain**, the gateway calls federation sync `POST /internal/registry/verify`
   (challenge hash only; sync fetches applicant well-known).
3. On success, status becomes **`pending_approval`** (staff approval and manifest publish are separate).

Gateway django does **not** fetch well-known JSON, sign manifests, or publish locally.

## Roles

| Role | Responsibility |
|------|----------------|
| **Mothership** | Registry intake UI; applicants click **Verify domain** (gateway → sync internal API). |
| **Applicant** | Serves well-known JSON at the **public FQDN** with the one-time challenge token (via **sync** env). |
| **Staff** | Approve applications; record publish serial after sync manifest publish. |

The same physical host can be mothership gateway + applicant sync (typical lab).

## Prerequisites

+ **Flagship host only:** `SDS_SITE_FQDN` must equal **`FLAGSHIP_GATEWAY_HOST`**
  (default `sds.crc.nd.edu`) **and** `FEDERATION_REGISTRY_INTAKE_ENABLED=true`.
+ Local lab mothership: align `SDS_SITE_FQDN` with `FLAGSHIP_GATEWAY_HOST`
  (e.g. both `sds.localhost` on that dev machine only).
+ Gateway migration `0022_registry_application` applied; [OAuth](./oauth-setup.md) for sign-in.
+ Gateway `FEDERATION_SYNC_INTERNAL_URL` (e.g. `http://sds-federation-local-sync:8000`) and
  `FEDERATION_SYNC_ADMIN_TOKEN` in `federation-shared.env` (compose loads both on app + sync).
+ Applicant **`SDS_SITE_FQDN`** matches the registry application FQDN.
+ **HTTPS** on the applicant FQDN, reachable from the **sync** container doing verify.

## Step-by-step

### 1. Start the gateway

```bash
docker network create sds-network-local   # once, if missing
cd gateway
./scripts/generate-secrets.sh local         # skip if .envs/local already exists
just up
```

### 2. Create a registry application

1. Sign in and open **`/users/federation/registry/`**.
2. **New application** — **Site FQDN**, display name, proposed site id.
3. Copy the **verification token** (shown **once**).

### 3. Publish the challenge on the applicant site

Set `FEDERATION_REGISTRY_CHALLENGE_TOKEN` on the process that serves
`GET /.well-known/sds-federation.json` at the application **FQDN** — almost always
**federation sync** (`federation/.env.local`, `.env.peer`, or production `site.env`).

#### Local lab (sync serves well-known)

```bash
cd federation
# FEDERATION_REGISTRY_CHALLENGE_TOKEN=<token> in .env.local or env file for compose
docker compose -f compose.local.yaml up -d --force-recreate sds-federation-local-sync
```

#### Sync-only peer

See [`federation/env.peer.example`](../../federation/env.peer.example) and
[`federation/docs/peer-remote-test.md`](../../federation/docs/peer-remote-test.md).

Do **not** put the applicant token in mothership `django.env` or `federation-shared.env`.

Confirm inside the serving container:

```bash
docker compose -f compose.local.yaml exec sds-federation-local-sync \
  printenv FEDERATION_REGISTRY_CHALLENGE_TOKEN
```

Well-known JSON is built in `federation/sds_federation/services/well_known.py` (includes
`registry_challenge` when the env var is set).

### 4. Preflight the well-known document

From a host that can reach the applicant FQDN (or from sync):

```bash
curl -sS "https://<fqdn>/.well-known/sds-federation.json" \
  | jq '{fqdn, registry_challenge}'
```

Expect matching `fqdn` and the same challenge string as in sync env.

Local sync port (sanity check on loopback):

```bash
curl -sS http://localhost:8001/.well-known/sds-federation.json | jq '{fqdn, registry_challenge}'
```

### 5. Verify domain (UI)

On the application detail page, click **Verify domain** (applicant only).

The gateway calls flagship sync internal verify; sync fetches `https://{fqdn}/.well-known/sds-federation.json`.

+ **Success:** status **`pending_approval`**.
+ **Failure:** status **`verification_failed`**; message on the page — fix well-known and retry.

Optional manual curl (same API the UI uses):

```bash
curl -sS -X POST "http://localhost:8001/internal/registry/verify" \
  -H "Authorization: Bearer $(grep '^FEDERATION_SYNC_ADMIN_TOKEN=' ../federation-shared.env | cut -d= -f2-)" \
  -H "Content-Type: application/json" \
  -d '{"fqdn":"<application-fqdn>","challenge_hash":"<hash from DB>"}'
```

## Local development

Default lab: **`SDS_SITE_FQDN=sds.localhost`**, gateway **`http://localhost:8000`**, sync
**`http://localhost:8001`**.

1. Start gateway + federation sync (`cd federation && just up`).
2. Application FQDN = applicant `SDS_SITE_FQDN` in sync/federation config.
3. Challenge token on **sync**, recreate sync after env edits.

Registry **`pending_approval`** is separate from sync **peer** E2E; see
[`federation/scripts/local_e2e/README.md`](../../federation/scripts/local_e2e/README.md).

## Automated tests

From `gateway/`:

```bash
just test-py sds_gateway/api_methods/tests/test_registry_application_verify.py \
  sds_gateway/api_methods/tests/test_federation_sync_client.py \
  sds_gateway/api_methods/tests/test_registry_challenge.py \
  sds_gateway/users/tests/test_registry_application_verify_view.py \
  sds_gateway/users/tests/test_registry_application_form.py
```

Federation verify engine tests: `federation/tests/test_registry_verify.py`.

## Troubleshooting

| Message / behavior | What to check |
|------------------|----------------|
| `registry_challenge` is null in JSON | Token not set on **applicant sync**, or container not **recreated** after edit. |
| Challenge mismatch | Token in env ≠ token from apply; re-apply and update sync env. |
| `fqdn` mismatch | Sync/federation `SDS_SITE_FQDN` and JSON `fqdn` ≠ application FQDN. |
| Challenge expired | Default ~72h; **Issue new verification token** on the application page. |
| Sync verify fetch error | HTTPS/DNS/TLS from **sync** container to `https://<fqdn>/...`. |
| Duplicate FQDN | Another open application exists for that hostname. |

**Lost the one-time token:** new application (or withdraw old) and set a new challenge on sync.

## Staff approval

Requires **`is_staff`**.

1. **`/users/federation/registry/`** — staff see all applications.
2. **`pending_approval`** → **Approve application** (optional site id) or **Reject**.

Approval sets **`approved`** and `site_name`; it does not publish the signed manifest.

## Publish signed registry (flagship)

Signing and manifest files live on **federation sync** (`[registry.publish]` in
`federation.toml`, signing key volume). Gateway only records the outcome in the DB.

1. Enable publish on sync; `FEDERATION_SYNC_ADMIN_TOKEN` in `federation-shared.env`.
2. Build site list from approved applications; call sync:

```bash
curl -sS -X POST "http://localhost:8001/internal/registry/publish" \
  -H "Authorization: Bearer $(grep '^FEDERATION_SYNC_ADMIN_TOKEN=' ../federation-shared.env | cut -d= -f2-)" \
  -H "Content-Type: application/json" \
  -d '{"sites":[...],"min_serial":null,"dry_run":false}'
```

3. On **`/users/federation/registry/`**, staff enter the returned **`serial`** and click
   **Record publish** (marks **`approved`** rows **`published`**).

Peers fetch from flagship sync (Traefik):

+ `/.well-known/sds-registry/sites.json`
+ `/.well-known/sds-registry/sites.json.sig`

Fingerprint: `uv run sds-federation-registry fingerprint --public-key-path certs/sds-registry.pub.pem`
→ `FEDERATION_REGISTRY_PUBKEY_FINGERPRINT` on sync.

## Challenge reissue and withdraw

Applicants (before staff approval):

+ **Issue new verification token** — new hash and 72h expiry; update sync env with new token.
+ **Withdraw application** — releases the FQDN.

## Not implemented yet

+ `well_known_path` challenge method (ACME-style path).
+ DRF API for applications (UI only today).
+ Gateway UI for manifest publish (staff **Record publish** after sync CLI/API).

## Related docs

+ [Federation README](../../federation/README.md)
+ [Registry sync refactor plan](../../federation/docs/registry-sync-refactor-plan.md)
+ [Network / Traefik / TLS](../../network/README.md)
+ [OAuth setup](./oauth-setup.md)
