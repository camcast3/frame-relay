"""Copilot-powered session analysis.

Three interchangeable backends, selected by FRAME_RELAY_COPILOT_BACKEND:

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
import re
import subprocess
from typing import Any

from . import config
from . import display_validation

# Thresholds drawn from the Sunshine/Apollo troubleshooting guidance.
LOSS_WARN_PCT = 5.0
JITTER_WARN_MS = 1.0
RSSI_WEAK_DBM = -70

ERROR_KEYWORDS = (
    "error", "fail", "failed", "exception", "disconnect", "timeout", "timed out",
    "packet loss", "could not", "unable", "denied", "refused", "crash", "fatal",
    "not supported", "unsupported", "decoder", "hdr", "codec",
)

# Lines that match ERROR_KEYWORDS but are normal, expected output. Apollo's encoder probe
# deliberately provokes failures ("you can safely ignore those errors") and both sides log
# plenty of informational codec/HDR/decoder chatter; surfacing it drowns the real signal.
BENIGN_LOG_PATTERNS = (
    "testing for available encoders",
    "ignore any errors mentioned above",
    "is not supported on this gpu",
    "nvapi_initialize() failed",
    "decoder guids reported as supported",
    "video decoder chosen",
    "decoder texture access",
    "color coding:",
    "display is hdr:",
    "client dynamicrange:",
    "hdr_state",
    "changing hdr states",
    "using windows recommended modes",
    # Artemis probes several optional command endpoints that Apollo does not implement;
    # the resulting 404s are expected on every single connect.
    "qnetworkreply::contentnotfounderror",
    "servercommandmanager::fetchavailablecommands",
    "reference frame invalidation is not supported",
    # Request/URL debug lines match on query parameters such as hdrMode=, not on real errors.
    "nvhttp::openconnection",
    "executing request:",
)

# Client-side audio trouble. Moonlight/Artemis logs out-of-sequence audio and enters a
# "fast audio recovery" mode when audio packets are lost or arrive reordered - the usual
# cause of brief audio dropouts while video still looks fine.
AUDIO_OOS_RE = re.compile(r"OOS audio data", re.I)
AUDIO_RECOVERY_RE = re.compile(r"fast audio recovery", re.I)
OPUS_CHANNELS_RE = re.compile(r"Opus initialized:.*?(\d+)\s+channels", re.I)
AUDIO_INIT_RE = re.compile(r"Initializing audio stream|Starting audio stream", re.I)
# Client log lines are stamped with an elapsed "HH:MM:SS - " prefix.
CLIENT_TS_RE = re.compile(r"^\s*(\d+):(\d{2}):(\d{2})\s*-")
# An out-of-sequence audio event this soon after the audio stream starts is just the normal
# initial resync, not a sign of a lossy path.
AUDIO_STARTUP_GRACE_S = 15

# Moonlight/Artemis prints a performance summary when a stream ends (and to its log during
# the stream). These numbers are the client's own measurement of the path and are far more
# reliable than guessing from the host side.
NET_FRAME_DROP_RE = re.compile(
    r"Frames dropped by your network connection:\s*([\d.]+)\s*%", re.I)
JITTER_FRAME_DROP_RE = re.compile(
    r"Frames dropped due to network jitter:\s*([\d.]+)\s*%", re.I)
NET_LATENCY_RE = re.compile(
    r"Average network latency:\s*(\d+)\s*ms(?:\s*\(variance:\s*(\d+)\s*ms\))?", re.I)
IDR_DROP_LIMIT_RE = re.compile(r"Reached consecutive drop limit", re.I)

# Frame loss the client attributes to the network. Anything sustained above this is visible
# as hitching and audible as audio dropouts, well before the 5% iperf3 threshold.
FRAME_DROP_WARN_PCT = 1.0


# --- context ------------------------------------------------------------------

def _tail(chunks: list[dict[str, Any]], lines: int) -> str:
    text = "\n".join(c.get("content", "") for c in chunks)
    rows = text.splitlines()
    return "\n".join(rows[-lines:])


def build_context(bundle: dict[str, Any], related: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    s = bundle["session"]
    display_samples = [
        sample for sample in bundle.get("display_samples", [])
        if sample.get("source") == "host"
    ]
    return {
        "scenario": {
            "comparison_label": s.get("comparison_label"),
            "apollo_app": s.get("apollo_app"),
            "game_title": s.get("game_title"),
            "network_path": s.get("network_path"),
            "host": s.get("host"),
            "client": s.get("client"),
            "client_role": s.get("client_role"),
            "client_platform": s.get("client_platform"),
            "client_version": s.get("client_version"),
            "requested_settings": s.get("requested_settings") or {},
            "codec": s.get("codec"),
            "resolution": s.get("resolution"),
            "fps": s.get("fps"),
            "bitrate_mbps": s.get("bitrate_mbps"),
            "hdr": bool(s.get("hdr")),
            "hdr_details": s.get("hdr_details") or {},
            "visual_assessment": s.get("visual_assessment") or {},
            "encoder_settings": s.get("encoder_settings"),
            "outcome": s.get("outcome"),
        },
        "notes": s.get("notes"),
        "net_tests": bundle.get("net_tests", []),
        "link_samples": bundle.get("link_samples", []),
        "display_samples": display_samples,
        "display_validation": display_validation.summarize(s, display_samples),
        "host_log_tail": _tail(bundle.get("host_logs", []), config.COPILOT_LOG_TAIL_LINES),
        "client_log_tail": _tail(bundle.get("client_logs", []), config.COPILOT_LOG_TAIL_LINES),
        "related_sessions": [
            {
                "id": r["id"],
                "comparison_label": r.get("comparison_label"),
                "apollo_app": r.get("apollo_app"),
                "game_title": r.get("game_title"),
                "network_path": r.get("network_path"),
                "host": r.get("host"),
                "client": r.get("client"),
                "client_role": r.get("client_role"),
                "client_platform": r.get("client_platform"),
                "requested_settings": r.get("requested_settings") or {},
                "effective_settings": {
                    "codec": r.get("codec"),
                    "resolution": r.get("resolution"),
                    "fps": r.get("fps"),
                    "bitrate_mbps": r.get("bitrate_mbps"),
                    "hdr": bool(r.get("hdr")),
                },
                "hdr_details": r.get("hdr_details") or {},
                "visual_assessment": r.get("visual_assessment") or {},
                "outcome": r.get("outcome"),
                "notes": (r.get("notes") or "")[:200],
            }
            for r in (related or [])
        ],
    }


# --- rule-based signal extraction (shared by mock backend + prompt hints) -----

def _log_findings(text: str) -> list[str]:
    hits: list[str] = []
    for line in text.splitlines():
        low = line.lower()
        if not any(k in low for k in ERROR_KEYWORDS):
            continue
        if any(b in low for b in BENIGN_LOG_PATTERNS):
            continue
        hits.append(line.strip())
    # de-dupe while preserving order, cap the list
    seen, out = set(), []
    for h in hits:
        if h not in seen:
            seen.add(h)
            out.append(h)
    return out[:15]


def _client_ts(line: str) -> int | None:
    """Elapsed seconds from a client log line's "HH:MM:SS - " prefix."""
    m = CLIENT_TS_RE.match(line)
    if not m:
        return None
    h, mi, s = (int(g) for g in m.groups())
    return h * 3600 + mi * 60 + s


