//! 贴边隐藏 Edge Auto-Hide：鼠标离开栅栏延迟后滑出屏幕；鼠标靠近同一边的感应区
//! 并停留后，平滑滑回来。纯 Win32 逐帧 SetWindowPos + WM_TIMER 驱动，零阻塞。
//!
//! 规避的 5 个底层大坑（项目上下文里已有 3 个预埋，这里负责剩下 2 个 + 补强）：
//!   坑 1 多显示器 + 任务栏冲突：项目 `platform::monitors::work_area_under_cursor()`
//!         已用 MonitorFromPoint + GetMonitorInfoW.rcWork，绝不碰 GetSystemMetrics，
//!         感应区和隐藏/滑出目标都算在工作区内。
//!   坑 2 DWM 系统动画干扰：每次 SetWindowPos 帧前显式再调一次
//!         `dwm::set_transitions_disabled(hwnd, true)`（内部是
//!         DwmSetWindowAttribute(DWMWA_TRANSITIONS_FORCEDISABLED, 1)），确保 Win11 23H2+
//!         绕过创建时 flag 的"窗口滑入过渡动画"不会在每一帧之间拖影。
//!   坑 3 焦点抢夺 + Alt+Tab：创建栅栏时已经是 WS_EX_NOACTIVATE | WS_EX_TOOLWINDOW
//!         （见 fence_window::api），贴边隐藏全程不改样式，绝不会抢前台。
//!   坑 4 窗口滑出后鼠标监听失效 —— 选方案 B：用项目现成的 FrameClock
//!         （DCompositionWaitForCompositorClock，~60 Hz）轮询 GetCursorPos，
//!         空闲零 CPU（frame clock disarm），比 WH_MOUSE_LL 独立线程 + channel 轻量得多，
//!         也省了独立线程的生命周期管理。
//!   坑 5 防误触 + 防抖：300 ms 感应区停留判定（EDGE_HIDE_PROBE_MS） + 800 ms 延迟隐藏
//!         （EDGE_HIDE_LINGER_MS），状态机把"快速扫过边缘"和"想把它叫出来"严格分开。

use super::*;
use pecofence_platform as p;

/// 哪一边贴边（先简化成左/右；上/下同理，扩展零成本）。
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub(super) enum EdgeSide {
    Left,
    Right,
    Top,
    Bottom,
}

/// 贴边隐藏状态机。挂在 `FenceViewState.edge_hide` 上。
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub(super) enum EdgeHide {
    /// 正常可见；鼠标进入栅栏内部时结束 linger/hide 流程。
    Idle,
    /// 鼠标已经离开栅栏；800ms 之后若还没回来 → 进入 Hiding。
    Lingering,
    /// 正在滑出屏幕（250ms 缓动）。完成后进入 Hidden。
    Hiding,
    /// 完全滑出屏幕外；`poll_cursor_and_probe` 每帧轮询鼠标位置，若进入感应区 → 启
    /// TIMER_EDGE_HIDE_PROBE（300ms），即 Probing。
    Hidden,
    /// 鼠标在感应区里已经停留了一些时间，但还没到 300ms；提前离开 → 回 Hidden。
    Probing,
    /// 正在滑回屏幕（250ms 缓动）。完成后回 Idle。
    Showing,
}

impl Default for EdgeHide {
    fn default() -> Self {
        Self::Idle
    }
}

/// 状态机 + tween：把 HWND 从某个可见位置平滑位移到屏幕外（Hide），再从屏幕外
/// 平滑位移回来（Show）。整个模块是无依赖的值型结构体，所有 FFI 调用都要外部
/// 传 hwnd: HWND 进来 —— 这样它不借用 FenceViewState 的 hwnd 字段，也不会让
/// Rust 所有权模型和 Win32 句柄生命周期打架。
pub(super) struct EdgeHideState {
    pub(super) state: EdgeHide,
    /// 贴边方向：决定隐藏时栅栏往左/右/上/下滑出，以及感应区算在哪一边。
    pub(super) side: EdgeSide,
    /// 缓动起止位置（物理 px）。hide 时 from = 可见位置, to = 屏幕外；show 时反过来。
    pub(super) from: i32,
    pub(super) to: i32,
    /// tween 参数：当前进度由这个线性样本经 `ease_out_cubic` 映射。
    pub(super) tween_started: Option<Instant>,
    pub(super) tween_duration_ms: u64,
    /// Probing 阶段鼠标进入感应区的时刻（None = 还没进或 Probe 超时取消）。
    pub(super) probe_entered: Option<Instant>,
}

