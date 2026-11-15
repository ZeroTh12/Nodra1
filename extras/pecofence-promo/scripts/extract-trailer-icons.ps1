# Exports 256 px Windows shell icons (real alpha) and the shell's own thumbnails of the
# "* study.png" fixtures for the 2026-09 trailer (v3).
#
#   powershell.exe -NoProfile -ExecutionPolicy Bypass -File extras\pecofence-promo\scripts\extract-trailer-icons.ps1
#
# Uses IShellItemImageFactory::GetImage (SIIGBF_ICONONLY for type icons, SIIGBF_THUMBNAILONLY
# for thumbnails) on harmless dummy files in .cache\promo2\iconsrc (nothing is executed).
# The 32 bpp DIB is read top-down with GetDIBits (reading bmBits directly flips thumbnails).
# Its alpha form is detected per image: on this system the icon bitmaps are straight alpha
# (semi-transparent pixels carry colour above alpha) and are saved unchanged; a premultiplied
# bitmap would be un-premultiplied. Writes public\trailer-v3\icons\*.png, icons\zip-48.png and
# icons\icons-meta.json (per-type handler / default-icon info so brand logos can be flagged),
# plus 128/192 px matching templates in .cache\promo2\icon-templates for measure-trailer-targets.py.
$ErrorActionPreference = "Stop"
$workspace = (Resolve-Path (Join-Path $PSScriptRoot "..\..\..")).Path
$promo = Join-Path $workspace "extras\pecofence-promo"
$outDir = Join-Path $promo "public\trailer-v3\icons"
$srcDir = Join-Path $workspace ".cache\promo2\iconsrc"
$studies = Join-Path $workspace ".cache\store-v2\studies"
New-Item -ItemType Directory -Force -Path $outDir, $srcDir | Out-Null

Add-Type -ReferencedAssemblies System.Drawing @"
using System;
using System.Text;
using System.Runtime.InteropServices;
using System.Drawing;
using System.Drawing.Imaging;