def _count_oos(client_log: str) -> tuple[int, int]:
    """Split out-of-sequence audio events into (startup_resync, mid_stream).

    Every audio (re)init is followed by a resync as the client finds the stream, so those
    events are expected. Only events well clear of a restart mean the path is losing audio.
    """
    startup = mid = 0
    last_init: int | None = None
    for line in client_log.splitlines():
        ts = _client_ts(line)
        if AUDIO_INIT_RE.search(line):
            last_init = ts
            continue
        if not AUDIO_OOS_RE.search(line):
            continue
        if (ts is not None and last_init is not None
                and 0 <= ts - last_init <= AUDIO_STARTUP_GRACE_S):
            startup += 1
        else:
            mid += 1
    return startup, mid


def _audio_findings(host_log: str, client_log: str) -> list[str]:
    """Detect audio dropouts, which show up as lost/reordered audio packets on the client.

    Video degrades gracefully (Apollo protects the video stream), so audio is usually the
    first thing to break on a marginal link - and the host log stays completely clean.
    """
    findings: list[str] = []

    startup_oos, mid_oos = _count_oos(client_log)
    if mid_oos:
        findings.append(
            f"Client reported out-of-sequence audio {mid_oos}x mid-stream - audio packets are "
            f"being lost or reordered on the path to the client, which is heard as brief audio "
            f"dropouts."
        )
    elif startup_oos:
        findings.append(
            f"Client reported out-of-sequence audio {startup_oos}x, but every event follows an "
            f"audio (re)start within {AUDIO_STARTUP_GRACE_S}s, so this is the normal initial "
            f"resync rather than a lossy path. Look elsewhere for steady-state audio dropouts."
        )

    chans = OPUS_CHANNELS_RE.search(host_log)
    if chans:
        try:
            n = int(chans.group(1))
        except ValueError:
            n = 0
        if n > 2:
            findings.append(
                f"Host negotiated {n}-channel (surround) Opus audio. That is several times "
                f"the bitrate of stereo and the client must decode and downmix it; on a "
                f"handheld or phone this alone can cause audio dropouts. The client chooses "
                f"this - set the client's audio configuration to stereo to rule it out."
            )
    return findings


