$ErrorActionPreference = "Stop"
$ProgressPreference = "SilentlyContinue"
$inst = "$env:TEMP\python-3.12.8-amd64.exe"
$urls = @(
  'https://mirrors.huaweicloud.com/python/3.12.8/python-3.12.8-amd64.exe',
  'https://registry.npmmirror.com/-/binary/python/3.12.8/python-3.12.8-amd64.exe',
  'https://www.python.org/ftp/python/3.12.8/python-3.12.8-amd64.exe'
)
$ok = $false
foreach ($u in $urls) {
  try {
    Write-Output "trying $u"
    Invoke-WebRequest -Uri $u -OutFile $inst -UseBasicParsing -TimeoutSec 600
    if ((Get-Item $inst).Length -gt 20MB) { $ok = $true; break }
    Write-Output "too small, trying next mirror"
  } catch { Write-Output "failed: $($_.Exception.Message)" }
}
if (-not $ok) { Write-Output "DOWNLOAD FAILED"; exit 1 }
Write-Output "downloaded $((Get-Item $inst).Length) bytes"
Write-Output "installing (per-user, prepend path) ..."
Start-Process -FilePath $inst -ArgumentList '/quiet', 'InstallAllUsers=0', 'PrependPath=1', 'Include_test=0', 'Include_launcher=0' -Wait
Write-Output "install done"
$py = "$env:LOCALAPPDATA\Programs\Python\Python312\python.exe"
if (Test-Path $py) { & $py --version } else { Write-Output "WARN: python.exe not found at $py" }
