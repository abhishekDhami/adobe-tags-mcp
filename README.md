# Adobe Tags MCP

An independent, local-first, read-only MCP + API for Adobe Experience Platform
Tags. It is not an official Adobe product.

## Docs

- [Project context](./docs/project-context.md) — scope, architecture, security boundaries, and response design
- [Starter prompt](./docs/starter-prompt.md) — a first prompt to use after configuring the local MCP
- [Testing](./docs/testing.md) — API and MCP test commands
- [Security policy](./SECURITY.md) — credential handling and vulnerability reporting
- [MIT License](./LICENSE)

---

## Requirements

- Python **3.10+**
- Adobe Developer Console project with **Experience Platform Tags (Reactor) API**
- Root folder: `adobe-tags-mcp/` (this repo)

---

## Environment files (split)

| File       | Contains                                          |
| ---------- | ------------------------------------------------- |
| `api/.env` | Adobe credentials, API bind, vault, `MCP_API_KEY` |
| `mcp/.env` | `API_BASE_URL`, same `MCP_API_KEY`, MCP transport |

Adobe secrets stay in **`api/.env` only**. MCP never talks to Adobe directly.

```powershell
cd adobe-tags-mcp
copy api\.env.example api\.env
copy mcp\.env.example mcp\.env
```

Use the **same** `MCP_API_KEY` in both files when `AUTH_ENABLED=true` (recommended).

Never commit either `.env` file, paste Adobe credentials into your MCP client
settings, or share them in logs, screenshots, or issues. If using
`user_oauth`, set a `VAULT_KEY` in `api/.env` to encrypt the locally stored
OAuth session.

---

## Create Adobe API credentials

The quickest setup is OAuth Server-to-Server. You need access to the Adobe
organization and a product profile that can access the required Tags
properties.

1. In Adobe Admin Console, ensure you have the required developer access and
   an appropriate Experience Platform/Data Collection Tags product profile.
