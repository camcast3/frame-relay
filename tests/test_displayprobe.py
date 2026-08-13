from __future__ import annotations

from asl_collector import displayprobe


def _luid(high: int, low: int) -> displayprobe.LUID:
    luid = displayprobe.LUID()
    luid.HighPart = high
    luid.LowPart = low
    return luid


def _path(
    adapter_id: displayprobe.LUID,
    source_id: int,
    target_id: int,
    source_mode_idx: int,
    target_mode_idx: int,
    *,
    flags: int = 0,
    output_technology: int = 5,
    rotation: int = 1,
    scaling: int = 128,
    refresh: tuple[int, int] = (0, 0),
) -> displayprobe.DISPLAYCONFIG_PATH_INFO:
    path = displayprobe.DISPLAYCONFIG_PATH_INFO()
    path.flags = flags
    path.sourceInfo.adapterId = adapter_id
    path.sourceInfo.id = source_id
    path.targetInfo.adapterId = adapter_id
    path.targetInfo.id = target_id
    if flags & displayprobe.DISPLAYCONFIG_PATH_SUPPORT_VIRTUAL_MODE:
        path.sourceInfo.virtualModeInfo.sourceModeInfoIdx = source_mode_idx
        path.targetInfo.virtualModeInfo.targetModeInfoIdx = target_mode_idx
    else:
        path.sourceInfo.modeInfoIdx = source_mode_idx
        path.targetInfo.modeInfoIdx = target_mode_idx
    path.targetInfo.outputTechnology = output_technology
    path.targetInfo.rotation = rotation
    path.targetInfo.scaling = scaling
    path.targetInfo.refreshRate.Numerator = refresh[0]
    path.targetInfo.refreshRate.Denominator = refresh[1]
    path.targetInfo.targetAvailable = 1
    return path


def _source_mode(
    adapter_id: displayprobe.LUID,
    source_id: int,
    width: int,
    height: int,
    x: int,
    y: int,
) -> displayprobe.DISPLAYCONFIG_MODE_INFO:
    mode = displayprobe.DISPLAYCONFIG_MODE_INFO()
    mode.infoType = displayprobe.DISPLAYCONFIG_MODE_INFO_TYPE_SOURCE
    mode.adapterId = adapter_id
    mode.id = source_id
    mode.sourceMode.width = width
    mode.sourceMode.height = height
    mode.sourceMode.position.x = x
    mode.sourceMode.position.y = y
    return mode


def _target_mode(
    adapter_id: displayprobe.LUID,
    target_id: int,
    width: int,
    height: int,
    refresh: tuple[int, int],
) -> displayprobe.DISPLAYCONFIG_MODE_INFO:
    mode = displayprobe.DISPLAYCONFIG_MODE_INFO()
    mode.infoType = displayprobe.DISPLAYCONFIG_MODE_INFO_TYPE_TARGET
    mode.adapterId = adapter_id
    mode.id = target_id
    mode.targetMode.targetVideoSignalInfo.activeSize.cx = width
    mode.targetMode.targetVideoSignalInfo.activeSize.cy = height
    mode.targetMode.targetVideoSignalInfo.vSyncFreq.Numerator = refresh[0]
    mode.targetMode.targetVideoSignalInfo.vSyncFreq.Denominator = refresh[1]
    return mode


def test_detect_skips_non_windows(monkeypatch):
    monkeypatch.setattr(displayprobe.platform, "system", lambda: "Linux")
    monkeypatch.setattr(
        displayprobe,
        "_detect_windows",
        lambda *_: (_ for _ in ()).throw(AssertionError("should not query Windows APIs")),
    )
    assert displayprobe.detect() == []


def test_classify_virtual_display_is_conservative():
    assert displayprobe.classify_virtual_display(
        "Sunshine Virtual Display",
        r"\\.\DISPLAY1",
        r"ROOT\SunshineVirtualDisplay\0000",
        r"\\?\DISPLAY#Sunshine#0001",
    ) is True
    assert displayprobe.classify_virtual_display(
        "Built-in Display",
        r"\\.\DISPLAY1",
        None,
        None,
    ) is False
    assert displayprobe.classify_virtual_display(
        "Dell U2720Q",
        r"\\.\DISPLAY2",
        r"\\?\DISPLAY#DEL4098#5&12345",
        r"\\?\PCI#VEN_10DE&DEV_1C82",
    ) is None
    assert displayprobe.rational_to_hz(
        displayprobe.DISPLAYCONFIG_RATIONAL(60000, 1001)
    ) == 59.94
    assert displayprobe.format_luid(_luid(-1, 0x1234)) == "ffffffff:00001234"


