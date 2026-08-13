# Maintainer guide

Implementation-facing documentation for repository maintainers and coding agents.

Keep [../../.github/copilot-instructions.md](../../.github/copilot-instructions.md) terse and mandatory; put the rationale and durable detail here. Keep operator walkthroughs in the user docs under `../user/`.

## Map

- [architecture.md](./architecture.md) — repo shape, layering, session-centric flow, runtime boundaries.
- [development.md](./development.md) — local setup, test loops, import-time config caveats, Docker smoke checks.
- [api-and-data-model.md](./api-and-data-model.md) — `models.py` contract, schema/migration rules, JSON columns, API/storage surfaces.
- [collectors-and-parsers.md](./collectors-and-parsers.md) — stdlib-only collector rules, parser/discovery splits, watch/live workflows, Windows console-session constraints.
- [copilot-backends.md](./copilot-backends.md) — `mock`/`cli`/`sdk` implementation, context parity, fallback behavior, config.
- [security-and-operations.md](./security-and-operations.md) — LAN trust boundary, screenshot-token design, artifacts/privacy, persistence, firewall/deployment concerns.

## Editing policy

- Update these maintainer docs when you change architecture, data contracts, or operational constraints.
- Update [../../.github/copilot-instructions.md](../../.github/copilot-instructions.md) only for short rules every agent must obey.
- Prefer links to existing user docs such as [../user/deploy.md](../user/deploy.md), [../user/host-client-setup.md](../user/host-client-setup.md), and [../user/first-multi-client-test.md](../user/first-multi-client-test.md) over copying their full prose here.
