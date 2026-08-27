"""Probe active Windows display topology with the documented User32 DisplayConfig APIs."""
from __future__ import annotations

import ctypes
import platform
import re
from ctypes import wintypes
from datetime import datetime, timezone
from typing import Any, Optional


UINT32 = ctypes.c_uint32
INT32 = ctypes.c_int32
UINT64 = ctypes.c_uint64

ERROR_SUCCESS = 0
ERROR_NOT_SUPPORTED = 50
ERROR_INVALID_PARAMETER = 87
ERROR_INSUFFICIENT_BUFFER = 122

QDC_ONLY_ACTIVE_PATHS = 0x00000002
QDC_VIRTUAL_MODE_AWARE = 0x00000010
QDC_VIRTUAL_REFRESH_RATE_AWARE = 0x00000040
DEFAULT_QUERY_FLAGS = (
    QDC_ONLY_ACTIVE_PATHS | QDC_VIRTUAL_MODE_AWARE | QDC_VIRTUAL_REFRESH_RATE_AWARE
)

DISPLAYCONFIG_MODE_INFO_TYPE_SOURCE = 1
DISPLAYCONFIG_MODE_INFO_TYPE_TARGET = 2

DISPLAYCONFIG_DEVICE_INFO_GET_SOURCE_NAME = 1
DISPLAYCONFIG_DEVICE_INFO_GET_TARGET_NAME = 2
DISPLAYCONFIG_DEVICE_INFO_GET_ADAPTER_NAME = 4
DISPLAYCONFIG_DEVICE_INFO_GET_ADVANCED_COLOR_INFO = 9

DISPLAYCONFIG_PATH_MODE_IDX_INVALID = 0xFFFFFFFF
DISPLAYCONFIG_PATH_TARGET_MODE_IDX_INVALID = 0xFFFF
DISPLAYCONFIG_PATH_SOURCE_MODE_IDX_INVALID = 0xFFFF
DISPLAYCONFIG_PATH_SUPPORT_VIRTUAL_MODE = 0x00000008

DISPLAYCONFIG_VIDEO_OUTPUT_TECHNOLOGY_NAMES = {
    0xFFFFFFFF: "other",
    0: "hd15",
    1: "svideo",
    2: "composite-video",
    3: "component-video",
    4: "dvi",
    5: "hdmi",
    6: "lvds",
    8: "d-jpn",
    9: "sdi",
    10: "displayport-external",
    11: "displayport-embedded",
    12: "udi-external",
    13: "udi-embedded",
    14: "sdtv-dongle",
    15: "miracast",
    16: "indirect-wired",
    17: "indirect-virtual",
    0x80000000: "internal",
}

DISPLAYCONFIG_ROTATION_NAMES = {
    1: "identity",
    2: "rotate90",
    3: "rotate180",
    4: "rotate270",
}

DISPLAYCONFIG_SCALING_NAMES = {
    1: "identity",
    2: "centered",
    3: "stretched",
    4: "aspect-ratio-centered-max",
    5: "custom",
    128: "preferred",
}

DISPLAYCONFIG_COLOR_ENCODING_NAMES = {
    0: "rgb",
    1: "ycbcr444",
    2: "ycbcr422",
    3: "ycbcr420",
    4: "intensity",
}

_VIRTUAL_HINTS = tuple(
    re.compile(pattern, re.IGNORECASE)
    for pattern in (
        r"\bapollo\b",
        r"\bsunshine\b",
        r"\bvirtual[\s_-]*display\b",
        r"\bindirect[\s_-]*display\b",
        r"\bidd\b",
    )
)

_PHYSICAL_HINTS = tuple(
    re.compile(pattern, re.IGNORECASE)
    for pattern in (
        r"\bbuilt[\s_-]*in\s+display\b",
        r"\binternal\s+display\b",
        r"\bintegrated\s+monitor\b",
        r"\blaptop\s+display\b",
    )
)


