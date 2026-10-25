# Resize the source PNG to every ICO size with high-quality interpolation.
param(
  [Parameter(Mandatory = $true)][string]$Source,
  [Parameter(Mandatory = $true)][string]$OutDir
)
Add-Type -AssemblyName System.Drawing

$src = [System.Drawing.Image]::FromFile($Source)
Write-Host "source: $($src.Width)x$src.Height, pixel format $($src.PixelFormat)"
New-Item -ItemType Directory -Force -Path $OutDir | Out-Null

foreach ($size in @(16, 24, 32, 48, 64, 128, 256)) {
  $bmp = New-Object System.Drawing.Bitmap $size, $size
  $g = [System.Drawing.Graphics]::FromImage($bmp)
  $g.InterpolationMode = [System.Drawing.Drawing2D.InterpolationMode]::HighQualityBicubic
  $g.PixelOffsetMode = [System.Drawing.Drawing2D.PixelOffsetMode]::HighQuality
  $g.SmoothingMode = [System.Drawing.Drawing2D.SmoothingMode]::HighQuality
  $g.DrawImage($src, 0, 0, $size, $size)
  $g.Dispose()
  $bmp.Save((Join-Path $OutDir "icon-$size.png"), [System.Drawing.Imaging.ImageFormat]::Png)
  $bmp.Dispose()
  Write-Host "wrote icon-$size.png"
}
$src.Dispose()
