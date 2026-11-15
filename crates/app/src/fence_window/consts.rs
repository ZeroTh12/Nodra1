//! Timer ids, delays, geometry and motion constants shared by the fence window modules.

use super::*;

pub(super) const RESIZE_BORDER_DIP: f32 = 6.0;
/// Opacity of the items a Peek search does not match.
pub(super) const SEARCH_DIM_ALPHA: f32 = 0.15;
/// Selection-fill strength of the Peek search matches other than the current one (which is
/// fully selected).
pub(super) const SEARCH_MATCH_SELECTION: f32 = 0.5;
/// Opacity of the tab pills a Peek search finds nothing in.
pub(super) const SEARCH_TAB_DIM_ALPHA: f32 = 0.4;
/// Esc registered as a hotkey on the fence for the length of a title drag in the system move
/// loop (`on_entersizemove`): the loop hears the keyboard only while the fence has the focus.
pub(super) const HOTKEY_MOVE_ESC: i32 = 1;
pub(super) const TIMER_PEEK_OPEN: usize = 31;
pub(super) const TIMER_PEEK_CLOSE: usize = 32;
pub(super) const TIMER_SHADOW: usize = 33;
/// Fades an "inactive" scrollbar out 2 s after the last scroll / pointer activity (WinUI
/// ScrollView no-indicator countdown).
pub(super) const TIMER_SCROLLBAR: usize = 34;
/// Explorer's "slow double-click" rename: a second click on the label of the already-selected
/// item enters rename once the double-click interval has passed without a double-click.
pub(super) const TIMER_RENAME: usize = 35;
/// Infotip delay (SPI_GETMOUSEHOVERTIME) after the pointer settles on an item / tab / button.
pub(super) const TIMER_TIP: usize = 36;
/// Infotip auto-pop (SPI_GETMESSAGEDURATION, default 5 s), comctl32's TTDT_AUTOPOP equivalent;
/// TTF_TRACK tips do not pop on their own.
pub(super) const TIMER_TIP_HIDE: usize = 38;
/// Overlay scrollbar expand / contract begin delays (WinUI ScrollBarExpandBeginTime 0.4 s and
/// ScrollBarContractBeginTime 0.5 s): the thumb widens only after the pointer has rested on
/// it and stays wide for a moment after it leaves.
pub(super) const TIMER_SCROLLBAR_EXPAND: usize = 39;
pub(super) const TIMER_SCROLLBAR_CONTRACT: usize = 40;
/// Track-click paging auto-repeat while the button is held.
pub(super) const TIMER_SCROLL_REPEAT: usize = 41;
/// A drag resting on a rolled fence's title unrolls it after the hover delay (Explorer's
/// navigation pane spring-loads a collapsed folder under a drag the same way).
pub(super) const TIMER_DRAG_PEEK: usize = 42;
pub(super) const TIMER_VISIBILITY_FINISH: usize = 43;
pub(super) const TIMER_CONTENT_FINISH: usize = 44;
/// The pointer rests on another tab with `rollUp.switchTabOnHover` on: switch to it after the
/// hover delay.
pub(super) const TIMER_TAB_HOVER: usize = 45;
/// Polls the right button during a title drag in the system move loop: the loop sends
/// WM_MOVING only while the pointer moves, so a right click on a resting pointer went unseen.
pub(super) const TIMER_MOVE_RBUTTON: usize = 46;
/// Settles the cell grid after the system size loop throttled its re-layout (`nc::on_size`):
/// the edge follows the pointer every message, the grid catches up between them.
pub(super) const TIMER_RESIZE_SETTLE: usize = 47;

