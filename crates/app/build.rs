// Embeds the application icon and a VERSIONINFO resource into the executable.
//
// No build-time crate dependencies: a small `.rc` is written to `OUT_DIR`, compiled with the
// Windows SDK's `rc.exe` (MSVC target) or MinGW's `windres` (GNU target) and handed to the
// linker. If neither can be found the build still succeeds, without an icon (a
// `cargo:warning` says so). `PECOFENCE_RC` / `PECOFENCE_WINDRES` override the paths.
//
// `crates/watchdog/build.rs` includes this file so both executables carry the same icon.

use std::env;
use std::path::{Path, PathBuf};
use std::process::Command;

fn main() {
    let manifest_dir = PathBuf::from(env::var("CARGO_MANIFEST_DIR").unwrap());
    let out_dir = PathBuf::from(env::var("OUT_DIR").unwrap());
    // Shared icon; the path is the same relative to either crate directory.
    let ico = manifest_dir
        .join("..")
        .join("app")
        .join("assets")
        .join("pecofence.ico");
    let ico = ico.canonicalize().unwrap_or(ico);
    // Forward slashes suit both rc.exe and windres; the verbatim `\\?\` prefix suits neither.
    let ico_slash = ico
        .display()
        .to_string()
        .trim_start_matches(r"\\?\")
        .replace('\\', "/");

    println!("cargo:rerun-if-changed=build.rs");
    println!("cargo:rerun-if-changed=../app/build.rs");
    println!("cargo:rerun-if-changed={}", ico.display());
    println!("cargo:rerun-if-env-changed=PECOFENCE_RC");
    println!("cargo:rerun-if-env-changed=PECOFENCE_WINDRES");

    if env::var("CARGO_CFG_TARGET_OS").as_deref() != Ok("windows") {
        return;
    }
    match env::var("CARGO_CFG_TARGET_ENV").as_deref() {
        Ok("gnu") => gnu_embed(&out_dir, &ico_slash),
        _ => msvc_embed(&out_dir, &ico_slash),
    }
}

/// The GNU toolchain: `windres` compiles the same resource script (icon, and for the app the
/// manifest as `RT_MANIFEST`) into a COFF object the linker embeds. The MSVC-only DELAYLOAD
/// optimisations are skipped; the DLLs load at startup instead. `windres` reads the `.rc` as
/// ANSI bytes, so a path with non-ASCII characters becomes garbage ("Invalid argument"); the
/// inputs are therefore copied beside it and addressed by bare ASCII names with the working
/// directory set to `OUT_DIR`.
fn gnu_embed(out_dir: &Path, ico: &str) {
    let Some(windres) = find_windres() else {
        println!("cargo:warning=windres not found (MinGW); building without an embedded icon");
        return;
    };
    let package = env::var("CARGO_PKG_NAME").unwrap_or_default();
    let ico_copy = out_dir.join("pecofence.ico");
    if std::fs::copy(ico, &ico_copy).is_err() {
        println!("cargo:warning=could not copy the icon beside windres; building without an embedded icon");
        return;
    }
    let manifest = out_dir.join("pecofence.manifest");
    std::fs::write(&manifest, SEGMENT_HEAP_MANIFEST).expect("write manifest");
    let rc_path = out_dir.join("pecofence.rc");
    let with_manifest = package == "pecofence";
    std::fs::write(&rc_path, rc_source("pecofence.ico", with_manifest.then_some("pecofence.manifest")))
        .expect("write .rc");
    let obj_path = out_dir.join("pecofence.res.o");
    let status = Command::new(&windres)
        .current_dir(out_dir)
        .arg("-i")
        .arg("pecofence.rc")
        .arg("-O")
        .arg("coff")
        .arg("-o")
        .arg("pecofence.res.o")
        .status();
    match status {
        Ok(s) if s.success() => {
            println!("cargo:rustc-link-arg-bins={}", obj_path.display());
        }
        Ok(s) => println!(
            "cargo:warning={} failed ({s}); building without an embedded icon",
            windres.display()
        ),
        Err(e) => println!(
            "cargo:warning=could not run {}: {e}; building without an embedded icon",
            windres.display()
        ),
    }
}

/// `PECOFENCE_WINDRES`, else `windres` on PATH.
fn find_windres() -> Option<PathBuf> {
    if let Some(p) = env::var("PECOFENCE_WINDRES").ok().filter(|p| !p.is_empty()) {
        let p = PathBuf::from(p);
        return p.is_file().then_some(p);
    }
    Command::new("windres")
        .arg("--version")
        .output()
        .is_ok()
        .then(|| PathBuf::from("windres"))
}

/// The MSVC toolchain: the original path — `rc.exe`, DELAYLOAD link options and the linker's
/// manifest embed.
fn msvc_embed(out_dir: &Path, ico: &str) {
    link_options(out_dir);
    let Some(rc) = find_rc() else {
        println!("cargo:warning=rc.exe not found (Windows SDK); building without an embedded icon");
        return;
    };

    let rc_path = out_dir.join("pecofence.rc");
    std::fs::write(&rc_path, rc_source(ico, None)).expect("write .rc");
    let res_path = out_dir.join("pecofence.res");
    // /nologo, /fo output; no /i needed because the script includes no headers.
    let status = Command::new(&rc)
        .arg("/nologo")
        .arg("/fo")
        .arg(&res_path)
        .arg(&rc_path)
        .status();
    match status {
        Ok(s) if s.success() => {
            println!("cargo:rustc-link-arg-bins={}", res_path.display());
        }
        Ok(s) => println!(
            "cargo:warning={} failed ({s}); building without an embedded icon",
            rc.display()
        ),
        Err(e) => println!(
            "cargo:warning=could not run {}: {e}; building without an embedded icon",
            rc.display()
        ),
    }
}

/// Memory: DLLs a process needs only now and then are delay-loaded (WinHTTP for the update
/// check; user32 and shell32 in the watchdog, which needs them once the app has exited), and
/// the app runs on the segment heap, which packaged (Store) apps get by default. The manifest
/// holds nothing else, so DPI awareness, common controls and OS compatibility are unchanged.
fn link_options(out_dir: &Path) {
    let package = env::var("CARGO_PKG_NAME").unwrap_or_default();
    let delayed: &[&str] = match package.as_str() {
        "pecofence" => &["winhttp.dll"],
        "pecofence-watchdog" => &["user32.dll", "shell32.dll"],
        _ => &[],
    };
    for dll in delayed {
        println!("cargo:rustc-link-arg-bins=/DELAYLOAD:{dll}");
    }
    if !delayed.is_empty() {
        println!("cargo:rustc-link-arg-bins=delayimp.lib");
    }
    if package == "pecofence" {
        let manifest = out_dir.join("pecofence.manifest");
        std::fs::write(&manifest, SEGMENT_HEAP_MANIFEST).expect("write manifest");
        println!("cargo:rustc-link-arg-bins=/MANIFEST:EMBED");
        println!(
            "cargo:rustc-link-arg-bins=/MANIFESTINPUT:{}",
            manifest.display()
        );
    }
}

const SEGMENT_HEAP_MANIFEST: &str = r#"<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<assembly xmlns="urn:schemas-microsoft-com:asm.v1" manifestVersion="1.0" xmlns:asmv3="urn:schemas-microsoft-com:asm.v3">
  <asmv3:application>
    <asmv3:windowsSettings xmlns="http://schemas.microsoft.com/SMI/2020/WindowsSettings">
      <heapType>SegmentHeap</heapType>
    </asmv3:windowsSettings>
  </asmv3:application>
</assembly>
"#;

/// The resource script: icon 1, an optional `RT_MANIFEST` (id 1, type 24) and a VERSIONINFO
/// block derived from the Cargo manifest. `ico` uses forward slashes (both rc.exe and windres
/// accept them); `manifest` is the same, embedded only by the GNU path (the MSVC path uses
/// the linker's `/MANIFEST:EMBED` instead).
fn rc_source(ico: &str, manifest: Option<&str>) -> String {
    let ver = |k: &str| env::var(format!("CARGO_PKG_VERSION_{k}")).unwrap_or_else(|_| "0".into());
    let (major, minor, patch) = (ver("MAJOR"), ver("MINOR"), ver("PATCH"));
    let version = env::var("CARGO_PKG_VERSION").unwrap_or_default();
    let name = env::var("CARGO_PKG_NAME").unwrap_or_default();
    let description = env::var("CARGO_PKG_DESCRIPTION").unwrap_or_default();
    let description = if description.is_empty() {
        name.clone()
    } else {
        description
    };
    // rc string literals: quotes must be doubled.
    let esc = |s: &str| s.replace('"', "\"\"");
    let ico = esc(ico);
    let manifest_line = manifest
        .map(|m| format!("\n1 24 \"{}\"", esc(m)))
        .unwrap_or_default();
    format!(
        r#"1 ICON "{ico}"{manifest_line}

1 VERSIONINFO
FILEVERSION {major},{minor},{patch},0
PRODUCTVERSION {major},{minor},{patch},0
FILEOS 0x40004L
FILETYPE 0x1L
BEGIN
  BLOCK "StringFileInfo"
  BEGIN
    BLOCK "040904b0"
    BEGIN
      VALUE "CompanyName", "Dayuan Jiang"
      VALUE "FileDescription", "{description}"
      VALUE "FileVersion", "{version}"
      VALUE "InternalName", "{name}"
      VALUE "LegalCopyright", "Copyright (c) Dayuan Jiang. Licensed under the Apache License 2.0."
      VALUE "OriginalFilename", "{name}.exe"
      VALUE "ProductName", "PecoFence"
      VALUE "ProductVersion", "{version}"
    END
  END
  BLOCK "VarFileInfo"
  BEGIN
    VALUE "Translation", 0x409, 1200
  END
END
"#,
        description = esc(&description),
        name = esc(&name),
        version = esc(&version),
    )
}

/// `PECOFENCE_RC`, else the newest `rc.exe` under the Windows 10/11 SDK, else `rc.exe` on PATH.
fn find_rc() -> Option<PathBuf> {
    if let Some(p) = env::var("PECOFENCE_RC").ok().filter(|p| !p.is_empty()) {
        let p = PathBuf::from(p);
        return p.is_file().then_some(p);
    }
    let kits = env::var("ProgramFiles(x86)")
        .map(PathBuf::from)
        .unwrap_or_else(|_| PathBuf::from(r"C:\Program Files (x86)"))
        .join(r"Windows Kits\10\bin");
    let mut best: Option<(Vec<u32>, PathBuf)> = None;
    if let Ok(entries) = std::fs::read_dir(&kits) {
        for entry in entries.flatten() {
            let name = entry.file_name();
            let Some(name) = name.to_str() else { continue };
            if !name.starts_with("10.") {
                continue;
            }
            let key: Vec<u32> = name.split('.').map(|p| p.parse().unwrap_or(0)).collect();
            let candidate = entry.path().join("x64").join("rc.exe");
            if candidate.is_file() && best.as_ref().is_none_or(|(k, _)| key > *k) {
                best = Some((key, candidate));
            }
        }
    }
    if let Some((_, path)) = best {
        return Some(path);
    }
    // Fall back to PATH (e.g. inside a Developer Command Prompt).
    Command::new("rc.exe")
        .arg("/?")
        .output()
        .is_ok()
        .then(|| PathBuf::from("rc.exe"))
}