class DisplayProbeError(RuntimeError):
    pass


class LUID(ctypes.Structure):
    _fields_ = [("LowPart", wintypes.DWORD), ("HighPart", wintypes.LONG)]


class POINTL(ctypes.Structure):
    _fields_ = [("x", wintypes.LONG), ("y", wintypes.LONG)]


class RECTL(ctypes.Structure):
    _fields_ = [
        ("left", wintypes.LONG),
        ("top", wintypes.LONG),
        ("right", wintypes.LONG),
        ("bottom", wintypes.LONG),
    ]


class DISPLAYCONFIG_RATIONAL(ctypes.Structure):
    _fields_ = [("Numerator", UINT32), ("Denominator", UINT32)]


class DISPLAYCONFIG_2DREGION(ctypes.Structure):
    _fields_ = [("cx", UINT32), ("cy", UINT32)]


class _DISPLAYCONFIG_VIDEO_SIGNAL_INFO_FIELDS(ctypes.Structure):
    _fields_ = [
        ("videoStandard", UINT32, 16),
        ("vSyncFreqDivider", UINT32, 6),
        ("reserved", UINT32, 10),
    ]


class _DISPLAYCONFIG_VIDEO_SIGNAL_INFO_UNION(ctypes.Union):
    _fields_ = [
        ("AdditionalSignalInfo", _DISPLAYCONFIG_VIDEO_SIGNAL_INFO_FIELDS),
        ("videoStandard", UINT32),
    ]


class DISPLAYCONFIG_VIDEO_SIGNAL_INFO(ctypes.Structure):
    _anonymous_ = ("u",)
    _fields_ = [
        ("pixelRate", UINT64),
        ("hSyncFreq", DISPLAYCONFIG_RATIONAL),
        ("vSyncFreq", DISPLAYCONFIG_RATIONAL),
        ("activeSize", DISPLAYCONFIG_2DREGION),
        ("totalSize", DISPLAYCONFIG_2DREGION),
        ("u", _DISPLAYCONFIG_VIDEO_SIGNAL_INFO_UNION),
        ("scanLineOrdering", UINT32),
    ]


class DISPLAYCONFIG_SOURCE_MODE(ctypes.Structure):
    _fields_ = [
        ("width", UINT32),
        ("height", UINT32),
        ("pixelFormat", UINT32),
        ("position", POINTL),
    ]


class DISPLAYCONFIG_TARGET_MODE(ctypes.Structure):
    _fields_ = [("targetVideoSignalInfo", DISPLAYCONFIG_VIDEO_SIGNAL_INFO)]


class DISPLAYCONFIG_DESKTOP_IMAGE_INFO(ctypes.Structure):
    _fields_ = [
        ("PathSourceSize", POINTL),
        ("DesktopImageRegion", RECTL),
        ("DesktopImageClip", RECTL),
    ]


class _DISPLAYCONFIG_MODE_INFO_UNION(ctypes.Union):
    _fields_ = [
        ("targetMode", DISPLAYCONFIG_TARGET_MODE),
        ("sourceMode", DISPLAYCONFIG_SOURCE_MODE),
        ("desktopImageInfo", DISPLAYCONFIG_DESKTOP_IMAGE_INFO),
    ]


class DISPLAYCONFIG_MODE_INFO(ctypes.Structure):
    _anonymous_ = ("u",)
    _fields_ = [
        ("infoType", UINT32),
        ("id", UINT32),
        ("adapterId", LUID),
        ("u", _DISPLAYCONFIG_MODE_INFO_UNION),
    ]


class _DISPLAYCONFIG_PATH_SOURCE_VIRTUAL_MODE(ctypes.Structure):
    _fields_ = [("cloneGroupId", UINT32, 16), ("sourceModeInfoIdx", UINT32, 16)]


