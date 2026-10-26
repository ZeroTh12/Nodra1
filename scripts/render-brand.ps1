# Render Nodra.svg to a 1024x1024 transparent PNG with headless Edge (no SVG toolchain
# needed on this machine). Output: .cache\nodra-render-1024.png
$ErrorActionPreference = "Stop"
Set-Location (Join-Path $PSScriptRoot "..")

$edge = @(
  "C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
  "C:\Program Files\Microsoft\Edge\Application\msedge.exe"
) | Where-Object { Test-Path $_ } | Select-Object -First 1
if (-not $edge) { throw "msedge.exe not found" }

$html = Join-Path $env:TEMP "nodra-render.html"
# windres taught this repo the lesson: non-ASCII paths break command-line tools. The SVG
# goes to an ASCII temp path so Edge's file:// URL needs no percent-encoding. The SVG is
# screenshotted as the top-level document (no wrapper HTML): it is a full-bleed tile, so
# whatever the browser background is, the rounded mask later clips the corners anyway.
$svgTmp = Join-Path $env:TEMP "nodra-brand.svg"
Copy-Item (Join-Path $PSScriptRoot "..\Nodra.svg") $svgTmp -Force

$out = Join-Path $PSScriptRoot "..\.cache\nodra-render-628.png"
$userData = Join-Path $env:TEMP "nodra-edge-profile"
# cmd /c keeps Edge's stderr noise out of PowerShell's error stream; poll for the file
# because the msedge launcher can return before the headless process finishes. The URL is
# built from the real $env:TEMP — a hardcoded path silently 404s when TEMP is redirected.
$url = "file:///" + ($svgTmp -replace '\\', '/')
cmd /c "`"$edge`" --headless=new --disable-gpu --no-first-run --no-default-browser-check --user-data-dir=`"$userData`" --window-size=628,628 --hide-scrollbars --default-background-color=00000000 --virtual-time-budget=8000 --screenshot=`"$out`" `"$url`" 2>nul"

for ($i = 0; $i -lt 40 -and -not (Test-Path $out); $i++) { Start-Sleep -Milliseconds 500 }
if (-not (Test-Path $out)) { throw "screenshot not written" }
# A failed load screenshots an error page; size alone can't tell it from the real tile
# (both ~22 KB compressed). The real tile is strongly coloured at its centre.
Add-Type -AssemblyName System.Drawing
$probe = [System.Drawing.Bitmap]::FromFile($out)
$c = $probe.GetPixel([int]($probe.Width / 2), [int]($probe.Height / 2))
$probe.Dispose()
if (($c.R -gt 235 -and $c.G -gt 235 -and $c.B -gt 235) -or ($c.R -lt 60 -and $c.G -lt 60 -and $c.B -lt 60)) {
  throw "screenshot centre pixel ($($c.R),$($c.G),$($c.B)) looks like an error page; SVG did not render"
}
$bmp = [System.Drawing.Image]::FromFile($out)
Write-Host "rendered: $($bmp.Width)x$($bmp.Height) centre=($($c.R),$($c.G),$($c.B)) -> $out"
$bmp.Dispose()
