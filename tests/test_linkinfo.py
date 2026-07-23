"""Unit tests for the link/AP detection parsers (against captured sample output)."""
from asl_collector import linkinfo
from conftest import SAMPLES


def test_parse_netsh_wlan():
    d = linkinfo.parse_netsh_wlan((SAMPLES / "netsh-wlan.txt").read_text())
    assert d["link_type"] == "wifi"
    assert d["ssid"] == "NegativeZone"
    assert d["bssid"] == "aa:bb:cc:11:22:33"
    assert d["phy_mode"] == "802.11ax"
    assert d["band"] == "5 GHz"
    assert d["channel"] == "149"
    assert d["signal_pct"] == 90
    assert d["rssi"] == -55          # 90/2 - 100
    assert d["link_speed"] == "1201 Mbps"


def test_parse_iw_link():
    d = linkinfo.parse_iw_link((SAMPLES / "iw-link.txt").read_text())
    assert d["bssid"] == "aa:bb:cc:11:22:44"
    assert d["iface"] == "wlan0"
    assert d["ssid"] == "NegativeZone"
    assert d["band"] == "5GHz"
    assert d["channel"] == "149"     # (5745-5000)//5
    assert d["rssi"] == -58
    assert d["link_speed"] == "1201.0 MBit/s"


def test_parse_nmcli_wifi_unescapes_bssid():
    d = linkinfo.parse_nmcli_wifi((SAMPLES / "nmcli-wifi.txt").read_text())
    assert d["ssid"] == "NegativeZone"
    assert d["bssid"] == "aa:bb:cc:11:22:44"   # \: unescaped
    assert d["channel"] == "149"
    assert d["band"] == "5GHz"
    assert d["signal_pct"] == 82


def test_parse_ethtool():
    d = linkinfo.parse_ethtool((SAMPLES / "ethtool.txt").read_text(), "eth0")
    assert d["link_type"] == "ethernet"
    assert d["link_speed"] == "2500Mb/s"
    assert d["iface"] == "eth0"


def test_parse_ethtool_link_down_returns_empty():
    assert linkinfo.parse_ethtool("Settings for eth0:\n\tLink detected: no\n", "eth0") == {}


def test_parse_get_netadapter():
    assert linkinfo.parse_get_netadapter("2.5 Gbps")["link_speed"] == "2.5 Gbps"


def test_freq_to_band_channel():
    assert linkinfo.freq_to_band_channel(5745) == ("5GHz", 149)
    assert linkinfo.freq_to_band_channel(2412) == ("2.4GHz", 1)
    assert linkinfo.freq_to_band_channel(6115)[0] == "6GHz"


def test_pct_to_dbm():
    assert linkinfo.pct_to_dbm(90) == -55
    assert linkinfo.pct_to_dbm(None) is None
