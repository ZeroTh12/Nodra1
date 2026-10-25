//! Monitor enumeration and DPI queries.

use crate::bindings::*;
use crate::wide::from_wide;
use windows_core::BOOL;

pub use crate::bindings::HMONITOR;

#[derive(Clone, Debug)]
pub struct MonitorInfo {
    pub handle: HMONITOR,
    /// GDI device name such as `\\.\DISPLAY1`.
    pub device_name: String,
    /// Full monitor rectangle in virtual-screen pixels.
    pub bounds: RECT,
    /// Work area (excluding taskbar) in virtual-screen pixels.
    pub work_area: RECT,
    /// Effective DPI (96 = 100%).
    pub dpi: u32,
    pub primary: bool,
}

impl MonitorInfo {
    pub fn scale(&self) -> f32 {
        self.dpi as f32 / USER_DEFAULT_SCREEN_DPI as f32
    }
}

pub fn enumerate() -> Vec<MonitorInfo> {
    let mut monitors: Vec<MonitorInfo> = Vec::new();
    // SAFETY: the callback only runs during this call and receives a pointer to `monitors`.
    unsafe {
        let _ = EnumDisplayMonitors(
            None,
            None,
            Some(enum_proc),
            LPARAM(&mut monitors as *mut Vec<MonitorInfo> as isize),
        );
    }
    monitors
}

unsafe extern "system" fn enum_proc(
    monitor: HMONITOR,
    _hdc: HDC,
    _rect: *mut RECT,
    data: LPARAM,
) -> BOOL {
    // SAFETY: `data` is the `Vec` pointer passed by `enumerate` on this same thread.
    let monitors = unsafe { &mut *(data.0 as *mut Vec<MonitorInfo>) };
    if let Some(info) = query(monitor) {
        monitors.push(info);
    }
    BOOL(1)
}

/// Queries a single monitor handle.
pub fn query(monitor: HMONITOR) -> Option<MonitorInfo> {
    let mut info = MONITORINFOEXW {
        Base: MONITORINFO {
            cbSize: size_of::<MONITORINFOEXW>() as u32,
            ..Default::default()
        },
        szDevice: [0; 32],
    };
    // SAFETY: `info.cbSize` announces the EX layout; out-pointers reference locals.
    unsafe {
        if !GetMonitorInfoW(monitor, (&mut info as *mut MONITORINFOEXW).cast()).as_bool() {
            return None;
        }
        let mut dpi_x = USER_DEFAULT_SCREEN_DPI as u32;
        let mut dpi_y = dpi_x;
        let _ = GetDpiForMonitor(monitor, MDT_EFFECTIVE_DPI, &mut dpi_x, &mut dpi_y);
        Some(MonitorInfo {
            handle: monitor,
            device_name: from_wide(&info.szDevice),
            bounds: info.Base.rcMonitor,
            work_area: info.Base.rcWork,
            dpi: dpi_x,
            primary: info.Base.dwFlags & MONITORINFOF_PRIMARY as u32 != 0,
        })
    }
}

const ERROR_INSUFFICIENT_BUFFER: i32 = 122;

/// What Windows' display configuration (the database behind Settings > Display) knows about
/// the monitor on one GDI source. `\\.\DISPLAYn` names the source, which Windows may hand to
/// another monitor after a replug, a dock or a driver update; this names the monitor.
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct DisplayTarget {
    /// The source it shows, as in [`MonitorInfo::device_name`].
    pub gdi_name: String,
    /// EDID manufacturer and product code, `GSM7787` as Device Manager shows it; `None` when
    /// the monitor reports no EDID.
    pub model: Option<String>,
    /// Device instance from the monitor's device path, `GSM7787#5&2C948443&0&UID24832`: it
    /// changes with the port and the dock. Empty when the monitor has no device node (seen
    /// with an HDMI monitor whose device Windows lists as not present).
    pub instance: String,
    /// Output technology and connector index on the adapter, which tell identical monitors
    /// without an instance apart.
    pub connector: (i32, u32),
}

/// The monitors on the active display paths. Empty when the query fails (session 0).
pub fn display_targets() -> Vec<DisplayTarget> {
    // The topology can change between sizing and querying: then the query asks for more room.
    for _ in 0..3 {
        let (mut paths_n, mut modes_n) = (0u32, 0u32);
        // SAFETY: out-pointers reference locals.
        if unsafe {
            GetDisplayConfigBufferSizes(QDC_ONLY_ACTIVE_PATHS as u32, &mut paths_n, &mut modes_n)
        } != 0
        {
            return Vec::new();
        }
        let mut paths = vec![DISPLAYCONFIG_PATH_INFO::default(); paths_n as usize];
        let mut modes = vec![DISPLAYCONFIG_MODE_INFO::default(); modes_n as usize];
        // SAFETY: the buffers hold the element counts passed with them.
        let r = unsafe {
            QueryDisplayConfig(
                QDC_ONLY_ACTIVE_PATHS as u32,
                &mut paths_n,
                paths.as_mut_ptr(),
                &mut modes_n,
                modes.as_mut_ptr(),
                std::ptr::null_mut(),
            )
        };
        if r == ERROR_INSUFFICIENT_BUFFER {
            continue;
        }
        if r != 0 {
            return Vec::new();
        }
        paths.truncate(paths_n as usize);
        return paths.iter().filter_map(target_of).collect();
    }
    Vec::new()
}

