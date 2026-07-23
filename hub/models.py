"""Pydantic request/response models — the API contract collectors and the UI code against."""
from __future__ import annotations

from typing import Any, Literal, Optional

from pydantic import BaseModel, Field

NetworkPath = Literal["local-LAN", "remote-Tailscale", "remote-WAN"]
Outcome = Literal["unknown", "pass", "fail", "partial"]
Source = Literal["host", "client"]
Role = Literal["apollo", "moonlight", "artemis"]
LinkType = Literal["ethernet", "wifi", "other"]


class SessionCreate(BaseModel):
    name: Optional[str] = None
    host: Optional[str] = None
    client: Optional[str] = None
    network_path: Optional[NetworkPath] = None
    codec: Optional[str] = None
    resolution: Optional[str] = None
    fps: Optional[int] = None
    bitrate_mbps: Optional[int] = None
    hdr: bool = False
    encoder_settings: dict[str, Any] = Field(default_factory=dict)
    notes: str = ""


class SessionUpdate(BaseModel):
    name: Optional[str] = None
    host: Optional[str] = None
    client: Optional[str] = None
    network_path: Optional[NetworkPath] = None
    codec: Optional[str] = None
    resolution: Optional[str] = None
    fps: Optional[int] = None
    bitrate_mbps: Optional[int] = None
    hdr: Optional[bool] = None
    encoder_settings: Optional[dict[str, Any]] = None
    outcome: Optional[Outcome] = None
    notes: Optional[str] = None


class LogChunkIn(BaseModel):
    source: Source
    role: Role
    machine: Optional[str] = None
    content: str = ""
    meta: dict[str, Any] = Field(default_factory=dict)


class LinkSampleIn(BaseModel):
    source: Source = "client"
    machine: Optional[str] = None
    link_type: Optional[LinkType] = None
    iface: Optional[str] = None
    ssid: Optional[str] = None
    bssid: Optional[str] = None
    band: Optional[str] = None
    channel: Optional[str] = None
    rssi: Optional[int] = None
    signal_pct: Optional[int] = None
    phy_mode: Optional[str] = None
    link_speed: Optional[str] = None
    sampled_at: Optional[str] = None


class LinkSampleBatch(BaseModel):
    samples: list[LinkSampleIn]


class NetTestIn(BaseModel):
    tool: str = "iperf3"
    direction: Optional[str] = None
    bitrate_target: Optional[str] = None
    throughput_mbps: Optional[float] = None
    jitter_ms: Optional[float] = None
    loss_pct: Optional[float] = None
    raw: Optional[str] = None


class ChatIn(BaseModel):
    message: str
