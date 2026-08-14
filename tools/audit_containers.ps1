[CmdletBinding()]
param(
  [datetime]$Cutoff = [datetime]::UtcNow.AddDays(-7),
  [string]$HubImage = 'apollo-streaming-lab:dependency-audit',
  [string]$TailscaleImage
)

$ErrorActionPreference = 'Stop'

function Invoke-Checked {
  param([string]$Description, [scriptblock]$Command)
  Write-Host "==> $Description"
  & $Command
  if ($LASTEXITCODE -ne 0) {
    throw "$Description failed with exit code $LASTEXITCODE"
  }
}

$fromLine = Select-String -Path "$PSScriptRoot\..\Dockerfile" -Pattern '^FROM\s+(.+)$' |
  Select-Object -First 1
if (-not $fromLine) {
  throw 'Dockerfile has no FROM line.'
}
$baseImage = $fromLine.Matches[0].Groups[1].Value.Trim()

Invoke-Checked "Pull base image $baseImage" { docker pull --quiet $baseImage }
$baseCreated = [datetime](docker image inspect $baseImage --format '{{.Created}}')
if ($baseCreated.ToUniversalTime() -gt $Cutoff.ToUniversalTime()) {
  throw "Base image was created $($baseCreated.ToUniversalTime().ToString('o')), newer than cutoff $($Cutoff.ToUniversalTime().ToString('o'))."
}

Invoke-Checked "Build hub image $HubImage" {
  docker build --tag $HubImage "$PSScriptRoot\.."
}
Invoke-Checked 'Scan hub image for critical/high vulnerabilities' {
  docker scout cves --only-severity critical,high --exit-code $HubImage
}

if ([string]::IsNullOrWhiteSpace($TailscaleImage)) {
  Write-Warning 'No TailscaleImage candidate supplied; tracked tailnet deployment remains securely disabled.'
  exit 0
}
if ($TailscaleImage -notmatch '^tailscale/tailscale:v\d+\.\d+\.\d+@sha256:[0-9a-fA-F]{64}$') {
  throw 'TailscaleImage must be an official tailscale/tailscale:vX.Y.Z@sha256:digest reference.'
}

Invoke-Checked "Pull Tailscale image $TailscaleImage" { docker pull --quiet $TailscaleImage }
$tailscaleCreated = [datetime](docker image inspect $TailscaleImage --format '{{.Created}}')
if ($tailscaleCreated.ToUniversalTime() -gt $Cutoff.ToUniversalTime()) {
  throw "Tailscale image was created $($tailscaleCreated.ToUniversalTime().ToString('o')), newer than cutoff $($Cutoff.ToUniversalTime().ToString('o'))."
}
Invoke-Checked 'Scan Tailscale image for critical/high vulnerabilities' {
  docker scout cves --only-severity critical,high --exit-code $TailscaleImage
}
