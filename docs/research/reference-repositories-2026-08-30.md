# Yandex MCP reference-source review (2026-08-30)

This note records the source-level comparison used by the reference-parity
implementation. It is deliberately commit-pinned: repository names and README
claims are not treated as stable API evidence.

## Sources inspected

| Project | Inspected commit | Useful evidence | Decision |
|---|---|---|---|
| `dlbolshov/yandex-wiki-search-mcp` | `0bce3d3` (1.5.0) | Wiki wire methods, typed envelopes, live drift notes, bounded clone polling, OAuth/store lifecycle | Primary current Wiki drift reference; reimplement contracts, do not copy its monolithic client or unrestricted local paths |
| `APonkratov/yandex-wiki-mcp` | `18f033f` | Earlier page/comment/resource/attachment/grid/recovery implementation | Historical cross-check for grid and upload-session payloads; it predates search and clone support |
| `slartus/mcp-yandex-wiki` | `f1a0f04` | Small independently live-tested `/v1/search`, page and collection implementation | Independent search/auth observation only; its raw-dict surface and minimal error policy are not adopted |
| `n-r-w/yandex-mcp` | `c23c3d0` | Read-only Go client, bounded response reading, `yc` IAM-token refresh with singleflight | Use the credential-provider shape and response caps; do not generalize its auth retry to mutations |
| `bim-ba/ycli` | `5c434db` | Resource subclients, dependency injection, cursor self-loop guards, operation polling, honest MCP annotations | Confirms the client/domain/MCP split and bounded pagination policy; no Disk implementation is available |
| `Patr56/yadisk-mcp` | `ce98ecb` | Exact 22-tool Disk feature inventory and local background-job UX | Primary Disk surface reference; retain our stricter typed clients, lifecycle, root policy and transfer security |
| `gorokhovdenis/yandex-disk-mcp` | `af03690` | Ten-operation raw REST example | Endpoint-name cross-check only; defaults, raw errors and missing policy are not production-safe |
| `theYahia/yandex-360-mcp` | `354d6e2` | One server spanning Yandex 360 domains; two Disk tools | Confirms unified-workspace demand, but its direct signed-URL fetch and text-only upload are not a safety reference |
| `yandex-cloud/mcp` | `28e6c80` | Official stdio proxy and remote Streamable HTTP/IAM deployment documentation | Deployment/auth UX reference only: the public repository contains server documentation, not the service implementation |

No third-party source code is copied into this project. The implementation is
independent and is verified through local contract tests and an optional live
scratch sweep.

## Wiki findings

### Search is documented, but still drift-prone

The official Wiki reference now documents `POST /v1/search`, including
`cursor`, `limit`, filters, ordering and highlighting. The latest inspected
`dlbolshov` source and its live notes report a split wire behavior: default mode
returns the top results without useful cursors, while `highlight=true` selects a
different paginated behavior. That finding is newer than the approved
compatibility contract.

For this release the public `wiki_search(query, limit, page)` schema remains
compatible: `page` uses the bounded deterministic slice and standalone cursor
input remains reserved. The live sweep must probe both documented cursor fields
and observed response cursors. Enabling a new public pagination mode requires
tenant evidence plus a versioned compatibility decision; documentation alone
must not silently change existing results.

### Wire operations and response shapes

The current and historical Wiki references agree on these important details:

- page updates use `POST /v1/pages/{id}`, not `PATCH` or `PUT`;
- descendants, comments, resources, attachments and grids use cursor envelopes;
- page attachment upload uses upload sessions, numbered parts, finish, and an
  attachment-finalization request;
- page clone is asynchronous and returns a status URL that must be polled;
- grid writes are revision-sensitive and conflicts must not be replayed;
- grid update and most row/column mutations return revision-oriented envelopes,
  while cell updates and row creation have distinct result shapes;
- delete/recovery uses an upstream recovery token.

The target keeps the stricter decisions that the reference implementations do
not provide: page/grid owner resolution before authorization, exact allowed-root
segment checks, opaque principal-bound recovery handles, immutable per-request
credentials, no mutation retry, exact-origin operation URLs, and descriptor-safe
local files.

### Current reference features outside the approved 27-tool surface

`dlbolshov` 1.5.0 has grown beyond the commit used for the approved manifest. It
also contains current-user lookup, comment deletion, attachment deletion,
attachment reading/downloading, redirect editing and additional search filters.
These are useful future candidates but are not silently added here: the agreed
surface is the exact 27-tool Wiki parity set plus `wiki_get_tree`, with explicit
permission and local/remote registration matrices.

## Disk findings

`Patr56/yadisk-mcp` provides the feature inventory adopted by the approved
22-tool Disk manifest: quota, list/recent/search/metadata, folder and path
mutations, foreground/background upload jobs, URL upload, public sharing, and
Trash operations. Its tests also call out useful failure cases such as root
permanent deletion, rename separator injection, job-ID collisions and error
redaction.

Several implementation details are intentionally replaced rather than copied:

- `realpath()` followed by a later open is vulnerable to path-swap races; this
  project walks and opens descriptors under explicit roots and streams the
  already-open handle;
- an unset upload allowlist in the reference permits every local path; this
  project omits local-file tools when the allowlist is empty;
- accepting HTTP and merely rejecting a few localhost/link-local strings is not
  a sufficient URL-upload boundary; this project requires HTTPS plus exact
  configured hostnames for server-side URL fetches;
- signed Yandex upload/download links require a separate tokenless client,
  redirect refusal, suffix and DNS validation, connected-peer verification,
  and byte/time caps;
- a module-global job dictionary and detached `create_task()` calls do not give
  deterministic shutdown or per-principal isolation; this project uses a
  lifespan-owned bounded job store with ownership and cancellation rules;
- every source and destination path is authorized against remote roots, and
  global Trash deletion is separately gated.

The smaller TypeScript Disk implementations confirm the basic REST endpoint
names but add no stronger contract or security evidence.

## Production/auth findings

The inspected projects reinforce three production rules already present in the
design:

1. API clients receive credentials explicitly and do not mutate shared default
   headers per request.
2. IAM credentials are short-lived and need a concurrency-safe refresh provider;
   a singleflight refresh avoids duplicate `yc` invocations.
3. Local stdio and remote Streamable HTTP are different trust modes. The official
   Yandex Cloud distribution documents browser OAuth/`yc` for its local proxy and
   bearer IAM tokens for hosted Streamable HTTP endpoints, but does not publish
   the hosted server implementation for source reuse.

The production increment therefore keeps MCP bearer validation separate from
downstream Yandex OAuth/IAM credentials, pins organization selection to trusted
configuration/account mappings, owns stores and clients in application lifespan,
and rejects remote deployments that lack persistent cryptographic keys.

## Implementation checklist derived from the comparison

- [x] Preserve real Wiki `POST /v1/search` with typed drift classification and
  a bounded descendants fallback.
- [x] Implement typed Wiki page, collection, recovery, attachment and grid
  clients with exact registration gates.
- [x] Exercise every implemented Wiki method in the opt-in sweep with
  unconditional cleanup; the separate documented/observed search cursor-mode
  probe remains pending live-tenant evidence.
- [x] Implement the exact 22-tool Disk manifest using the shared path, cursor,
  signed-transfer and operation-polling foundations.
- [x] Implement bounded, owner-bound background jobs with deterministic shutdown.
- [ ] Finish static bearer, OAuth, IAM refresh, Redis/store isolation and remote
  transport hardening.
- [ ] Run the full cross-platform/static/package acceptance matrix; live tenant
  verification remains separately secret-gated.
