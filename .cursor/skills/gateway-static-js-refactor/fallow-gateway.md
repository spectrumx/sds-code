# Fallow (gateway)

Run all commands from `gateway/` (config: `.fallowrc.json`). Ignores `sds_gateway/static/js/deprecated/**`.

## Dependencies

fallow requires node ^24.0, it will fail if you have a default node of v26 installed, for example.
If you have trouble doing a git commit from a GUI client, you may need to install nove v24 globally,
or use nvm to set the version and run git commit from the command line.

For Linux:

```bash
apt install node
```

For MacOS:

```bash
brew install node
```

```bash
nvm use 24.19.0
nvm alias default 24.19.0
```

## npm scripts

| Script | Purpose |
|--------|---------|
| `npm run fallow` | `fallow --summary` (overview) |
| `npm run fallow:static-js` | Dead-code per file under `static/js/` (full graph, scoped reporting) |

## Commands to use in refactors

```bash
# Summary / combined view
npm run fallow

# Cyclomatic + cognitive hotspots (prioritize splits)
npx fallow health --format human
npx fallow health --format json -q   # machine-readable

# Clone groups (in-file and cross-file)
npx fallow dupes --format human
npx fallow dupes --format json -q

# Unused exports / cycles (static/js scoped via script)
npm run fallow:static-js
npx fallow dead-code --format human

# Changed-files gate (PR-sized work)
npx fallow audit --changed-since main --format human
```

## CI / pre-commit (must stay green)

```bash
bash scripts/fallow-cross-file-dupes.sh
```

Fails if any clone group spans **more than one file**. Fixing usually means shared helper or single canonical implementation.

## Interpreting results

| Signal | Typical refactor move |
|--------|------------------------|
| High cognitive/cyclomatic on one function | Extract helpers; early return; reduce branches |
| Dupes across files | Shared util or generalize existing manager method |
| Dead export after refactor | Remove export or wire usage; re-run `fallow:static-js` |
| `audit --changed-since` only on touched files | Use while iterating; run full dupes/health before merge |

## Config notes

- `ignoreExportsUsedInFile: true` — same-file-only usage may not count as “used” for export pruning; prefer explicit exports only where needed.
- Do not add `deprecated/` paths to analysis scope for fixes.

## Optional

```bash
npx fallow config    # resolved config path
npx fallow list      # entry points / discovered files
npx fallow explain <issue-type>
```

For agent tooling: `npx fallow schema` (CLI JSON).
