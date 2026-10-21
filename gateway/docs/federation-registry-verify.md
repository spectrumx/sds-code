# Federation registry: domain verification

How to apply for federation registry membership on the gateway (mothership intake),
publish a domain-control challenge on the applicant site, and run **Verify domain**.

+ [Federation registry: domain verification](#federation-registry-domain-verification)
    + [Overview](#overview)
    + [Roles](#roles)
    + [Prerequisites](#prerequisites)
    + [Step-by-step](#step-by-step)
        + [1. Start the gateway](#1-start-the-gateway)
        + [2. Create a registry application](#2-create-a-registry-application)
        + [3. Publish the challenge on the applicant site](#3-publish-the-challenge-on-the-applicant-site)
        + [4. Preflight the well-known document](#4-preflight-the-well-known-document)
        + [5. Verify domain](#5-verify-domain)
    + [Local development](#local-development)
    + [Automated tests](#automated-tests)
    + [Troubleshooting](#troubleshooting)
    + [Not implemented yet](#not-implemented-yet)
    + [Related docs](#related-docs)

## Overview

Registry **domain verification** proves that the applicant controls the hostname they
registered. The mothership gateway:

1. Stores a **hashed** challenge when the user applies (raw token shown once in the UI).
2. On **Verify domain**, fetches `https://{fqdn}/.well-known/sds-federation.json` from
   the app container.
3. Checks `registry_challenge` against the stored hash and `fqdn` against the application.
4. On success, sets status to **`pending_approval`** (human approval and signed registry
   manifest are separate work).

Design background: [`federation/docs/federation-registry-design.md`](../../federation/docs/federation-registry-design.md).

## Roles

| Role | Responsibility |
|------|----------------|
| **Mothership** | Logged-in users apply and click **Verify domain** (e.g. CRC gateway). |
| **Applicant** | Serves well-known JSON at the **public FQDN** with the one-time challenge token. |

The same physical gateway can be both mothership and applicant (typical for a single-site
lab test).

## Prerequisites

+ **Flagship host only:** `SDS_SITE_FQDN` must equal **`FLAGSHIP_GATEWAY_HOST`**
  (default `sds.crc.nd.edu`) **and** `FEDERATION_REGISTRY_INTAKE_ENABLED=true`.
  Setting the env var on a peer host has no effect — intake stays off. Peer gateways
  use `FEDERATION_ENABLED` for sync only.
+ Local lab acting as mothership: align `SDS_SITE_FQDN` with `FLAGSHIP_GATEWAY_HOST`
  (e.g. both `sds.localhost` by setting `FLAGSHIP_GATEWAY_HOST=sds.localhost` only on
  that dev machine — never on production peers).
+ Gateway running with migration `0022_registry_application` applied.
+ [OAuth (Auth0) setup](./oauth-setup.md) so you can sign in.
+ Applicant **`SDS_SITE_FQDN`** matches the FQDN on the registry application.
+ **HTTPS** on the applicant FQDN, reachable from the **mothership app container**
  (see [Local development](#local-development)).

## Step-by-step

### 1. Start the gateway

```bash
docker network create sds-network-local   # once, if missing
cd gateway
./scripts/generate-secrets.sh local         # skip if .envs/local already exists
just up
```

> On macOS, `generate-secrets.sh` may warn on `chmod --changes`; env files are still
> valid. Use `just up` if the script exits before starting compose.

### 2. Create a registry application

1. Sign in and open **`/users/federation/registry/`** (or use the user menu link when
   `FEDERATION_ENABLED` is true).
2. **New application** — enter **Site FQDN** (hostname only, no `https://`), display
   name, and proposed site id.
3. On the detail page, copy the **verification token** (shown **once**; not stored in
   the database).

### 3. Publish the challenge on the applicant site

On the **applicant** gateway, set in **`gateway/.envs/local/django.env`** (or production
`django.env`):

```bash
FEDERATION_REGISTRY_CHALLENGE_TOKEN=<paste the one-time token>
```

Ensure **`SDS_SITE_FQDN`** equals the application FQDN.

Recreate the app container so Compose reloads `env_file` ( **`restart` is not enough** ):

```bash
cd gateway
docker compose -f compose.local.yaml up -d --force-recreate sds-gateway-local-app
```

Confirm the variable inside the container:

```bash
docker compose -f compose.local.yaml exec sds-gateway-local-app \
  printenv FEDERATION_REGISTRY_CHALLENGE_TOKEN
```

The well-known builder only includes `registry_challenge` when that setting is non-empty
(see `build_sds_federation_document()` in `api_methods/federation/well_known.py`).

### 4. Preflight the well-known document

**HTTP on port 8000** (sanity check only; verify does not use this URL):

```bash
curl -sS http://localhost:8000/.well-known/sds-federation.json \
  | jq '{fqdn, registry_challenge}'
```

**HTTPS on the application FQDN** (what verify actually uses — run from the mothership
container):

```bash
docker compose -f compose.local.yaml exec sds-gateway-local-app \
  curl -sS "https://<fqdn>/.well-known/sds-federation.json" \
  | jq '{fqdn, registry_challenge}'
```

Expect matching `fqdn` and the same challenge string as in `django.env`.

### 5. Verify domain

On the mothership UI, open the application detail page and click **Verify domain**.

+ **Success:** status **`pending_approval`**, message that the domain is verified.
+ **Failure:** status **`verification_failed`** (retry allowed); see
  [Troubleshooting](#troubleshooting).

## Local development

Default lab: **`SDS_SITE_FQDN=sds.localhost`**, **`ADMIN_CONSOLE_ENV=local`** (default when
`DJANGO_DEBUG=true`), gateway on **`http://localhost:8000`**.

### Local verify without Traefik (same gateway)

When **`ADMIN_CONSOLE_ENV` is `local`** and the application **FQDN equals `SDS_SITE_FQDN`**,
verify fetches well-known over **HTTP** from the app container:

```text
http://sds-gateway-local-app:8000/.well-known/sds-federation.json
```

No HTTPS or `/etc/hosts` entry is required for that case. Requirements:

1. Registry application FQDN = **`sds.localhost`** (or whatever `SDS_SITE_FQDN` is).
2. `FEDERATION_REGISTRY_CHALLENGE_TOKEN` set and app container **recreated** (see step 3).
3. Rebuild/restart the gateway app image so it includes current code.

Optional override: `FEDERATION_REGISTRY_VERIFY_FETCH_BASE` (e.g. second local gateway
container for `peer.local`).

### Other FQDNs or production-like verify

Applications for **other** hostnames still use **`https://{fqdn}/...`** from the
container. Use Traefik ([`network/README.md`](../../network/README.md)), a tunnel, or a
real staging host.

### Continue to federation peer E2E

Registry **`pending_approval`** is separate from **sync peer** testing. After verify
succeeds (or even if you skip registry for sync-only work):

```bash
cd federation
just up                                    # or just deploy-local-peer-2-peer
# see federation/scripts/local_e2e/README.md
just verify-federation-live
```

Align `federation.toml` `[site].fqdn` with `SDS_SITE_FQDN` and `FEDERATION_SITE_NAME`
with `django.env`.

For federation **sync** live tests (export/webhook), see
[`federation/scripts/local_e2e/README.md`](../../federation/scripts/local_e2e/README.md).

## Automated tests

From `gateway/`:

```bash
just test-py sds_gateway/api_methods/tests/test_registry_application_verify.py \
  sds_gateway/api_methods/tests/test_registry_challenge.py \
  sds_gateway/api_methods/tests/test_federation_well_known.py \
  sds_gateway/users/tests/test_registry_application_form.py
```

Quote the `-k` expression so the shell does not split on `or`:

```bash
just test-py -k 'registry_application or federation_well_known'
```

## Troubleshooting

| Message / behavior | What to check |
|------------------|----------------|
| `registry_challenge` is null in JSON | Token not in `django.env`, or container not **recreated** after edit. |
| Challenge mismatch | Token in env ≠ token from apply; re-apply and update env. |
| `fqdn` mismatch | `SDS_SITE_FQDN` and JSON `fqdn` ≠ application FQDN. |
| Challenge expired | Default ~72h; use **Issue new verification token** on the application page. |
| Could not fetch well-known | HTTPS/DNS/TLS from app container to `https://<fqdn>/...`. |
| Duplicate FQDN | Another open application exists for that hostname. |

**Lost the one-time token:** create a new application (or clear the old row) and set a
new `FEDERATION_REGISTRY_CHALLENGE_TOKEN`.

## Staff approval

Requires a user with **`is_staff`** (e.g. `createsuperuser`).

1. Open **`/users/federation/registry/`** — staff see **all** applications in the list.
2. Open a row with status **`pending_approval`**.
3. On the detail page, use the **Staff review** card: **Approve application** (optional site id) or **Reject application**.

URL: `/users/federation/registry/applications/<uuid>/`.

Approval sets status **`approved`** and `site_name`; it does **not** publish the signed registry manifest automatically.

## Publish signed registry (flagship)

After one or more applications are **`approved`**, staff publish the manifest:

1. Set **`FEDERATION_REGISTRY_SIGNING_KEY_PATH`** (Ed25519 private PEM) and optional
   **`FEDERATION_REGISTRY_MANIFEST_STORAGE_DIR`** (default: `{BASE_DIR}/registry_manifest`).
2. On **`/users/federation/registry/`**, click **Publish signed registry** (staff, flagship host only), **or** run:
   `python manage.py publish_registry_manifest`
3. Peers fetch:
   + `/.well-known/sds-registry/sites.json`
   + `/.well-known/sds-registry/sites.json.sig` (base64 Ed25519 over the raw JSON bytes)

Publish bumps **`serial`**, writes the files, and moves **`approved`** rows to **`published`**.

Fingerprint for well-known / peers: `python manage.py registry_pubkey_fingerprint`.

## Challenge reissue and withdraw

On the application detail page (before staff approval), applicants can:

+ **Issue new verification token** — new `registry_challenge` hash and 72h expiry; token shown once in the modal.
+ **Withdraw application** — releases the FQDN so a new application can be submitted.

## Not implemented yet

+ `well_known_path` challenge method (ACME-style path).
+ DRF API for applications (UI only today).

## Related docs

+ [Federation registry design](../../federation/docs/federation-registry-design.md)
+ [Federation README](../../federation/README.md) (peers, well-known, `--discover`)
+ [Network / Traefik / TLS](../../network/README.md)
+ [OAuth setup](./oauth-setup.md)
