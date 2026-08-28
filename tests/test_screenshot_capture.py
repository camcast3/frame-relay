from __future__ import annotations

import binascii
import subprocess
import zlib

import pytest

from frame_relay_collector import screenshot


def _png_bytes(width: int, height: int) -> bytes:
    def _chunk(kind: bytes, payload: bytes) -> bytes:
        crc = binascii.crc32(kind + payload) & 0xFFFFFFFF
        return (
            len(payload).to_bytes(4, "big")
            + kind
            + payload
            + crc.to_bytes(4, "big")
        )

    ihdr = (
        width.to_bytes(4, "big")
        + height.to_bytes(4, "big")
        + b"\x08\x06\x00\x00\x00"
    )
    row = b"\x00" + (b"\x00\x00\x00\xFF" * width)
    return (
        screenshot.PNG_SIGNATURE
        + _chunk(b"IHDR", ihdr)
        + _chunk(b"IDAT", zlib.compress(row * height))
        + _chunk(b"IEND", b"")
    )


def test_capture_windows_uses_powershell_and_returns_png_metadata(tmp_path, monkeypatch):
    out_path = tmp_path / "capture.png"
    monkeypatch.setattr(screenshot.platform, "system", lambda: "Windows")
    monkeypatch.setattr(screenshot, "_temp_png_path", lambda: str(out_path))
    monkeypatch.setattr(
        screenshot.shutil,
        "which",
        lambda name: "C:\\Windows\\System32\\WindowsPowerShell\\v1.0\\powershell.exe"
        if name in {"powershell", "powershell.exe", "pwsh"}
        else None,
    )

    seen: dict[str, list[str]] = {}

    def fake_run(cmd, **kwargs):
        seen["cmd"] = list(cmd)
        seen["env"] = kwargs.get("env")
        out_path.write_bytes(_png_bytes(2560, 1440))
        return subprocess.CompletedProcess(
            cmd,
            0,
            stdout='{"display_name":"\\\\\\\\.\\\\DISPLAY1","width":2560,"height":1440}',
            stderr="",
        )

    monkeypatch.setattr(screenshot.subprocess, "run", fake_run)

    captured = screenshot.capture(r"\\.\DISPLAY2")

    assert seen["cmd"][0].endswith("powershell.exe")
    assert "PrimaryScreen" in seen["cmd"][-1]
    assert "AllScreens" in seen["cmd"][-1]
    assert "CopyFromScreen" in seen["cmd"][-1]
    assert seen["env"]["FRAME_RELAY_SCREENSHOT_DISPLAY"] == r"\\.\DISPLAY2"
    assert captured["path"] == str(out_path)
    assert captured["display_name"] == r"\\.\DISPLAY1"
    assert captured["width"] == 2560
    assert captured["height"] == 1440
    assert captured["captured_at"].endswith("Z")
    assert out_path.read_bytes().startswith(screenshot.PNG_SIGNATURE)


def test_capture_windows_cleans_up_invalid_png(tmp_path, monkeypatch):
    out_path = tmp_path / "invalid.png"
    monkeypatch.setattr(screenshot.platform, "system", lambda: "Windows")
    monkeypatch.setattr(screenshot, "_temp_png_path", lambda: str(out_path))
    monkeypatch.setattr(screenshot.shutil, "which", lambda name: "powershell.exe")

    def fake_run(cmd, **kwargs):
        out_path.write_text("not a png", encoding="utf-8")
        return subprocess.CompletedProcess(cmd, 0, stdout="{}", stderr="")

    monkeypatch.setattr(screenshot.subprocess, "run", fake_run)

    with pytest.raises(screenshot.ScreenshotError, match="valid PNG"):
        screenshot.capture()

    assert not out_path.exists()


def test_capture_linux_falls_back_to_next_available_tool(tmp_path, monkeypatch):
    out_path = tmp_path / "linux.png"
    monkeypatch.setattr(screenshot.platform, "system", lambda: "Linux")
    monkeypatch.setattr(screenshot, "_temp_png_path", lambda: str(out_path))

    which_map = {
        "grim": "/usr/bin/grim",
        "scrot": "/usr/bin/scrot",
    }
    monkeypatch.setattr(screenshot.shutil, "which", lambda name: which_map.get(name))

    calls: list[str] = []

    def fake_run(cmd, **kwargs):
        calls.append(cmd[0])
        if cmd[0].endswith("grim"):
            out_path.write_text("partial", encoding="utf-8")
            return subprocess.CompletedProcess(cmd, 1, stdout="", stderr="permission denied")
        out_path.write_bytes(_png_bytes(1920, 1080))
        return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")

    monkeypatch.setattr(screenshot.subprocess, "run", fake_run)

    captured = screenshot.capture()

    assert calls == ["/usr/bin/grim", "/usr/bin/scrot"]
    assert captured["display_name"] == "Desktop"
    assert captured["width"] == 1920
    assert captured["height"] == 1080
    assert out_path.exists()


def test_capture_linux_without_supported_tools_is_explicit(monkeypatch):
    monkeypatch.setattr(screenshot.platform, "system", lambda: "Linux")
    monkeypatch.setattr(screenshot.shutil, "which", lambda name: None)

    with pytest.raises(screenshot.UnsupportedScreenshotError, match="grim"):
        screenshot.capture()


def test_capture_rejects_unsupported_platform(monkeypatch):
    monkeypatch.setattr(screenshot.platform, "system", lambda: "Darwin")

    with pytest.raises(screenshot.UnsupportedScreenshotError, match="Darwin"):
        screenshot.capture()
