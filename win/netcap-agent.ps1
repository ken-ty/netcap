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
# netcap install writes the CLI's version here, so get can report which agent is installed
$Version = '@VERSION@'
if ($Version.StartsWith('@')) { $Version = 'unknown' }

function Deny([string]$m) {
  [Console]::Error.WriteLine("netcap-agent: $m")
  exit 77
}

$words = @($args)
$allowed = $Verbs
if ($words.Count -ge 1 -and $words[0] -eq '--allow') {
  if ($words.Count -lt 2) { Deny "usage: netcap-agent.ps1 --allow '<verb> …'" }
  # sshd runs this line through its default shell. PowerShell passes '<verb> …' as one word, but cmd.exe (the default
  # unless DefaultShell is set) does not group '…', so the verbs arrive as several words with the quotes on them (#57)
  $allowed = @((($words | Select-Object -Skip 1) -join ' ') -split '\s+' |
               ForEach-Object { $_.Trim("'", '"') } | Where-Object { $_ })
  $orig = $env:SSH_ORIGINAL_COMMAND
  if (-not $orig) { Deny "call with a command (allowed verbs: $($allowed -join ' '))" }
  # The requested command is only split on whitespace. Quotes and expressions are not interpreted
  $words = @($orig -split '\s+' | Where-Object { $_ })
  # netcap sends "powershell … -File …\netcap-agent.ps1 <verb> …". Drop everything up to the agent
  for ($i = 0; $i -lt $words.Count; $i++) {
    # netcap quotes the path ('C:\…\netcap-agent.ps1'), so compare without the quotes
    if ($words[$i].Trim("'", '"') -match 'netcap-agent\.ps1$') { $words = @($words | Select-Object -Skip ($i + 1)); break }
  }
}

if ($words.Count -eq 0) { Deny "usage: netcap-agent.ps1 <verb> [args...] (verbs: $($Verbs -join ' '))" }
$verb = $words[0]
$rest = @($words | Select-Object -Skip 1)
if ($Verbs -notcontains $verb) { Deny "unknown verb: $verb" }
if ($allowed -notcontains $verb) { Deny "not allowed for this key: $verb (allowed: $($allowed -join ' '))" }

if ($verb -eq 'check') {
  # The measurement accepts only --bytes <number>, from 1 to 100 MB: even a read-only key could otherwise make the
  # device transfer as much as it asks (#91). At most 9 digits, so [int] cannot overflow
  if ($rest.Count -gt 0 -and ($rest.Count -ne 2 -or $rest[0] -ne '--bytes' -or $rest[1] -notmatch '^[0-9]{1,9}$' -or
                              [int]$rest[1] -lt 1 -or [int]$rest[1] -gt 100000000)) {
    Deny 'check accepts only --bytes <number>, 1 to 100000000'
  }
  & (Join-Path $Dir 'netcap-check.ps1') @rest
  exit $LASTEXITCODE
}

# on may end with --for <seconds>. Take it off before the numbers are checked, and pass it on as is
$forArgs = @()
if ($verb -eq 'on' -and $rest.Count -ge 2 -and $rest[-2] -eq '--for') {
  if ($rest[-1] -notmatch '^[1-9][0-9]{0,7}$') { Deny "--for takes seconds: $($rest[-1])" }
  $forArgs = @('--for', $rest[-1])
  $rest = @($rest | Select-Object -First ($rest.Count - 2))
}
# Only on / set take numbers. The other verbs take no arguments
foreach ($a in $rest) {
  if ($a -notmatch '^[0-9]+([.][0-9]+)?$') { Deny "arguments must be numbers: $a" }
  # 0 is refused on every OS, as the CLI does
  if ($a -notmatch '[1-9]') { Deny "arguments must be greater than 0: $a" }
}
if ($verb -eq 'get') {
  # Add the agent's version to the key=value line
  $out = @(& (Join-Path $Dir 'netshape.ps1') get)
  $rc = $LASTEXITCODE
  if ($out.Count -gt 0) { $out[0] = "$($out[0]) agent=$Version" }
  $out
  exit $(if ($null -eq $rc) { 0 } else { $rc })
}
& (Join-Path $Dir 'netshape.ps1') $verb @rest @forArgs
exit $LASTEXITCODE
