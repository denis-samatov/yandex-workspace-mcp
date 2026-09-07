# Minimal read-only quick start

## 1. Install the locked environment

Use Python 3.12 or 3.13 and run from the repository root:

```bash
uv sync --frozen
uv run python examples/permission_demo.py
```

The example needs no token and makes no network requests. Expected status lines (structured audit logs may also be printed):

```text
READ_ONLY_WRITE: denied; upstream calls=0
OUTSIDE_ALLOWED_ROOT: denied; upstream calls=0
ALLOWED_WRITE: accepted by mock; upstream calls=1
```

These are service-layer checks against an `AsyncMock`, not an MCP wire transcript or a live Yandex test. Read the [source](../examples/permission_demo.py) and [regression tests](../tests/security/test_permission_gating.py).

## 2. Configure a local Disk-only session

Copy `.env.example` to `.env`, then set the following values in that file. Replace the token locally and choose an existing Disk subtree you intend to expose:

```dotenv
YANDEX_OAUTH_TOKEN=replace-locally
YANDEX_DISK_ENABLED=true
YANDEX_WIKI_ENABLED=false
MCP_TRANSPORT=stdio
DISK_READ=true
DISK_WRITE=false
DISK_DELETE=false
DISK_ALLOWED_ROOTS=/Work
```

Run diagnostics before connecting your MCP client:

```bash
uv run yandex-workspace-mcp doctor
uv run yandex-workspace-mcp
```

With stdio, the MCP client normally starts the process. Use the command/args structure in the [README](../README.md#client-configuration-claude-desktop--cursor), with the absolute clone path. Keep credentials in local configuration and outside Git.

An initial read request is `disk_list` for a path under `/Work`; tool availability follows the enabled service and permission flags. Do not enable write/delete merely to try the server.

## 3. Understand the validation boundary

| Check | What it establishes | What it does not establish |
| --- | --- | --- |
| Offline example | Writes are gated before the mocked upstream call | Live API behavior or transport/authentication correctness |
| Security and contract tests | Regression coverage for implemented policies and typed responses | Guaranteed security or compatibility with future API changes |
| Opt-in live contract sweep | Behavior on explicitly supplied scratch subtrees | Production capacity or correctness on every workspace |
| Your staging deployment | Behavior under your credentials, roots, workload, and transport | A universal production-readiness claim |

For HTTP transport, use the [deployment guide](deployment.md) and [authentication guide](authentication.md); the local stdio example is not an HTTP deployment recipe.
