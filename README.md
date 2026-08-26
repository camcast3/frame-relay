# Apollo Streaming Lab

Apollo Streaming Lab helps you run repeatable **Apollo/Sunshine** streaming tests and keep the
results in one place. Each session can combine:
- the **Apollo host log**,
- the **Moonlight/Artemis client log** or manual Xbox/Android evidence,
- **requested vs effective** stream settings,
- **Wi-Fi/link samples** and **iperf3** results,
- **screenshots, notes, and outcome**, and
- optional **Copilot analysis** to help explain what happened.

Use it when you want to compare clients, prove whether a problem is the network versus the decoder
or HDR path, or keep a clean record of LAN/WireGuard streaming tests.

## Start Here

If you are new to the project, begin with
**[First multi-client test](./docs/user/first-multi-client-test.md)**. It is the canonical
zero-context walkthrough from hub startup to a finished matched comparison, including the
authenticated screenshot flow and Xbox/manual capture.

## Fastest LAN / Docker start

```powershell
git clone https://github.com/camcast3/apollo-streaming-lab.git
cd apollo-streaming-lab
Copy-Item .env.example .env
docker compose -f docker-compose.lan.yaml up -d --build
```

Then open `http://<hub-host>:8080` from the devices that will capture or review sessions.

## What you use during a test

- **Hub** — browser UI and database for sessions, comparisons, artifacts, notes, and Copilot
  analysis.
- **Host collector** — Windows script beside Apollo that uploads the host log, classifies the
  client's network path, and records display/link evidence.
- **Client capture** — Windows/Linux collectors for Moonlight or Artemis, or manual entry for
  Xbox/Android when no collector can run.

## User guides

- **[First multi-client test](./docs/user/first-multi-client-test.md)** — canonical start-to-
  finish walkthrough; begin here.
- **[Host & client setup](./docs/user/host-client-setup.md)** — one-time setup for the hub,
  Apollo host, and clients, plus local and remote capture flows.
- **[Steam Game Mode / Big Picture launcher](./docs/user/steam-game-mode.md)** — wrap an existing
  Moonlight or Artemis Steam shortcut so every launch is captured automatically.
- **[Deploying the hub](./docs/user/deploy.md)** — LAN/WireGuard, tailnet-only, or direct-on-host
  deployment.
- **[Agent-less capture (Android & Xbox)](./docs/user/agentless-capture.md)** — manual evidence
  entry for platforms that cannot run the collector.
- **[Log paths & logging knobs](./docs/user/log-paths.md)** — where each platform writes logs and
  how to turn verbosity up.
- **[Scenario matrix](./docs/user/scenario-matrix.md)** — repeatable local/Wi-Fi/remote run order.
- **[Troubleshooting](./docs/user/troubleshooting.md)** — common failure modes and what to inspect
  in a session.
- **[Copilot analysis](./docs/user/copilot-analysis.md)** — what Analyze/chat can tell you and how
  the optional backends behave.

## Maintainers

For code, schemas, deployment internals, or maintenance work, start with the audience router in
[docs/README.md](./docs/README.md).