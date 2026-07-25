"""Infer the client IP and network path from Apollo's live connections (host-side).

Apollo doesn't log the client IP, but while a stream is active the client holds a TCP
connection to Apollo's RTSP/HTTP(S) ports. We sample the host's established connections to
those ports, take the peer IP, and classify it:

    100.64.0.0/10  -> remote-Tailscale   (Tailscale CGNAT range)
    private (RFC1918) -> local-LAN
    public         -> remote-WAN

Parsing is format-agnostic (works for both Windows ``netstat -n`` and Linux ``ss``/``netstat``):
we pull the IPv4 endpoints off each line and match the one whose port is an Apollo port.
"""
from __future__ import annotations

import ipaddress
import platform
import re
import shutil
import subprocess
import threading
from typing import Iterable, Optional

_IPV4 = re.compile(r"(\d{1,3}(?:\.\d{1,3}){3}):(\d+)")
_TAILSCALE_CGNAT = ipaddress.ip_network("100.64.0.0/10")


def apollo_ports(base: int = 47989) -> list[int]:
    """Apollo/Sunshine TCP ports derived from the base port: HTTP (base-5), HTTPS (base), RTSP (base+21)."""
    return [base - 5, base, base + 21]


def classify_network_path(ip: str, wg_subnets: Optional[Iterable[str]] = None) -> Optional[str]:
    try:
        addr = ipaddress.ip_address(ip)
    except ValueError:
        return None
    if addr.is_loopback or addr.is_link_local or addr.is_unspecified or addr.is_multicast:
        return None
    # A client whose IP falls in a WireGuard subnet is remote-over-WireGuard, not LAN.
    for net in wg_subnets or []:
        try:
            if addr in ipaddress.ip_network(net, strict=False):
                return "remote-WireGuard"
        except ValueError:
            continue
    if addr in _TAILSCALE_CGNAT:
        return "remote-Tailscale"
    if addr.is_private:
        return "local-LAN"
    return "remote-WAN"


def parse_conns(text: str, ports: Iterable[int]) -> list[str]:
    """Return peer (client) IPs for connections whose local endpoint uses an Apollo port."""
    portset = {int(p) for p in ports}
    clients: list[str] = []
    for line in text.splitlines():
        eps = _IPV4.findall(line)  # [(ip, port), ...]
        if len(eps) < 2:
            continue
        local_ep = next(((ip, p) for ip, p in eps if int(p) in portset), None)
        if not local_ep:
            continue
        peer = next((ip for ip, p in eps if (ip, p) != local_ep), None)
        if not peer or peer == "0.0.0.0":
            continue
        addr = ipaddress.ip_address(peer)
        if addr.is_loopback or addr.is_link_local or addr.is_unspecified:
            continue
        clients.append(peer)
    return clients


def _run(cmd: list[str]) -> Optional[str]:
    if not shutil.which(cmd[0]):
        return None
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=15)
        return p.stdout
    except Exception:  # noqa: BLE001
        return None


def detect_client_ip(ports: Iterable[int]) -> Optional[str]:
    """Best-effort: the peer IP currently connected to an Apollo port (None if none/idle)."""
    system = platform.system()
    text = None
    if system == "Windows":
        text = _run(["netstat", "-n", "-p", "TCP"])
    else:
        text = _run(["ss", "-tn", "state", "established"]) or _run(["netstat", "-tn"])
    if not text:
        return None
    clients = parse_conns(text, ports)
    if not clients:
        return None
    return max(set(clients), key=clients.count)


class ClientMonitor:
    """Samples the connected client IP on a timer (host-side) so a brief stream is still caught."""

    def __init__(self, ports: Iterable[int], interval: float = 15.0):
        self.ports = list(ports)
        self.interval = interval
        self.seen: list[str] = []
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None

    def _tick(self) -> None:
        ip = detect_client_ip(self.ports)
        if ip:
            self.seen.append(ip)

    def _loop(self) -> None:
        self._tick()
        while not self._stop.wait(self.interval):
            self._tick()

    def current(self) -> Optional[str]:
        """Best client IP seen so far, without stopping the monitor (for live enrichment)."""
        return max(set(self.seen), key=self.seen.count) if self.seen else None

    def start(self) -> None:
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()

    def stop(self) -> Optional[str]:
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=self.interval + 5)
        return max(set(self.seen), key=self.seen.count) if self.seen else None
