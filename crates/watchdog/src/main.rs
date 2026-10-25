//! pecofence-watchdog: keeps an eye on the main process.
//!
//! 1. While it runs: each wait slice ends with a ping (`SendMessageTimeout(WM_NULL,
//!    SMTO_ABORTIFHUNG)`) to one of its windows. Two consecutive unanswered pings mean the UI
//!    thread is stuck — the freeze Windows reports as "not responding" — and the process is
//!    terminated as if it had hung.
//! 2. When it exits (on its own or terminated above): if it died without restoring the
//!    desktop icons (marker file still present), the "show desktop icons" toggle is sent and,
//!    unless Windows is shutting down or the instance had barely started (a crash loop), the
//!    app is started again: a hang costs a few seconds, not the fences until the next manual
//!    start. A clean quit (marker gone) changes nothing.
//!
//! Usage: `pecofence-watchdog <parent-pid> <marker-path>`

#![windows_subsystem = "windows"]

use pecofence_platform::{desktop, process, shell_icons, sysparams, window};
use std::path::{Path, PathBuf};
use std::time::{Duration, Instant};

/// One watchdog cycle: how long to wait on the process between pings.
const WAIT_SLICE: Duration = Duration::from_secs(20);
/// How long a ping may take before it counts as unanswered.
const PING_TIMEOUT_MS: u32 = 10_000;
/// Unanswered pings before the process is considered hung.
const PING_MISSES: u32 = 2;
/// An instance that dies within this of the watchdog's start is a crash loop, not restarted.
const MIN_LIFETIME: Duration = Duration::from_secs(30);

/// A top-level window of `pid`: any of them answers for the app's single UI thread.
fn window_of(pid: u32) -> Option<pecofence_platform::HWND> {
    desktop::top_level_windows()
        .into_iter()
        .find(|&hwnd| desktop::window_pid(hwnd) == pid)
}

/// True when the process answers a ping. No window at all (quick hide keeps only hidden
/// windows; a fresh start may have none yet) is not a hang: the probe passes.
fn answers_ping(pid: u32) -> bool {
    match window_of(pid) {
        Some(hwnd) => window::responds(hwnd, PING_TIMEOUT_MS),
        None => true,
    }
}

/// Starts `pecofence.exe` from beside this watchdog again.
fn restart_app() -> bool {
    if sysparams::shutting_down() {
        return false;
    }
    let Some(dir) = std::env::current_exe().ok().and_then(|p| p.parent().map(Path::to_path_buf)) else {
        return false;
    };
    let app = dir.join("pecofence.exe");
    if !app.is_file() {
        return false;
    }
    process::spawn_detached(&app.to_string_lossy(), &[]).is_ok()
}

fn main() {
    let args: Vec<String> = std::env::args().skip(1).collect();
    let Some(pid) = args.first().and_then(|a| a.parse::<u32>().ok()) else {
        return;
    };
    let Some(marker) = args.get(1).map(PathBuf::from) else {
        return;
    };
    let started = Instant::now();

    // Wait for the parent, pinging its UI thread between the wait slices.
    let mut misses: u32 = 0;
    loop {
        if process::wait_for_exit_or(pid, WAIT_SLICE.as_millis() as u32) {
            break;
        }
        if answers_ping(pid) {
            misses = 0;
        } else {
            misses += 1;
            if misses >= PING_MISSES {
                process::terminate(pid);
                break;
            }
        }
    }

    if !marker.exists() {
        return; // clean shutdown restored the icons already
    }

    // It died on us: restart it unless this smells of a loop (it had barely started). A
    // PecoFence started meanwhile takes the icons over below either way.
    if started.elapsed() >= MIN_LIFETIME {
        restart_app();
    }

    // Give Explorer a moment, then restore if still hidden. Explorer may be restarting or hung,
    // so keep trying for a while; if it never works the marker stays, and the next start adopts
    // the hidden icons and restores them at exit. A PecoFence started meanwhile takes them
    // over: the icons and the marker are its own then.
    let instance = pecofence_core::brand::var("PECOFENCE_INSTANCE").ok();
    let [mutex, _] = pecofence_core::brand::instance_mutex_names(instance.as_deref());
    std::thread::sleep(std::time::Duration::from_millis(300));
    for attempt in 0..10 {
        if attempt > 0 {
            std::thread::sleep(std::time::Duration::from_secs(1));
        }
        if window::SingleInstance::is_held(&mutex) {
            return;
        }
        let restored = !shell_icons::desktop_icons_hidden()
            || desktop::resolve_icon_host(desktop::detect_generation()).is_some_and(|host| {
                shell_icons::set_desktop_icons_hidden(false, host.def_view, host.host)
                    == Some(false)
            });
        if restored {
            let _ = std::fs::remove_file(&marker);
            return;
        }
    }
}