def _client_stat_findings(client_log: str) -> list[str]:
    """Read Moonlight/Artemis' own performance summary out of the client log.

    The client measures the path end-to-end, so these numbers separate *loss* from *jitter*
    and from host-side slowness far more reliably than inference from the host side.
    """
    findings: list[str] = []

    drops = [float(m) for m in NET_FRAME_DROP_RE.findall(client_log)]
    worst = max(drops) if drops else 0.0
    if worst >= FRAME_DROP_WARN_PCT:
        findings.append(
            f"Client reports {worst:.2f}% of frames dropped by the network connection "
            f"(threshold {FRAME_DROP_WARN_PCT}%). The path is losing packets, which shows up "
            f"as hitching video and audio dropouts."
        )

        lat = NET_LATENCY_RE.search(client_log)
        jitter_drops = [float(m) for m in JITTER_FRAME_DROP_RE.findall(client_log)]
        worst_jitter = max(jitter_drops) if jitter_drops else 0.0
        if lat and lat.group(2) is not None and int(lat.group(2)) <= 1 and worst_jitter < 1.0:
            findings.append(
                f"Network latency is only {lat.group(1)} ms with {lat.group(2)} ms variance and "
                f"{worst_jitter:.2f}% jitter-related drops, so this is packet *loss*, not "
                f"congestion delay - typical of a Wi-Fi link that cannot absorb the bitrate's "
                f"bursts. Lower the client's bitrate (or move it to Ethernet) rather than "
                f"chasing latency."
            )

    if IDR_DROP_LIMIT_RE.search(client_log):
        findings.append(
            "Client hit its consecutive-drop limit and had to request a new IDR/key frame - a "
            "burst of packets was lost outright, which is long enough to hear as an audio gap."
        )
    return findings


def _stream_findings(scenario: dict[str, Any]) -> list[str]:
    findings: list[str] = []
    requested = scenario.get("requested_settings") or {}
    effective = {
        "codec": scenario.get("codec"),
        "resolution": scenario.get("resolution"),
        "fps": scenario.get("fps"),
        "bitrate_mbps": scenario.get("bitrate_mbps"),
        "hdr": scenario.get("hdr"),
    }
    for field, label in (
        ("codec", "codec"),
        ("resolution", "resolution"),
        ("fps", "frame rate"),
        ("bitrate_mbps", "bitrate"),
    ):
        req, got = requested.get(field), effective.get(field)
        if req is not None and got is not None and str(req).lower() != str(got).lower():
            findings.append(f"Client requested {label} {req}, but Apollo used {got}.")

    req_hdr = requested.get("hdr")
    hd = scenario.get("hdr_details") or {}
    if req_hdr is True and hd.get("host_display_hdr") is False:
        findings.append(
            "Client requested HDR, but the Apollo host display was SDR; the stream cannot carry "
            "the intended native HDR presentation."
        )
    if req_hdr is True and hd.get("encoded_hdr") is False:
        findings.append(
            "Client requested HDR, but Apollo encoded SDR. Check the host HDR display state, "
            "virtual display mode, codec support, and Apollo HDR configuration."
        )
    if hd.get("encoded_hdr") is True and hd.get("client_display_hdr") is False:
        findings.append(
            "Apollo encoded HDR, but the client reports an SDR display path; expect tone mapping, "
            "washed-out color, clipping, or an HDR fallback on this client."
        )
    tone = hd.get("tone_mapping")
    if tone and str(tone).lower() not in ("off", "disabled", "none", "native"):
        findings.append(f"Client HDR path reports tone mapping ({tone}); it is not a native HDR pass-through.")
    status = str(hd.get("status") or "").lower()
    if status in ("partial", "fallback", "failed"):
        findings.append(f"Structured HDR result is {status} for this client.")
    return findings


