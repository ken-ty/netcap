# uninstall.ps1 — removes netshape completely (also lifts the cap). As Administrator:
#   powershell -NoProfile -ExecutionPolicy Bypass -File C:\ProgramData\netcap\uninstall.ps1
$ErrorActionPreference = 'Continue'
$Dir = 'C:\ProgramData\netcap'
if (Test-Path "$Dir\netshape.ps1") { & "$Dir\netshape.ps1" off }
Get-NetQosPolicy -ErrorAction SilentlyContinue |
  Where-Object { $_.Name -like 'netcap-*' } |
  ForEach-Object { Remove-NetQosPolicy -Name $_.Name -Confirm:$false }
Remove-Item -Recurse -Force $Dir -ErrorAction SilentlyContinue
'removed'
