# Migrating to Frame Relay

Frame Relay is the new name for the project formerly called Apollo Streaming Lab. The migration
keeps compatibility paths so existing hosts and clients can upgrade without losing sessions or
breaking immediately.

## Canonical names

| Previous | Current |
|---|---|
| `python -m hub` | `python -m frame_relay` |
| `python -m asl_collector` | `python -m frame_relay_collector` |
| `Start-AslSession.ps1` | `Start-FrameRelaySession.ps1` |
| `asl-session.sh` | `frame-relay-session.sh` |
| `ASL_*` environment variables | `FRAME_RELAY_*` |
| `X-ASL-Screenshot-Token` | `X-Frame-Relay-Screenshot-Token` |
| Apollo Streaming Lab Steam paths | Frame Relay Steam paths |

The previous Python package, scripts, environment variables, screenshot header, and
`python -m hub` entry point remain accepted as deprecated aliases. New documentation and setup
should use only the Frame Relay names.

## Hub data

Direct runs create `data/frame-relay.db`. If `data/asl.db` already exists and no explicit database
path is configured, Frame Relay continues using that legacy file.

Docker Compose now uses the project name `frame-relay`, so its default data volume is
`frame-relay_hub-data`. Before the first Compose upgrade, copy an existing legacy volume:

```powershell
docker compose -p apollo-streaming-lab -f docker-compose.lan.yaml down
# Confirm the old hub and any other database writers are stopped before copying SQLite.
docker compose -f docker-compose.lan.yaml build
$legacyVolume = "apollo-streaming-lab_hub-data" # replace if your old Compose project used another name
docker volume inspect $legacyVolume | Out-Null
if ($LASTEXITCODE -ne 0) {
  throw "Legacy volume '$legacyVolume' does not exist; find the correct source before continuing."
}
if (docker volume inspect frame-relay_hub-data 2>$null) {
  throw "frame-relay_hub-data already exists; inspect or back it up instead of overwriting it."
}
docker volume create frame-relay_hub-data
docker run --rm --user 0 --entrypoint sh `
  -v "${legacyVolume}:/from:ro" `
  -v frame-relay_hub-data:/to `
  frame-relay-hub `
  -c "set -eu; test ! -e /to/frame-relay.db; cp -a /from/. /to/; if [ -f /to/asl.db ] && [ ! -f /to/frame-relay.db ]; then mv /to/asl.db /to/frame-relay.db; fi; chown -R frame-relay:frame-relay /to"
```

Confirm the copied database and artifacts before removing the old volume.

## Environment variables

Rename `.env` keys:

```text
ASL_DATA_DIR                         -> FRAME_RELAY_DATA_DIR
ASL_DB_PATH                          -> FRAME_RELAY_DB_PATH
ASL_ARTIFACTS_DIR                    -> FRAME_RELAY_ARTIFACTS_DIR
ASL_HOST / ASL_PORT                  -> FRAME_RELAY_HOST / FRAME_RELAY_PORT
ASL_COPILOT_*                        -> FRAME_RELAY_COPILOT_*
ASL_SCREENSHOT_TOKEN                 -> FRAME_RELAY_SCREENSHOT_TOKEN
ASL_SCREENSHOT_MAX_UPLOAD_BYTES      -> FRAME_RELAY_SCREENSHOT_MAX_UPLOAD_BYTES
```

When both names are set, the `FRAME_RELAY_*` value wins.

## Host/client collectors

Update long-lived launchers and scheduled tasks to the new script names. Existing compatibility
wrappers still delegate to the new collector, but they are retained only to make migration safe.

On Windows:

```powershell
.\collectors\windows\Start-FrameRelaySession.ps1 `
  -HubUrl http://<hub-host>:8080 `
  -Source host `
  -Watch
```

On Linux:

```bash
collectors/linux/frame-relay-session.sh \
  --hub-url http://<hub-host>:8080 \
  --source client --role moonlight --create --launch-client --stop-session
```

## Steam wrapper

Rerun the platform installer:

```powershell
.\collectors\windows\Install-FrameRelaySteamWrapper.ps1
```

```bash
collectors/linux/install-frame-relay-steam-wrapper.sh
```

Setup copies an existing legacy Steam profile into the new user directory when needed and installs
a compatibility launcher for old Steam Launch Options. Replace Launch Options with the newly
printed `frame-relay-steam-launch` command when convenient.

Tailnet users must also update the preserved profile URL:

```bash
collectors/linux/install-frame-relay-steam-wrapper.sh \
  --reconfigure \
  --hub-url https://frame-relay.<tailnet>.ts.net
```

Use the equivalent `-Reconfigure -HubUrl` options on Windows.

## Tailscale

The example ACL tags are now `tag:frame-relay-hub` and `tag:frame-relay-collector`. Update the
tailnet policy and issue a matching tagged auth key before changing the sidecar hostname.
