---
name: yandex-workspace
description: Guide for agents using the Yandex Workspace MCP server
---

# Yandex Workspace Skill

This skill instructs agents on how to best interact with the `yandex-workspace-mcp` server.

## Best Practices

1. **Unified Search First**: To find information across the workspace, always start with `search_workspace` to query both Yandex Disk and Yandex Wiki simultaneously. Use the returned locator/slug to fetch detailed content.
2. **Wiki as Documentation, Disk as Artifacts**: Treat Yandex Wiki as the source of truth for structured documentation, project notes, and dynamic tables. Treat Yandex Disk as the source for raw files, datasets, and binary artifacts.
3. **Safe Wiki Updates (Optimistic Locking)**: Before calling `wiki_update_page` or `wiki_append_page`, you MUST call `wiki_get_page` to retrieve the current content and the `version` (revision). Pass this version back when updating to prevent overwriting someone else's changes.
4. **Destructive Actions**: Do not perform destructive actions (`disk_delete`, `disk_move` with overwrite) without explicit user consent.
5. **Conflict Handling**: If you encounter a `RevisionConflict` when updating a wiki page, re-fetch the page using `wiki_get_page`, merge the user's new content if possible, and try the update again.
6. **Allowed Roots Constraints**: Be aware that your operations are confined to configured `ALLOWED_ROOTS`. Do not attempt to traverse outside these roots, as the operations will be blocked.
7. **Read Before Write**: When asked to make mass changes, first fetch the list of objects (using `disk_list`, `wiki_get_tree`, etc.) and present a plan to the user before executing the write operations.
