# Federation scripts

| Location | Purpose |
|----------|---------|
| `bin/` | Operator entrypoints (onboard, doctor, render, registry helpers) — use via `just` |
| `lib/` | Shared bash helpers and `env-selection.sh` (sourced, not run directly) |
| `*.py` | Python helpers invoked by bash or `just` |
| `local_e2e/` | Local end-to-end lab notes and env example |

Examples:

```bash
just federation-onboard
just federation-preflight-apply
./scripts/bin/federation-join-registry.sh --token "$TOKEN" --site-env
./scripts/bin/federation-join-registry.sh --preflight --site-env
```