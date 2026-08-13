# Copilot backends

User-facing behavior is summarized in [../user/copilot-analysis.md](../user/copilot-analysis.md). This page covers the implementation contract.

## Call flow

1. [../../hub/routers/analysis.py](../../hub/routers/analysis.py) loads the session bundle from `service.py`.
2. It finds related sessions for comparison.
3. [../../hub/copilot.py](../../hub/copilot.py) builds a structured context with `build_context(...)`.
4. `diagnose()` or `chat()` builds a prompt and dispatches to `_run(...)`.
5. `_run(...)` chooses `mock`, `cli`, or `sdk`, with fallback to `mock` for real-backend failures.

## Backend contract

| Backend | Implementation | Network use | Contract |
|---|---|---|---|
| `mock` | rule-based logic inside `copilot.py` | none | Must stay deterministic, offline, and good enough for tests/demo use. |
| `cli` | shells out to the Copilot CLI | yes | Uses the same prompt/context as every other backend. |
| `sdk` | lazy import of the Copilot Python SDK | yes | Also receives the exact same prompt/context. |

The key invariant is **context parity**: switching backends must not change what data Copilot sees.

## What `build_context(...)` includes

`build_context(...)` assembles a stable JSON-shaped payload containing:

- `scenario` — session identity, requested/effective settings, HDR details, visual assessment, comparison metadata
- `notes`
- `net_tests`
- `link_samples`
- host-only `display_samples`
- derived `display_validation`
- host/client log tails, capped by `ASL_COPILOT_LOG_TAIL_LINES`
- related sessions summarized for comparison

If you change this structure, update:

- `build_prompt(...)`
- any logic in the `mock` analyzer that expects the field
- tests that inspect findings
- user/maintainer docs if the externally visible contract changed

## Opt-in data behavior

- `mock` keeps all analysis local.
- `cli` and `sdk` only send data out when the operator explicitly clicks **Analyze** or sends a chat message.
- The prompt uses the stored bundle plus **log tails**, not the full historical log corpus.

Do not add background/automatic Copilot calls without updating both docs and user expectations.

## Fallback semantics

Real backends are allowed to fail without breaking the feature:

- `cli` failures (missing token/binary, non-zero exit, timeout, etc.) return the `mock` answer plus a short backend-error note.
- `sdk` failures (missing package/import drift/runtime errors) do the same.

That fallback behavior is intentional. Preserve it when changing backend code or config handling.

## Relevant configuration

Resolved in [../../hub/config.py](../../hub/config.py):

| Variable | Purpose |
|---|---|
| `ASL_COPILOT_BACKEND` | `mock`, `cli`, or `sdk` |
| `ASL_COPILOT_TOKEN` | Copilot-entitled token; falls back to `GITHUB_TOKEN` |
| `ASL_COPILOT_MODEL` | model name; `auto` means backend default |
| `ASL_COPILOT_CLI_PATH` | CLI binary path for the `cli` backend |
| `ASL_COPILOT_LOG_TAIL_LINES` | trailing log lines per source included in context |

Tests force `ASL_COPILOT_BACKEND=mock`; keep that path first-class.
