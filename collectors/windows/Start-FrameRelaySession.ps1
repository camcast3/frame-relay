<#
.SYNOPSIS
  Capture an Frame Relay session on this Windows machine (Apollo host, or a
  Moonlight/Artemis client) and ship logs + Wi-Fi/link samples to the hub.

.EXAMPLE
  # HOST, recommended: leave this running. It waits for whichever session the client creates,
  # captures into it, then waits for the next one. Safe to restart; no session id needed.
  .\Start-FrameRelaySession.ps1 -HubUrl http://192.0.2.10:8080 -Source host -Watch

.EXAMPLE
  # Apollo host, attach to one existing session, sample the link every 15s until you press Enter
  .\Start-FrameRelaySession.ps1 -HubUrl https://frame-relay.<tailnet>.ts.net `
      -SessionId 20260723T101951-ab12 -Source host

.EXAMPLE
  # Windows Artemis client, create the session on the fly (newest Artemis log)
  $log = (Get-ChildItem "$env:TEMP\Artemis-*.log" |
          Sort-Object LastWriteTime -Desc | Select-Object -First 1).FullName
  .\Start-FrameRelaySession.ps1 -HubUrl https://frame-relay.<tailnet>.ts.net -Create `
      -Name "Windows Artemis LAN" -Host STREAM-HOST -Client laptop -NetworkPath local-LAN `
      -Source client -Role artemis -LogPath $log

.EXAMPLE
  # Windows Moonlight/Artemis client, zero copy-paste: attach to the newest session the host
  # created (no -SessionId), auto-detect the newest Artemis log.
  .\Start-FrameRelaySession.ps1 -HubUrl http://192.0.2.10:8080 -Source client -Role artemis -AttachLatest

.EXAMPLE
  # LIVE client logs, no paths to type: the collector wraps Artemis - it finds the app for -Role,
  # launches it, and captures its stderr in real time (the %TEMP% log is buffered and only
  # flushes in bursts). Capture ends when you close Artemis.
  .\Start-FrameRelaySession.ps1 -HubUrl http://192.0.2.10:8080 -Source client -Role artemis `
      -Create -Name "couch LAN AV1" -LaunchClient

.EXAMPLE
  # Same, but point at a specific executable (non-standard install location)
  .\Start-FrameRelaySession.ps1 -HubUrl http://192.0.2.10:8080 -Source client -Role artemis `
      -AttachLatest -Launch "$env:ProgramFiles\Artemis Game Streaming\Artemis.exe"
#>
[CmdletBinding()]
param(
  [Parameter(Mandatory = $true)][string]$HubUrl,
  [string]$SessionId,
  [switch]$AttachLatest,
  [switch]$Create,
  [switch]$Watch,
  [double]$WatchIntervalSeconds = 5,
  [ValidateSet('host', 'client')][string]$Source = 'host',
  [ValidateSet('apollo', 'moonlight', 'artemis')][string]$Role,
  [string[]]$LogPath,
  [string]$Launch,
  [switch]$LaunchClient,
  [string[]]$LaunchArgs,
  [string]$Machine,
  [double]$IntervalSeconds = 15,
  [double]$PostIntervalSeconds = 30,
  [string]$ScreenshotToken,
  [double]$ScreenshotPollInterval = 3,
  [int]$DurationSeconds = 0,
  [switch]$StopSession,
  # metadata used only with -Create
  [string]$Name,
  [string]$ComparisonLabel,
  [string]$ApolloApp,
  [string]$GameTitle,
  [string]$ClientPlatform,
  [string]$ClientVersion,
  [string]$HostName,
  [string]$Client,
  [ValidateSet('local-LAN', 'remote-WireGuard', 'remote-Tailscale', 'remote-WAN')][string]$NetworkPath,
  [string[]]$WgSubnet,
  [string]$Codec,
  [string]$Resolution,
  [int]$Fps,
  [int]$BitrateMbps,
  [switch]$Hdr,
  [switch]$NoHdr
)

