# Security and operations

## Trust boundary: the hub assumes a trusted network

The hub has **no general built-in auth**.

- Session CRUD, ingest, manual artifact upload, HTML pages, and `/artifacts/...` are reachable by anyone who can reach the hub port.
- The LAN/WireGuard Docker deployment publishes `:8080`; treat firewalling and network segmentation as the real access control.
- The Tailscale sidecar deployment narrows reachability to the tailnet, but it still does not add per-user app auth.

If the network is not trusted, put the hub behind a stronger perimeter than the app currently provides.

## Screenshot shared-token design

Screenshot requests are the exception: [../../hub/routers/screenshot_requests.py](../../hub/routers/screenshot_requests.py) is gated by a shared bearer secret.

- `FRAME_RELAY_SCREENSHOT_TOKEN` blank → feature disabled (`503`)
- every screenshot-request route requires `X-Frame-Relay-Screenshot-Token`
- the same token must be configured on the hub and on any screenshot-capable collector/helper
- completion is source-bound (`host` vs `client`) and only allowed from `pending`
- requested screenshots must be PNGs

This is a deployment-wide shared secret, not user identity. Keep it on trusted devices only and rotate it if a collector is lost.

## Artifacts are visible and persisted separately from request auth

Artifacts live under `FRAME_RELAY_ARTIFACTS_DIR` and are served directly from `/artifacts`.

Important consequences:

- manual artifact uploads are not token-protected
- a completed requested screenshot becomes a normal artifact row plus a normal `/artifacts/...` file
- screenshot-request auth protects **queuing and fulfillment**, not later artifact reads

Session deletion cascades the database rows, but the current code path does **not** sweep leftover artifact files from disk. If you need hard-delete or retention cleanup, implement and test filesystem cleanup explicitly.

## Secrets and local state

- `.env` is for secrets such as `FRAME_RELAY_COPILOT_TOKEN`, `FRAME_RELAY_SCREENSHOT_TOKEN`, and deployment-specific settings.
- `data/` holds SQLite plus artifact files.
- Both are gitignored and must never be committed.
- Direct runs default to `./data`; Docker uses the mounted volume behind `/data`.

`FRAME_RELAY_COPILOT_TOKEN` falls back to `GITHUB_TOKEN`; treat both as secrets.

## Screenshot/privacy/HDR limitations

Screenshots and visual notes are useful, but they are not authoritative measurement tools.

- requested host/client screenshots are near-simultaneous, not frame-perfect synchronized
- Windows HDR desktop capture may be tone-mapped by the OS
- protected video surfaces may capture as black
- screenshots and operator ratings can expose personal desktop content, notifications, or app windows
- screenshots and ratings are subjective visual evidence, not calibrated HDR colorimetry

That limitation is deliberate and should stay visible in docs and UI wording.

## Interactive collectors and persistence

- Run Windows host collectors in the logged-in interactive session; do not treat SYSTEM/non-interactive service capture as supported for display validation or desktop screenshots.
- Host `--watch` mode is safe to leave running and safe to restart because it keys off missing host log chunks rather than local state.
- `python -m frame_relay` runs in the foreground and has no built-in restart manager. Use Docker or an OS service wrapper if you want always-on behavior.

## Firewall and deployment concerns

- The hub and the stream are separate surfaces. Opening hub access does not open Apollo ports, and vice versa.
- LAN/WireGuard hub deployment needs inbound access to `:8080`; Apollo itself needs its own TCP/UDP ports reachable from clients.
- Tailnet-only deployment intentionally publishes no LAN port and relies on `tailscale serve`.
  It is fail-closed at an intentionally invalid tracked digest until a reviewed version+digest
  passes the dependency policy and is committed. Do not substitute `latest` or an env override.

Use [../user/deploy.md](../user/deploy.md) for deployment commands and [../user/host-client-setup.md](../user/host-client-setup.md) for host/client reachability details.
