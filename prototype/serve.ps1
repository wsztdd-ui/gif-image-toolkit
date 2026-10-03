$ErrorActionPreference = "Stop"
$root = $PSScriptRoot
$listener = New-Object System.Net.HttpListener
$listener.Prefixes.Add("http://127.0.0.1:8642/")
$listener.Start()
Write-Output "serving $root at http://127.0.0.1:8642/"
while ($listener.IsListening) {
  $ctx = $listener.GetContext()
  try {
    $path = $ctx.Request.Url.AbsolutePath
    if ($path -eq "/") { $path = "/prototype.html" }
    $file = Join-Path $root ($path -replace "/", "\")
    if ((Test-Path $file) -and -not (Get-Item $file).PSIsContainer) {
      $bytes = [System.IO.File]::ReadAllBytes($file)
      $ctx.Response.ContentType = "text/html; charset=utf-8"
      $ctx.Response.ContentLength64 = $bytes.Length
      $ctx.Response.OutputStream.Write($bytes, 0, $bytes.Length)
    } else {
      $ctx.Response.StatusCode = 404
    }
  } catch {
    try { $ctx.Response.StatusCode = 500 } catch {}
  }
  try { $ctx.Response.OutputStream.Close() } catch {}
}