class _DISPLAYCONFIG_PATH_SOURCE_UNION(ctypes.Union):
    _fields_ = [
        ("modeInfoIdx", UINT32),
        ("virtualModeInfo", _DISPLAYCONFIG_PATH_SOURCE_VIRTUAL_MODE),
    ]


class DISPLAYCONFIG_PATH_SOURCE_INFO(ctypes.Structure):
    _anonymous_ = ("u",)
    _fields_ = [
        ("adapterId", LUID),
        ("id", UINT32),
        ("u", _DISPLAYCONFIG_PATH_SOURCE_UNION),
        ("statusFlags", UINT32),
    ]


class _DISPLAYCONFIG_PATH_TARGET_VIRTUAL_MODE(ctypes.Structure):
    _fields_ = [("desktopModeInfoIdx", UINT32, 16), ("targetModeInfoIdx", UINT32, 16)]


class _DISPLAYCONFIG_PATH_TARGET_UNION(ctypes.Union):
    _fields_ = [
        ("modeInfoIdx", UINT32),
        ("virtualModeInfo", _DISPLAYCONFIG_PATH_TARGET_VIRTUAL_MODE),
    ]


class DISPLAYCONFIG_PATH_TARGET_INFO(ctypes.Structure):
    _anonymous_ = ("u",)
    _fields_ = [
        ("adapterId", LUID),
        ("id", UINT32),
        ("u", _DISPLAYCONFIG_PATH_TARGET_UNION),
        ("outputTechnology", INT32),
        ("rotation", UINT32),
        ("scaling", UINT32),
        ("refreshRate", DISPLAYCONFIG_RATIONAL),
        ("scanLineOrdering", UINT32),
        ("targetAvailable", wintypes.BOOL),
        ("statusFlags", UINT32),
    ]


class DISPLAYCONFIG_PATH_INFO(ctypes.Structure):
    _fields_ = [
        ("sourceInfo", DISPLAYCONFIG_PATH_SOURCE_INFO),
        ("targetInfo", DISPLAYCONFIG_PATH_TARGET_INFO),
        ("flags", UINT32),
    ]


class DISPLAYCONFIG_DEVICE_INFO_HEADER(ctypes.Structure):
    _fields_ = [
        ("type", UINT32),
        ("size", UINT32),
        ("adapterId", LUID),
        ("id", UINT32),
    ]


class DISPLAYCONFIG_SOURCE_DEVICE_NAME(ctypes.Structure):
    _fields_ = [
        ("header", DISPLAYCONFIG_DEVICE_INFO_HEADER),
        ("viewGdiDeviceName", wintypes.WCHAR * 32),
    ]


class DISPLAYCONFIG_TARGET_DEVICE_NAME_FLAGS(ctypes.Structure):
    _fields_ = [("value", UINT32)]


class DISPLAYCONFIG_TARGET_DEVICE_NAME(ctypes.Structure):
    _fields_ = [
        ("header", DISPLAYCONFIG_DEVICE_INFO_HEADER),
        ("flags", DISPLAYCONFIG_TARGET_DEVICE_NAME_FLAGS),
        ("outputTechnology", INT32),
        ("edidManufactureId", wintypes.WORD),
        ("edidProductCodeId", wintypes.WORD),
        ("connectorInstance", UINT32),
        ("monitorFriendlyDeviceName", wintypes.WCHAR * 64),
        ("monitorDevicePath", wintypes.WCHAR * 128),
    ]


class DISPLAYCONFIG_ADAPTER_NAME(ctypes.Structure):
    _fields_ = [
        ("header", DISPLAYCONFIG_DEVICE_INFO_HEADER),
        ("adapterDevicePath", wintypes.WCHAR * 128),
    ]


class DISPLAYCONFIG_GET_ADVANCED_COLOR_INFO(ctypes.Structure):
    _fields_ = [
        ("header", DISPLAYCONFIG_DEVICE_INFO_HEADER),
        ("value", UINT32),
        ("colorEncoding", UINT32),
        ("bitsPerColorChannel", UINT32),
    ]


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _enum_key(value: int) -> int:
    return int(value) & 0xFFFFFFFF