// ── 贴边隐藏 Edge Auto-Hide ──────────────────────────────────────────────────────
/// 鼠标离开栅栏后，栅栏还在屏幕上停留多久再滑走（ms）。800ms 够用户点进去又退开，
/// 也能覆盖正常鼠标移动路径上短暂经过栅栏的情况。
pub(super) const EDGE_HIDE_LINGER_MS: u32 = 800;
/// 鼠标进入屏幕边缘感应区后，必须停多久才认定是"想把栅栏叫出来"（ms）。300ms 防抖，
/// 快速扫过边缘不会误触。
pub(super) const EDGE_HIDE_PROBE_MS: u32 = 300;
/// 感应区厚度（DIP）。Windows 11 的"拖出边缘取消贴靠"也用 8 DIP 左右，选 10 留余量；
/// 低于任务栏的边仍然用 MonitorInfo.work_area，所以感应区不会塞进任务栏。
pub(super) const EDGE_HIDE_ZONE_DIP: i32 = 10;
/// 贴边隐藏/滑出的总时长（ms）。250ms = Fluent 的容器变换曲线值，和 roll_up 对齐。
pub(super) const EDGE_HIDE_DURATION_MS: u32 = 250;
/// 栅栏完全滑出后，在屏幕外保留多少 DIP（避免 SetWindowPos 把它裁成 0 宽/高）。
pub(super) const EDGE_HIDE_PEEK_DIP: i32 = 2;
/// 栅栏滑出屏幕后，轮询鼠标是否进入感应区的间隔（ms）。用低频 WM_TIMER 而不是帧时钟：
/// 静止的 GIF/壁纸一个像素都不动，60/120 Hz 的唤醒纯粹是浪费电；120 ms 的检测延迟在
/// 300 ms 的停留判定里完全看不出来。
pub(super) const EDGE_HIDE_POLL_MS: u32 = 120;
pub(super) const TIMER_EDGE_HIDE_LINGER: usize = 51;
pub(super) const TIMER_EDGE_HIDE_PROBE: usize = 52;
pub(super) const TIMER_EDGE_HIDE_POLL: usize = 53;
/// Minimum spacing between two cell-grid re-layouts while the user drags a fence's edge: one
/// compositor frame. The chrome (plate, rim, clip) still follows every WM_SIZE, so the frame
/// keeps up with the pointer; the content re-flows on the next beat, close enough that it never
/// visibly trails the edge (the old 60 ms beat read as a stutter).
pub(super) const RESIZE_CONTENT_MS: u128 = 16;
/// DWM can suspend completion callbacks for fully occluded windows. UI state must still
/// settle after the longest (250 ms) transition, independently of compositor visibility.
pub(super) const COMPOSITION_FINISH_MS: u32 = 400;
/// The selected (anchor) item's label unfolds to its full name like the desktop's focused
/// icon. Windows is uncapped; six lines keep a 255-character name from covering two rows in a
/// small fence.
pub(super) const MAX_UNFOLD_LINES: u32 = 6;
pub(super) const SCROLLBAR_EXPAND_BEGIN_MS: u32 = 400;
pub(super) const SCROLLBAR_CONTRACT_BEGIN_MS: u32 = 500;
/// Win32 scrollbar SCROLL_FIRST_DELAY / SCROLL_REPEAT_DELAY.
pub(super) const SCROLL_PAGE_FIRST_MS: u32 = 200;
pub(super) const SCROLL_PAGE_REPEAT_MS: u32 = 50;
/// Inactive-scrollbar linger after the last activity (WinUI ScrollView `s_noIndicatorCountdown`).
pub(super) const SCROLLBAR_LINGER_MS: u32 = 2000;
/// Marquee auto-scroll: a per-frame velocity proportional to how far the pointer is outside
/// the item area (DIP/s per DIP of overshoot, clamped), like Explorer's list view.
pub(super) const MARQUEE_SCROLL_GAIN: f32 = 12.0;
pub(super) const MARQUEE_SCROLL_MIN: f32 = 60.0;
pub(super) const MARQUEE_SCROLL_MAX: f32 = 1200.0;
/// OLE drag auto-scroll: a pointer inside the item area within this many DIPs of its top /
/// bottom edge scrolls, faster the closer it is to the edge (roughly one list row deep).
pub(super) const DRAG_SCROLL_ZONE_DIP: f32 = 20.0;
pub(super) const DRAG_SCROLL_MIN: f32 = 120.0;
pub(super) const DRAG_SCROLL_MAX: f32 = 720.0;
/// The drag must linger in the zone this long before the scroll starts (oleidl default).
pub(super) const DRAG_SCROLL_ARM: Duration = Duration::from_millis(50);
/// Explorer / ListView type-to-select: the typed prefix resets after this pause.
pub(super) const TYPE_AHEAD_TIMEOUT: Duration = Duration::from_millis(1000);
/// Pointer within this many DIPs of the right edge counts as "on the scrollbar".
pub(super) const SCROLLBAR_HOT_DIP: f32 = 12.0;
/// Right resize border left beside a shown scrollbar (the expanded thumb ends 3 DIP from the
/// edge; the rest of the 12 DIP strip belongs to the bar).
pub(super) const SCROLLBAR_RESIZE_BORDER_DIP: f32 = 3.0;
pub(super) const WM_NCLBUTTONUP: u32 = 0x00A2;
pub(super) const WM_NCRBUTTONDOWN: u32 = 0x00A4;
pub(super) const WM_NCRBUTTONDBLCLK: u32 = 0x00A6;
/// The second right press of a double-click (CS_DBLCLKS): a press like any other for the fence.
pub(super) const WM_RBUTTONDBLCLK: u32 = 0x0206;
/// `SC_MOVE | HTCAPTION`: starts the caption drag loop as if the title had just been pressed.
pub const SC_MOVE_CAPTION: usize = 0xF012;

