# Adobe Tags MCP: project context

## Purpose

Adobe Tags MCP is an independent, local-first Model Context Protocol (MCP)
server for reviewing Adobe Experience Platform Tags (Reactor) configuration
with AI clients such as ChatGPT Desktop and Cursor.

It helps practitioners inspect properties, rules, data elements, extensions,
libraries, revisions, deployments, dependencies, and resource usage. It is
not an official Adobe product or a replacement for the Adobe Tags interface.

## What it does not do

Adobe Tags resources are read-only through this project. It does not create,
update, delete, build, approve, submit, or publish Adobe Tags resources.

The MCP does offer local workspace-session tools that remember a selected
property or library on the user's machine. Those tools only write local hints;
they never change Adobe Tags.

## Architecture

```text
AI client (ChatGPT Desktop, Cursor, ...)
        | stdio or local Streamable HTTP
        v
MCP adapter (Python)
        | HTTP + local MCP_API_KEY
        v
Local API (FastAPI)
        | Adobe OAuth + curated read-only requests
        v
Adobe Experience Platform Tags / Reactor API
```

The MCP adapter never calls Adobe directly and never stores Adobe credentials.
The local API reads Adobe credentials from `api/.env`, obtains OAuth tokens,
and turns Adobe JSON:API responses into smaller AI-oriented responses.

## Read-only controls

The Adobe client permits only `GET` requests and Adobe Reactor's read-oriented
`POST /search` endpoint. All other Adobe request methods are blocked in code.

The API and optional MCP HTTP transport accept loopback hosts only. The normal
desktop setup uses MCP stdio transport.

## Authentication and local data

Two authentication modes are supported:

- `server_to_server`: OAuth Server-to-Server credentials in `api/.env`.
- `user_oauth`: an Adobe user signs in through the local browser flow. Tokens
  are stored locally under `data/`; configure `VAULT_KEY` to encrypt them.

`mcp/.env` contains only the local API address and the API-to-MCP shared key.
It must not contain Adobe client credentials or OAuth tokens.

## Response design

The project is not a raw Reactor passthrough. It returns curated, stable,
AI-oriented views with useful defaults, including logic summaries, revision and
live-status context, dependency information, and library review summaries.

## Deployment boundary

This repository is intended for each user or organization to run in its own
controlled environment. It does not provide a public hosted, multi-tenant
service. A company may operate an internal deployment under its own security
and access controls; unrelated organizations should retain control of their
own Adobe credentials and OAuth tokens.