def _enum_name(mapping: dict[int, str], value: int) -> str:
    key = _enum_key(value)
    return mapping.get(key, f"unknown({key})")


def _clean_string(value: Any) -> Optional[str]:
    text = str(value or "").split("\x00", 1)[0].strip()
    return text or None


def _luid_equal(left: LUID, right: LUID) -> bool:
    return left.LowPart == right.LowPart and left.HighPart == right.HighPart


def format_luid(luid: LUID) -> str:
    return f"{luid.HighPart & 0xFFFFFFFF:08x}:{luid.LowPart:08x}"


def rational_to_hz(rational: DISPLAYCONFIG_RATIONAL) -> Optional[float | int]:
    if not rational.Denominator:
        return None
    hz = round(rational.Numerator / rational.Denominator, 3)
    return int(hz) if float(hz).is_integer() else hz


def rotation_name(value: int) -> str:
    return _enum_name(DISPLAYCONFIG_ROTATION_NAMES, value)


def scaling_name(value: int) -> str:
    return _enum_name(DISPLAYCONFIG_SCALING_NAMES, value)


def output_technology_name(value: int) -> str:
    return _enum_name(DISPLAYCONFIG_VIDEO_OUTPUT_TECHNOLOGY_NAMES, value)


def color_encoding_name(value: int) -> str:
    return _enum_name(DISPLAYCONFIG_COLOR_ENCODING_NAMES, value)


def classify_virtual_display(
    friendly_name: Optional[str],
    source_name: Optional[str],
    device_path: Optional[str],
    adapter_device_path: Optional[str],
    output_technology: Optional[str] = None,
) -> Optional[bool]:
    if output_technology in {"indirect-virtual", "indirect-wired"}:
        return True
    haystack = "\n".join(
        text for text in (friendly_name, source_name, device_path, adapter_device_path) if text
    )
    if any(pattern.search(haystack) for pattern in _VIRTUAL_HINTS):
        return True
    if any(pattern.search(haystack) for pattern in _PHYSICAL_HINTS):
        return False
    return None


def _load_user32():
    user32 = ctypes.WinDLL("user32", use_last_error=True)
    user32.GetDisplayConfigBufferSizes.argtypes = [
        UINT32,
        ctypes.POINTER(UINT32),
        ctypes.POINTER(UINT32),
    ]
    user32.GetDisplayConfigBufferSizes.restype = wintypes.LONG
    user32.QueryDisplayConfig.argtypes = [
        UINT32,
        ctypes.POINTER(UINT32),
        ctypes.POINTER(DISPLAYCONFIG_PATH_INFO),
        ctypes.POINTER(UINT32),
        ctypes.POINTER(DISPLAYCONFIG_MODE_INFO),
        ctypes.POINTER(UINT32),
    ]
    user32.QueryDisplayConfig.restype = wintypes.LONG
    user32.DisplayConfigGetDeviceInfo.argtypes = [
        ctypes.POINTER(DISPLAYCONFIG_DEVICE_INFO_HEADER)
    ]
    user32.DisplayConfigGetDeviceInfo.restype = wintypes.LONG
    return user32