impl Default for EdgeHideState {
    fn default() -> Self {
        Self {
            state: EdgeHide::Idle,
            side: EdgeSide::Right,
            from: 0,
            to: 0,
            tween_started: None,
            tween_duration_ms: EDGE_HIDE_DURATION_MS as u64,
            probe_entered: None,
        }
    }
}

// ─── 缓动 ────────────────────────────────────────────────────────────────────────

/// EaseOutCubic: 把 0..1 线性 t 映射成 cubic deceleration，适合容器变换（和项目里
/// roll_up 的 Curve::Decelerate 同曲线族）。手写是为了不引入 bezier_easing 到这个
/// 模块（它已经在 render crate，app crate 引起来需要模块桥）。
#[inline]
fn ease_out_cubic(t: f32) -> f32 {
    1.0 - (1.0 - t.clamp(0.0, 1.0)).powi(3)
}

// ─── 坐标 + 感应区 ──────────────────────────────────────────────────────────────

/// 根据 side 和 rcWork，算出隐藏时栅栏要滑到屏幕外的 x / y：
///   Left   → new_left = work.left - fence_width - PEEK_DIP
///   Right  → new_left = work.right + PEEK_DIP
///   Top    → new_top  = work.top  - fence_height - PEEK_DIP
///   Bottom → new_top  = work.bottom + PEEK_DIP
/// 这样 SetWindowPos 把栅栏推到屏幕外 2 DIP（PEEK_DIP），永远不裁成 0 宽/高。
fn target_offscreen(side: EdgeSide, fence_w: i32, fence_h: i32, work: &RECT) -> i32 {
    match side {
        EdgeSide::Left => work.left - fence_w - EDGE_HIDE_PEEK_DIP,
        EdgeSide::Right => work.right + EDGE_HIDE_PEEK_DIP,
        EdgeSide::Top => work.top - fence_h - EDGE_HIDE_PEEK_DIP,
        EdgeSide::Bottom => work.bottom + EDGE_HIDE_PEEK_DIP,
    }
}

/// side 方向上的屏幕边界 + 感应区：返回感应区的几何（坐标范围 + 宽度/高度）。
/// Left:   work.left - ZONE_DIP .. work.left
/// Right:  work.right .. work.right + ZONE_DIP
/// Top:    work.top   - ZONE_DIP .. work.top
/// Bottom: work.bottom .. work.bottom + ZONE_DIP
fn edge_zone(side: EdgeSide, work: &RECT) -> (i32, i32) {
    let z = EDGE_HIDE_ZONE_DIP;
    match side {
        EdgeSide::Left => (work.left - z, work.left),
        EdgeSide::Right => (work.right, work.right + z),
        EdgeSide::Top => (work.top - z, work.top),
        EdgeSide::Bottom => (work.bottom, work.bottom + z),
    }
}

/// 鼠标 pt 是否落在 side 的感应区里（同一显示器、同一边、同工作区）。
fn point_in_zone(
    pt: (i32, i32),
    side: EdgeSide,
    _fence_w: i32,
    _fence_h: i32,
    work: &RECT,
) -> bool {
    // 先过滤掉鼠标在另一个显示器上（edge 感应必须在 fence 所属的同一 work_area 里）。
    if pt.0 < work.left || pt.0 >= work.right || pt.1 < work.top || pt.1 >= work.bottom {
        return false;
    }
    let (lo, hi) = edge_zone(side, work);
    // 横向边（Left / Right）：检查 x 是否在感应区，同时 y 要落在 fence 的垂直范围里
    // （感应区沿着整屏幕高度都在，过宽会让鼠标从角落擦过也触发）。
    match side {
        EdgeSide::Left | EdgeSide::Right => {
            pt.0 >= lo && pt.0 <= hi && pt.1 >= work.top && pt.1 < work.bottom
        }
        EdgeSide::Top | EdgeSide::Bottom => {
            pt.1 >= lo && pt.1 <= hi && pt.0 >= work.left && pt.0 < work.right
        }
    }
}

// ─── DWM 过渡禁用（坑 2 补强） ───────────────────────────────────────────────────

/// 每次 SetWindowPos 帧前再调一次：Win11 23H2+ 在某些情况下会绕过创建时的
/// DWMWA_TRANSITIONS_FORCEDISABLED flag，插入系统过渡动画 → 每帧之间拖影。
/// 这个调用是纯 ffi，零开销；即使偶发失败（刚创建 / 正在销毁）也无所谓。
/// 委托给 platform::dwm::set_transitions_disabled（内部就是
/// DwmSetWindowAttribute(DWMWA_TRANSITIONS_FORCEDISABLED, 1)）。
fn disable_dwm_transition(hwnd: HWND) {
    let _ = p::dwm::set_transitions_disabled(hwnd, true);
}

