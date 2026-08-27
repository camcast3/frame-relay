"""Best-effort screenshot capture helpers.

HDR captures may be tone-mapped by the OS/driver stack, and protected video
surfaces can appear blank even when the PNG itself is valid.
"""
from __future__ import annotations

from datetime import datetime, timezone
import json
import os
import platform
import shutil
import subprocess
import tempfile
from typing import TypedDict


PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"


class ScreenshotError(RuntimeError):
    """Screenshot capture failed."""


class UnsupportedScreenshotError(ScreenshotError):
    """Screenshot capture is unavailable on this platform."""


class CaptureResult(TypedDict):
    path: str
    display_name: str
    width: int
    height: int
    captured_at: str


def _captured_at() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _temp_png_path() -> str:
    fd, path = tempfile.mkstemp(prefix="frame_relay_screenshot_", suffix=".png")
    os.close(fd)
    try:
        os.unlink(path)
    except FileNotFoundError:
        pass
    return path


def _cleanup(path: str) -> None:
    try:
        os.unlink(path)
    except FileNotFoundError:
        pass
    except OSError:
        pass


def _png_dimensions(path: str) -> tuple[int, int]:
    try:
        with open(path, "rb") as fh:
            header = fh.read(33)
    except FileNotFoundError as exc:
        raise ScreenshotError(f"screenshot capture did not create {path}") from exc
    except OSError as exc:
        raise ScreenshotError(f"unable to read captured screenshot {path}: {exc}") from exc
    if len(header) < 24 or not header.startswith(PNG_SIGNATURE):
        raise ScreenshotError(f"capture output is not a valid PNG: {path}")
    ihdr_length = int.from_bytes(header[8:12], "big")
    ihdr_type = header[12:16]
    if ihdr_length != 13 or ihdr_type != b"IHDR":
        raise ScreenshotError(f"capture output is not a valid PNG: {path}")
    width = int.from_bytes(header[16:20], "big")
    height = int.from_bytes(header[20:24], "big")
    if width <= 0 or height <= 0:
        raise ScreenshotError(f"capture output has invalid PNG dimensions: {path}")
    return width, height


