#!/usr/bin/env bash
cat <<'EOF'
Usage: just deploy [OPTIONS] [ENV]

Run a full SDS Gateway deployment for the selected environment.

ENV may be local, production, or ci. When omitted, the environment is
auto-detected (see `just env`).

On first deploy (except ci), creates scripts/prod-hostnames.env and prompts
whether this machine is a production host.

This recipe wraps ./scripts/deploy.sh and forwards supported OPTIONS:

    --auto-gen-prod-env    Auto-generate production environment secrets
    -f, --force            Overwrite existing env files when generating secrets
    -s, --skip-secrets     Skip secret generation (use existing secrets)
    -n, --skip-network     Skip network creation
    --skip-sfs             Skip SeaweedFS stack deployment
    -d, --detach           Run services in detached mode (default for prod)

Examples:
    just deploy
    just deploy local
    just deploy --force production
    just deploy ci --skip-secrets

Notes:
    - Use `just redeploy` for quick rebuilds after the initial deploy
    - For deploy.sh details: ./scripts/deploy.sh --help
EOF
