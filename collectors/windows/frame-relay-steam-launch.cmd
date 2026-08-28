@echo off
setlocal EnableExtensions EnableDelayedExpansion

set "FRAME_RELAY_ROOT=%LOCALAPPDATA%\FrameRelay"
set "PYTHONPATH=%FRAME_RELAY_ROOT%\lib"
set "FRAME_RELAY_CONFIG=%FRAME_RELAY_ROOT%\steam-launch.json"
set "FRAME_RELAY_LOG=%FRAME_RELAY_ROOT%\logs\steam-launch.log"

where py >nul 2>nul
if %ERRORLEVEL% EQU 0 (
  py -3 -m frame_relay_collector.steamlaunch --config "%FRAME_RELAY_CONFIG%" --log-file "%FRAME_RELAY_LOG%" %*
  exit /b !ERRORLEVEL!
)

where python >nul 2>nul
if %ERRORLEVEL% EQU 0 (
  python -m frame_relay_collector.steamlaunch --config "%FRAME_RELAY_CONFIG%" --log-file "%FRAME_RELAY_LOG%" %*
  exit /b !ERRORLEVEL!
)

echo Python 3 is required for Frame Relay. 1>&2
exit /b 1
