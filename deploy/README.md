# Apollo Streaming Lab deploy

> Two deployment options:
> - **LAN / WireGuard** (recommended for the WireGuard + LAN model): use
>   `docker compose -f docker-compose.lan.yaml up -d --build` — see
>   [../docs/host-client-setup.md](../docs/host-client-setup.md).
> - **Tailnet-only** (this file): Tailscale sidecar, no LAN ports.

1. Copy `.env.example` to `.env`.
2. Set `TS_AUTHKEY` from the Tailscale admin console; prefer an auth key tagged `tag:apollo-hub`.
3. Optionally set `ASL_COPILOT_TOKEN` and `ASL_COPILOT_BACKEND=cli` or `sdk`.
4. Apply `deploy/tailscale-acl.snippet.hujson` in the Tailscale admin console.
5. Start on the watchtower Docker host:

```powershell
docker compose up -d --build
```

Confirm:

```powershell
docker compose ps
```

Open `https://apollo-streaming-lab.<tailnet>.ts.net` from a tailnet device.

Also confirm the hub is not reachable at `http://<LAN-IP>:8080`; the compose file publishes no LAN ports.
