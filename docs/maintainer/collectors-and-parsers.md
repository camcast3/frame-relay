# Collectors and parsers

## Non-negotiable collector rule

Everything under [../../collectors/asl_collector](../../collectors/asl_collector) must remain **standard-library only**. The collector is expected to run from an unprepared system Python.

- Use `urllib` for hub traffic (see [../../collectors/asl_collector/client.py](../../collectors/asl_collector/client.py)).
- Do not add `requests`, `httpx`, or any other third-party dependency there.
- PowerShell/Bash wrappers under `collectors/windows/` and `collectors/linux/` should stay thin launchers around the Python package.

## Discovery and parser boundaries

Keep filesystem/app discovery separate from parsing:

- [../../collectors/asl_collector/logfind.py](../../collectors/asl_collector/logfind.py) — candidate log paths
- [../../collectors/asl_collector/appfind.py](../../collectors/asl_collector/appfind.py) — candidate client executables

Keep subprocess/OS interaction separate from pure parsing:

- `hostmeta.py`, `clientmeta.py` — stream/HDR metadata from logs
- `linkinfo.py`, `conninfo.py`, `hostmeta.py` — parse command/log text, with probing outside the pure parser when possible
- display topology in [../../collectors/asl_collector/displayprobe.py](../../collectors/asl_collector/displayprobe.py)
- network parsing under [../../network](../../network)

When adding support for a new OS command or log shape:

1. keep the parser pure over captured text whenever possible
2. add/update a sample in `samples/`
3. add/update the matching test

`candidate_*` helpers and pure parse functions are expected to be unit-testable without touching the live machine.

## Capture workflows

[../../collectors/asl_collector/session.py](../../collectors/asl_collector/session.py) supports four important patterns:

- **Host watch mode** (`--watch`) — long-lived, idempotent, follows sessions created elsewhere, and back-fills logs from session start when it notices a session late.
- **Client creates session** (`--create`) — recommended matched-client workflow; the host watcher follows.
- **Client attaches** (`--attach-latest` or auto-select) — host-created workflow without ID copy/paste.
- **Launch mode** (`--launch` / `--launch-client`) — wraps the client app and captures buffered logs from live stderr instead of waiting for a file flush.

Other invariants worth preserving:

- the host collector fills **blank** session fields live (codec/resolution/fps/bitrate/HDR, client IP, network path) and never overwrites existing UI/CLI values
- live posting is timer-based (`--post-interval`); a final flush always happens when capture ends
- `awaiting_host` / `awaiting_client` are keyed from missing log chunks, not blank name fields
- network-path choices are fixed literals, not free-form text

Operator workflows live in [../user/host-client-setup.md](../user/host-client-setup.md), [../user/agentless-capture.md](../user/agentless-capture.md), and [../user/first-multi-client-test.md](../user/first-multi-client-test.md).

## Display evidence and console-session requirements

Windows display topology capture is host-only and runs through `QueryDisplayConfig` / `DisplayConfigGetDeviceInfo`.

- Run the Windows host collector in the **logged-in interactive console session**, not as SYSTEM or a non-interactive service.
- Treat the same rule as mandatory for any screenshot helper bound to the active desktop; there is no supported service-session display/screenshot contract here.
- `watch` mode intentionally skips the unreliable `before` baseline when it attaches after a session already started; `during` and `after` remain the trustworthy evidence.
- Agent-less clients (Android/Xbox) do not supply display samples; their evidence is manual log/link/artifact entry in the hub UI.

## Screenshot note

The current collector package is primarily about capture/orchestration. The hub already exposes screenshot-request API/state. Any collector-side screenshot fulfillment work must preserve the constraints documented in [./api-and-data-model.md](./api-and-data-model.md) and [./security-and-operations.md](./security-and-operations.md): shared token, source-bound completion, and interactive desktop capture assumptions.
