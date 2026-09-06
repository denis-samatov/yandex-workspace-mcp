# Contributing

Thanks for considering an improvement to Yandex Workspace MCP.

## Before opening a pull request

1. Open an issue for behavior changes or new tools so the scope and permission model can be discussed first.
2. Keep the server read-only by default. New write or destructive behavior must have an explicit configuration gate, allowlist checks, and audit coverage.
3. Never include real OAuth tokens, organization identifiers, private workspace paths, or production documents in fixtures, logs, screenshots, or examples.

## Local checks

```bash
uv sync --all-extras
uv run ruff check .
uv run pytest
uv run python scripts/check_tool_matrix.py
```

If a change affects authentication, deployment, permissions, or API drift, update the corresponding documentation under `docs/` and add focused tests.

## Pull requests

- Describe the user-visible behavior and security boundary.
- Link the related issue.
- Include tests for success, denial, and upstream failure paths where applicable.
- Keep unrelated formatting or dependency changes out of the same pull request.
