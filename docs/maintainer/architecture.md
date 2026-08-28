# Architecture

## System map

| Area | Key files | Responsibility |
|---|---|---|
| `hub/` | [../../hub/main.py](../../hub/main.py), [../../hub/routers/](../../hub/routers), [../../hub/service.py](../../hub/service.py), [../../hub/db.py](../../hub/db.py), [../../hub/models.py](../../hub/models.py) | FastAPI JSON API, server-rendered Jinja UI, SQLite storage, artifact serving, Copilot analysis, screenshot-request auth/state. |
| `collectors/frame_relay_collector/` | [../../collectors/frame_relay_collector/session.py](../../collectors/frame_relay_collector/session.py) and helpers | Machine-local capture agent: logs, link samples, Windows display topology, session orchestration, metadata enrichment. |
| `network/` | [../../network](../../network) | `iperf3` runner/parser plus per-network-path scenario presets. |

The normal data flow is:

1. A host or client collector creates/attaches to a session.
2. Collectors POST logs, link samples, display samples, net tests, and optional artifacts to the hub.
3. The hub stores everything under one session row plus child tables in SQLite.
4. The UI renders the bundle, `display_validation` derives Windows-display checks, and Copilot consumes the same aggregate on demand.

## Hub layering

The hub is intentionally layered:

- **Routers** in [../../hub/routers](../../hub/routers) own HTTP concerns: request validation, status codes, multipart handling, and route shape.
- **`service.py`** owns application/data rules: session lifecycle, bundle assembly, comparison logic, screenshot-request state transitions, and all SQL call sites.
- **`db.py`** owns raw `sqlite3`: schema DDL, idempotent initialization, additive session-column migrations, connection settings, and row JSON decoding.
- **`models.py`** is the shared API contract used by collectors, routers, templates, JS, and Copilot context assembly.

`main.py` wires four routers today: `sessions`, `ingest`, `analysis`, and `screenshot_requests`. It also mounts `/static` and `/artifacts`.

## The session is the central entity

Everything hangs off `sessions`:

- `log_chunks` — host/client log payloads
- `link_samples` — sampled Ethernet/Wi-Fi evidence
- `display_samples` — Windows host display topology snapshots
- `net_tests` — `iperf3` results
- `artifacts` — manual uploads plus requested screenshots
- `screenshot_requests` — pending/completed/failed request rows
- `chat_messages` — Copilot follow-up history

Those child tables reference `sessions(id)` with `ON DELETE CASCADE`. `service.get_bundle()` is the aggregate read used by the session detail API/page and by [../../hub/copilot.py](../../hub/copilot.py).

## Derived layers

Two important derived modules sit beside the storage stack:

- [../../hub/display_validation.py](../../hub/display_validation.py) computes pass/partial/fail from stored host `display_samples` plus requested/effective stream settings.
- [../../hub/copilot.py](../../hub/copilot.py) builds a structured context from the stored bundle and the derived display-validation result.

Neither module should bypass `service.py` or add ad-hoc persistence.

## Runtime and deployment boundaries

- The **hub** is the only persistent server process. It may use third-party dependencies and runs either:
  - directly with `python -m frame_relay`,
  - in Docker with `docker compose -f docker-compose.lan.yaml up -d --build` (LAN/WireGuard, published `:8080`),
  - or in Docker with `docker compose up -d --build` (tailnet-only via Tailscale sidecar).
- **Collectors** run on the machines under test. They are intentionally stdlib-only and talk to the hub over HTTP; they do not share a database or filesystem with the hub.
- The **network runner** is a one-shot helper that posts `iperf3` results into an existing session; it is not a long-lived service.

Deployment reachability and trust boundaries are operational choices, not application auth features. See [./security-and-operations.md](./security-and-operations.md) and [../user/deploy.md](../user/deploy.md).