fn target_of(path: &DISPLAYCONFIG_PATH_INFO) -> Option<DisplayTarget> {
    let mut source = DISPLAYCONFIG_SOURCE_DEVICE_NAME {
        header: DISPLAYCONFIG_DEVICE_INFO_HEADER {
            r#type: DISPLAYCONFIG_DEVICE_INFO_GET_SOURCE_NAME,
            size: size_of::<DISPLAYCONFIG_SOURCE_DEVICE_NAME>() as u32,
            adapterId: path.sourceInfo.adapterId,
            id: path.sourceInfo.id,
        },
        ..Default::default()
    };
    let mut target = DISPLAYCONFIG_TARGET_DEVICE_NAME {
        header: DISPLAYCONFIG_DEVICE_INFO_HEADER {
            r#type: DISPLAYCONFIG_DEVICE_INFO_GET_TARGET_NAME,
            size: size_of::<DISPLAYCONFIG_TARGET_DEVICE_NAME>() as u32,
            adapterId: path.targetInfo.adapterId,
            id: path.targetInfo.id,
        },
        ..Default::default()
    };
    // SAFETY: each header announces the size of the packet it heads.
    unsafe {
        if DisplayConfigGetDeviceInfo(&mut source.header) != 0
            || DisplayConfigGetDeviceInfo(&mut target.header) != 0
        {
            return None;
        }
    }
    // SAFETY: plain-data union; the bitfield view is always valid.
    let edid = unsafe { target.flags.Anonymous.Anonymous }.edidIdsValid();
    Some(DisplayTarget {
        gdi_name: from_wide(&source.viewGdiDeviceName),
        model: edid.then(|| edid_model(target.edidManufactureId, target.edidProductCodeId)),
        instance: device_instance(&from_wide(&target.monitorDevicePath)),
        connector: (target.outputTechnology, target.connectorInstance),
    })
}

/// `GSM7787`: the EDID manufacturer's three 5-bit letters (big-endian in the EDID, which
/// Windows hands over byte-swapped), then the product code in hex.
fn edid_model(manufacturer: u16, product: u16) -> String {
    let m = manufacturer.swap_bytes();
    let letter = |shift: u16| char::from(b'@' + ((m >> shift) & 0x1f) as u8);
    format!("{}{}{}{product:04X}", letter(10), letter(5), letter(0))
}

/// `GSM7787#5&2C948443&0&UID24832` from
/// `\\?\DISPLAY#GSM7787#5&2c948443&0&UID24832#{e6f07b5f-ee97-4a90-b076-33f57bf4eaa7}`.
fn device_instance(path: &str) -> String {
    let path = path.to_ascii_uppercase();
    let Some((_, rest)) = path.split_once("DISPLAY#") else {
        return String::new();
    };
    rest.rsplit_once("#{")
        .map_or(rest, |(id, _)| id)
        .to_string()
}

pub fn monitor_from_window(hwnd: HWND) -> HMONITOR {
    // SAFETY: plain FFI call.
    unsafe { MonitorFromWindow(hwnd, MONITOR_DEFAULTTONEAREST as u32) }
}

pub fn monitor_from_point(x: i32, y: i32) -> HMONITOR {
    // SAFETY: plain FFI call.
    unsafe { MonitorFromPoint(POINT { x, y }, MONITOR_DEFAULTTONEAREST as u32) }
}

pub fn dpi_for_window(hwnd: HWND) -> u32 {
    // SAFETY: plain FFI call.
    unsafe { GetDpiForWindow(hwnd) }
}

pub fn system_dpi() -> u32 {
    // SAFETY: plain FFI call.
    unsafe { GetDpiForSystem() }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn edid_ids_read_like_device_manager() {
        // An LG UltraFine as QueryDisplayConfig reports it: 27934 / 30599.
        assert_eq!(edid_model(27934, 30599), "GSM7787");
    }

    #[test]
    fn device_instance_drops_the_interface_parts() {
        assert_eq!(
            device_instance(
                r"\\?\DISPLAY#GSM7787#5&2c948443&0&UID24832#{e6f07b5f-ee97-4a90-b076-33f57bf4eaa7}"
            ),
            "GSM7787#5&2C948443&0&UID24832"
        );
        assert_eq!(device_instance(""), "");
    }
}