def _query_active_paths(
    user32,
    flags: int = DEFAULT_QUERY_FLAGS,
    max_attempts: int = 5,
) -> tuple[list[DISPLAYCONFIG_PATH_INFO], list[DISPLAYCONFIG_MODE_INFO], int]:
    active_flags = flags
    fallback_errors = {ERROR_INVALID_PARAMETER, ERROR_NOT_SUPPORTED}
    while True:
        fallback_without_refresh = False
        for _ in range(max_attempts):
            path_count = UINT32()
            mode_count = UINT32()
            rc = user32.GetDisplayConfigBufferSizes(
                active_flags, ctypes.pointer(path_count), ctypes.pointer(mode_count)
            )
            if rc == ERROR_INSUFFICIENT_BUFFER:
                continue
            if rc in fallback_errors and active_flags & QDC_VIRTUAL_REFRESH_RATE_AWARE:
                active_flags &= ~QDC_VIRTUAL_REFRESH_RATE_AWARE
                fallback_without_refresh = True
                break
            if rc != ERROR_SUCCESS:
                raise DisplayProbeError(f"GetDisplayConfigBufferSizes failed: {rc}")

            path_array = (DISPLAYCONFIG_PATH_INFO * max(1, path_count.value))()
            mode_array = (DISPLAYCONFIG_MODE_INFO * max(1, mode_count.value))()
            query_path_count = UINT32(path_count.value)
            query_mode_count = UINT32(mode_count.value)
            rc = user32.QueryDisplayConfig(
                active_flags,
                ctypes.pointer(query_path_count),
                path_array,
                ctypes.pointer(query_mode_count),
                mode_array,
                None,
            )
            if rc == ERROR_INSUFFICIENT_BUFFER:
                continue
            if rc in fallback_errors and active_flags & QDC_VIRTUAL_REFRESH_RATE_AWARE:
                active_flags &= ~QDC_VIRTUAL_REFRESH_RATE_AWARE
                fallback_without_refresh = True
                break
            if rc != ERROR_SUCCESS:
                raise DisplayProbeError(f"QueryDisplayConfig failed: {rc}")
            return (
                list(path_array)[:query_path_count.value],
                list(mode_array)[:query_mode_count.value],
                active_flags,
            )
        if fallback_without_refresh:
            continue
        raise DisplayProbeError("QueryDisplayConfig did not stabilize after repeated retries")


def _init_device_request(packet: Any, info_type: int, adapter_id: LUID, item_id: int) -> None:
    packet.header.type = info_type
    packet.header.size = ctypes.sizeof(packet)
    packet.header.adapterId = adapter_id
    packet.header.id = item_id


def _mode_from_index(
    modes: list[DISPLAYCONFIG_MODE_INFO], idx: int, expected_type: int
) -> Optional[DISPLAYCONFIG_MODE_INFO]:
    if idx < 0 or idx >= len(modes):
        return None
    mode = modes[idx]
    if mode.infoType != expected_type:
        return None
    return mode


def _find_mode(
    modes: list[DISPLAYCONFIG_MODE_INFO], adapter_id: LUID, item_id: int, expected_type: int
) -> Optional[DISPLAYCONFIG_MODE_INFO]:
    for mode in modes:
        if mode.infoType != expected_type:
            continue
        if mode.id != item_id:
            continue
        if _luid_equal(mode.adapterId, adapter_id):
            return mode
    return None


def _source_mode_for_path(
    path: DISPLAYCONFIG_PATH_INFO, modes: list[DISPLAYCONFIG_MODE_INFO]
) -> Optional[DISPLAYCONFIG_MODE_INFO]:
    if path.flags & DISPLAYCONFIG_PATH_SUPPORT_VIRTUAL_MODE:
        idx = path.sourceInfo.virtualModeInfo.sourceModeInfoIdx
        if idx != DISPLAYCONFIG_PATH_SOURCE_MODE_IDX_INVALID:
            mode = _mode_from_index(modes, idx, DISPLAYCONFIG_MODE_INFO_TYPE_SOURCE)
            if mode is not None:
                return mode
    elif path.sourceInfo.modeInfoIdx != DISPLAYCONFIG_PATH_MODE_IDX_INVALID:
        mode = _mode_from_index(
            modes, path.sourceInfo.modeInfoIdx, DISPLAYCONFIG_MODE_INFO_TYPE_SOURCE
        )
        if mode is not None:
            return mode
    return _find_mode(
        modes,
        path.sourceInfo.adapterId,
        path.sourceInfo.id,
        DISPLAYCONFIG_MODE_INFO_TYPE_SOURCE,
    )


