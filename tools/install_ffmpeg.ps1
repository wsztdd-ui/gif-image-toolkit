$ErrorActionPreference = "Stop"
$ProgressPreference = "SilentlyContinue"
$bin = Join-Path $PSScriptRoot "..\bin"
$base = "https://registry.npmmirror.com/-/binary/ffmpeg-static/b6.0"
$gz1 = "$env:TEMP\ff_win32_x64.gz"
$gz2 = "$env:TEMP\fp_win32_x64.gz"

Write-Output "downloading ffmpeg (npmmirror) ..."
Invoke-WebRequest -Uri "$base/ffmpeg-win32-x64.gz" -OutFile $gz1 -UseBasicParsing -TimeoutSec 900
Write-Output "downloading ffprobe (npmmirror) ..."
Invoke-WebRequest -Uri "$base/ffprobe-win32-x64.gz" -OutFile $gz2 -UseBasicParsing -TimeoutSec 900

foreach ($pair in @(@($gz1, "ffmpeg.exe"), @($gz2, "ffprobe.exe"))) {
  $dst = Join-Path $bin $pair[1]
  $inStream = [System.IO.File]::OpenRead($pair[0])
  $outStream = [System.IO.File]::Create($dst)
  $gzip = New-Object System.IO.Compression.GZipStream($inStream, [System.IO.Compression.CompressionMode]::Decompress)
  $gzip.CopyTo($outStream)
  $gzip.Dispose(); $outStream.Dispose(); $inStream.Dispose()
}

Write-Output "installed:"
& (Join-Path $bin "ffmpeg.exe") -version | Select-Object -First 1
& (Join-Path $bin "ffprobe.exe") -version | Select-Object -First 1
