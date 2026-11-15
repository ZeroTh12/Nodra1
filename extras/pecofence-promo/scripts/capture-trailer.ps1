param([string[]]$Scenes = @("overview","dark","auto","tabs","ai"))
# Records the native takes for the 2026-09 trailer (v3) from the isolated fixture build.
# A full-screen backdrop covers the display while each take runs; the previous
# foreground window and cursor position are restored afterwards.
$ErrorActionPreference = "Stop"
$workspace = (Resolve-Path (Join-Path $PSScriptRoot "..\..\..")).Path
$promo = Join-Path $workspace "extras\pecofence-promo"
$fixtureRoot = Join-Path $promo ".capture\reviewed\trailer-v3"
$rawRoot = Join-Path $promo ".capture\trailer-v3-raw"
$assetRoot = Join-Path $workspace ".cache\store-v2"
New-Item -ItemType Directory -Force -Path $rawRoot | Out-Null
Add-Type -AssemblyName System.Windows.Forms
Add-Type -AssemblyName System.Drawing
Add-Type @"
using System;
using System.Text;
using System.Collections.Generic;
using System.Runtime.InteropServices;
public static class TrailerCapture {
 public delegate bool EnumProc(IntPtr h,IntPtr l);
 public struct Point { public int X,Y; }
 [DllImport("user32.dll")] public static extern bool SetProcessDpiAwarenessContext(IntPtr p);
 [DllImport("user32.dll")] public static extern uint GetDpiForSystem();
 [DllImport("user32.dll")] public static extern bool EnumWindows(EnumProc p,IntPtr l);
 [DllImport("user32.dll")] public static extern uint GetWindowThreadProcessId(IntPtr h,out uint p);
 [DllImport("user32.dll",CharSet=CharSet.Unicode)] public static extern int GetWindowText(IntPtr h,StringBuilder s,int n);
 [DllImport("user32.dll",CharSet=CharSet.Unicode)] public static extern int GetClassName(IntPtr h,StringBuilder s,int n);
 [DllImport("user32.dll")] public static extern bool SetWindowPos(IntPtr h,IntPtr a,int x,int y,int w,int t,uint f);
 [DllImport("user32.dll")] public static extern bool ShowWindow(IntPtr h,int n);
 [DllImport("user32.dll")] public static extern IntPtr GetForegroundWindow();
 [DllImport("user32.dll")] public static extern bool SetForegroundWindow(IntPtr h);
 [DllImport("user32.dll")] public static extern bool PostMessage(IntPtr h,uint m,IntPtr w,IntPtr l);
 [DllImport("user32.dll")] public static extern bool GetCursorPos(out Point p);
 [DllImport("user32.dll")] public static extern bool SetCursorPos(int x,int y);
 public static string Title(IntPtr h) { var s=new StringBuilder(300);GetWindowText(h,s,300);return s.ToString(); }
 public static string Class(IntPtr h) { var s=new StringBuilder(150);GetClassName(h,s,150);return s.ToString(); }
 public static List<IntPtr> Windows(uint pid) { var r=new List<IntPtr>();EnumWindows((h,l)=>{uint p;GetWindowThreadProcessId(h,out p);if(p==pid)r.Add(h);return true;},IntPtr.Zero);return r; }
}
"@
[TrailerCapture]::SetProcessDpiAwarenessContext([IntPtr](-4)) | Out-Null
$screen = [Windows.Forms.Screen]::PrimaryScreen.Bounds
$work = [Windows.Forms.Screen]::PrimaryScreen.WorkingArea
$scale = [TrailerCapture]::GetDpiForSystem() / 96.0
$plateW = 2560; $plateH = 1440
if ($screen.Width -ne 3840 -or $screen.Height -ne 2160) { throw "Trailer capture expects a 3840x2160 display; found $screen" }
$plateX = [int](($screen.Width-$plateW)/2); $plateY = [int](($screen.Height-$plateH)/2)
$buildRoot = Join-Path $promo ".capture\reviewed-build\target-v4\debug"
$binary = Join-Path $buildRoot "pecofence.exe"
$cli = Join-Path $buildRoot "pecofence-cli.exe"
$hash = (Get-FileHash -LiteralPath $binary -Algorithm SHA256).Hash.ToLowerInvariant()
$previous = [TrailerCapture]::GetForegroundWindow()
$cursor = New-Object TrailerCapture+Point
[TrailerCapture]::GetCursorPos([ref]$cursor) | Out-Null
$saved = @{instance=$env:PECOFENCE_INSTANCE; test=$env:PECOFENCE_UI_TEST_WINDOWS; fixture=$env:PECOFENCE_DEMO_DESKTOP; local=$env:LOCALAPPDATA}
$manifest = [Collections.Generic.List[object]]::new()

