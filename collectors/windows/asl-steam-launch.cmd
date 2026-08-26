@echo off
setlocal EnableExtensions EnableDelayedExpansion

set "ASL_ROOT=%LOCALAPPDATA%\ApolloStreamingLab"
set "PYTHONPATH=%ASL_ROOT%\lib"
set "ASL_CONFIG=%ASL_ROOT%\steam-launch.json"
set "ASL_LOG=%ASL_ROOT%\logs\steam-launch.log"

where py >nul 2>nul
if %ERRORLEVEL% EQU 0 (
  py -3 -m asl_collector.steamlaunch --config "%ASL_CONFIG%" --log-file "%ASL_LOG%" %*
  exit /b !ERRORLEVEL!
)

where python >nul 2>nul
if %ERRORLEVEL% EQU 0 (
  python -m asl_collector.steamlaunch --config "%ASL_CONFIG%" --log-file "%ASL_LOG%" %*
  exit /b !ERRORLEVEL!
)

echo Python 3 is required for Apollo Streaming Lab. 1>&2
exit /b 1
