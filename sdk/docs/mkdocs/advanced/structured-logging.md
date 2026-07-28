# Structured Logging

The SDK writes structured JSONL logs to `~/.local/state/spectrumx/logs/YYYY-MM-DD.jsonl`.
Each line is a JSON object with fields like `ts`, `pid`, `lvl`, `cat`, and `msg`.

## Custom log file location

By default, logs are written to `~/.local/state/spectrumx/logs/`. Use `log_file` to
redirect them to a project-specific path — useful for isolating logs per project,
running multiple SDK instances, or keeping logs alongside your data:

```python
from spectrumx import Client
from pathlib import Path

# Log next to your data files
sds = Client(
    host=SDS_HOST,
    log_file=Path("my_spectrum_files") / "sdk.log",
)

# Per-project logs in a dedicated directory
sds = Client(
    host=SDS_HOST,
    log_file=Path("logs") / "spectrumx.log",
)

# Combine with other client options
sds = Client(
    host=SDS_HOST,
    env_file=Path(".env"),            # default
    env_config={"SDS_SECRET_TOKEN": "my-custom-token"},  # overrides
    log_file=Path("my_spectrum_files") / "sdk.log",
)
```

!!! note
    The `log_file` parameter accepts any `Path` or string path. Parent directories
    are created automatically if they don't exist. The file is opened in append
    mode, so logs accumulate across restarts.

## Filtering with jq

Use [`jq`](https://jqlang.org/) to filter and analyze log files on the command line.

### By category

```bash
# Filesystem operations only
jq 'select(.cat == "filesystem")' ~/.local/state/spectrumx/logs/2026-06-29.jsonl

# Network operations
jq 'select(.cat == "network")' ~/.local/state/spectrumx/logs/2026-06-29.jsonl

# Upload-specific messages
jq 'select(.cat == "upload")' ~/.local/state/spectrumx/logs/2026-06-29.jsonl

# Download-specific messages
jq 'select(.cat == "download")' ~/.local/state/spectrumx/logs/2026-06-29.jsonl

# Auth messages
jq 'select(.cat == "auth")' ~/.local/state/spectrumx/logs/2026-06-29.jsonl

# Config messages
jq 'select(.cat == "config")' ~/.local/state/spectrumx/logs/2026-06-29.jsonl
```

### By severity

```bash
# Warnings and errors only
jq 'select(.lvl == "WARNING" or .lvl == "ERROR")' ~/.local/state/spectrumx/logs/2026-06-29.jsonl

# Errors only with full exception info
jq 'select(.lvl == "ERROR")' ~/.local/state/spectrumx/logs/2026-06-29.jsonl
```

### Compound filters

```bash
# Filesystem warnings and errors
jq 'select(.cat == "filesystem" and (.lvl == "WARNING" or .lvl == "ERROR"))' ~/.local/state/spectrumx/logs/2026-06-29.jsonl

# Everything except generic "log" category
jq 'select(.cat != "log")' ~/.local/state/spectrumx/logs/2026-06-29.jsonl

# Messages with exception details
jq 'select(.exc_info != null)' ~/.local/state/spectrumx/logs/2026-06-29.jsonl
```

### Aggregations

```bash
# Count messages per category
jq -r '.cat' ~/.local/state/spectrumx/logs/2026-06-29.jsonl | sort | uniq -c | sort -rn

# Count messages per severity level
jq -r '.lvl' ~/.local/state/spectrumx/logs/2026-06-29.jsonl | sort | uniq -c | sort -rn

# Extract just the messages for a category
jq -r 'select(.cat == "network") | .msg' ~/.local/state/spectrumx/logs/2026-06-29.jsonl
```

### Pretty-print and format

```bash
# Colorized output (jq highlights strings by default)
jq . ~/.local/state/spectrumx/logs/2026-06-29.jsonl

# Compact view: timestamp + level + category + message
jq -r '"\(.ts[11:19]) [\(.lvl)] [\(.cat)] \(.msg)"' ~/.local/state/spectrumx/logs/2026-06-29.jsonl

# Tabular output with header
jq -r '["TS","LVL","CAT","MSG"], ["---","---","---","---"], (.[] | [.ts[11:19], .lvl, .cat, .msg]) | @tsv' ~/.local/state/spectrumx/logs/2026-06-29.jsonl | column -t -s $'\t'
```

### Watch in real time

```bash
# Tail and filter: show only filesystem logs as they arrive
tail -f ~/.local/state/spectrumx/logs/2026-06-29.jsonl | jq 'select(.cat == "filesystem")'

# Tail with compact format
tail -f ~/.local/state/spectrumx/logs/2026-06-29.jsonl | jq -r '"\(.ts[11:19]) [\(.lvl)] [\(.cat)] \(.msg)"'
```

## Log categories reference

| Category     | Description                     | Examples                              |
|--------------|---------------------------------|---------------------------------------|
| `log`        | Generic/default messages        | Dry-run notices, user-facing messages |
| `config`     | SDK configuration               | Config loading, env variable warnings |
| `auth`       | Authentication operations       | Token validation, auth success/failure|
| `network`    | HTTP/network operations         | Response info, connection errors      |
| `filesystem` | File and capture CRUD           | Upload/download paths, capture ops    |
| `download`   | File download operations        | Download skip/reason, dry-run notices, path resolution |
| `upload`     | File upload metadata operations | Upload status, metadata updates       |