def test_query_active_paths_retries_refresh_flag_and_insufficient_buffer():
    adapter = _luid(0, 1)
    path = _path(adapter, 0, 0, 0, 1, output_technology=5, refresh=(144, 1))
    source = _source_mode(adapter, 0, 2560, 1440, 0, 0)
    target = _target_mode(adapter, 0, 2560, 1440, (144, 1))

    class FakeUser32:
        def __init__(self):
            self.size_calls: list[int] = []
            self.query_calls: list[int] = []
            self._refresh_rejected = False
            self._buffer_retry = False

        def GetDisplayConfigBufferSizes(self, flags, path_count_p, mode_count_p):
            self.size_calls.append(flags)
            if flags & displayprobe.QDC_VIRTUAL_REFRESH_RATE_AWARE and not self._refresh_rejected:
                self._refresh_rejected = True
                return displayprobe.ERROR_INVALID_PARAMETER
            path_count_p.contents.value = 1
            mode_count_p.contents.value = 2
            return displayprobe.ERROR_SUCCESS

        def QueryDisplayConfig(
            self, flags, path_count_p, path_array, mode_count_p, mode_array, _topology_p
        ):
            self.query_calls.append(flags)
            if not self._buffer_retry:
                self._buffer_retry = True
                return displayprobe.ERROR_INSUFFICIENT_BUFFER
            path_count_p.contents.value = 1
            mode_count_p.contents.value = 2
            path_array[0] = path
            mode_array[0] = source
            mode_array[1] = target
            return displayprobe.ERROR_SUCCESS

    fake = FakeUser32()
    paths, modes, used_flags = displayprobe._query_active_paths(fake)

    assert used_flags == (
        displayprobe.QDC_ONLY_ACTIVE_PATHS | displayprobe.QDC_VIRTUAL_MODE_AWARE
    )
    assert fake.size_calls[0] == displayprobe.DEFAULT_QUERY_FLAGS
    assert fake.query_calls == [used_flags, used_flags]
    assert len(paths) == 1
    assert len(modes) == 2
    assert displayprobe.output_technology_name(paths[0].targetInfo.outputTechnology) == "hdmi"


def test_detect_windows_formats_expected_samples():
    adapter_virtual = _luid(0, 1)
    adapter_physical = _luid(0, 2)
    paths = [
        _path(
            adapter_virtual,
            0,
            10,
            0,
            1,
            flags=displayprobe.DISPLAYCONFIG_PATH_SUPPORT_VIRTUAL_MODE,
            output_technology=17,
            refresh=(144, 1),
        ),
        _path(
            adapter_physical,
            1,
            11,
            2,
            3,
            output_technology=5,
            refresh=(0, 0),
        ),
    ]
    modes = [
        _source_mode(adapter_virtual, 0, 3840, 2160, 0, 0),
        _target_mode(adapter_virtual, 10, 3840, 2160, (144, 1)),
        _source_mode(adapter_physical, 1, 1920, 1080, 3840, 0),
        _target_mode(adapter_physical, 11, 1920, 1080, (60000, 1001)),
    ]

    class FakeApi:
        def query_active_paths(self):
            return paths, modes, displayprobe.DEFAULT_QUERY_FLAGS

        def get_source_name(self, adapter_id, source_id):
            key = (displayprobe.format_luid(adapter_id), source_id)
            return {
                ("00000000:00000001", 0): r"\\.\DISPLAY1",
                ("00000000:00000002", 1): r"\\.\DISPLAY2",
            }[key]

        def get_target_name(self, adapter_id, target_id):
            key = (displayprobe.format_luid(adapter_id), target_id)
            return {
                ("00000000:00000001", 10): (
                    "Sunshine Virtual Display",
                    r"ROOT\SunshineVirtualDisplay\0000",
                ),
                ("00000000:00000002", 11): (
                    "Dell U2720Q",
                    r"\\?\DISPLAY#DEL4098#5&12345",
                ),
            }[key]

        def get_adapter_name(self, adapter_id):
            return {
                "00000000:00000001": r"\\?\DISPLAY#Sunshine#0001",
                "00000000:00000002": r"\\?\PCI#VEN_10DE&DEV_1C82",
            }[displayprobe.format_luid(adapter_id)]

        def get_advanced_color_info(self, adapter_id, target_id):
            key = (displayprobe.format_luid(adapter_id), target_id)
            if key == ("00000000:00000001", 10):
                return {
                    "hdr_supported": True,
                    "hdr_enabled": True,
                    "bits_per_channel": 10,
                    "color_encoding": "rgb",
                }
            return {
                "hdr_supported": None,
                "hdr_enabled": None,
                "bits_per_channel": None,
                "color_encoding": None,
            }

    samples = displayprobe._detect_windows(FakeApi())

    assert len(samples) == 2
    assert samples[0] == {
        "source": "host",
        "machine": None,
        "phase": None,
        "adapter_id": "00000000:00000001",
        "adapter_device_path": r"\\?\DISPLAY#Sunshine#0001",
        "source_id": 0,
        "target_id": 10,
        "source_name": r"\\.\DISPLAY1",
        "friendly_name": "Sunshine Virtual Display",
        "device_path": r"ROOT\SunshineVirtualDisplay\0000",
        "is_virtual": True,
        "primary": True,
        "width": 3840,
        "height": 2160,
        "refresh_hz": 144,
        "rotation": "identity",
        "scaling": "preferred",
        "output_technology": "indirect-virtual",
        "hdr_supported": True,
        "hdr_enabled": True,
        "bits_per_channel": 10,
        "color_encoding": "rgb",
        "sampled_at": samples[0]["sampled_at"],
    }
    assert samples[1] == {
        "source": "host",
        "machine": None,
        "phase": None,
        "adapter_id": "00000000:00000002",
        "adapter_device_path": r"\\?\PCI#VEN_10DE&DEV_1C82",
        "source_id": 1,
        "target_id": 11,
        "source_name": r"\\.\DISPLAY2",
        "friendly_name": "Dell U2720Q",
        "device_path": r"\\?\DISPLAY#DEL4098#5&12345",
        "is_virtual": None,
        "primary": False,
        "width": 1920,
        "height": 1080,
        "refresh_hz": 59.94,
        "rotation": "identity",
        "scaling": "preferred",
        "output_technology": "hdmi",
        "hdr_supported": None,
        "hdr_enabled": None,
        "bits_per_channel": None,
        "color_encoding": None,
        "sampled_at": samples[1]["sampled_at"],
    }
    assert samples[0]["sampled_at"] == samples[1]["sampled_at"]
