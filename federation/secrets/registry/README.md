# Registry signing key (flagship sync only)

Operator workflow: [../../docs/federation-operator-runbook.md](../../docs/federation-operator-runbook.md).

Place the Ed25519 **private** signing key here as `sign.pem` (mode `600` on the host).

- **Container path:** `/etc/sds/secrets/registry/sign.pem` (see `[registry.publish]` in `federation.toml`)
- **Generate:** `uv run sds-federation-registry keygen --out-dir .` (from `federation/`, writes `sign.pem` and `registry.pub.pem`; place keys per paths below)
- **Migrate from gateway:** copy the same PEM previously mounted at `FEDERATION_REGISTRY_SIGNING_KEY_PATH` on the gateway app container.

Publish the public key to `federation/certs/sds-registry.pub.pem` (or your site name) and set
`FEDERATION_REGISTRY_PUBKEY_FINGERPRINT` on the sync process:

```bash
uv run sds-federation-registry fingerprint --public-key-path certs/sds-registry.pub.pem
```

This directory is gitignored; never commit `sign.pem`.
