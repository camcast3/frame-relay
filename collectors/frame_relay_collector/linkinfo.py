"""Detect the active network link and (on Wi-Fi) which access point it is using.

The command *parsers* are separated from the command *runners* so they can be unit
tested against captured sample output. ``detect()`` picks the right commands for the
platform and returns a link sample dict matching the hub's LinkSampleIn model.

Windows exposes Wi-Fi signal only as a percentage; we also derive an approximate RSSI
(dBm) with the common ``rssi = pct/2 - 100`` conversion so charts line up with Linux
(which reports true dBm). The percentage is preserved separately.
"""
from __future__ import annotations

import platform
import re
import shutil
import subprocess
from typing import Any, Optional


# --- parsers ------------------------------------------------------------------

def pct_to_dbm(pct: Optional[int]) -> Optional[int]:
    """Windows netsh reports signal quality %; approximate dBm for a comparable chart."""
    if pct is None:
        return None
    return round(pct / 2 - 100)


def freq_to_band_channel(mhz: int) -> tuple[str, Optional[int]]:
    if 2400 <= mhz <= 2500:
        return "2.4GHz", (mhz - 2407) // 5
    if 5925 <= mhz <= 7125:
        return "6GHz", (mhz - 5950) // 5
    if 5000 <= mhz < 5925:
        return "5GHz", (mhz - 5000) // 5
    return "?", None


def netsh_bssid_blocked(text: str) -> bool:
    """True when Windows withheld the BSSID because Location Services are off.

    Windows 11 24H2+ treats a BSSID as location data, so `netsh wlan show interfaces`
    omits it (and prints a permission notice) unless Location Services are enabled. SSID,
    band, channel and signal still come through, so the only thing lost is **roam
    detection** - which needs the BSSID to tell one AP from another.
    """
    low = text.lower()
    if "location" not in low:
        return False
    return ("location permission" in low
            or "location services" in low
            or "privacy & security" in low)


def parse_netsh_wlan(text: str) -> dict[str, Any]:
    """Parse `netsh wlan show interfaces` (Windows)."""
    kv: dict[str, str] = {}
    for line in text.splitlines():
        if " : " in line:
            k, _, v = line.partition(" : ")
            kv[k.strip().lower()] = v.strip()
    if not kv.get("ssid") and kv.get("state", "").lower() != "connected":
        return {}
    pct = None
    if kv.get("signal", "").endswith("%"):
        try:
            pct = int(kv["signal"].rstrip("%"))
        except ValueError:
            pct = None
    rate = kv.get("receive rate (mbps)") or kv.get("transmit rate (mbps)")
    return {
        "link_type": "wifi",
        "iface": kv.get("name"),
        "ssid": kv.get("ssid") or None,
        "bssid": (kv.get("bssid") or "").lower() or None,
        "band": kv.get("band"),
        "channel": kv.get("channel"),
        "phy_mode": kv.get("radio type"),
        "signal_pct": pct,
        "rssi": pct_to_dbm(pct),
        "link_speed": f"{rate} Mbps" if rate else None,
    }


def parse_iw_link(text: str) -> dict[str, Any]:
    """Parse `iw dev <dev> link` (Linux)."""
    if text.strip().lower().startswith("not connected"):
        return {}
    out: dict[str, Any] = {"link_type": "wifi"}
    m = re.search(r"Connected to ([0-9a-fA-F:]{17})(?:\s+\(on (\S+)\))?", text)
    if m:
        out["bssid"] = m.group(1).lower()
        if m.group(2):
            out["iface"] = m.group(2)
    m = re.search(r"^\s*SSID:\s*(.+)$", text, re.MULTILINE)
    if m:
        out["ssid"] = m.group(1).strip()
    m = re.search(r"^\s*freq:\s*(\d+)", text, re.MULTILINE)
    if m:
        band, ch = freq_to_band_channel(int(m.group(1)))
        out["band"] = band
        out["channel"] = str(ch) if ch is not None else None
    m = re.search(r"^\s*signal:\s*(-?\d+)\s*dBm", text, re.MULTILINE)
    if m:
        out["rssi"] = int(m.group(1))
    m = re.search(r"^\s*rx bitrate:\s*([\d.]+)\s*(\S+)", text, re.MULTILINE)
    if m:
        out["link_speed"] = f"{m.group(1)} {m.group(2)}"
    return out