def _target_mode_for_path(
    path: DISPLAYCONFIG_PATH_INFO, modes: list[DISPLAYCONFIG_MODE_INFO]
) -> Optional[DISPLAYCONFIG_MODE_INFO]:
    if path.flags & DISPLAYCONFIG_PATH_SUPPORT_VIRTUAL_MODE:
        idx = path.targetInfo.virtualModeInfo.targetModeInfoIdx
        if idx != DISPLAYCONFIG_PATH_TARGET_MODE_IDX_INVALID:
            mode = _mode_from_index(modes, idx, DISPLAYCONFIG_MODE_INFO_TYPE_TARGET)
            if mode is not None:
                return mode
    elif path.targetInfo.modeInfoIdx != DISPLAYCONFIG_PATH_MODE_IDX_INVALID:
        mode = _mode_from_index(
            modes, path.targetInfo.modeInfoIdx, DISPLAYCONFIG_MODE_INFO_TYPE_TARGET
        )
        if mode is not None:
            return mode
    return _find_mode(
        modes,
        path.targetInfo.adapterId,
        path.targetInfo.id,
        DISPLAYCONFIG_MODE_INFO_TYPE_TARGET,
    )


def _advanced_color_defaults() -> dict[str, Any]:
    return {
        "hdr_supported": None,
        "hdr_enabled": None,
        "bits_per_channel": None,
        "color_encoding": None,
    }


class _DisplayConfigApi:
    def __init__(self, user32=None):
        self._user32 = user32 or _load_user32()

    def query_active_paths(
        self,
    ) -> tuple[list[DISPLAYCONFIG_PATH_INFO], list[DISPLAYCONFIG_MODE_INFO], int]:
        return _query_active_paths(self._user32)

    def get_source_name(self, adapter_id: LUID, source_id: int) -> Optional[str]:
        request = DISPLAYCONFIG_SOURCE_DEVICE_NAME()
        _init_device_request(request, DISPLAYCONFIG_DEVICE_INFO_GET_SOURCE_NAME, adapter_id, source_id)
        rc = self._user32.DisplayConfigGetDeviceInfo(ctypes.byref(request.header))
        if rc != ERROR_SUCCESS:
            return None
        return _clean_string(request.viewGdiDeviceName)

    def get_target_name(self, adapter_id: LUID, target_id: int) -> tuple[Optional[str], Optional[str]]:
        request = DISPLAYCONFIG_TARGET_DEVICE_NAME()
        _init_device_request(request, DISPLAYCONFIG_DEVICE_INFO_GET_TARGET_NAME, adapter_id, target_id)
        rc = self._user32.DisplayConfigGetDeviceInfo(ctypes.byref(request.header))
        if rc != ERROR_SUCCESS:
            return None, None
        return (
            _clean_string(request.monitorFriendlyDeviceName),
            _clean_string(request.monitorDevicePath),
        )

    def get_adapter_name(self, adapter_id: LUID) -> Optional[str]:
        request = DISPLAYCONFIG_ADAPTER_NAME()
        _init_device_request(request, DISPLAYCONFIG_DEVICE_INFO_GET_ADAPTER_NAME, adapter_id, 0)
        rc = self._user32.DisplayConfigGetDeviceInfo(ctypes.byref(request.header))
        if rc != ERROR_SUCCESS:
            return None
        return _clean_string(request.adapterDevicePath)

    def get_advanced_color_info(self, adapter_id: LUID, target_id: int) -> dict[str, Any]:
        request = DISPLAYCONFIG_GET_ADVANCED_COLOR_INFO()
        _init_device_request(
            request,
            DISPLAYCONFIG_DEVICE_INFO_GET_ADVANCED_COLOR_INFO,
            adapter_id,
            target_id,
        )
        rc = self._user32.DisplayConfigGetDeviceInfo(ctypes.byref(request.header))
        if rc != ERROR_SUCCESS:
            return _advanced_color_defaults()
        return {
            "hdr_supported": bool(request.value & 0x1),
            "hdr_enabled": bool(request.value & 0x2),
            "bits_per_channel": int(request.bitsPerColorChannel),
            "color_encoding": color_encoding_name(request.colorEncoding),
        }


