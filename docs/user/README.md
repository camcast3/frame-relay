# User/operator guides

Start with [First multi-client test](./first-multi-client-test.md). It is the canonical
zero-context walkthrough from Docker start to a completed matched comparison.

## Start here

- [First multi-client test](./first-multi-client-test.md) — the main guide: bring up the hub,
  start the host watcher, run Windows/Linux clients, handle Xbox/manual capture, request
  authenticated screenshots, and compare results.

## Set up and operate

- [Host & client setup](./host-client-setup.md) — one-time setup plus local and remote capture
  flows.
- [Steam Game Mode / Big Picture launcher](./steam-game-mode.md) — make a Moonlight or Artemis
  Steam shortcut automatically create, capture, and stop each test on Windows or Linux.
- [Migrating to Frame Relay](./migrating-to-frame-relay.md) — upgrade existing Apollo Streaming
  Lab installations without losing Docker data or breaking collectors.
- [Deploying the hub](./deploy.md) — LAN/WireGuard, tailnet-only, or direct-on-host deployment.
- [Agent-less capture (Android & Xbox)](./agentless-capture.md) — manual evidence entry when the
  collector cannot run.
- [Copilot analysis](./copilot-analysis.md) — what Analyze/chat can tell you and how to enable the
  optional online backends.

## Reference

- [Log paths & logging knobs](./log-paths.md) — where each platform writes logs and how to turn
  verbosity up.
- [Scenario matrix](./scenario-matrix.md) — repeatable local/Wi-Fi/remote run order.
- [Troubleshooting](./troubleshooting.md) — common failure modes and what to inspect in a session.