2. In [Adobe Developer Console](https://developer.adobe.com/console/home),
   create a project or open an existing project.
3. Select **Add API**, choose the Experience Platform/Data Collection Tags API
   available to your organization, and select **OAuth Server-to-Server**.
4. Assign the least-privilege product profile that provides the Tags access you
   need, then save the configured API.
5. Copy the Client ID, Client Secret, and IMS Organization ID into `api/.env`.
   Keep them on your machine; they do not belong in `mcp/.env` or your AI
   client configuration.

Adobe's [OAuth Server-to-Server setup guide](https://developer.adobe.com/developer-console/docs/guides/services/services-add-api-oauth-s2s)
has the current Developer Console flow and product-profile details.

### Configure `api/.env`

In `api/.env`:

```env
ADOBE_AUTH_MODE=server_to_server
ADOBE_CLIENT_ID=your_client_id
ADOBE_CLIENT_SECRET=your_client_secret
ADOBE_ORG_ID=your_org_id@AdobeOrg
```

User OAuth: set `ADOBE_AUTH_MODE=user_oauth` in `api/.env`, fill the OAuth
fields including `VAULT_KEY`, restart the API, then open
`http://127.0.0.1:3000/auth/adobe/start`.

---

## Why this runs locally

This project intentionally does not provide a public hosted, multi-tenant
service. Such a service would require unrelated organizations to trust a
third-party server with OAuth tokens or API credentials that can access their
Adobe Tags configuration. Running locally keeps those credentials and tokens
under the user's control.

A company-internal deployment is a different model: the service and its
credentials remain within the organization's controlled environment and can be
protected by its existing identity, access-control, and security practices.

---

## Option A — Manual setup (no scripts)

Use this on company laptops where `.\scripts\*.ps1` is blocked.

### 1. One-time setup

**Windows (PowerShell or CMD):**

```powershell
cd adobe-tags-mcp

# Create virtual environment at repo root
python -m venv .venv

# Activate virtual environment

# Install dependencies (API + MCP share one venv)
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -r api\requirements-dev.txt
.\.venv\Scripts\python.exe -m pip install -r mcp\requirements-dev.txt

```

**macOS / Linux:**

```bash
cd adobe-tags-mcp
python -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r api/requirements-dev.txt
python -m pip install -r mcp/requirements-dev.txt

```

### 2. Start API (every time)

**Windows:**

```powershell
cd api
python -m app.main
```

**macOS / Linux:**

```bash
cd api
python -m app.main
```

API runs at `http://127.0.0.1:3000` (loopback only — `API_HOST=0.0.0.0` is rejected).

### 3. Validate API

**Windows (PowerShell):**

```powershell
Invoke-RestMethod http://127.0.0.1:3000/health
Invoke-RestMethod http://127.0.0.1:3000/api/v1/auth/status
Invoke-RestMethod http://127.0.0.1:3000/api/v1/tags/properties
```

**macOS / Linux (curl):**

```bash
curl http://127.0.0.1:3000/health
```

**Mode A login (browser):** open `http://127.0.0.1:3000/auth/adobe/start`

### 4. Start MCP (optional — after API works)

**Windows:**

```powershell
cd mcp
python -m app.server
```

**macOS / Linux:**

```bash
cd mcp
python -m app.server
```

---

## Option B — Setup scripts (Windows, if allowed)

If your machine allows local PowerShell scripts:

```powershell
.\scripts\setup.ps1
# Edit api\.env (Adobe) and ensure mcp\.env MCP_API_KEY matches
```

Start API:

```powershell
.\scripts\start.ps1
```

`start.ps1` opens the API in a new window. Validate with:

```powershell
Invoke-RestMethod http://127.0.0.1:3000/health
```

If scripts are blocked, use **Option A** above.

---

## API endpoints

See [project context](./docs/project-context.md) for the architecture and
read-only design. Key API endpoints:

| Method | Path                                                            | Notes                                                                                                         |
| ------ | --------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------- |
| GET    | `/health`                                                       |
| GET    | `/api/v1/auth/status`                                           |
| POST   | `/api/v1/auth/disconnect`                                       |
| GET    | `/auth/adobe/start` (Mode A)                                    |
| GET    | `/api/v1/tags/properties`                                       |
| GET    | `/api/v1/tags/properties/{propertyId}/rules`                    |
| GET    | `/api/v1/tags/rules/{ruleId}`                                   | AI view + **`versions`**; default `depth=context`                                                             |
| GET    | `/api/v1/tags/rules/{ruleId}/rule-components`                   | Components only                                                                                               |
| GET    | `/api/v1/tags/rules/{ruleId}/versions`                          | Important revisions by default; `?view=full` for all                                                          |
| GET    | `/api/v1/tags/properties/{propertyId}/data-elements`            |
| GET    | `/api/v1/tags/data-elements/{dataElementId}`                    | DE view + **`versions`**                                                                                      |
| GET    | `/api/v1/tags/data-elements/{dataElementId}/versions`           | Important revisions; `?view=full` for all                                                                     |
| GET    | `/api/v1/tags/properties/{propertyId}/extensions`               |
| GET    | `/api/v1/tags/extensions/{extensionId}`                         | Extension view + **`versions`**                                                                               |
| GET    | `/api/v1/tags/extensions/{extensionId}/versions`                | Important revisions; `?view=full` for all                                                                     |
| GET    | `/api/v1/tags/search?query=...`                                 |
| GET    | `/api/v1/tags/properties/{propertyId}/environments`             |
| GET    | `/api/v1/tags/properties/{propertyId}/development-libraries`    | Active dev library (resolve or disambiguate)                                                                  |
| GET    | `/api/v1/tags/properties/{propertyId}/published-libraries`      | Publish history                                                                                               |
| GET    | `/api/v1/tags/libraries/{libraryId}`                            |
| GET    | `/api/v1/tags/libraries/{libraryId}/resources`                  |
| GET    | `/api/v1/tags/libraries/{libraryId}/resources`                  | Rules/DE/extensions in library                                                                                |
| GET    | `/api/v1/tags/libraries/{libraryId}/review-development-library` | Pre-publish live vs pending (`?depth=summary\|full`)                                                          |
| GET    | `/api/v1/tags/rules/{ruleId}/dependencies`                      | DE + extension refs; `?versionScope=latest\|live`; getVar + tokens                                            |
| GET    | `/api/v1/tags/properties/{propertyId}/usage`                    | Where-used; `query` + `versionScope=latest` + `mode=freeText` (defaults) + `detail=hits\|summary\|components` |
| GET    | `/api/v1/session`                                               | Active property/library hints                                                                                 |
| PATCH  | `/api/v1/session`                                               | Set active property/library                                                                                   |
| POST   | `/api/v1/session/clear`                                         | Clear workspace hints                                                                                         |

### Libraries vs property resources

In Adobe Tags, **rules, data elements, and extensions** live on the property. A **library** is a publish container: you add changed resources to a library, build it, then submit/approve/publish to an environment (Development, Staging, Production).

| Endpoint                                        | Purpose                                      |
| ----------------------------------------------- | -------------------------------------------- |
| `.../properties/{id}/rules` (etc.)              | All resources on the property                |
| `.../properties/{id}/development-libraries`     | **Active dev library** — use before publish  |
| `.../properties/{id}/published-libraries`       | **Publish history** — what already went live |
| `.../libraries/{id}/resources`                  | Membership list for a library                |
| `.../libraries/{id}/review-development-library` | Pre-publish: pending vs publishedLive        |

**Development library workflow**

```text
1. GET .../properties/{id}/development-libraries
   → status=resolved + library.id   OR   status=ambiguous + candidates (user picks one)

2. GET .../libraries/{libraryId}/review-development-library?depth=summary
   → new/modified/disabled; compare pending vs publishedLive; see idUsage

3. Optional: PATCH .../session  { activeLibraryId, activeLibraryName }
   → remember the choice for follow-up questions in the same session
```

List items on `published-libraries` include `publishedAt` when `state=published`, otherwise `updatedAt`.

**Pagination** (default 25 per page, max 50):

```http
GET .../published-libraries?page=1&pageSize=25    ← newest first (default sort)
GET .../published-libraries?page=2&pageSize=25    ← next 25
GET .../published-libraries?page=1&pageSize=1     ← latest publish only
```

Check `data.pagination` in the response:

```json
{
  "page": 1,
  "pageSize": 25,
  "totalItems": 90,
  "totalPages": 4,
  "hasNextPage": true,
  "hasPreviousPage": false
}
```

Interactive docs (development only): `http://127.0.0.1:3000/docs`

---

## MCP client setup (stdio)

Start the **API first** (see Option A §2). MCP is a thin adapter: it talks only to the local API (`API_BASE_URL` in `mcp/.env`), never to Adobe directly.

### Cursor

Add to Cursor MCP settings (`.cursor/mcp.json`). On Windows, use the absolute
path to `mcp/run-mcp.cmd` inside **your own cloned repository**. This script
sets the MCP working directory to `mcp/` automatically.

Replace `<absolute-path-to-your-cloned-repository>` below with the folder where
you cloned this repository. For example, if you cloned it to
`C:\Users\your-name\Projects\adobe-tags-mcp`, the command value would be
`C:\Users\your-name\Projects\adobe-tags-mcp\mcp\run-mcp.cmd`.

```json
"adobe-tags-mcp": {
  "command": "<absolute-path-to-your-cloned-repository>\\mcp\\run-mcp.cmd",
  "args": [],
  "env": {
    "MCP_TRANSPORT": "stdio",
    "API_BASE_URL": "http://127.0.0.1:3000",
    "AUTH_ENABLED": "true",
    "MCP_API_KEY": "paste-same-key-as-in-api-and-mcp-env"
  }
}
```

`run-mcp.cmd` `cd`s into `mcp/` and runs the repo-root `.venv` Python as `-m app.server`. Match `MCP_API_KEY` with `api/.env` / `mcp/.env`. No Adobe secrets in this block.

### ChatGPT Desktop

1. Open **Settings → Connectors / Advanced → MCP servers** (wording varies by ChatGPT Desktop build).
2. Add a local stdio server. On Windows, replace
   `<absolute-path-to-your-cloned-repository>` with the folder where you
   cloned this repository:

| Field             | Value to enter                                                                  |
| ----------------- | ------------------------------------------------------------------------------- |
| Name              | `adobe-tags-mcp`                                                                |
| Command           | `<absolute-path-to-your-cloned-repository>\.venv\Scripts\python.exe`            |
| Args              | `-m` `app.server`                                                               |
| Working directory | `<absolute-path-to-your-cloned-repository>\mcp`                                 |
| Env               | Use the values in `mcp/.env`; do not add Adobe credentials to ChatGPT settings. |

For example, a clone at `C:\Users\your-name\Projects\adobe-tags-mcp` uses
`C:\Users\your-name\Projects\adobe-tags-mcp\.venv\Scripts\python.exe` as
the command and `C:\Users\your-name\Projects\adobe-tags-mcp\mcp` as the
working directory.

3. Confirm the API is up (`http://127.0.0.1:3000/health`) and Adobe is connected (`/api/v1/auth/status`) before chatting.

### MCP tools

Discovery: `list_properties`, `list_rules`, `get_rule`, `list_data_elements`, `get_data_element`, `list_extensions`, `get_extension`, `search_tags_resources`

Versions: `list_rule_revisions`, `list_data_element_revisions`, `list_extension_revisions`

Libraries: `list_environments`, `list_published_libraries`, `get_development_library`, `get_library`, `list_library_resources`, `review_development_library`

Analysis: `get_rule_dependencies`, `find_usage`

System / session: `get_system_health`, `get_system_status`, `get_adobe_auth_status`, `get_workspace_session`, `set_workspace_session`, `clear_workspace_session`
