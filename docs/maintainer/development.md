# Development

## Local setup (Windows / PowerShell)

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

Python 3.11 is the project baseline. Use Windows-style commands/examples unless a file is explicitly Linux-only.

## Running the hub

```powershell
# dev server, localhost only unless you add --host 0.0.0.0
.\.venv\Scripts\python.exe -m uvicorn hub.main:app --reload --port 8080

# normal direct run, bound from ASL_HOST/ASL_PORT (defaults 0.0.0.0:8080)
.\.venv\Scripts\python.exe -m hub
```

Important caveat: bare `uvicorn hub.main:app` binds `127.0.0.1` by default. Use `python -m hub` or pass `--host 0.0.0.0` when you need other devices to reach the hub.

## Tests and validation

Use the smallest pytest selection that covers the change.

```powershell
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m pytest tests/test_linkinfo.py::test_parse_netsh_wlan
.\.venv\Scripts\python.exe -m pytest tests/test_docs_links.py -q
```

Typical targeted choices:

- parser/discovery work → the matching `tests/test_*.py` file plus any new sample fixture
- hub API/data-model work → the closest API/service contract tests
- documentation-only work → `tests/test_docs_links.py`

## Import-time config caveat

[../../hub/config.py](../../hub/config.py) reads environment variables at import time. Tests must set `ASL_*` first.

[../../tests/conftest.py](../../tests/conftest.py) does exactly that before importing `hub`:

- prepends `collectors/` to `sys.path`
- sets `ASL_DATA_DIR`
- forces `ASL_COPILOT_BACKEND=mock`
- sets `ASL_SCREENSHOT_TOKEN`

If you need different config inside a test, either:

- set env before importing any `hub` module in a fresh process, or
- monkeypatch `hub.config` attributes after import when the code path allows it.

## No linter / formatter

There is no configured formatter or lint command in this repo. Some files carry `# noqa` comments, but there is no `ruff`, `flake8`, or formatter config to update. Do not add one opportunistically.

## Docker smoke validation

Use the compose file that matches the surface you are touching:

```powershell
# tailnet-only sidecar deployment
docker compose up -d --build
docker compose ps

# LAN / WireGuard deployment
docker compose -f docker-compose.lan.yaml up -d --build
docker compose -f docker-compose.lan.yaml ps
```

Useful quick checks:

```powershell
Invoke-WebRequest http://127.0.0.1:8080/health | Select-Object -Expand Content
docker compose logs --tail 50
```

Use Docker as a smoke check, not as a substitute for pytest. Full deployment/firewall expectations live in [../user/deploy.md](../user/deploy.md) and [./security-and-operations.md](./security-and-operations.md).