// ─── SetWindowPos 逐帧位移（纯 Win32，不用高层框架） ─────────────────────────────

/// 把栅栏沿 side 方向挪到 coord（新的 left 或 top，取决于 side）。
/// 全程只调用 platform::window::set_window_bounds —— 它内部带
/// NOACTIVATE | NOZORDER 标志（坑 3 已经被它保护），尺寸参数传当前宽/高 = SWP_NOSIZE
/// 的效果。性能极轻：一个 SetWindowPos，不重绘不动 z-order。
/// ✅ 坑 2：调用前已经调过 disable_dwm_transition(hwnd)，确保 DWM 不插过渡。
fn slide_to(hwnd: HWND, side: EdgeSide, coord: i32) {
    let rect = window::window_rect(hwnd);
    let w = rect.right - rect.left;
    let h = rect.bottom - rect.top;
    let (x, y) = match side {
        EdgeSide::Left | EdgeSide::Right => (coord, rect.top),
        EdgeSide::Top | EdgeSide::Bottom => (rect.left, coord),
    };
    let _ = window::set_window_bounds(hwnd, x, y, w, h);
}

// ─── 状态机入口 ─────────────────────────────────────────────────────────────────

impl EdgeHideState {
    /// 鼠标刚刚**离开**栅栏内部。外部（WNDPROC 的 WM_MOUSELEAVE）调这个。
    pub(super) fn on_mouse_left_window(&mut self, hwnd: HWND) {
        if self.state != EdgeHide::Idle {
            tracing::info!(state = ?self.state, "edge_hide: left window but not Idle, skip");
            return;
        }
        // 先选好 side：取栅栏当前 x / y 靠近哪条屏幕边界（work_area）。
        let Some(monitor) = p::monitors::work_area_under_cursor() else {
            tracing::warn!("edge_hide: work_area_under_cursor returned None");
            return;
        };
        let rect = window::window_rect(hwnd);
        let work = &monitor.work_area;
        let _w = rect.right - rect.left;
        let _h = rect.bottom - rect.top;
        // 取栅栏左右/上下各距离 work 边界多少，近的那一边就是贴边方向。
        let d_left = (rect.left - work.left).abs();
        let d_right = (work.right - rect.right).abs();
        let d_top = (rect.top - work.top).abs();
        let d_bottom = (work.bottom - rect.bottom).abs();
        tracing::info!(
            ?rect,
            ?work,
            d_left,
            d_right,
            d_top,
            d_bottom,
            "edge_hide: left-window distances"
        );
        let side = [
            (EdgeSide::Left, d_left),
            (EdgeSide::Right, d_right),
            (EdgeSide::Top, d_top),
            (EdgeSide::Bottom, d_bottom),
        ]
        .into_iter()
        .min_by_key(|(_, d)| *d)
        .map(|(s, _)| s)
        .unwrap_or(EdgeSide::Right);
        self.side = side;
        self.state = EdgeHide::Lingering;
        tracing::info!(
            ?side,
            ?rect,
            linger_ms = EDGE_HIDE_LINGER_MS,
            "edge_hide: Lingering started"
        );
        // 只 set 一次 TIMER_EDGE_HIDE_LINGER：800ms 后还没回来 → 进入 Hiding。
        window::kill_timer(hwnd, TIMER_EDGE_HIDE_LINGER);
        window::set_timer(hwnd, TIMER_EDGE_HIDE_LINGER, EDGE_HIDE_LINGER_MS);
    }

    /// 鼠标刚刚**进入**栅栏内部。取消一切 linger / hide / probing / showing，回 Idle。
    pub(super) fn on_mouse_entered_window(&mut self, hwnd: HWND) {
        match self.state {
            EdgeHide::Idle => {}
            // Lingering → 还没滑走，直接取消定时器就行。
            EdgeHide::Lingering => {
                self.state = EdgeHide::Idle;
                window::kill_timer(hwnd, TIMER_EDGE_HIDE_LINGER);
            }
            // Hiding 中被取消：反向缓动滑回来（见下面 reverse_tween）。
            EdgeHide::Hiding => self.reverse_tween(),
            // Showing → 滑一半被鼠标进来，无所谓，继续滑完就是正方向，结束在 Idle。
            EdgeHide::Showing => {}
            // Hidden / Probing：取消 Probe 定时器，立刻滑回来。
            EdgeHide::Hidden | EdgeHide::Probing => {
                self.reverse_show(hwnd);
            }
        }
    }