def parse_ethtool(text: str, iface: Optional[str] = None) -> dict[str, Any]:
    """Parse `ethtool <dev>` (Linux) for a wired link."""
    out: dict[str, Any] = {"link_type": "ethernet", "iface": iface}
    m = re.search(r"^\s*Speed:\s*(\S+)", text, re.MULTILINE)
    if m and m.group(1).lower() != "unknown!":
        out["link_speed"] = m.group(1)
    if re.search(r"Link detected:\s*no", text):
        return {}
    return out


def parse_nmcli_wifi(text: str) -> dict[str, Any]:
    """Parse `nmcli -t -f ACTIVE,SSID,BSSID,CHAN,FREQ,RATE,SIGNAL dev wifi` (Linux).

    nmcli terse mode escapes the colons inside a BSSID as ``\\:``.
    """
    for line in text.splitlines():
        # split on unescaped colons
        fields = re.split(r"(?<!\\):", line)
        fields = [f.replace("\\:", ":") for f in fields]
        if fields and fields[0] == "yes":
            active, ssid, bssid, chan, freq, rate, signal = (fields + [""] * 7)[:7]
            pct = int(signal) if signal.isdigit() else None
            band = None
            if freq:
                mhz = int(re.sub(r"\D", "", freq) or 0)
                band, _ = freq_to_band_channel(mhz)
            return {
                "link_type": "wifi", "ssid": ssid or None, "bssid": bssid.lower() or None,
                "channel": chan or None, "band": band, "signal_pct": pct,
                "rssi": pct_to_dbm(pct), "link_speed": rate or None,
            }
    return {}


def parse_get_netadapter(text: str) -> dict[str, Any]:
    """Parse `Get-NetAdapter | ... LinkSpeed` output (Windows wired)."""
    m = re.search(r"([\d.]+\s*[GM]bps)", text)
    return {"link_type": "ethernet", "link_speed": m.group(1) if m else None}


# --- runners ------------------------------------------------------------------

def _run(cmd: list[str]) -> Optional[str]:
    exe = shutil.which(cmd[0])
    if not exe:
        return None
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=15)
        return p.stdout if p.returncode == 0 else None
    except Exception:  # noqa: BLE001
        return None


_warned_bssid_blocked = False


def _detect_windows() -> dict[str, Any]:
    global _warned_bssid_blocked
    out = _run(["netsh", "wlan", "show", "interfaces"])
    if out:
        sample = parse_netsh_wlan(out)
        if sample:
            if (sample.get("link_type") == "wifi" and not sample.get("bssid")
                    and not _warned_bssid_blocked):
                _warned_bssid_blocked = True
                if netsh_bssid_blocked(out):
                    print("note: Windows withheld the Wi-Fi BSSID because Location Services "
                          "are off, so AP-roam detection is disabled for this machine. "
                          "Enable Settings > Privacy & security > Location to capture it.")
                else:
                    print("note: no BSSID reported for this Wi-Fi link, so AP-roam detection "
                          "is disabled for this machine.")
            return sample
    ps = _run(["powershell", "-NoProfile", "-Command",
               "Get-NetAdapter -Physical | Where-Object Status -eq 'Up' | "
               "Select-Object -First 1 -ExpandProperty LinkSpeed"])
    if ps:
        return parse_get_netadapter(ps)
    return {"link_type": "other"}


def _detect_linux() -> dict[str, Any]:
    dev = _run(["bash", "-lc", "iw dev | awk '/Interface/ {print $2; exit}'"])
    dev = (dev or "").strip()
    if dev:
        link = _run(["iw", "dev", dev, "link"])
        if link and "Not connected" not in link:
            return parse_iw_link(link)
    nm = _run(["nmcli", "-t", "-f", "ACTIVE,SSID,BSSID,CHAN,FREQ,RATE,SIGNAL", "dev", "wifi"])
    if nm:
        sample = parse_nmcli_wifi(nm)
        if sample:
            return sample
    # wired fallback: first non-loopback interface that is up
    dev = _run(["bash", "-lc", "ip -o link show up | awk -F': ' '$2!=\"lo\"{print $2; exit}'"])
    dev = (dev or "").strip()
    if dev:
        et = _run(["ethtool", dev])
        if et:
            return parse_ethtool(et, dev)
    return {"link_type": "other", "iface": dev or None}


def detect() -> dict[str, Any]:
    """Return the current link sample for this machine (best effort, platform aware)."""
    system = platform.system()
    if system == "Windows":
        return _detect_windows()
    if system == "Linux":
        return _detect_linux()
    return {"link_type": "other"}
