# Apollo Streaming Lab

[![CI](https://github.com/camcast3/apollo-streaming-lab/actions/workflows/ci.yml/badge.svg)](https://github.com/camcast3/apollo-streaming-lab/actions/workflows/ci.yml)
[![Python 3.11](https://img.shields.io/badge/python-3.11-blue.svg)](https://www.python.org/)
[![License: MIT](https://img.shields.io/badge/license-MIT-green.svg)](./LICENSE)

A self-hosted troubleshooting and test harness for **Apollo/Sunshine** game streams and
**Moonlight/Artemis** clients.

Apollo Streaming Lab records host/client evidence in one session so you can compare hardware,
network paths, codecs, display modes, HDR behavior, and client performance without manually
aligning separate logs.

> [!WARNING]
> **Experimental trusted-network software.** The hub has no general application authentication.
> Anyone who can reach its HTTP port can view and modify sessions and access artifacts. Keep it
> on a trusted LAN, behind WireGuard/Tailscale, or behind an authenticated reverse proxy. Do not
> expose the LAN Compose port directly to the public internet.

## Features

- side-by-side Apollo and Moonlight/Artemis logs
- requested versus effective codec, resolution, FPS, bitrate, and HDR evidence
- Wi-Fi/Ethernet samples, AP roaming history, and optional iperf3 results
- Windows virtual-display topology and restoration checks
- manual and authenticated on-demand screenshot evidence
- matched session comparisons, operator notes, and outcomes
- optional local/CLI/SDK Copilot-assisted analysis
- Windows and Linux collectors with host watch mode and live client launch capture
- Steam Game Mode/Big Picture wrappers for automatically tracked Moonlight/Artemis tests

## Components

| Component | Purpose |
|---|---|
| Hub | FastAPI + SQLite web UI/API for sessions, comparisons, logs, and artifacts |
| Host collector | Captures Apollo logs, client connection path, link state, and Windows display evidence |
| Client collector | Captures Moonlight/Artemis output and client link state on Windows/Linux |
| Agent-less workflow | Manual Android/Xbox log, link, overlay, and screenshot evidence |

Collectors under `collectors/asl_collector/` use only the Python standard library.

## Quick start

Python 3.11 and Docker are the supported baseline.

```powershell
git clone https://github.com/camcast3/apollo-streaming-lab.git
cd apollo-streaming-lab
Copy-Item .env.example .env
docker compose -f docker-compose.lan.yaml up -d --build
```

Open `http://<hub-host>:8080` from a trusted device. Start the Windows Apollo host watcher:

```powershell
.\collectors\windows\Start-AslSession.ps1 `
  -HubUrl http://<hub-host>:8080 `
  -Source host `
  -Watch
```

Then follow the **[First multi-client test](./docs/user/first-multi-client-test.md)**. It covers
client capture, matched comparisons, screenshots, Xbox/manual evidence, and safe cleanup.

## Documentation

### Operate the lab

- **[First multi-client test](./docs/user/first-multi-client-test.md)** — canonical start-to-
  finish walkthrough.
- **[Host and client setup](./docs/user/host-client-setup.md)** — LAN, WireGuard, host watcher,
  and collector workflows.
- **[Steam Game Mode / Big Picture](./docs/user/steam-game-mode.md)** — automatically track
  Moonlight or Artemis launches on Windows/Linux.
- **[Deployment](./docs/user/deploy.md)** — LAN/WireGuard, tailnet-only, and direct-host options.
- **[Agent-less capture](./docs/user/agentless-capture.md)** — Android and Xbox evidence entry.
- **[Troubleshooting](./docs/user/troubleshooting.md)** — symptoms, evidence, and likely causes.

### Develop and maintain

- **[Documentation router](./docs/README.md)**
- **[Architecture](./docs/maintainer/architecture.md)**
- **[Development](./docs/maintainer/development.md)**
- **[Security and operations](./docs/maintainer/security-and-operations.md)**
- **[Dependency security](./docs/maintainer/dependency-security.md)**

## Development

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install --require-hashes -r requirements-dev.txt
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe tools\check_public_repo.py
```

Dependency locks use exact hashes and a seven-day release holdback. Runtime images are
version-and-digest pinned. Read [CONTRIBUTING.md](./CONTRIBUTING.md) before changing dependencies,
schemas, collectors, security boundaries, or deployment behavior.

## Privacy and data

The hub stores logs, link metadata, screenshots, notes, and SQLite state locally. These may expose
device names, SSIDs/BSSIDs, addresses, applications, notifications, or desktop content.

- `.env`, `data/`, local databases, and artifacts are gitignored.
- Review and sanitize evidence before sharing it.
- Screenshot tokens protect request/fulfillment operations, not later artifact reads.
- Session deletion does not currently guarantee artifact-file erasure.

See [SECURITY.md](./SECURITY.md) and
[security and operations](./docs/maintainer/security-and-operations.md).

## Contributing and support

- [Contributing](./CONTRIBUTING.md)
- [Support](./SUPPORT.md)
- [Security policy](./SECURITY.md)
- [Code of conduct](./CODE_OF_CONDUCT.md)

## License and trademarks

Code and documentation are available under the [MIT License](./LICENSE). The FRAME RELAY Steam
artwork is separately dedicated under CC0-1.0.

This independent project is not affiliated with or endorsed by Apollo, Sunshine, Moonlight,
Artemis, Tailscale, Microsoft, Valve, or GitHub. See [NOTICE.md](./NOTICE.md).