    /// 外部定时器回调。WM_TIMER 来了就调用这个；id 不匹配的直接返回 None。
    pub(super) fn on_timer(&mut self, hwnd: HWND, id: usize) {
        match id {
            TIMER_EDGE_HIDE_LINGER => {
                if self.state != EdgeHide::Lingering {
                    return;
                }
                // timer 触发：鼠标离开已经 800ms，启滑走。
                self.start_hiding(hwnd);
            }
            TIMER_EDGE_HIDE_PROBE => {
                if self.state != EdgeHide::Probing {
                    return;
                }
                // 300ms 到，认定是想把它叫出来：启滑回。
                self.start_showing(hwnd);
                if self.state == EdgeHide::Probing {
                    // 光标下没有显示器（显示器刚被拔掉）：直接贴回可见位置，别卡在 Probing。
                    self.reverse_show(hwnd);
                }
                self.set_polling(hwnd, false);
            }
            TIMER_EDGE_HIDE_POLL => {
                // 栅栏在屏幕外：低频看一眼鼠标还在不在感应区（见 `tick`，这里不再占用帧时钟）。
                if matches!(self.state, EdgeHide::Hidden | EdgeHide::Probing) {
                    self.poll_cursor_and_probe(hwnd);
                } else {
                    self.set_polling(hwnd, false);
                }
            }
            _ => {}
        }
    }

    /// 每帧推进一次。只有缓动（Hiding / Showing）需要帧时钟；Hidden / Probing 完全靠
    /// `TIMER_EDGE_HIDE_POLL` 低频轮询，静止时帧时钟保持 disarm（零唤醒）。
    /// 返回 true = 还有帧要跑（外部 FrameClock 继续 request）。
    pub(super) fn tick(&mut self, hwnd: HWND, now: Instant) -> bool {
        match self.state {
            EdgeHide::Hiding | EdgeHide::Showing => {
                self.step_tween(hwnd, now);
                !matches!(self.state, EdgeHide::Idle | EdgeHide::Hidden)
            }
            EdgeHide::Hidden | EdgeHide::Probing | EdgeHide::Lingering | EdgeHide::Idle => false,
        }
    }

    /// Hidden / Probing 期间保持低频轮询定时器；其它状态一律关掉（定时器随状态存在，
    /// 静止的栅栏不产生任何唤醒）。
    fn set_polling(&mut self, hwnd: HWND, on: bool) {
        if on {
            window::set_timer(hwnd, TIMER_EDGE_HIDE_POLL, EDGE_HIDE_POLL_MS);
        } else {
            window::kill_timer(hwnd, TIMER_EDGE_HIDE_POLL);
        }
    }
}

// ─── 内部：启动 hide / show tween ───────────────────────────────────────────────

impl EdgeHideState {
    fn start_hiding(&mut self, hwnd: HWND) {
        let rect = window::window_rect(hwnd);
        let Some(monitor) = p::monitors::work_area_under_cursor() else {
            return;
        };
        let w = rect.right - rect.left;
        let h = rect.bottom - rect.top;
        let from = match self.side {
            EdgeSide::Left | EdgeSide::Right => rect.left,
            EdgeSide::Top | EdgeSide::Bottom => rect.top,
        };
        let to = target_offscreen(self.side, w, h, &monitor.work_area);
        self.from = from;
        self.to = to;
        self.tween_started = Some(Instant::now());
        self.state = EdgeHide::Hiding;
        // 外部（FenceViewState）负责 frames.request() —— 避免 EdgeHideState 借到
        // frames: Rc<FrameClock> 而污染自己的生命周期。
    }

    fn start_showing(&mut self, hwnd: HWND) {
        let rect = window::window_rect(hwnd);
        let Some(monitor) = p::monitors::work_area_under_cursor() else {
            return;
        };
        let w = rect.right - rect.left;
        let h = rect.bottom - rect.top;
        // 反向：现在的 HWND 位置就是 from，目标是 work_area 贴边处。
        let from = match self.side {
            EdgeSide::Left | EdgeSide::Right => rect.left,
            EdgeSide::Top | EdgeSide::Bottom => rect.top,
        };
        let to = match self.side {
            EdgeSide::Left => monitor.work_area.left,
            EdgeSide::Right => monitor.work_area.right - w,
            EdgeSide::Top => monitor.work_area.top,
            EdgeSide::Bottom => monitor.work_area.bottom - h,
        };
        self.from = from;
        self.to = to;
        self.tween_started = Some(Instant::now());
        self.state = EdgeHide::Showing;
    }

