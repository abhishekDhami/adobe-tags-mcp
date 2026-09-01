# Security policy

## Supported versions

Security fixes are applied to the latest version on the default branch.

## Reporting a vulnerability

Do not open a public issue for a suspected vulnerability or for exposed
credentials. Contact the repository maintainer privately with the affected
version, a clear description, and safe reproduction steps. Do not include
Adobe credentials, access tokens, API keys, or customer data.

## Local credential handling

This project is designed to run locally. Keep Adobe credentials in `api/.env`
only; do not add them to MCP client settings, source code, screenshots, logs,
or issues. `api/.env`, `mcp/.env`, and the local `data/` directory are ignored
by Git.

The API is intentionally limited to loopback hosts. Do not expose it through a
tunnel or public network interface. When using `user_oauth`, configure a
`VAULT_KEY` so the local OAuth session file is encrypted at rest.
