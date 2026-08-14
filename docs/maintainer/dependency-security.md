# Dependency security

Dependency updates follow two independent gates:

1. **Age gate:** select no release or image newer than seven days.
2. **Vulnerability gate:** runtime Python locks and deployed images must have no known
   critical/high vulnerabilities in the configured scanners.

A newer security release does not automatically bypass the age gate. If no artifact satisfies
both rules, the affected optional deployment fails closed until one does.

## Python locks

- `requirements.in` lists direct runtime dependencies.
- `requirements.txt` is the exact, SHA256-hashed runtime lock used by Docker and direct installs.
- `requirements-dev.in` lists development/test tooling and references the runtime input/lock.
- `requirements-dev.txt` is the exact, hashed development lock.
- Test-only packages such as `pytest`, `httpx`, `pip-audit`, and `uv` are not installed in the
  runtime image.

Install:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install --require-hashes -r requirements-dev.txt
```

Regenerate with the dynamic seven-day cutoff:

```powershell
.\.venv\Scripts\python.exe tools\lock_requirements.py
```

Reproduce a specific cutoff:

```powershell
.\.venv\Scripts\python.exe tools\lock_requirements.py `
  --cutoff 2026-08-06T23:38:38Z
```

The tool uses `uv pip compile --exclude-newer --generate-hashes`, verifies PyPI upload timestamps,
and audits both locks through `pip-audit` with OSV.

Before accepting a lock change, regenerate both graphs into temporary files and compare every
version, marker, and allowed artifact hash back to the `.in` manifests:

```powershell
.\.venv\Scripts\python.exe tools\lock_requirements.py --check
```

`--check` reuses the cutoff recorded in the committed runtime lock. It fails on injected packages,
hand-edited versions/hashes, directives, direct URLs, or dependency-graph drift.

## Runtime container

The Python base is pinned by version, distro, and immutable digest in the `Dockerfile`. The final
runtime removes package-management/build tooling and the unused Debian `perl-base` runtime after
dependency installation. The resulting image is intentionally not suitable for in-container
package management; rebuild it from reviewed locks instead.

Audit:

```powershell
.\tools\audit_containers.ps1
```

The script checks the base-image creation time against the seven-day cutoff, builds the hub, and
uses Docker Scout's critical/high exit gate.

## Tailscale sidecar

`docker-compose.yaml` contains an intentionally unpullable digest sentinel; deployment environment
variables cannot override it. Enabling tailnet deployment requires a reviewed source-control
change to:

```text
tailscale/tailscale:<version>@sha256:<immutable-digest>
```

The image must be official, at least seven days old, and pass:

```powershell
.\tools\audit_containers.ps1 `
  -TailscaleImage tailscale/tailscale:<version>@sha256:<immutable-digest>
```

Only after that command passes should the sentinel be replaced and committed. If no official image
qualifies, use `docker-compose.lan.yaml` over LAN/WireGuard and leave tailnet deployment disabled.

Never restore `latest`, `stable`, an unversioned base image, unhashed Python requirements, or a
scanner exception merely to make an update pass.
