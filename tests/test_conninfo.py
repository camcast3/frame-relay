"""Unit tests for client-IP / network-path inference from live connections."""
from asl_collector import conninfo

WIN_NETSTAT = """
Active Connections

  Proto  Local Address          Foreign Address        State
  TCP    192.168.50.10:48010    192.168.50.20:52344    ESTABLISHED
  TCP    192.168.50.10:47989    192.168.50.20:52350    ESTABLISHED
  TCP    0.0.0.0:48010          0.0.0.0:0              LISTENING
  TCP    192.168.50.10:139      0.0.0.0:0              LISTENING
"""

SS_ESTAB = """ESTAB 0 0 192.168.50.10:48010 100.100.20.5:41000
ESTAB 0 0 192.168.50.10:47989 100.100.20.5:41002
"""


def test_apollo_ports():
    assert conninfo.apollo_ports(47989) == [47984, 47989, 48010]


def test_classify_network_path():
    assert conninfo.classify_network_path("192.168.50.20") == "local-LAN"
    assert conninfo.classify_network_path("10.1.2.3") == "local-LAN"
    assert conninfo.classify_network_path("100.100.20.5") == "remote-Tailscale"
    assert conninfo.classify_network_path("8.8.8.8") == "remote-WAN"
    assert conninfo.classify_network_path("127.0.0.1") is None
    assert conninfo.classify_network_path("169.254.1.2") is None
    assert conninfo.classify_network_path("not-an-ip") is None


def test_classify_wireguard_subnet():
    # A client in the configured WG subnet is remote-WireGuard, not local-LAN.
    assert conninfo.classify_network_path("10.44.0.7", ["10.44.0.0/24"]) == "remote-WireGuard"
    # A LAN client not in the WG subnet still classifies as local-LAN.
    assert conninfo.classify_network_path("192.168.50.20", ["10.44.0.0/24"]) == "local-LAN"
    # An invalid subnet is ignored, not fatal.
    assert conninfo.classify_network_path("10.44.0.7", ["bogus"]) == "local-LAN"


def test_parse_conns_windows_lan():
    ports = conninfo.apollo_ports(47989)
    clients = conninfo.parse_conns(WIN_NETSTAT, ports)
    assert clients == ["192.168.50.20", "192.168.50.20"]   # LISTENING line excluded
    assert conninfo.classify_network_path(clients[0]) == "local-LAN"


def test_parse_conns_ss_tailscale():
    ports = conninfo.apollo_ports(47989)
    clients = conninfo.parse_conns(SS_ESTAB, ports)
    assert set(clients) == {"100.100.20.5"}
    assert conninfo.classify_network_path(clients[0]) == "remote-Tailscale"


def test_parse_conns_no_apollo_ports():
    assert conninfo.parse_conns("TCP 1.2.3.4:80 5.6.7.8:1234 ESTABLISHED", [47989]) == []


def test_default_wg_subnets_require_explicit_configuration():
    from asl_collector.session import DEFAULT_WG_SUBNETS
    assert DEFAULT_WG_SUBNETS == []
    assert conninfo.classify_network_path("10.44.0.7", DEFAULT_WG_SUBNETS) == "local-LAN"
