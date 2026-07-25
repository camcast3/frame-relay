# Copilot analysis

Every session has an on-demand **Analyze** button and a follow-up **chat**. Analysis is
**opt-in per session** — session data (scenario, iperf3 results, link samples, and the tail of
both logs) only leaves the box when you click **Analyze** or ask a chat question.

The analyzer lives in [`hub/copilot.py`](../hub/copilot.py) and has three interchangeable
backends selected by `ASL_COPILOT_BACKEND`. All three receive the *same* structured context from
`build_context(...)`, so switching backends never changes what Copilot sees.

| Backend | What it does | Needs a token? |
|---------|--------------|----------------|
| `mock` (default) | Offline, rule-based diagnosis. No network, always available. Doubles as the fallback. | No |
| `cli` | Shells out to the Copilot CLI (`copilot -p <prompt> -s --no-ask-user [--model <model>]`). | Yes |
| `sdk` | Embeds the GitHub Copilot Python SDK (imported lazily). | Yes |

`cli` and `sdk` **fall back to `mock`** on any error (missing token, CLI not found, import
failure, non-zero exit), appending a short note about what failed — so the feature never breaks.

## The `mock` analyzer's rules
Even offline it flags the common Apollo/Sunshine failure modes from the session data:
- **iperf3 packet loss > 5%** or **jitter > 1 ms** on a net test.
- **Wi-Fi roam** — more than one client BSSID during the session (a mid-stream AP change).
- **Weak Wi-Fi** — client RSSI below −70 dBm.
- **NIC-speed mismatch** — host Ethernet faster than the client's (buffer-overrun packet loss).
- **Log errors** — error/disconnect/timeout/codec/HDR/decoder keywords in either log tail.

It then prints a prioritized "likely focus" conclusion.

## Configuration
Set these in `.env` (see [deploy.md](./deploy.md)); resolved in [`hub/config.py`](../hub/config.py):

| Variable | Default | Purpose |
|----------|---------|---------|
| `ASL_COPILOT_BACKEND` | `mock` | `mock` / `cli` / `sdk`. |
| `ASL_COPILOT_TOKEN` | — | GitHub token with a Copilot entitlement (`cli`/`sdk`). Falls back to `GITHUB_TOKEN`. |
| `ASL_COPILOT_MODEL` | `auto` | Model name; `auto` uses the app default (no `--model` flag). |
| `ASL_COPILOT_CLI_PATH` | `copilot` | Path to the Copilot CLI binary (`cli` backend). |
| `ASL_COPILOT_LOG_TAIL_LINES` | `400` | Trailing log lines per source included in the prompt. |
