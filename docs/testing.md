# Testing

Run the test suite from the repository root after completing the setup steps in
the [README](../README.md).

## API tests

**Windows:**

```powershell
cd adobeTagsMCP
.\.venv\Scripts\python.exe -m pytest -q api\tests
```

**macOS / Linux:**

```bash
cd adobeTagsMCP
.venv/bin/python -m pytest -q api/tests
```

## MCP tests

Offline MCP tests use a mocked local API and are always safe to run:

```powershell
cd adobeTagsMCP
.\.venv\Scripts\python.exe -m pytest -q mcp\tests
```

Live MCP tests call the local API and Adobe. Start the API and authenticate
with Adobe first, then run:

```powershell
$env:RUN_LIVE_MCP_E2E = "1"
.\.venv\Scripts\python.exe -m pytest -q mcp\tests\test_live_e2e.py
```
