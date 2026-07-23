"""Copilot-powered session analysis.

Three interchangeable backends, selected by ASL_COPILOT_BACKEND:

* ``mock`` (default) - a fully offline, rule-based analyzer. No token, no network. It is
  deliberately useful on its own so the feature is demoable and testable, and it doubles as
  the fallback when a real backend is unavailable.
* ``cli``  - shells out to the Copilot CLI programmatic mode
  (``copilot -p <prompt> -s --no-ask-user --model <model>``).
* ``sdk``  - embeds the GitHub Copilot Python SDK (``github/copilot-sdk``). Imported lazily so
  the hub runs without the package installed; falls back to ``mock`` if the import fails.

All backends receive the same structured context built from the session bundle, so switching
backends never changes what data Copilot sees.
"""
from __future__ import annotations

import json
import subprocess
from typing import Any

from . import config

# Thresholds drawn from the Sunshine/Apollo troubleshooting guidance.
LOSS_WARN_PCT = 5.0
JITTER_WARN_MS = 1.0
RSSI_WEAK_DBM = -70

ERROR_KEYWORDS = (
    "error", "fail", "failed", "exception", "disconnect", "timeout", "timed out",
    "packet loss", "could not", "unable", "denied", "refused", "crash", "fatal",
    "not supported", "unsupported", "decoder", "hdr", "codec",
)


# --- context ------------------------------------------------------------------

def _tail(chunks: list[dict[str, Any]], lines: int) -> str:
    text = "\n".join(c.get("content", "") for c in chunks)
    rows = text.splitlines()
    return "\n".join(rows[-lines:])