def _comparison_findings(scenario: dict[str, Any], peers: list[dict[str, Any]]) -> list[str]:
    label = scenario.get("comparison_label")
    if not label:
        return []
    matched = [p for p in peers if p.get("comparison_label") == label]
    if not matched:
        return []
    findings: list[str] = []
    current_role = scenario.get("client_role") or scenario.get("client")
    current_hd = scenario.get("hdr_details") or {}
    current_status = current_hd.get("status")
    current_visual = (scenario.get("visual_assessment") or {}).get("rating")
    for peer in matched:
        peer_name = peer.get("client_role") or peer.get("client") or peer.get("id")
        peer_status = (peer.get("hdr_details") or {}).get("status")
        if current_status and peer_status and current_status != peer_status:
            findings.append(
                f"Matched test case differs by client: {current_role} HDR result is "
                f"{current_status}, while {peer_name} is {peer_status}."
            )
        peer_visual = (peer.get("visual_assessment") or {}).get("rating")
        if current_visual is not None and peer_visual is not None and abs(current_visual - peer_visual) >= 2:
            findings.append(
                f"Operator HDR rating differs materially: {current_role} {current_visual}/5 "
                f"versus {peer_name} {peer_visual}/5."
            )
    return findings


def _display_findings(ctx: dict[str, Any]) -> list[str]:
    samples = ctx.get("display_samples") or []
    if not samples:
        return []
    result = ctx.get("display_validation") or {}
    checks = result.get("checks") or {}
    findings: list[str] = []
    topology_observed = checks.get("topology_observed")
    if topology_observed is False:
        findings.append("No active Windows display topology was observed during the stream.")
    if checks.get("virtual_display_active") is False:
        findings.append(
            "The active streamed display was not identified as an Apollo/Sunshine virtual "
            "display."
        )
    elif topology_observed is True and checks.get("virtual_display_active") is None:
        findings.append(
            "Display topology was captured, but the active target could not be confidently "
            "identified as virtual from its Windows device names."
        )
    if checks.get("resolution_matches") is False:
        findings.append(
            f"Virtual display resolution mismatch: expected "
            f"{result.get('expected', {}).get('resolution')}, observed "
            f"{result.get('actual', {}).get('resolution')}."
        )
    if checks.get("refresh_matches") is False:
        findings.append(
            f"Virtual display refresh mismatch: expected about "
            f"{result.get('expected', {}).get('refresh_hz')} Hz, observed "
            f"{result.get('actual', {}).get('refresh_hz')} Hz."
        )
    if checks.get("hdr_matches") is False:
        findings.append(
            f"Windows Advanced Color state does not match the requested HDR mode "
            f"(expected {result.get('expected', {}).get('hdr')}, observed "
            f"{result.get('actual', {}).get('hdr')})."
        )
    if checks.get("topology_restored_after") is False:
        findings.append("The Windows display topology did not return to its pre-stream targets.")
    return findings


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
    findings += _audio_findings(ctx.get("host_log_tail", ""), ctx.get("client_log_tail", ""))
    findings += _client_stat_findings(ctx.get("client_log_tail", ""))
    return {
        "network": findings,
        "display": _display_findings(ctx),
        "stream": _stream_findings(ctx.get("scenario", {})),
        "comparison": _comparison_findings(
            ctx.get("scenario", {}), ctx.get("related_sessions", [])
        ),
        "host_log": host_findings,
        "client_log": client_findings,
    }