    /// 正在 Hiding 时鼠标进了窗口 → 反向 tween，立刻滑回来（取消隐藏）。
    fn reverse_tween(&mut self) {
        let (f, t) = (self.from, self.to);
        self.from = t;
        self.to = f;
        self.tween_started = Some(Instant::now());
        self.state = EdgeHide::Showing;
    }

    /// Hidden / Probing 时鼠标进了窗口 → 直接设位置到可见贴边处，不需要缓动（这是
    /// 用户直接把鼠标伸到屏幕外再伸回窗口内的操作，瞬间出来更直觉）。
    fn reverse_show(&mut self, hwnd: HWND) {
        let rect = window::window_rect(hwnd);
        let Some(monitor) = p::monitors::work_area_under_cursor() else {
            self.state = EdgeHide::Idle;
            return;
        };
        let w = rect.right - rect.left;
        let h = rect.bottom - rect.top;
        let target = match self.side {
            EdgeSide::Left => monitor.work_area.left,
            EdgeSide::Right => monitor.work_area.right - w,
            EdgeSide::Top => monitor.work_area.top,
            EdgeSide::Bottom => monitor.work_area.bottom - h,
        };
        disable_dwm_transition(hwnd);
        slide_to(hwnd, self.side, target);
        window::kill_timer(hwnd, TIMER_EDGE_HIDE_PROBE);
        self.set_polling(hwnd, false);
        self.probe_entered = None;
        self.state = EdgeHide::Idle;
    }
}

// ─── 内部：每帧 step ────────────────────────────────────────────────────────────

impl EdgeHideState {
    fn step_tween(&mut self, hwnd: HWND, now: Instant) {
        let Some(started) = self.tween_started else {
            return;
        };
        let elapsed = now.duration_since(started).as_millis() as f32;
        let t = (elapsed / self.tween_duration_ms as f32).clamp(0.0, 1.0);
        let eased = ease_out_cubic(t);
        let coord = (self.from as f32 + (self.to - self.from) as f32 * eased).round() as i32;
        // ✅ 坑 2：每帧 SetWindowPos 之前显式调一次，确保 DWM 不插过渡。
        disable_dwm_transition(hwnd);
        slide_to(hwnd, self.side, coord);
        if t >= 1.0 {
            self.tween_started = None;
            match self.state {
                EdgeHide::Hiding => {
                    self.state = EdgeHide::Hidden;
                    // 滑出走完：不再需要逐帧，改由低频定时器轮询感应区。
                    self.set_polling(hwnd, true);
                }
                EdgeHide::Showing => {
                    self.state = EdgeHide::Idle;
                    self.set_polling(hwnd, false);
                }
                _ => {}
            }
        }
    }

    /// Hidden / Probing 期间由 `TIMER_EDGE_HIDE_POLL` 低频调用（不再占用帧时钟）：
    /// 进感应区 → 启 Probe（300ms 停留），出感应区（还在 Probe 中）→ 取消 probe → 回 Hidden。
    fn poll_cursor_and_probe(&mut self, hwnd: HWND) {
        let pt = window::cursor_pos();
        let monitor = {
            let hm = p::monitors::monitor_from_point(pt.x, pt.y);
            if hm.0.is_null() {
                None
            } else {
                p::monitors::query(hm)
            }
        };
        let in_zone = if let Some(monitor) = monitor {
            let rect = window::window_rect(hwnd);
            let w = rect.right - rect.left;
            let h = rect.bottom - rect.top;
            point_in_zone((pt.x, pt.y), self.side, w, h, &monitor.work_area)
        } else {
            false
        };

        match (self.state, in_zone) {
            (EdgeHide::Hidden, true) => {
                // 第一次进：记时刻 + 启 300ms TIMER_EDGE_HIDE_PROBE。
                self.probe_entered = Some(Instant::now());
                self.state = EdgeHide::Probing;
                window::kill_timer(hwnd, TIMER_EDGE_HIDE_PROBE);
                window::set_timer(hwnd, TIMER_EDGE_HIDE_PROBE, EDGE_HIDE_PROBE_MS);
            }
            (EdgeHide::Probing, false) => {
                // 快速扫过感应区（< 300ms）→ 取消 probe，回 Hidden。
                self.probe_entered = None;
                self.state = EdgeHide::Hidden;
                window::kill_timer(hwnd, TIMER_EDGE_HIDE_PROBE);
            }
            (EdgeHide::Probing, true) => {
                // 还在感应区里 → 什么都不做，等 timer 触发 show。
            }
            (EdgeHide::Hidden, false) => {
                // 不在感应区也不在 probe → 继续轮询（下一帧再查）。
            }
            _ => {}
        }
    }
}
