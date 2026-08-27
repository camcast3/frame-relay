<#
.SYNOPSIS
  Install or update the user-local Frame Relay Steam wrapper.

.DESCRIPTION
  If -ClientRole is omitted, setup asks whether the Steam shortcut is Moonlight or Artemis.
  Steam shortcut records are read only to find their grid id; shortcuts.vdf is never modified.
#>
[CmdletBinding()]
param(
  [ValidateSet('moonlight', 'artemis')][string]$ClientRole,
  [string]$HubUrl,
  [switch]$Reconfigure,
  [string]$Shortcut,
  [string[]]$SteamConfigDir,
  [switch]$SkipArtwork
)

$ErrorActionPreference = 'Stop'

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

$collectorsDir = Split-Path $PSScriptRoot -Parent
$env:PYTHONPATH = $collectorsDir
$setupArgs = @('-m', 'frame_relay_collector.steamsetup')
if ($ClientRole) { $setupArgs += @('--client-role', $ClientRole) }
if ($HubUrl) { $setupArgs += @('--hub-url', $HubUrl) }
if ($Reconfigure) { $setupArgs += '--reconfigure' }
if ($Shortcut) { $setupArgs += @('--shortcut', $Shortcut) }
foreach ($path in $SteamConfigDir) { $setupArgs += @('--steam-config-dir', $path) }
if ($SkipArtwork) { $setupArgs += '--skip-artwork' }

& $pythonExe @($pythonPrefix + $setupArgs)