# --- prompt -------------------------------------------------------------------

SYSTEM_PROMPT = (
    "You are diagnosing a game-streaming test between an Apollo/Sunshine host and a "
    "Moonlight/Artemis client. Given stream identity, requested versus effective settings, the "
    "HDR pipeline, matched client comparisons, network tests, Wi-Fi/link samples, and both log "
    "tails, explain concisely: (1) what happened, (2) the most "
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
    if signals["display"]:
        lines.append("\n**Virtual display:**")
        lines += [f"- {n}" for n in signals["display"]]
    if signals["stream"]:
        lines.append("\n**Requested / effective stream and HDR:**")
        lines += [f"- {n}" for n in signals["stream"]]
    if signals["comparison"]:
        lines.append("\n**Matched client comparison:**")
        lines += [f"- {n}" for n in signals["comparison"]]
    if signals["host_log"]:
        lines.append("\n**Host (Apollo) log flags:**")
        lines += [f"- `{h}`" for h in signals["host_log"]]
    if signals["client_log"]:
        lines.append("\n**Client (Moonlight/Artemis) log flags:**")
        lines += [f"- `{h}`" for h in signals["client_log"]]

    if not (net or signals["display"] or signals["stream"] or signals["comparison"]
            or signals["host_log"] or signals["client_log"]):
        lines.append("\nNo errors, packet loss, jitter, weak-signal or roam events were "
                     "detected in the supplied data. If the experience still felt off, capture "
                     "the Apollo performance overlay stats and attach an iperf3 run.")

    # A simple prioritized conclusion.
    lines.append("\n**Likely focus:**")
    if any("roam" in n for n in net):
        lines.append("- Wi-Fi roaming mid-stream. Lock the client to one AP/band or use Ethernet, then re-test.")
    elif any("dropped by the network connection" in n for n in net):
        lines.append("- Packet loss on the path to the client. Lower the client's bitrate until the "
                     "drop rate falls below 1%, and compare against a wired run to confirm the "
                     "wireless link is the limit.")
    elif any("out-of-sequence audio" in n and "mid-stream" in n for n in net):
        lines.append("- Audio packet loss on the path to the client. Check the client's link "
                     "(Wi-Fi vs Ethernet), lower the bitrate so bursts stop crowding out audio, "
                     "and confirm the client is set to stereo.")
    elif any("surround) Opus" in n for n in net):
        lines.append("- Surround audio on a client that must downmix it. Set the client's audio "
                     "configuration to stereo and re-test.")
    elif any("loss" in n or "jitter" in n for n in net):
        lines.append("- Network path quality. Re-run iperf3, lower bitrate ~15%, and compare a wired run.")
    elif any("Weak Wi-Fi" in n for n in net):
        lines.append("- Wi-Fi signal strength. Improve placement/AP or switch to Ethernet.")
    elif signals["display"]:
        lines.append("- Windows virtual-display creation, mode, HDR state, or teardown. Fix the "
                     "failed topology check above before attributing the result to the network.")
    elif signals["stream"] or signals["comparison"]:
        lines.append("- Stream negotiation or HDR-pipeline mismatch above. Re-run the same test "
                     "case with matched settings and verify every HDR stage before comparing visuals.")
    elif signals["host_log"] or signals["client_log"]:
        lines.append("- Application-level errors above (codec/HDR/decoder/pairing). Address the flagged lines first.")
    else:
        lines.append("- Insufficient signal; gather overlay stats + iperf3 and re-analyze.")

    if question:
        lines.append(f"\n**Re: your question** \"{question}\" - answered from the same data above; "
                     f"enable a real Copilot backend "
                     f"(FRAME_RELAY_COPILOT_BACKEND=cli|sdk) for free-form Q&A.")
    lines.append(
        "\n_(mock analyzer - set FRAME_RELAY_COPILOT_BACKEND=cli or sdk "
        "to use GitHub Copilot.)_"
    )
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