$ErrorActionPreference = 'Stop'
if ($Hdr -and $NoHdr) { throw '-Hdr and -NoHdr are mutually exclusive.' }

# Prefer the real interpreter; the bare 'python' alias can be the Store stub.
if (Get-Command py -ErrorAction SilentlyContinue) {
  $pythonExe = 'py'
  $pythonPrefix = @('-3')
}
elseif (Get-Command python -ErrorAction SilentlyContinue) {
  $pythonExe = 'python'
  $pythonPrefix = @()
}
else {
  throw 'Python 3 not found. Install Python 3 and re-run.'
}

$collectorsDir = Split-Path $PSScriptRoot -Parent   # ...\collectors (contains frame_relay_collector)
$env:PYTHONPATH = $collectorsDir

# Log discovery is centralized in the collector (frame_relay_collector/logfind.py): omit -LogPath and it
# auto-detects from -Source/-Role on every platform. Pass -LogPath to override.

$collectorArgs = @('-m', 'frame_relay_collector', '--hub-url', $HubUrl, '--source', $Source,
         '--interval', $IntervalSeconds, '--post-interval', $PostIntervalSeconds,
         '--duration', $DurationSeconds)
if ($SessionId)   { $collectorArgs += @('--session-id', $SessionId) }
if ($AttachLatest){ $collectorArgs += '--attach-latest' }
if ($Watch)       { $collectorArgs += @('--watch', '--watch-interval', $WatchIntervalSeconds) }
if ($Create)      { $collectorArgs += '--create' }
if ($Role)        { $collectorArgs += @('--role', $Role) }
if ($Machine)     { $collectorArgs += @('--machine', $Machine) }
if ($StopSession) { $collectorArgs += '--stop-session' }
foreach ($p in $LogPath) { $collectorArgs += @('--log', $p) }
if ($Launch)      { $collectorArgs += @('--launch', $Launch) }
if ($LaunchClient){ $collectorArgs += '--launch-client' }
foreach ($a in $LaunchArgs) { $collectorArgs += @('--launch-arg', $a) }
if ($ScreenshotToken) { $collectorArgs += @('--screenshot-token', $ScreenshotToken) }
if ($PSBoundParameters.ContainsKey('ScreenshotPollInterval')) {
  $collectorArgs += @('--screenshot-poll-interval', $ScreenshotPollInterval)
}
if ($Name)        { $collectorArgs += @('--name', $Name) }
if ($ComparisonLabel) { $collectorArgs += @('--comparison-label', $ComparisonLabel) }
if ($ApolloApp)   { $collectorArgs += @('--apollo-app', $ApolloApp) }
if ($GameTitle)   { $collectorArgs += @('--game-title', $GameTitle) }
if ($ClientPlatform) { $collectorArgs += @('--client-platform', $ClientPlatform) }
if ($ClientVersion) { $collectorArgs += @('--client-version', $ClientVersion) }
if ($HostName)    { $collectorArgs += @('--host', $HostName) }
if ($Client)      { $collectorArgs += @('--client', $Client) }
if ($NetworkPath) { $collectorArgs += @('--network-path', $NetworkPath) }
foreach ($sn in $WgSubnet) { $collectorArgs += @('--wg-subnet', $sn) }
if ($Codec)       { $collectorArgs += @('--codec', $Codec) }
if ($Resolution)  { $collectorArgs += @('--resolution', $Resolution) }
if ($Fps)         { $collectorArgs += @('--fps', $Fps) }
if ($BitrateMbps) { $collectorArgs += @('--bitrate-mbps', $BitrateMbps) }
if ($Hdr)         { $collectorArgs += '--hdr' }
if ($NoHdr)       { $collectorArgs += '--no-hdr' }

& $pythonExe @($pythonPrefix + $collectorArgs)
