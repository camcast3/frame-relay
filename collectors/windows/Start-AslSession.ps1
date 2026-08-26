<#
.SYNOPSIS
  Capture an Apollo Streaming Lab session on this Windows machine (Apollo host, or a
  Moonlight/Artemis client) and ship logs + Wi-Fi/link samples to the hub.

.EXAMPLE
  # HOST, recommended: leave this running. It waits for whichever session the client creates,
  # captures into it, then waits for the next one. Safe to restart; no session id needed.
  .\Start-AslSession.ps1 -HubUrl http://192.168.69.159:8080 -Source host -Watch

.EXAMPLE
  # Apollo host, attach to one existing session, sample the link every 15s until you press Enter
  .\Start-AslSession.ps1 -HubUrl https://apollo-streaming-lab.<tailnet>.ts.net `
      -SessionId 20260723T101951-ab12 -Source host

.EXAMPLE
  # Windows Artemis client, create the session on the fly (newest Artemis log)
  $log = (Get-ChildItem "$env:TEMP\Artemis-*.log" |
          Sort-Object LastWriteTime -Desc | Select-Object -First 1).FullName
  .\Start-AslSession.ps1 -HubUrl https://apollo-streaming-lab.<tailnet>.ts.net -Create `
      -Name "Windows Artemis LAN" -Host DOMINO -Client laptop -NetworkPath local-LAN `
      -Source client -Role artemis -LogPath $log

.EXAMPLE
  # Windows Moonlight/Artemis client, zero copy-paste: attach to the newest session the host
  # created (no -SessionId), auto-detect the newest Artemis log.
  .\Start-AslSession.ps1 -HubUrl http://192.168.69.159:8080 -Source client -Role artemis -AttachLatest

.EXAMPLE
  # LIVE client logs, no paths to type: the collector wraps Artemis - it finds the app for -Role,
  # launches it, and captures its stderr in real time (the %TEMP% log is buffered and only
  # flushes in bursts). Capture ends when you close Artemis.
  .\Start-AslSession.ps1 -HubUrl http://192.168.69.159:8080 -Source client -Role artemis `
      -Create -Name "couch LAN AV1" -LaunchClient

.EXAMPLE
  # Same, but point at a specific executable (non-standard install location)
  .\Start-AslSession.ps1 -HubUrl http://192.168.69.159:8080 -Source client -Role artemis `
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
$python = if (Get-Command py -ErrorAction SilentlyContinue) { @('py', '-3') }
          elseif (Get-Command python -ErrorAction SilentlyContinue) { @('python') }
          else { throw 'Python 3 not found. Install Python 3 and re-run.' }

$collectorsDir = Split-Path $PSScriptRoot -Parent   # ...\collectors (contains asl_collector)
$env:PYTHONPATH = $collectorsDir

# Log discovery is centralized in the collector (asl_collector/logfind.py): omit -LogPath and it
# auto-detects from -Source/-Role on every platform. Pass -LogPath to override.

$asl = @('-m', 'asl_collector', '--hub-url', $HubUrl, '--source', $Source,
         '--interval', $IntervalSeconds, '--post-interval', $PostIntervalSeconds,
         '--duration', $DurationSeconds)
if ($SessionId)   { $asl += @('--session-id', $SessionId) }
if ($AttachLatest){ $asl += '--attach-latest' }
if ($Watch)       { $asl += @('--watch', '--watch-interval', $WatchIntervalSeconds) }
if ($Create)      { $asl += '--create' }
if ($Role)        { $asl += @('--role', $Role) }
if ($Machine)     { $asl += @('--machine', $Machine) }
if ($StopSession) { $asl += '--stop-session' }
foreach ($p in $LogPath) { $asl += @('--log', $p) }
if ($Launch)      { $asl += @('--launch', $Launch) }
if ($LaunchClient){ $asl += '--launch-client' }
foreach ($a in $LaunchArgs) { $asl += @('--launch-arg', $a) }
if ($ScreenshotToken) { $asl += @('--screenshot-token', $ScreenshotToken) }
if ($PSBoundParameters.ContainsKey('ScreenshotPollInterval')) {
  $asl += @('--screenshot-poll-interval', $ScreenshotPollInterval)
}
if ($Name)        { $asl += @('--name', $Name) }
if ($ComparisonLabel) { $asl += @('--comparison-label', $ComparisonLabel) }
if ($ApolloApp)   { $asl += @('--apollo-app', $ApolloApp) }
if ($GameTitle)   { $asl += @('--game-title', $GameTitle) }
if ($ClientPlatform) { $asl += @('--client-platform', $ClientPlatform) }
if ($ClientVersion) { $asl += @('--client-version', $ClientVersion) }
if ($HostName)    { $asl += @('--host', $HostName) }
if ($Client)      { $asl += @('--client', $Client) }
if ($NetworkPath) { $asl += @('--network-path', $NetworkPath) }
foreach ($sn in $WgSubnet) { $asl += @('--wg-subnet', $sn) }
if ($Codec)       { $asl += @('--codec', $Codec) }
if ($Resolution)  { $asl += @('--resolution', $Resolution) }
if ($Fps)         { $asl += @('--fps', $Fps) }
if ($BitrateMbps) { $asl += @('--bitrate-mbps', $BitrateMbps) }
if ($Hdr)         { $asl += '--hdr' }
if ($NoHdr)       { $asl += '--no-hdr' }

& $python[0] @($python[1..($python.Length - 1)] + $asl)
