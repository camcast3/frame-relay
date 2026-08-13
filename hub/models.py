"""Pydantic request/response models — the API contract collectors and the UI code against."""
from __future__ import annotations

from typing import Any, Literal, Optional

from pydantic import BaseModel, Field, field_validator

NetworkPath = Literal["local-LAN", "remote-WireGuard", "remote-Tailscale", "remote-WAN"]
Outcome = Literal["unknown", "pass", "fail", "partial"]
Source = Literal["host", "client"]
Role = Literal["apollo", "moonlight", "artemis"]
LinkType = Literal["ethernet", "wifi", "other"]
DisplayPhase = Literal["before", "during", "after"]
SCREENSHOT_REQUEST_ERROR_MAX_LENGTH = 2000


class RequestedSettings(BaseModel):
    codec: Optional[str] = None
    resolution: Optional[str] = None
    fps: Optional[int] = None
    bitrate_mbps: Optional[int] = None
    hdr: Optional[bool] = None


class HdrDetails(BaseModel):
    requested: Optional[bool] = None
    host_display_hdr: Optional[bool] = None
    encoded_hdr: Optional[bool] = None
    color_primaries: Optional[str] = None
    transfer_function: Optional[str] = None
    bit_depth: Optional[int] = None
    client_decoder: Optional[str] = None
    client_renderer: Optional[str] = None
    client_display_hdr: Optional[bool] = None
    tone_mapping: Optional[str] = None
    status: Optional[str] = None
    evidence: Optional[list[str]] = None
    confidence: Optional[float] = Field(default=None, ge=0, le=1)


class VisualAssessment(BaseModel):
    rating: Optional[int] = Field(default=None, ge=1, le=5)
    brightness: Optional[str] = None
    black_levels: Optional[str] = None
    colors: Optional[str] = None
    notes: Optional[str] = None
    artifact_ids: list[int] = Field(default_factory=list)


class SessionCreate(BaseModel):
    name: Optional[str] = None
    host: Optional[str] = None
    client: Optional[str] = None
    comparison_label: Optional[str] = None
    apollo_app: Optional[str] = None
    game_title: Optional[str] = None
    client_role: Optional[str] = None
    client_platform: Optional[str] = None
    client_version: Optional[str] = None
    network_path: Optional[NetworkPath] = None
    codec: Optional[str] = None
    resolution: Optional[str] = None
    fps: Optional[int] = None
    bitrate_mbps: Optional[int] = None
    hdr: bool = False
    encoder_settings: dict[str, Any] = Field(default_factory=dict)
    requested_settings: RequestedSettings = Field(default_factory=RequestedSettings)
    hdr_details: HdrDetails = Field(default_factory=HdrDetails)
    visual_assessment: VisualAssessment = Field(default_factory=VisualAssessment)
    notes: str = ""


class SessionUpdate(BaseModel):
    name: Optional[str] = None
    host: Optional[str] = None
    client: Optional[str] = None
    comparison_label: Optional[str] = None
    apollo_app: Optional[str] = None
    game_title: Optional[str] = None
    client_role: Optional[str] = None
    client_platform: Optional[str] = None
    client_version: Optional[str] = None
    network_path: Optional[NetworkPath] = None
    codec: Optional[str] = None
    resolution: Optional[str] = None
    fps: Optional[int] = None
    bitrate_mbps: Optional[int] = None
    hdr: Optional[bool] = None
    encoder_settings: Optional[dict[str, Any]] = None
    requested_settings: Optional[RequestedSettings] = None
    hdr_details: Optional[HdrDetails] = None
    visual_assessment: Optional[VisualAssessment] = None
    outcome: Optional[Outcome] = None
    notes: Optional[str] = None


class SessionObservationPatch(BaseModel):
    comparison_label: Optional[str] = None
    apollo_app: Optional[str] = None
    game_title: Optional[str] = None
    client_role: Optional[str] = None
    client_platform: Optional[str] = None
    client_version: Optional[str] = None
    requested_settings: Optional[RequestedSettings] = None
    hdr_details: Optional[HdrDetails] = None


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


class DisplaySampleIn(BaseModel):
    source: Literal["host"] = "host"
    machine: Optional[str] = None
    phase: DisplayPhase
    adapter_id: Optional[str] = None
    adapter_device_path: Optional[str] = None
    source_id: Optional[int] = None
    target_id: Optional[int] = None
    source_name: Optional[str] = None
    friendly_name: Optional[str] = None
    device_path: Optional[str] = None
    is_virtual: Optional[bool] = None
    primary: Optional[bool] = None
    width: Optional[int] = None
    height: Optional[int] = None
    refresh_hz: Optional[float] = None
    rotation: Optional[str] = None
    scaling: Optional[str] = None
    output_technology: Optional[str] = None
    hdr_supported: Optional[bool] = None
    hdr_enabled: Optional[bool] = None
    bits_per_channel: Optional[int] = None
    color_encoding: Optional[str] = None
    sampled_at: Optional[str] = None


class DisplaySampleBatch(BaseModel):
    samples: list[DisplaySampleIn]


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


class ScreenshotRequestIn(BaseModel):
    targets: list[Source] = Field(default_factory=lambda: ["host", "client"])

    @field_validator("targets")
    @classmethod
    def normalize_targets(cls, value: list[Source]) -> list[Source]:
        targets: list[Source] = []
        for target in value:
            if target not in targets:
                targets.append(target)
        if not targets:
            raise ValueError("targets must not be empty")
        return targets


class ScreenshotRequestFailIn(BaseModel):
    source: Source
    error: str = Field(min_length=1)
    machine: Optional[str] = None

    @field_validator("error")
    @classmethod
    def normalize_error(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("error must not be empty")
        return normalized[:SCREENSHOT_REQUEST_ERROR_MAX_LENGTH]
