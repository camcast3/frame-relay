# Apollo Streaming Lab — documentation

All project documentation lives here. Start with the [root README](../README.md) for the
overview, architecture, and dev quickstart, then dive into a guide below.

## Guides
- **[Host & client setup](./host-client-setup.md)** — wire up the Apollo host, the hub, and each
  Moonlight/Artemis client for local (LAN) and remote (WireGuard) tests, plus the per-test
  capture walkthrough.
- **[Deploying the hub](./deploy.md)** — the two deployment options (LAN/WireGuard and
  tailnet-only) and all `.env` configuration.
- **[Agent-less capture (Android & Xbox)](./agentless-capture.md)** — manual capture via the
  hub's **Manual entry** panel for clients that can't run the collector.
- **[Copilot analysis](./copilot-analysis.md)** — the `mock`/`cli`/`sdk` backends and their config.

## Reference
- **[Log paths & logging knobs](./log-paths.md)** — where each platform writes its log and how to
  turn verbosity up.
- **[Scenario matrix](./scenario-matrix.md)** — the local→remote / Ethernet→Wi-Fi test template.
- **[Troubleshooting](./troubleshooting.md)** — common streaming failure modes and where the
  hub/collectors help.
