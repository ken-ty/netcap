# uninstall.ps1 — removes netshape completely (also lifts the cap). As Administrator:
#   powershell -NoProfile -ExecutionPolicy Bypass -File C:\ProgramData\netcap\uninstall.ps1
$ErrorActionPreference = 'Continue'
$Dir = 'C:\ProgramData\netcap'
if (Test-Path "$Dir\netshape.ps1") { & "$Dir\netshape.ps1" off }
Unregister-ScheduledTask -TaskPath '\netcap\' -TaskName expire -Confirm:$false -ErrorAction SilentlyContinue
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
if (Test-Path -LiteralPath $Dir) {
  if ((Get-Item -LiteralPath $Dir -Force).Attributes -band [IO.FileAttributes]::ReparsePoint) { [IO.Directory]::Delete($Dir) }
  else { Remove-Links $Dir; Remove-Item -Recurse -Force -LiteralPath $Dir -ErrorAction SilentlyContinue }
}
'removed'