/// Shadow bitmaps are re-uploaded (`UpdateLayeredWindow`, several ms for a large fence) at most
/// this often while the body is being resized *interactively*: one compositor frame, so the
/// shadow stays attached to the plate instead of trailing behind it as a ghost. A trailing
/// update catches the final geometry. Animated (frame-clock) resizes bypass the throttle.
pub(super) const SHADOW_MIN_INTERVAL_MS: u128 = 16;
/// Hover-peek closes this long after the pointer left (no Fluent reference value).
pub(super) const PEEK_CLOSE_MS: u32 = 400;
pub(super) const SNAP_DIST_DIP: i32 = 10;
/// Tab header geometry (DIPs).
pub(super) const TAB_MIN_W: f32 = 48.0;
pub(super) const TAB_MAX_W: f32 = 160.0;
pub(super) const TAB_GAP: f32 = 4.0;
pub(super) const TAB_LEFT: f32 = 8.0;
/// Right-hand title space reserved for the chevron / rolled item count.
pub(super) const TAB_RIGHT_RESERVE: f32 = 44.0;
/// Room a scrolled tab strip keeps beside the active tab where more tabs lie behind the strip's
/// end: 16 DIP of the next tab, then the fade.
pub(super) const TAB_SCROLL_MARGIN: f32 = 16.0 + pecofence_render::fence_chrome::STRIP_FADE_W;
/// A tab dragged along a scrolled strip, or a fence dragged over it to merge, scrolls the strip
/// while the pointer is this close to an end (DIPs), at this speed (DIPs per second).
pub(super) const TAB_EDGE_ZONE: f32 = 32.0;
pub(super) const TAB_EDGE_SPEED: f32 = 360.0;
/// Left tab column width limits (DIPs) and what a row needs beside its caption: 10 before
/// it and 8 after, 14 more before it when a tab shows a colour dot.
pub(super) const TAB_RAIL_MIN_W: f32 = 96.0;
pub(super) const TAB_RAIL_MAX_W: f32 = 160.0;
pub(super) const TAB_RAIL_TEXT_ROOM: f32 = 18.0;
pub(super) const TAB_RAIL_DOT_ROOM: f32 = 14.0;
/// Width of the insertion gap a tabbed strip opens for a fence dragged over it (WinUI TabView's
/// default tab width; the merged tab is laid out for real once it lands).
pub(super) const TAB_MERGE_GAP_W: f32 = 96.0;

/// In-place drag image limits (Explorer's DefView renders the selection in place only for a
/// small footprint; beyond it the shell's thumbnail stack + count badge is used): at most this
/// many items and this footprint in DIPs — a 2×2 block of 96 px icons or 3×2 of 48 px still
/// lifts off in place, any Rows-layout selection wider than that does not.
pub(super) const DRAG_IMAGE_MAX_ITEMS: usize = 4;
pub(super) const DRAG_IMAGE_MAX_DIP: f32 = 320.0;

/// Dragging a tab header this far (DIPs) out of the title row splits it into its own fence.
pub(super) const TAB_DETACH_DIP: f32 = 28.0;

/// WinUI ScrollBarVerticalThumbMinHeight.
pub(super) const SCROLLBAR_THUMB_MIN: f32 = 30.0;

/// Scale of a fence at the start of its entrance / end of its exit (Fluent Direct Entrance).
pub(super) const ENTRANCE_SCALE: f32 = 0.97;
/// Distance (DIPs) the incoming tab content slides from the side of the new tab. Fluent
/// publishes no figure for page-refresh slides; fences are small, so this stays short.
pub(super) const TAB_SLIDE_DIP: f32 = 24.0;
