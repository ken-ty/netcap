# netcap-agent.ps1 — the entry point netcap calls on a Windows device. Also works as-is as an ssh forced command
#
#   netcap-agent.ps1 <verb> [args...]           directly
#   netcap-agent.ps1 --allow '<verb> <verb> …'  as a forced command. The requested command
#                                               arrives in $env:SSH_ORIGINAL_COMMAND
#
# verbs: status get check on off set (same as the mac netcap-agent)
#
# The side being controlled decides what is allowed. For an Administrator key, one line in
# C:\ProgramData\ssh\administrators_authorized_keys limits what that key may ask for:
#
#   restrict,command="powershell -NoProfile -ExecutionPolicy Bypass -File C:\ProgramData\netcap\netcap-agent.ps1 --allow 'status get check'" ssh-ed25519 AAAA… netcap@laptop
#
# On Windows an Administrator's ssh session runs elevated. There is no second layer like sudoers on mac,
# so this is the only gate. That is why pinning it with a forced command matters even more than on mac.
$ErrorActionPreference = 'Stop'

$Dir = 'C:\ProgramData\netcap'
$Verbs = 'status', 'get', 'check', 'on', 'off', 'set'

function Deny([string]$m) {
  [Console]::Error.WriteLine("netcap-agent: $m")
  exit 77
}

$words = @($args)
$allowed = $Verbs
if ($words.Count -ge 1 -and $words[0] -eq '--allow') {
  if ($words.Count -ne 2) { Deny "usage: netcap-agent.ps1 --allow '<verb> …'" }
  $allowed = @($words[1] -split '\s+' | Where-Object { $_ })
  $orig = $env:SSH_ORIGINAL_COMMAND
  if (-not $orig) { Deny "call with a command (allowed verbs: $($allowed -join ' '))" }
  # The requested command is only split on whitespace. Quotes and expressions are not interpreted
  $words = @($orig -split '\s+' | Where-Object { $_ })
  # netcap sends "powershell … -File '…\netcap-agent.ps1' <verb> …" (the path is quoted, since it has
  # backslashes). Drop everything up to the agent
  for ($i = 0; $i -lt $words.Count; $i++) {
    if ($words[$i] -match "netcap-agent\.ps1'?$") { $words = @($words | Select-Object -Skip ($i + 1)); break }
  }
}

if ($words.Count -eq 0) { Deny "usage: netcap-agent.ps1 <verb> [args...] (verbs: $($Verbs -join ' '))" }
$verb = $words[0]
$rest = @($words | Select-Object -Skip 1)
if ($Verbs -notcontains $verb) { Deny "unknown verb: $verb" }
if ($allowed -notcontains $verb) { Deny "not allowed for this key: $verb (allowed: $($allowed -join ' '))" }

if ($verb -eq 'check') {
  # The measurement accepts only --bytes <number>
  if ($rest.Count -gt 0 -and ($rest.Count -ne 2 -or $rest[0] -ne '--bytes' -or $rest[1] -notmatch '^[0-9]+$')) {
    Deny 'check accepts only --bytes <number>'
  }
  & (Join-Path $Dir 'netcap-check.ps1') @rest
  exit $LASTEXITCODE
}

# Only on / set take numbers. The other verbs take no arguments
foreach ($a in $rest) { if ($a -notmatch '^[0-9]+([.][0-9]+)?$') { Deny "arguments must be numbers: $a" } }
& (Join-Path $Dir 'netshape.ps1') $verb @rest
exit $LASTEXITCODE
