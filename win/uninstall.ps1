# uninstall.ps1 — removes netshape completely (also lifts the cap, and removes WinDivert if it was fetched). As Administrator:
#   powershell -NoProfile -ExecutionPolicy Bypass -File C:\ProgramData\netcap\uninstall.ps1
$ErrorActionPreference = 'Continue'
$Dir = 'C:\ProgramData\netcap'
if (Test-Path "$Dir\netshape.ps1") { & "$Dir\netshape.ps1" off }
# off stops the download shaper too. The WinDivert driver stays loaded until reboot: netcap never stops its service
# (basil00/WinDivert#406), and Windows removes the service at the next reboot
foreach ($t in 'expire', 'download', 'cleanup') {
  Stop-ScheduledTask -TaskPath '\netcap\' -TaskName $t -ErrorAction SilentlyContinue
  Unregister-ScheduledTask -TaskPath '\netcap\' -TaskName $t -Confirm:$false -ErrorAction SilentlyContinue
}
Get-NetQosPolicy -ErrorAction SilentlyContinue |
  Where-Object { $_.Name -like 'netcap-*' } |
  ForEach-Object { Remove-NetQosPolicy -Name $_.Name -Confirm:$false }
# Windows PowerShell 5.1's Remove-Item -Recurse may follow a link (junction or symlink) and delete what it points to.
# Remove each link itself first (Directory.Delete without recursion removes only the link), then the rest
function Remove-Links($path) {
  foreach ($i in @(Get-ChildItem -LiteralPath $path -Force -ErrorAction SilentlyContinue)) {
    if ($i.Attributes -band [IO.FileAttributes]::ReparsePoint) {
      if ($i.PSIsContainer) { [IO.Directory]::Delete($i.FullName) } else { [IO.File]::Delete($i.FullName) }
    } elseif ($i.PSIsContainer) { Remove-Links $i.FullName }
  }
}
# A loaded driver's file cannot be removed, and netcap never unloads WinDivert (basil00/WinDivert#406): its service is
# marked for deletion and goes at the next reboot. Whatever is left then goes at startup, by a one-time task
function Remove-NowOrAtStartup([string]$path) {
  Remove-Item -Recurse -Force -LiteralPath $path -ErrorAction SilentlyContinue
  if (-not (Test-Path -LiteralPath $path)) { return $false }
  $cmd = 'Remove-Item -Recurse -Force -LiteralPath ''{0}''; ' -f $path +
         'Unregister-ScheduledTask -TaskPath ''\netcap\'' -TaskName cleanup -Confirm:$false'
  $enc = [Convert]::ToBase64String([Text.Encoding]::Unicode.GetBytes($cmd))
  Register-ScheduledTask -TaskPath '\netcap\' -TaskName cleanup -Trigger (New-ScheduledTaskTrigger -AtStartup) -Force `
    -Action (New-ScheduledTaskAction -Execute 'powershell.exe' -Argument "-NoProfile -EncodedCommand $enc") `
    -Principal (New-ScheduledTaskPrincipal -UserId 'S-1-5-18' -LogonType ServiceAccount -RunLevel Highest) | Out-Null
  $true
}
if (Test-Path -LiteralPath $Dir) {
  if ((Get-Item -LiteralPath $Dir -Force).Attributes -band [IO.FileAttributes]::ReparsePoint) { [IO.Directory]::Delete($Dir) }
  else { Remove-Links $Dir; if (Remove-NowOrAtStartup $Dir) { "$Dir\windivert\WinDivert64.sys is the loaded driver's: it goes at the next startup" } }
}
'removed'
