<#
.SYNOPSIS
  Capture an Apollo Streaming Lab session on this Windows machine (Apollo host, or a
  Moonlight/Artemis client) and ship logs + Wi-Fi/link samples to the hub.

.EXAMPLE
  # Apollo host, attach to an existing session, sample the link every 15s until you press Enter
  .\Start-AslSession.ps1 -HubUrl https://apollo-streaming-lab.<tailnet>.ts.net `
      -SessionId 20260723T101951-ab12 -Source host

.EXAMPLE
  # Windows Moonlight client, create the session on the fly
  .\Start-AslSession.ps1 -HubUrl https://apollo-streaming-lab.<tailnet>.ts.net -Create `
      -Name "Windows Moonlight LAN" -Host DOMINO -Client laptop -NetworkPath local-LAN `
      -Source client -Role moonlight -LogPath "$env:TEMP\Moonlight\Moonlight.log"
#>
[CmdletBinding()]
param(
  [Parameter(Mandatory = $true)][string]$HubUrl,
  [string]$SessionId,
  [switch]$Create,
  [ValidateSet('host', 'client')][string]$Source = 'host',
  [ValidateSet('apollo', 'moonlight', 'artemis')][string]$Role,
  [string[]]$LogPath,
  [string]$Machine,
  [double]$IntervalSeconds = 15,
  [int]$DurationSeconds = 0,
  [switch]$StopSession,
  # metadata used only with -Create
  [string]$Name,
  [string]$HostName,
  [string]$Client,
  [ValidateSet('local-LAN', 'remote-Tailscale', 'remote-WAN')][string]$NetworkPath,
  [string]$Codec,
  [string]$Resolution,
  [int]$Fps,
  [int]$BitrateMbps,
  [switch]$Hdr
)

$ErrorActionPreference = 'Stop'

# Prefer the real interpreter; the bare 'python' alias can be the Store stub.
$python = if (Get-Command py -ErrorAction SilentlyContinue) { @('py', '-3') }
          elseif (Get-Command python -ErrorAction SilentlyContinue) { @('python') }
          else { throw 'Python 3 not found. Install Python 3 and re-run.' }

$collectorsDir = Split-Path $PSScriptRoot -Parent   # ...\collectors (contains asl_collector)
$env:PYTHONPATH = $collectorsDir

# Auto-discover the Apollo log on a host if none was given.
if (-not $LogPath -and $Source -eq 'host') {
  $candidates = @(
    "$env:ProgramFiles\Apollo\config\sunshine.log",
    "${env:ProgramFiles(x86)}\Apollo\config\sunshine.log",
    "$env:ProgramFiles\Sunshine\config\sunshine.log"
  )
  $found = $candidates | Where-Object { Test-Path $_ } | Select-Object -First 1
  if ($found) { $LogPath = @($found); Write-Host "Using Apollo log: $found" }
  else { Write-Warning "No Apollo log auto-detected; pass -LogPath explicitly." }
}

$asl = @('-m', 'asl_collector', '--hub-url', $HubUrl, '--source', $Source,
         '--interval', $IntervalSeconds, '--duration', $DurationSeconds)
if ($SessionId)   { $asl += @('--session-id', $SessionId) }
if ($Create)      { $asl += '--create' }
if ($Role)        { $asl += @('--role', $Role) }
if ($Machine)     { $asl += @('--machine', $Machine) }
if ($StopSession) { $asl += '--stop-session' }
foreach ($p in $LogPath) { $asl += @('--log', $p) }
if ($Name)        { $asl += @('--name', $Name) }
if ($HostName)    { $asl += @('--host', $HostName) }
if ($Client)      { $asl += @('--client', $Client) }
if ($NetworkPath) { $asl += @('--network-path', $NetworkPath) }
if ($Codec)       { $asl += @('--codec', $Codec) }
if ($Resolution)  { $asl += @('--resolution', $Resolution) }
if ($Fps)         { $asl += @('--fps', $Fps) }
if ($BitrateMbps) { $asl += @('--bitrate-mbps', $BitrateMbps) }
if ($Hdr)         { $asl += '--hdr' }

& $python[0] @($python[1..($python.Length - 1)] + $asl)