def build_context(bundle: dict[str, Any], related: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    s = bundle["session"]
    return {
        "scenario": {
            "network_path": s.get("network_path"),
            "host": s.get("host"),
            "client": s.get("client"),
            "codec": s.get("codec"),
            "resolution": s.get("resolution"),
            "fps": s.get("fps"),
            "bitrate_mbps": s.get("bitrate_mbps"),
            "hdr": bool(s.get("hdr")),
            "encoder_settings": s.get("encoder_settings"),
            "outcome": s.get("outcome"),
        },
        "notes": s.get("notes"),
        "net_tests": bundle.get("net_tests", []),
        "link_samples": bundle.get("link_samples", []),
        "host_log_tail": _tail(bundle.get("host_logs", []), config.COPILOT_LOG_TAIL_LINES),
        "client_log_tail": _tail(bundle.get("client_logs", []), config.COPILOT_LOG_TAIL_LINES),
        "related_sessions": [
            {"id": r["id"], "network_path": r.get("network_path"),
             "outcome": r.get("outcome"), "notes": (r.get("notes") or "")[:200]}
            for r in (related or [])
        ],
    }


# --- rule-based signal extraction (shared by mock backend + prompt hints) -----

def _log_findings(text: str) -> list[str]:
    hits: list[str] = []
    for line in text.splitlines():
        low = line.lower()
        if any(k in low for k in ERROR_KEYWORDS):
            hits.append(line.strip())
    # de-dupe while preserving order, cap the list
    seen, out = set(), []
    for h in hits:
        if h not in seen:
            seen.add(h)
            out.append(h)
    return out[:15]


def analyze_signals(ctx: dict[str, Any]) -> dict[str, Any]:
    findings: list[str] = []

    for t in ctx.get("net_tests", []):
        loss = t.get("loss_pct")
        jit = t.get("jitter_ms")
        if loss is not None and loss > LOSS_WARN_PCT:
            findings.append(f"iperf3 packet loss {loss:.1f}% exceeds {LOSS_WARN_PCT}% - the "
                            f"network path cannot carry the stream cleanly.")
        if jit is not None and jit > JITTER_WARN_MS:
            findings.append(f"iperf3 jitter {jit:.2f} ms exceeds {JITTER_WARN_MS} ms - "
                            f"expect frame-pacing hitches.")

    samples = ctx.get("link_samples", [])
    client_samples = [s for s in samples if s.get("source") == "client"]
    bssids = {s.get("bssid") for s in client_samples if s.get("bssid")}
    if len(bssids) > 1:
        findings.append(f"Client roamed between {len(bssids)} access points during the session "
                        f"({', '.join(sorted(b for b in bssids if b))}) - a mid-stream roam "
                        f"typically causes a visible stall.")
    weak = [s for s in client_samples if s.get("rssi") is not None and s["rssi"] < RSSI_WEAK_DBM]
    if weak:
        worst = min(s["rssi"] for s in weak)
        findings.append(f"Weak Wi-Fi signal (down to {worst} dBm, below {RSSI_WEAK_DBM} dBm) - "
                        f"move closer to the AP or switch to Ethernet.")

    # Ethernet speed mismatch (buffer-overrun failure mode from the docs).
    def _speed(src: str) -> str | None:
        for s in samples:
            if s.get("source") == src and s.get("link_type") == "ethernet" and s.get("link_speed"):
                return s["link_speed"]
        return None

    host_speed, client_speed = _speed("host"), _speed("client")
    if host_speed and client_speed and host_speed != client_speed:
        findings.append(f"Host NIC ({host_speed}) is faster than the client NIC ({client_speed}) "
                        f"- burst traffic can overrun the slowest hop (buffer-overrun packet loss). "
                        f"Consider capping the host NIC or lowering bitrate.")

    host_findings = _log_findings(ctx.get("host_log_tail", ""))
    client_findings = _log_findings(ctx.get("client_log_tail", ""))
    return {
        "network": findings,
        "host_log": host_findings,
        "client_log": client_findings,
    }


# --- prompt -------------------------------------------------------------------

SYSTEM_PROMPT = (
    "You are diagnosing a game-streaming test between an Apollo/Sunshine host and a "
    "Moonlight/Artemis client. Given the scenario, network tests, Wi-Fi/link samples, and the "
    "tail of both host and client logs, explain concisely: (1) what happened, (2) the most "
    "likely root cause, (3) a concrete fix, and (4) the single most useful next test to run. "
    "Prefer specifics from the data. Note whether this looks like a local-LAN vs remote issue."
)


def build_prompt(ctx: dict[str, Any], question: str | None = None) -> str:
    parts = [SYSTEM_PROMPT, "", "## Session context (JSON)", "```json",
             json.dumps(ctx, indent=2, default=str), "```"]
    signals = analyze_signals(ctx)
    if any(signals.values()):
        parts += ["", "## Automatically detected signals",
                  json.dumps(signals, indent=2)]
    if question:
        parts += ["", "## Question", question]
    return "\n".join(parts)


# --- backends -----------------------------------------------------------------

def _mock(ctx: dict[str, Any], question: str | None) -> str:
    signals = analyze_signals(ctx)
    sc = ctx["scenario"]
    lines: list[str] = []
    lines.append(f"### Rule-based analysis ({sc.get('network_path') or 'unknown path'})")
    net = signals["network"]
    if net:
        lines.append("\n**Network / link:**")
        lines += [f"- {n}" for n in net]
    if signals["host_log"]:
        lines.append("\n**Host (Apollo) log flags:**")
        lines += [f"- `{h}`" for h in signals["host_log"]]
    if signals["client_log"]:
        lines.append("\n**Client (Moonlight/Artemis) log flags:**")
        lines += [f"- `{h}`" for h in signals["client_log"]]

    if not (net or signals["host_log"] or signals["client_log"]):
        lines.append("\nNo errors, packet loss, jitter, weak-signal or roam events were "
                     "detected in the supplied data. If the experience still felt off, capture "
                     "the Apollo performance overlay stats and attach an iperf3 run.")

    # A simple prioritized conclusion.
    lines.append("\n**Likely focus:**")
    if any("roam" in n for n in net):
        lines.append("- Wi-Fi roaming mid-stream. Lock the client to one AP/band or use Ethernet, then re-test.")
    elif any("loss" in n or "jitter" in n for n in net):
        lines.append("- Network path quality. Re-run iperf3, lower bitrate ~15%, and compare a wired run.")
    elif any("Weak Wi-Fi" in n for n in net):
        lines.append("- Wi-Fi signal strength. Improve placement/AP or switch to Ethernet.")
    elif signals["host_log"] or signals["client_log"]:
        lines.append("- Application-level errors above (codec/HDR/decoder/pairing). Address the flagged lines first.")
    else:
        lines.append("- Insufficient signal; gather overlay stats + iperf3 and re-analyze.")

    if question:
        lines.append(f"\n**Re: your question** \"{question}\" - answered from the same data above; "
                     f"enable a real Copilot backend (ASL_COPILOT_BACKEND=cli|sdk) for free-form Q&A.")
    lines.append("\n_(mock analyzer - set ASL_COPILOT_BACKEND=cli or sdk to use GitHub Copilot.)_")
    return "\n".join(lines)


def _cli(prompt: str) -> str:
    import os
    env = dict(os.environ)
    if config.COPILOT_TOKEN:
        env["GITHUB_TOKEN"] = config.COPILOT_TOKEN
    cmd = [config.COPILOT_CLI_PATH, "-p", prompt, "-s", "--no-ask-user"]
    if config.COPILOT_MODEL and config.COPILOT_MODEL != "auto":
        cmd += ["--model", config.COPILOT_MODEL]
    proc = subprocess.run(cmd, capture_output=True, text=True, env=env, timeout=180)
    if proc.returncode != 0:
        raise RuntimeError(f"copilot cli failed ({proc.returncode}): {proc.stderr.strip()}")
    return proc.stdout.strip()


def _sdk(prompt: str) -> str:
    # Imported lazily; the package name/shape may evolve, so we guard and fall back.
    try:
        from copilot import CopilotClient  # type: ignore
    except Exception as exc:  # noqa: BLE001
        raise RuntimeError(f"Copilot SDK not available: {exc}")
    client = CopilotClient()
    client.start()
    try:
        session = client.create_session(model=config.COPILOT_MODEL)
        resp = session.send_and_wait(prompt=prompt)
        return getattr(resp, "output", str(resp))
    finally:
        try:
            client.stop()
        except Exception:  # noqa: BLE001
            pass


def _run(prompt: str, ctx: dict[str, Any], question: str | None) -> str:
    backend = config.COPILOT_BACKEND
    if backend == "cli":
        try:
            return _cli(prompt)
        except Exception as exc:  # noqa: BLE001
            return f"{_mock(ctx, question)}\n\n> Copilot CLI backend error, used mock: {exc}"
    if backend == "sdk":
        try:
            return _sdk(prompt)
        except Exception as exc:  # noqa: BLE001
            return f"{_mock(ctx, question)}\n\n> Copilot SDK backend error, used mock: {exc}"
    return _mock(ctx, question)


def diagnose(bundle: dict[str, Any], related: list[dict[str, Any]] | None = None) -> str:
    ctx = build_context(bundle, related)
    return _run(build_prompt(ctx), ctx, None)


def chat(bundle: dict[str, Any], history: list[dict[str, Any]], message: str,
         related: list[dict[str, Any]] | None = None) -> str:
    ctx = build_context(bundle, related)
    convo = "\n".join(f"{m['role']}: {m['content']}" for m in history[-10:])
    prompt = build_prompt(ctx, question=message)
    if convo:
        prompt += f"\n\n## Prior conversation\n{convo}"
    return _run(prompt, ctx, message)