def _run_capture(
    cmd: list[str],
    *,
    label: str,
    env: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    try:
        return subprocess.run(  # noqa: S603 - collector invokes fixed/local tools only
            cmd,
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
            env=env,
        )
    except FileNotFoundError as exc:
        raise UnsupportedScreenshotError(f"{label} is not installed") from exc
    except subprocess.TimeoutExpired as exc:
        raise ScreenshotError(f"{label} timed out while capturing the screenshot") from exc
    except OSError as exc:
        raise ScreenshotError(f"{label} failed to start: {exc}") from exc


def _command_error(label: str, proc: subprocess.CompletedProcess[str]) -> ScreenshotError:
    details = (proc.stderr or proc.stdout or "").strip()
    if details:
        return ScreenshotError(f"{label} failed: {details}")
    return ScreenshotError(f"{label} exited with code {proc.returncode}")


def _capture_windows(preferred_display_name: str | None = None) -> CaptureResult:
    powershell = (
        shutil.which("powershell")
        or shutil.which("powershell.exe")
        or shutil.which("pwsh")
    )
    if not powershell:
        raise UnsupportedScreenshotError("PowerShell is not available for screenshot capture")

    path = _temp_png_path()
    escaped = path.replace("'", "''")
    script = f"""
$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName System.Windows.Forms
Add-Type -AssemblyName System.Drawing
$preferred = $env:FRAME_RELAY_SCREENSHOT_DISPLAY
if (-not $preferred) {{ $preferred = $env:ASL_SCREENSHOT_DISPLAY }}
$screen = $null
if ($preferred) {{
    $screen = [System.Windows.Forms.Screen]::AllScreens |
        Where-Object {{ $_.DeviceName -eq $preferred }} |
        Select-Object -First 1
}}
if ($null -eq $screen) {{ $screen = [System.Windows.Forms.Screen]::PrimaryScreen }}
if ($null -eq $screen) {{ throw 'No primary screen is available for capture.' }}
$bounds = $screen.Bounds
if ($bounds.Width -le 0 -or $bounds.Height -le 0) {{
    throw "Primary screen has invalid bounds: $($bounds.Width)x$($bounds.Height)"
}}
$bitmap = New-Object System.Drawing.Bitmap($bounds.Width, $bounds.Height)
$graphics = [System.Drawing.Graphics]::FromImage($bitmap)
try {{
    $graphics.CopyFromScreen($bounds.Location, [System.Drawing.Point]::Empty, $bounds.Size)
    $bitmap.Save('{escaped}', [System.Drawing.Imaging.ImageFormat]::Png)
    [Console]::Out.Write((@{{
        display_name = $screen.DeviceName
        width = $bounds.Width
        height = $bounds.Height
    }} | ConvertTo-Json -Compress))
}}
finally {{
    if ($graphics -ne $null) {{ $graphics.Dispose() }}
    if ($bitmap -ne $null) {{ $bitmap.Dispose() }}
}}
""".strip()
    try:
        env = dict(os.environ)
        if preferred_display_name:
            env["FRAME_RELAY_SCREENSHOT_DISPLAY"] = preferred_display_name
        else:
            env.pop("FRAME_RELAY_SCREENSHOT_DISPLAY", None)
        proc = _run_capture(
            [
                powershell,
                "-NoLogo",
                "-NoProfile",
                "-NonInteractive",
                "-ExecutionPolicy",
                "Bypass",
                "-Command",
                script,
            ],
            label="PowerShell screenshot capture",
            env=env,
        )
        if proc.returncode != 0:
            raise _command_error("PowerShell screenshot capture", proc)
        width, height = _png_dimensions(path)
        display_name = "Primary display"
        stdout = (proc.stdout or "").strip()
        if stdout:
            try:
                payload = json.loads(stdout)
            except json.JSONDecodeError:
                payload = {}
            if isinstance(payload, dict):
                value = payload.get("display_name")
                if value not in (None, ""):
                    display_name = str(value)
                width = int(payload.get("width") or width)
                height = int(payload.get("height") or height)
        return {
            "path": path,
            "display_name": display_name,
            "width": width,
            "height": height,
            "captured_at": _captured_at(),
        }
    except Exception:
        _cleanup(path)
        raise


def _capture_linux() -> CaptureResult:
    path = _temp_png_path()
    candidates = [
        ("grim", ["grim", path], "Desktop"),
        ("gnome-screenshot", ["gnome-screenshot", "-f", path], "Desktop"),
        ("scrot", ["scrot", path], "Desktop"),
        ("ImageMagick import", ["import", "-window", "root", path], "Desktop"),
    ]
    errors: list[str] = []
    try:
        for label, cmd, display_name in candidates:
            executable = shutil.which(cmd[0])
            if not executable:
                continue
            proc = _run_capture([executable] + cmd[1:], label=label)
            if proc.returncode != 0:
                errors.append(str(_command_error(label, proc)))
                _cleanup(path)
                continue
            try:
                width, height = _png_dimensions(path)
            except ScreenshotError as exc:
                errors.append(f"{label}: {exc}")
                _cleanup(path)
                continue
            return {
                "path": path,
                "display_name": display_name,
                "width": width,
                "height": height,
                "captured_at": _captured_at(),
            }
    except Exception:
        _cleanup(path)
        raise

    _cleanup(path)
    if errors:
        raise ScreenshotError("; ".join(errors))
    raise UnsupportedScreenshotError(
        "screenshot capture is unsupported on Linux without grim, gnome-screenshot, "
        "scrot, or ImageMagick import"
    )


def capture(preferred_display_name: str | None = None) -> CaptureResult:
    system = platform.system()
    if system == "Windows":
        return _capture_windows(preferred_display_name)
    if system == "Linux":
        return _capture_linux()
    raise UnsupportedScreenshotError(
        f"screenshot capture is unsupported on {system or 'this platform'}"
    )