public static class ShellImage {
    [ComImport, Guid("bcc18b79-ba16-442f-80c4-8a59c30c463b"), InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
    interface IShellItemImageFactory { [PreserveSig] int GetImage(SIZE size, int flags, out IntPtr phbm); }
    [StructLayout(LayoutKind.Sequential)] struct SIZE { public int cx; public int cy; }
    [StructLayout(LayoutKind.Sequential)] struct BITMAP { public int bmType, bmWidth, bmHeight, bmWidthBytes; public ushort bmPlanes, bmBitsPixel; public IntPtr bmBits; }
    [StructLayout(LayoutKind.Sequential)] struct BITMAPINFOHEADER { public uint biSize; public int biWidth, biHeight; public ushort biPlanes, biBitCount; public uint biCompression, biSizeImage; public int biXPelsPerMeter, biYPelsPerMeter; public uint biClrUsed, biClrImportant; }
    [StructLayout(LayoutKind.Sequential)] struct DIBSECTION { public BITMAP dsBm; public BITMAPINFOHEADER dsBmih; public uint f0, f1, f2; public IntPtr dshSection; public uint dsOffset; }

    [DllImport("shell32.dll", CharSet = CharSet.Unicode, PreserveSig = false)]
    static extern void SHCreateItemFromParsingName(string path, IntPtr pbc, [MarshalAs(UnmanagedType.LPStruct)] Guid riid, [MarshalAs(UnmanagedType.Interface)] out IShellItemImageFactory ppv);
    [StructLayout(LayoutKind.Sequential)] struct BITMAPINFO { public BITMAPINFOHEADER h; public uint c0, c1, c2, c3; }
    [DllImport("gdi32.dll")] static extern int GetDIBits(IntPtr hdc, IntPtr hbm, uint start, uint lines, [Out] byte[] bits, ref BITMAPINFO bi, uint usage);
    [DllImport("user32.dll")] static extern IntPtr GetDC(IntPtr h);
    [DllImport("user32.dll")] static extern int ReleaseDC(IntPtr h, IntPtr dc);
    [DllImport("gdi32.dll")] static extern bool DeleteObject(IntPtr h);
    [DllImport("gdi32.dll")] static extern int GetObject(IntPtr h, int c, ref DIBSECTION ds);
    [DllImport("shlwapi.dll", CharSet = CharSet.Unicode)] static extern int AssocQueryString(int flags, int str, string assoc, string extra, StringBuilder o, ref uint n);

    public static bool FlipVertical = false;   // set when the caller detects an inverted bitmap
    public static string RawDump = null;   // debug: write the untouched BGRA pixels here
    public static string Assoc(string ext, int what) {
        uint n = 1024; var sb = new StringBuilder(1024);
        int hr = AssocQueryString(0x40 /*ASSOCF_NOTRUNCATE*/, what, ext, null, sb, ref n);
        return hr == 0 ? sb.ToString() : "";
    }

    // Writes a straight-alpha PNG; returns "w,h,premultiplied,semiTransparentPx,colorAboveAlphaPx,noAlpha".
    // colorAboveAlphaPx > 0 proves the source was already straight alpha (premultiplied data never has
    // a colour channel above alpha); in that case pixels are copied unchanged.
    public static string Export(string path, int size, int flags, string outPng) {
        IShellItemImageFactory f;
        SHCreateItemFromParsingName(path, IntPtr.Zero, typeof(IShellItemImageFactory).GUID, out f);
        IntPtr hbm;
        var sz = new SIZE(); sz.cx = size; sz.cy = size;
        int hr = f.GetImage(sz, flags, out hbm);
        Marshal.ReleaseComObject(f);
        if (hr != 0) throw new Exception(String.Format("GetImage 0x{0:X8} for {1}", hr, path));
        try {
            var ds = new DIBSECTION();
            if (GetObject(hbm, Marshal.SizeOf(typeof(DIBSECTION)), ref ds) == 0 || ds.dsBm.bmBits == IntPtr.Zero)
                throw new Exception("not a DIB section");
            if (ds.dsBm.bmBitsPixel != 32) throw new Exception("expected 32 bpp, got " + ds.dsBm.bmBitsPixel);
            int w = ds.dsBm.bmWidth, h = ds.dsBm.bmHeight;
            // Let GDI convert to a top-down 32 bpp buffer (alpha byte is preserved for 32 -> 32).
            var bi = new BITMAPINFO();
            bi.h.biSize = 40; bi.h.biWidth = w; bi.h.biHeight = -h; bi.h.biPlanes = 1; bi.h.biBitCount = 32;
            var px = new byte[w * h * 4];
            IntPtr hdc = GetDC(IntPtr.Zero);
            int lines = GetDIBits(hdc, hbm, 0, (uint)h, px, ref bi, 0);
            ReleaseDC(IntPtr.Zero, hdc);
            if (lines != h) throw new Exception("GetDIBits returned " + lines);
            if (FlipVertical) {
                var t = new byte[px.Length];
                for (int y = 0; y < h; y++) Buffer.BlockCopy(px, (h - 1 - y) * w * 4, t, y * w * 4, w * 4);
                px = t;
            }
            if (RawDump != null) System.IO.File.WriteAllBytes(RawDump, px);
            int allZeroAlpha = 1, semi = 0, violations = 0;
            for (int i = 0; i < px.Length; i += 4) {
                byte a = px[i + 3];
                if (a != 0) allZeroAlpha = 0;
                if (a > 0 && a < 255) semi++;
                if (Math.Max(px[i], Math.Max(px[i + 1], px[i + 2])) > a) violations++;
            }
            bool premult = allZeroAlpha == 0 && violations == 0;
            for (int i = 0; i < px.Length; i += 4) {
                if (allZeroAlpha == 1) { px[i + 3] = 255; continue; }   // opaque bitmap without alpha
                int a = px[i + 3];
                if (premult) {
                    if (a == 0) { px[i] = px[i + 1] = px[i + 2] = 0; }
                    else if (a < 255) for (int c = 0; c < 3; c++) px[i + c] = (byte)Math.Min(255, (px[i + c] * 255 + a / 2) / a);
                }
            }
            using (var bmp = new Bitmap(w, h, PixelFormat.Format32bppArgb)) {
                var bd = bmp.LockBits(new Rectangle(0, 0, w, h), ImageLockMode.WriteOnly, PixelFormat.Format32bppArgb);
                for (int y = 0; y < h; y++) Marshal.Copy(px, y * w * 4, bd.Scan0 + y * bd.Stride, w * 4);
                bmp.UnlockBits(bd);
                bmp.Save(outPng, ImageFormat.Png);
            }
            return String.Format("{0},{1},{2},{3},{4},{5}", w, h, premult, semi, violations, allZeroAlpha == 1);
        } finally { DeleteObject(hbm); }
    }
}
"@

$ICONONLY = 0x4; $THUMBNAILONLY = 0x8
# name -> dummy source (created empty unless it already exists / is copied from the fixtures)
$types = [ordered]@{
    "folder"      = "Folder"
    "pdf"         = "Document.pdf"
    "txt"         = "Notes.txt"
    "md"          = "Checklist.md"
    "zip"         = "Assets.zip"
    "url"         = "Project links.url"
    "mp4"         = "Clip.mp4"
    "docx"        = "Letter.docx"
    "xlsx"        = "Budget.xlsx"
    "png-generic" = "Picture.png"
    "exe"         = "setup.exe"
}
function Parse([string]$r) {
    $p = $r.Split(",")
    return [ordered]@{ width = [int]$p[0]; height = [int]$p[1]; sourcePremultiplied = [bool]::Parse($p[2]); semiTransparentPx = [int]$p[3]; colorAboveAlphaPx = [int]$p[4]; opaqueNoAlpha = [bool]::Parse($p[5]) }
}
$meta = [ordered]@{ generatedAt = [DateTime]::UtcNow.ToString("o"); icons = [ordered]@{}; thumbs = [ordered]@{} }
foreach ($name in $types.Keys) {
    $src = Join-Path $srcDir $types[$name]
    if ($name -eq "folder") { New-Item -ItemType Directory -Force -Path $src | Out-Null }
    elseif ($name -eq "url") { Copy-Item -LiteralPath (Join-Path $studies "Project links.url") -Destination $src -Force }
    elseif (-not (Test-Path -LiteralPath $src)) { New-Item -ItemType File -Path $src | Out-Null }
    $out = Join-Path $outDir "$name.png"
    $r = [ShellImage]::Export($src, 256, $ICONONLY, $out)
    $ext = if ($name -eq "folder") { "Folder" } else { [IO.Path]::GetExtension($src) }
    $meta.icons[$name] = [ordered]@{ source = $src; bitmap = (Parse $r)
        friendlyApp = [ShellImage]::Assoc($ext, 4); defaultIcon = [ShellImage]::Assoc($ext, 15); progId = [ShellImage]::Assoc($ext, 20) }
    Write-Output "$name <- $($types[$name]): $r | $($meta.icons[$name].friendlyApp) | $($meta.icons[$name].defaultIcon)"
}
foreach ($p in Get-ChildItem -LiteralPath $studies -Filter "* study.png") {
    $slug = ($p.BaseName.ToLowerInvariant() -replace "[^a-z0-9]+", "-").Trim("-")
    $out = Join-Path $outDir "thumb-$slug.png"
    $r = [ShellImage]::Export($p.FullName, 256, $THUMBNAILONLY, $out)
    $meta.thumbs[$p.Name] = [ordered]@{ file = "thumb-$slug.png"; source = $p.FullName; bitmap = (Parse $r) }
    Write-Output "thumb $($p.Name): $r"
}
$meta | ConvertTo-Json -Depth 6 | Set-Content -LiteralPath (Join-Path $outDir "icons-meta.json") -Encoding utf8

# 7-Zip ships no icon above 48 px: at 256 the shell centres the 48 px glyph in a faint tile, while the
# fences draw the 48 px glyph at 2x inside that tile. Export the native 48 px glyph as well.
$r = [ShellImage]::Export((Join-Path $srcDir $types["zip"]), 48, $ICONONLY, (Join-Path $outDir "zip-48.png"))
Write-Output "zip-48: $r"

# Matching templates for measure-trailer-targets.py: the same shell images at the sizes the fences
# draw them (64 / 96 DIP at 200% = 128 / 192 px). Not deliverables; kept in .cache.
$tplDir = Join-Path $workspace ".cache\promo2\icon-templates"
New-Item -ItemType Directory -Force -Path $tplDir | Out-Null
foreach ($size in 128, 192) {
    foreach ($name in $types.Keys) {
        [ShellImage]::Export((Join-Path $srcDir $types[$name]), $size, $ICONONLY, (Join-Path $tplDir "$name-$size.png")) | Out-Null
    }
    Copy-Item -LiteralPath (Join-Path $outDir "zip-48.png") -Destination (Join-Path $tplDir "zip-48.png") -Force
    foreach ($p in Get-ChildItem -LiteralPath $studies -Filter "* study.png") {
        $slug = ($p.BaseName.ToLowerInvariant() -replace "[^a-z0-9]+", "-").Trim("-")
        $r = [ShellImage]::Export($p.FullName, $size, $THUMBNAILONLY, (Join-Path $tplDir "thumb-$slug-$size.png"))
        if ($size -eq 192 -and $slug -eq "atelier-study") { Write-Output "template thumb 192: $r" }
    }
}
