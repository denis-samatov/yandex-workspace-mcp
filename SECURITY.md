# Security Policy

## Supported versions

This project does not yet have tagged releases or maintained version
branches — only `main` is supported. Security fixes land on `main`.

## Reporting a vulnerability

Please **do not** open a public GitHub issue for security vulnerabilities.

Instead, use GitHub's private vulnerability reporting: go to the
[Security tab](../../security/advisories/new) of this repository and click
"Report a vulnerability". This opens a private conversation with the
maintainer and lets you attach a fix if you have one, without disclosing the
issue publicly first.

Please include:

- A description of the vulnerability and its potential impact.
- Steps to reproduce, or a minimal proof of concept.
- The affected file(s)/tool(s), if known.

There is no fixed SLA for a first response, but reports are read as they
arrive.

## Security design

See [`docs/security.md`](docs/security.md) for how this server enforces
read-only-by-default access, path allowlisting, SSRF-safe upload/download,
and audit logging. Those properties are covered by tests in
[`tests/security/`](tests/security/).

## Known limitations

- `wiki_update_page` does not implement optimistic locking (see the
  Limitations section of [`README.md`](README.md)); concurrent writers to
  the same page can overwrite each other's changes. This is a data-integrity
  risk, not a vulnerability that exposes data to unauthorized parties.