def _build_sample(
    path: DISPLAYCONFIG_PATH_INFO,
    modes: list[DISPLAYCONFIG_MODE_INFO],
    api: Any,
    sampled_at: str,
) -> dict[str, Any]:
    source_mode = _source_mode_for_path(path, modes)
    target_mode = _target_mode_for_path(path, modes)
    source_name = None
    friendly_name = None
    device_path = None
    adapter_device_path = None
    advanced_color = _advanced_color_defaults()
    try:
        source_name = api.get_source_name(path.sourceInfo.adapterId, path.sourceInfo.id)
    except Exception:  # noqa: BLE001
        source_name = None
    try:
        friendly_name, device_path = api.get_target_name(path.targetInfo.adapterId, path.targetInfo.id)
    except Exception:  # noqa: BLE001
        friendly_name, device_path = None, None
    try:
        adapter_device_path = api.get_adapter_name(path.sourceInfo.adapterId)
    except Exception:  # noqa: BLE001
        adapter_device_path = None
    try:
        advanced_color = api.get_advanced_color_info(path.targetInfo.adapterId, path.targetInfo.id)
    except Exception:  # noqa: BLE001
        advanced_color = _advanced_color_defaults()

    width = None
    height = None
    primary = False
    if source_mode is not None:
        width = int(source_mode.sourceMode.width)
        height = int(source_mode.sourceMode.height)
        primary = source_mode.sourceMode.position.x == 0 and source_mode.sourceMode.position.y == 0
    elif target_mode is not None:
        width = int(target_mode.targetMode.targetVideoSignalInfo.activeSize.cx)
        height = int(target_mode.targetMode.targetVideoSignalInfo.activeSize.cy)

    refresh_hz = rational_to_hz(path.targetInfo.refreshRate)
    if refresh_hz is None and target_mode is not None:
        refresh_hz = rational_to_hz(target_mode.targetMode.targetVideoSignalInfo.vSyncFreq)

    output_technology = output_technology_name(path.targetInfo.outputTechnology)
    return {
        "source": "host",
        "machine": None,
        "phase": None,
        "adapter_id": format_luid(path.sourceInfo.adapterId),
        "adapter_device_path": adapter_device_path,
        "source_id": int(path.sourceInfo.id),
        "target_id": int(path.targetInfo.id),
        "source_name": source_name,
        "friendly_name": friendly_name,
        "device_path": device_path,
        "is_virtual": classify_virtual_display(
            friendly_name,
            source_name,
            device_path,
            adapter_device_path,
            output_technology=output_technology,
        ),
        "primary": primary,
        "width": width,
        "height": height,
        "refresh_hz": refresh_hz,
        "rotation": rotation_name(path.targetInfo.rotation),
        "scaling": scaling_name(path.targetInfo.scaling),
        "output_technology": output_technology,
        "hdr_supported": advanced_color["hdr_supported"],
        "hdr_enabled": advanced_color["hdr_enabled"],
        "bits_per_channel": advanced_color["bits_per_channel"],
        "color_encoding": advanced_color["color_encoding"],
        "sampled_at": sampled_at,
    }


def _detect_windows(api: Optional[Any] = None) -> list[dict[str, Any]]:
    probe = api or _DisplayConfigApi()
    paths, modes, _flags_used = probe.query_active_paths()
    sampled_at = _now()
    return [_build_sample(path, modes, probe, sampled_at) for path in paths]


def detect() -> list[dict[str, Any]]:
    """Return one topology sample per active Windows display path."""
    if platform.system() != "Windows":
        return []
    try:
        return _detect_windows()
    except Exception:  # noqa: BLE001
        return []
