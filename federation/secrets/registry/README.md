# Registry signing key (flagship sync only)

Place the Ed25519 **private** signing key here as `sign.pem` (mode `600` on the host).

- **Container path:** `/etc/sds/secrets/registry/sign.pem` (see `[registry.publish]` in `federation.toml`)
- **Generate:** `uv run sds-federation-registry generate-keypair --out-dir .` (from `federation/`, then move keys appropriately)
- **Migrate from gateway:** copy the same PEM previously mounted at `FEDERATION_REGISTRY_SIGNING_KEY_PATH` on the gateway app container.

Publish the public key to `federation/certs/sds-registry.pub.pem` (or your site name) and set
`FEDERATION_REGISTRY_PUBKEY_FINGERPRINT` on the sync process:

```bash
uv run sds-federation-registry fingerprint /path/to/sds-registry.pub.pem
```

This directory is gitignored; never commit `sign.pem`.