function Start-Recorder([string]$Path) {
    $info = [Diagnostics.ProcessStartInfo]::new("ffmpeg")
    $info.Arguments = "-hide_banner -loglevel error -y -filter_complex ddagrab=output_idx=0:framerate=60:draw_mouse=0 -c:v hevc_nvenc -preset p1 -rc constqp -qp 12 -g 60 `"$Path`""
    $info.UseShellExecute = $false
    $info.RedirectStandardInput = $true
    $info.CreateNoWindow = $true
    return [Diagnostics.Process]::Start($info)
}

try {
 [TrailerCapture]::SetCursorPos($screen.Width - 4, $screen.Height - 4) | Out-Null
 $Scenes = @($Scenes | ForEach-Object { $_ -split "," } | Where-Object { $_ })
 foreach ($scene in $Scenes) {
    if (-not (Test-Path -LiteralPath (Join-Path $fixtureRoot $scene))) { throw "Unknown scene" }
    $caseDir = Join-Path $fixtureRoot $scene
    $appDir = Join-Path $caseDir "app"
    $fixture = Join-Path $caseDir "desktop-fixture"
    $configPath = Join-Path $appDir "config\config.json"
    Copy-Item -LiteralPath (Join-Path $caseDir "config.final.json") -Destination $configPath -Force
    Copy-Item -LiteralPath $binary -Destination (Join-Path $appDir "pecofence.exe")
    Copy-Item -LiteralPath (Join-Path $workspace "target\release\WebView2Loader.dll") -Destination (Join-Path $appDir "WebView2Loader.dll")
    $wallpaper = Join-Path $assetRoot $(if($scene -eq "dark"){"paper-dark.png"}else{"paper-light.png"})
    $back = [Windows.Forms.Form]::new()
    $back.FormBorderStyle="None"; $back.StartPosition="Manual"; $back.ShowInTaskbar=$false
    $back.Bounds=$screen; $back.Text="PecoFence trailer isolated backdrop"
    $back.BackgroundImage=[Drawing.Image]::FromFile($wallpaper); $back.BackgroundImageLayout="Stretch"
    $app=$null; $recorder=$null; $done=@{}; $shown=@{}
    $stepsPath = Join-Path $caseDir "cli-steps.json"
    $cliSteps = @(); if (Test-Path -LiteralPath $stepsPath) { $cliSteps = @((Get-Content -LiteralPath $stepsPath -Raw | ConvertFrom-Json) | ForEach-Object { $_ }) }
    $events=[Collections.Generic.List[object]]::new()
    $clock=[Diagnostics.Stopwatch]::new()
    function Mark([string]$What) { $events.Add(@{t=[Math]::Round($clock.Elapsed.TotalSeconds,3);what=$What}) }
    function Invoke-Cli([string]$Name,[string[]]$CliArgs) {
        $out = Join-Path $rawRoot "$scene-$Name.json"
        Mark "cli:$Name"
        Start-Process -FilePath $cli -ArgumentList $CliArgs -RedirectStandardOutput $out -RedirectStandardError (Join-Path $rawRoot "$scene-$Name.err") -WindowStyle Hidden | Out-Null
    }
    try {
        $back.Show()
        [TrailerCapture]::SetWindowPos($back.Handle,[IntPtr](-1),0,0,0,0,0x13) | Out-Null
        [Windows.Forms.Application]::DoEvents()
        Start-Sleep -Milliseconds 300
        $clock.Start()
        $recorder = Start-Recorder (Join-Path $rawRoot "$scene.mkv")
        Start-Sleep -Milliseconds 700
        $env:PECOFENCE_INSTANCE="trailer-$scene"
        $env:PECOFENCE_UI_TEST_WINDOWS="1"
        $env:PECOFENCE_DEMO_DESKTOP=$fixture
        $env:LOCALAPPDATA=Join-Path $caseDir "appdata"
        New-Item -ItemType Directory -Force -Path $env:LOCALAPPDATA | Out-Null
        $args=@("--portable","--no-hide-icons","--wallpaper",('"' + $wallpaper + '"'),"--test-script",('"' + (Join-Path $caseDir "commands.txt") + '"'),"--exit-after","26000")
        Mark "app-start"
        $app=Start-Process -FilePath (Join-Path $appDir "pecofence.exe") -ArgumentList $args -WindowStyle Hidden -PassThru
        $timer=[Diagnostics.Stopwatch]::StartNew()
        while (-not $app.HasExited -and $timer.Elapsed.TotalSeconds -lt 24) {
            [Windows.Forms.Application]::DoEvents()
            foreach ($window in [TrailerCapture]::Windows([uint32]$app.Id)) {
                $title=[TrailerCapture]::Title($window)
                if ($title -eq "Capture inbox") { [TrailerCapture]::ShowWindow($window,0)|Out-Null;continue }
                if ([TrailerCapture]::Class($window) -eq "PecoFence.Fence") {
                    if (-not $shown[$window.ToInt64()] -and $timer.Elapsed.TotalSeconds -gt 1.8) {
                        [TrailerCapture]::ShowWindow($window,4)|Out-Null
                        $shown[$window.ToInt64()]=$true
                        Mark "show:$title"
                    }
                    [TrailerCapture]::SetWindowPos($window,[IntPtr](-1),0,0,0,0,0x13)|Out-Null
                    if ($timer.Elapsed.TotalSeconds -gt 3.0 -and -not $done["leave$($window.ToInt64())"]) {
                        [TrailerCapture]::PostMessage($window,0x2A3,[IntPtr]::Zero,[IntPtr]::Zero)|Out-Null
                        $done["leave$($window.ToInt64())"]=$true
                    }
                }
            }
            $t=$timer.Elapsed.TotalSeconds
            if ($scene -eq "auto") {
                $times=@(5.0,6.2,7.4,8.6)
                $names=@("Form study.png","Launch checklist.md","Sol study.png","Q3 report.pdf")
                for ($i=0; $i -lt 4; $i++) {
                    if ($t -gt $times[$i] -and -not $done["in$i"]) {
                        $done["in$i"]=$true
                        Copy-Item -LiteralPath (Join-Path $caseDir "incoming-$($names[$i])") -Destination (Join-Path $fixture $names[$i])
                        Mark "arrive:$($names[$i])"
                    }
                }
            }
            foreach ($s in $cliSteps) {
                if ($t -gt $s.t -and -not $done[$s.n]) {
                    $done[$s.n]=$true
                    $stepArgs = @($s.a | ForEach-Object { $_.Replace("{plateX}", "$plateX").Replace("{plateY}", "$plateY") })
                    Invoke-Cli $s.n $stepArgs
                }
            }
            Start-Sleep -Milliseconds 30
        }
        if (-not $app.HasExited) { $app.WaitForExit(6000)|Out-Null }
        Mark "app-exit"
        Start-Sleep -Milliseconds 500
        $recorder.StandardInput.Write("q"); $recorder.StandardInput.Close()
        if (-not $recorder.WaitForExit(15000)) { $recorder.Kill() }
        Copy-Item -LiteralPath $configPath -Destination (Join-Path $rawRoot "$scene-state.json")
        $events | ConvertTo-Json -Depth 4 | Set-Content -LiteralPath (Join-Path $rawRoot "$scene-events.json") -Encoding utf8
        $manifest.Add(@{scene=$scene;capturedAt=[DateTime]::UtcNow.ToString("o");sourceBinarySha256=$hash;dpi=[int]($scale*96);plate=@($plateX,$plateY,$plateW,$plateH);exitCode=$app.ExitCode;fixtureOnly=$true})
        Write-Output "Captured $scene; exit=$($app.ExitCode)"
    } finally {
        if ($app -and -not $app.HasExited) { $app.WaitForExit(5000)|Out-Null; if (-not $app.HasExited) { $app.Kill() } }
        if ($recorder -and -not $recorder.HasExited) { try { $recorder.StandardInput.Write("q") } catch {}; $recorder.WaitForExit(8000)|Out-Null }
        $back.Close();$back.BackgroundImage.Dispose();$back.Dispose()
    }
 }
} finally {
    $env:PECOFENCE_INSTANCE=$saved.instance;$env:PECOFENCE_UI_TEST_WINDOWS=$saved.test
    $env:PECOFENCE_DEMO_DESKTOP=$saved.fixture;$env:LOCALAPPDATA=$saved.local
    [TrailerCapture]::SetCursorPos($cursor.X, $cursor.Y) | Out-Null
    [TrailerCapture]::SetForegroundWindow($previous)|Out-Null
    $manifest|ConvertTo-Json -Depth 8|Set-Content -LiteralPath (Join-Path $rawRoot "capture-manifest.json") -Encoding utf8
}
