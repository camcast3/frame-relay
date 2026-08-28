# Collectors and parsers

## Non-negotiable collector rule

Everything under [../../collectors/frame_relay_collector](../../collectors/frame_relay_collector) must remain **standard-library only**. The collector is expected to run from an unprepared system Python.

- Use `urllib` for hub traffic (see [../../collectors/frame_relay_collector/client.py](../../collectors/frame_relay_collector/client.py)).
- Do not add `requests`, `httpx`, or any other third-party dependency there.
- PowerShell/Bash wrappers under `collectors/windows/` and `collectors/linux/` should stay thin launchers around the Python package.

## Discovery and parser boundaries

Keep filesystem/app discovery separate from parsing:

- [../../collectors/frame_relay_collector/logfind.py](../../collectors/frame_relay_collector/logfind.py) — candidate log paths
- [../../collectors/frame_relay_collector/appfind.py](../../collectors/frame_relay_collector/appfind.py) — candidate client executables

Keep subprocess/OS interaction separate from pure parsing:

- `hostmeta.py`, `clientmeta.py` — stream/HDR metadata from logs
- `linkinfo.py`, `conninfo.py`, `hostmeta.py` — parse command/log text, with probing outside the pure parser when possible
- display topology in [../../collectors/frame_relay_collector/displayprobe.py](../../collectors/frame_relay_collector/displayprobe.py)
- network parsing under [../../network](../../network)

When adding support for a new OS command or log shape:

1. keep the parser pure over captured text whenever possible
2. add/update a sample in `samples/`
3. add/update the matching test

`candidate_*` helpers and pure parse functions are expected to be unit-testable without touching the live machine.

## Capture workflows

[../../collectors/frame_relay_collector/session.py](../../collectors/frame_relay_collector/session.py) supports four important patterns:

- **Host watch mode** (`--watch`) — long-lived, idempotent, follows sessions created elsewhere, and back-fills logs from session start when it notices a session late.
- **Client creates session** (`--create`) — recommended matched-client workflow; the host watcher follows.
- **Client attaches** (`--attach-latest` or auto-select) — host-created workflow without ID copy/paste.
- **Launch mode** (`--launch` / `--launch-client`) — wraps the client app and captures buffered logs from live stderr instead of waiting for a file flush.
- **Steam launch mode** (`steamlaunch.py`) — reads a validated user profile, preserves Steam's
  expanded `%command%` as argument tokens, then delegates to the normal create/launch/stop flow.

Other invariants worth preserving:

- the host collector fills **blank** session fields live (codec/resolution/fps/bitrate/HDR, client IP, network path) and never overwrites existing UI/CLI values
- live posting is timer-based (`--post-interval`); a final flush always happens when capture ends
- `awaiting_host` / `awaiting_client` are keyed from missing log chunks, not blank name fields
- network-path choices are fixed literals, not free-form text

Operator workflows live in [../user/host-client-setup.md](../user/host-client-setup.md), [../user/agentless-capture.md](../user/agentless-capture.md), and [../user/first-multi-client-test.md](../user/first-multi-client-test.md).

## Steam setup boundary

[../../collectors/frame_relay_collector/steamsetup.py](../../collectors/frame_relay_collector/steamsetup.py)
contains the shared Windows/Linux setup logic. Native shell/PowerShell/CMD files remain thin:

- profiles use XDG directories on Linux and `%LOCALAPPDATA%\FrameRelay` on Windows
- `client_role` is required and limited to `moonlight` or `artemis`
- setup may parse `shortcuts.vdf` read-only to find a non-Steam shortcut's unsigned grid ID
- setup installs custom grid files but never rewrites Steam shortcut records
- Moonlight and Artemis map to the same role-neutral artwork bundle
- invalid config or hub session creation is fail-closed; the client app must not launch untracked
- a client launch failure stops a session created by that invocation, but never an attached one

Original artwork and provenance live under
[../../assets/steam/frame-relay](../../assets/steam/frame-relay). Preserve the four
Steam dimensions/names and verify redistribution terms for any replacement assets.

## Display evidence and console-session requirements

Windows display topology capture is host-only and runs through `QueryDisplayConfig` / `DisplayConfigGetDeviceInfo`.

- Run the Windows host collector in the **logged-in interactive console session**, not as SYSTEM or a non-interactive service.
- Treat the same rule as mandatory for any screenshot helper bound to the active desktop; there is no supported service-session display/screenshot contract here.
- `watch` mode intentionally skips the unreliable `before` baseline when it attaches after a session already started; `during` and `after` remain the trustworthy evidence.
- Agent-less clients (Android/Xbox) do not supply display samples; their evidence is manual log/link/artifact entry in the hub UI.

## Screenshot note

The current collector package is primarily about capture/orchestration. The hub already exposes screenshot-request API/state. Any collector-side screenshot fulfillment work must preserve the constraints documented in [./api-and-data-model.md](./api-and-data-model.md) and [./security-and-operations.md](./security-and-operations.md): shared token, source-bound completion, and interactive desktop capture assumptions.
