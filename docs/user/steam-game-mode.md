# Steam Game Mode / Big Picture launcher

Use this when Moonlight or Artemis is already a non-Steam shortcut and you want every launch from
Steam to create, capture, and stop an Apollo Streaming Lab session automatically.

The wrapper supports:

- Linux Steam Game Mode, including Bazzite/SteamOS-style installations
- Windows Steam Big Picture
- Moonlight or Artemis, selected during setup
- the same role-neutral Steam cover, hero/background, logo, and wide cover for both clients

The wrapper is fail-closed. If its profile is invalid or the hub cannot create the session, the
streaming client does not launch.

## Before setup

1. Install Python 3.
2. Add Moonlight or Artemis to Steam as a non-Steam shortcut.
3. Launch Steam at least once so `userdata/<id>/config/shortcuts.vdf` exists.
4. Make sure the hub URL opens from the client.
5. Leave the Apollo host collector running in `-Watch` mode.

Setup reads `shortcuts.vdf` only to find the selected shortcut's grid ID. It never rewrites the
file. Steam Launch Options remain a manual change.

## Linux setup

From the repository:

```bash
chmod +x collectors/linux/install-steam-wrapper.sh
collectors/linux/install-steam-wrapper.sh
```

Setup asks:

1. whether the shortcut is **Moonlight** or **Artemis**
2. the Apollo Streaming Lab hub URL
3. which shortcut to use if more than one entry matches

For unattended setup:

```bash
collectors/linux/install-steam-wrapper.sh \
  --client-role moonlight \
  --hub-url http://192.168.69.159:8080 \
  --shortcut Moonlight
```

Then open the existing shortcut's **Properties → Launch Options** and paste the exact line printed
by setup. Existing Flatpak/client arguments are retained in the printed replacement. It normally
looks like:

```text
"/home/USER/.local/bin/asl-steam-launch" -- %command%
```

Restart Steam after setting Launch Options or installing artwork.

Default Linux locations:

| Item | Path |
|---|---|
| Profile | `${XDG_CONFIG_HOME:-~/.config}/apollo-streaming-lab/steam-launch.json` |
| Installed collector/artwork | `${XDG_DATA_HOME:-~/.local/share}/apollo-streaming-lab/` |
| Launcher | `~/.local/bin/asl-steam-launch` |
| Local log | `${XDG_STATE_HOME:-~/.local/state}/apollo-streaming-lab/steam-launch.log` |

## Windows setup

From PowerShell in the repository:

```powershell
.\collectors\windows\Install-AslSteamWrapper.ps1
```

The same setup questions are used. For unattended setup:

```powershell
.\collectors\windows\Install-AslSteamWrapper.ps1 `
  -ClientRole artemis `
  -HubUrl http://192.168.69.159:8080 `
  -Shortcut Artemis
```

Paste the printed line into the existing shortcut's **Properties → Launch Options**. It normally
looks like the following; any existing client arguments are retained in the printed replacement:

```text
"C:\Users\USER\AppData\Local\ApolloStreamingLab\bin\asl-steam-launch.cmd" -- %command%
```

Restart Steam afterward.

Default Windows locations:

| Item | Path |
|---|---|
| Profile and installed payload | `%LOCALAPPDATA%\ApolloStreamingLab\` |
| Launcher | `%LOCALAPPDATA%\ApolloStreamingLab\bin\asl-steam-launch.cmd` |
| Local log | `%LOCALAPPDATA%\ApolloStreamingLab\logs\steam-launch.log` |

## Test profile

The installer creates a minimal profile containing the hub URL, selected client role, default
session-name template, and collector intervals. Add known test controls directly to the JSON:

```json
{
  "hub_url": "http://192.168.69.159:8080",
  "client_role": "moonlight",
  "name_template": "{hostname} - {client_role} - {timestamp}",
  "comparison_label": "ff7r-4k120-sdr-lan-v1",
  "apollo_app": "Playnite",
  "game_title": "FINAL FANTASY VII REMAKE INTERGRADE",
  "network_path": "local-LAN",
  "requested_settings": {
    "codec": "AV1",
    "resolution": "3840x2160",
    "fps": 120,
    "bitrate_mbps": 113,
    "hdr": false
  },
  "collector": {
    "interval": 15,
    "post_interval": 30,
    "screenshot_poll_interval": 3
  }
}
```

Supported name fields are `{hostname}`, `{client_role}`, `{date}`, `{time}`, and `{timestamp}`.
Explicit profile values are treated as known controls and are not overwritten by log evidence.
Omit values you do not know.

Keep `ASL_SCREENSHOT_TOKEN` in the environment rather than adding it to this file.

## Normal use

1. Start the client from its normal Steam tile.
2. The wrapper validates the profile and creates the hub session.
3. Moonlight/Artemis launches only after session creation succeeds.
4. Client logs and link samples post while the app runs.
5. Closing the client performs a final flush and stops the session.

Every launch of the wrapped shortcut is a test. Do not use that shortcut for casual, untracked
streaming unless you remove its Launch Options wrapper.

## Artwork

Both client roles use the same original Apollo Streaming Lab streaming-client artwork:

- portrait cover: `600x900`
- hero/background: `1920x620`
- transparent logo
- wide cover: `920x430`

Setup finds the non-Steam shortcut's unsigned grid ID and copies the four images into that Steam
user's `config/grid` directory. The assets are original, role-neutral, and marked CC0-1.0 in
`assets/steam/streaming-client/PROVENANCE.txt`.

Use `--skip-artwork` on Linux or `-SkipArtwork` on Windows if you only want the wrapper.

## Change client or hub

Reconfigure an existing profile:

```bash
collectors/linux/install-steam-wrapper.sh --reconfigure
```

```powershell
.\collectors\windows\Install-AslSteamWrapper.ps1 -Reconfigure
```

Without the reconfigure flag, upgrades preserve the existing profile.

## Upgrade and rollback

After pulling repository updates, rerun the platform installer. It replaces the installed
collector, launcher, and artwork while preserving the profile.

To roll back:

1. Remove the wrapper line from the shortcut's Launch Options.
2. Remove the four custom artwork files through Steam or from the shortcut's `config/grid`
   directory using the grid ID printed during setup.
3. Delete the user-local Apollo Streaming Lab installation paths listed above.

If launch fails in Game Mode/Big Picture, inspect the local log first. A failed wrapped-command
start marks any newly created session stopped so it does not remain active on the hub.
