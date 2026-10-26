//! Theme / accent / backdrop / icon-variant / shadow / tray-glyph helpers and visual refresh.

use super::live_wallpaper::{LIVE_REFRESH, LiveWallpaper};
use super::wallpaper_refresh::LIVE_MARK;
use super::*;

/// The theme for `mode`, retinted with the user's accent when it could be read (WinUI
/// AccentFillColorDefault: AccentLight2 on dark, AccentDark1 on light). A custom theme
/// starts from its own base style and its values win over the accent.
pub(super) fn theme_for(
    mode: ThemeMode,
    style: pecofence_core::ThemeStyle,
    custom: Option<&CustomTheme>,
    accent: Option<&systheme::AccentPalette>,
) -> Theme {
    let style = custom.map_or(style, |c| c.base);
    let mut theme = Theme::for_mode(mode);
    if style == pecofence_core::ThemeStyle::LiquidGlass {
        theme = theme.with_liquid_glass();
    }
    if let Some(p) = accent {
        theme = theme.with_accent(if mode == ThemeMode::Dark {
            p.light2
        } else {
            p.dark1
        });
    }
    match custom {
        Some(c) => c.apply(theme),
        None => theme,
    }
}

/// The custom theme the settings name, read from the `themes` folder: None when no theme is
/// chosen, an error (also written to the log) when the file is missing or invalid. The fences
/// then keep the built-in style.
pub(super) fn load_custom_theme(
    state: &AppState,
) -> std::result::Result<Option<CustomTheme>, String> {
    let Some(name) = state.config.settings.custom_theme.as_deref() else {
        return Ok(None);
    };
    let path = state.themes_dir().join(format!("{name}.json"));
    let result = if name.contains(['/', '\\']) {
        Err("the name must not contain a path".to_string())
    } else {
        std::fs::read_to_string(&path)
            .map_err(|e| e.to_string())
            .and_then(|text| CustomTheme::parse(&text))
    };
    if let Err(error) = &result {
        tracing::warn!(path = %path.display(), %error, "custom theme not loaded");
    }
    let theme = result?;
    // A misspelt font would fall back without a word, so it is an error like a wrong key.
    let faces = [&theme.fonts.label_family, &theme.fonts.title_family];
    let installed = |face: &&String| pecofence_platform::fonts::font_family_exists(face);
    if let Some(face) = faces.into_iter().flatten().find(|f| !installed(f)) {
        let error = format!(r#"the font "{face}" is not installed"#);
        tracing::warn!(path = %path.display(), %error, "custom theme not loaded");
        return Err(error);
    }
    Ok(Some(theme))
}

/// The themes a new `themes` folder starts with, named in the interface language, so the
/// list has something to pick and a file to copy.
fn example_themes(language: pecofence_core::i18n::Language) -> [(&'static str, &'static str); 10] {
    [
        (
            pecofence_core::i18n::text_in(language, "摩卡拿铁"),
            include_str!("../../../../ui/themes/catppuccin-mocha.json"),
        ),
        (
            pecofence_core::i18n::text_in(language, "东京之夜"),
            include_str!("../../../../ui/themes/tokyo-night.json"),
        ),
        (
            pecofence_core::i18n::text_in(language, "北欧极光"),
            include_str!("../../../../ui/themes/nord.json"),
        ),
        (
            pecofence_core::i18n::text_in(language, "德古拉"),
            include_str!("../../../../ui/themes/dracula.json"),
        ),
        (
            pecofence_core::i18n::text_in(language, "玫瑰松林"),
            include_str!("../../../../ui/themes/rose-pine.json"),
        ),
        (
            pecofence_core::i18n::text_in(language, "常青之森"),
            include_str!("../../../../ui/themes/everforest.json"),
        ),
        (
            pecofence_core::i18n::text_in(language, "月之暗面"),
            include_str!("../../../../ui/themes/one-dark.json"),
        ),
        (
            pecofence_core::i18n::text_in(language, "熔金暖石"),
            include_str!("../../../../ui/themes/gruvbox.json"),
        ),
        (
            pecofence_core::i18n::text_in(language, "神奈冲浪"),
            include_str!("../../../../ui/themes/kanagawa.json"),
        ),
        (
            pecofence_core::i18n::text_in(language, "午夜代码"),
            include_str!("../../../../ui/themes/github-dark.json"),
        ),
    ]
}

/// Writes the example themes into the `themes` folder that 「打开主题文件夹」 just made.
pub(super) fn write_example_themes(dir: &Path) {
    for (name, text) in example_themes(pecofence_core::i18n::language()) {
        let path = dir.join(format!("{name}.json"));
        if let Err(e) = std::fs::write(&path, text) {
            tracing::warn!(path = %path.display(), error = %e, "example theme not written");
        }
    }
}

/// The theme files in the `themes` folder by name, as Settings lists them.
pub(super) fn custom_theme_names(state: &AppState) -> Vec<String> {
    let mut names: Vec<String> = std::fs::read_dir(state.themes_dir())
        .into_iter()
        .flatten()
        .flatten()
        .map(|entry| entry.path())
        .filter(|p| {
            p.is_file()
                && p.extension()
                    .is_some_and(|x| x.eq_ignore_ascii_case("json"))
        })
        .filter_map(|p| Some(p.file_stem()?.to_string_lossy().into_owned()))
        .collect();
    names.sort_by_key(|n| n.to_lowercase());
    names
}

pub(super) fn pick_theme_mode(setting: ThemeSetting, args: &Args) -> ThemeMode {
    if args.light {
        return ThemeMode::Light;
    }
    if args.dark {
        return ThemeMode::Dark;
    }
    match setting {
        ThemeSetting::Light => ThemeMode::Light,
        ThemeSetting::Dark => ThemeMode::Dark,
        ThemeSetting::FollowAppMode => {
            if systheme::apps_use_light_theme() {
                ThemeMode::Light
            } else {
                ThemeMode::Dark
            }
        }
        ThemeSetting::FollowWindowsMode => {
            if systheme::system_uses_light_theme() {
                ThemeMode::Light
            } else {
                ThemeMode::Dark
            }
        }
    }
}

/// Developer knob: `PECOFENCE_ACRYLIC="tint_alpha,luminosity_opacity,blur_sigma_px"` overrides the
/// acrylic recipe so the material can be tuned without rebuilding.
fn tuned_tint(
    mut tint: pecofence_render::backdrop::MicaTint,
) -> pecofence_render::backdrop::MicaTint {
    if let Ok(spec) = pecofence_core::brand::var("PECOFENCE_ACRYLIC") {
        let parts: Vec<f32> = spec
            .split(',')
            .filter_map(|p| p.trim().parse().ok())
            .collect();
        if let [a, lum, sigma, rest @ ..] = &parts[..] {
            let (a, lum, sigma) = (*a, *lum, *sigma);
            tint.color.a = a;
            tint.luminosity_opacity = lum;
            tint.blur_sigma_dip = sigma;
            if let Some(c) = rest.first() {
                tint.chroma = *c;
            }
            tracing::info!(
                a,
                lum,
                sigma,
                chroma = tint.chroma,
                "acrylic recipe overridden via PECOFENCE_ACRYLIC"
            );
        }
    }
    tint
}

pub(super) fn wallpaper_snapshot(
    wallpaper_override: Option<&str>,
) -> Result<wallpaper::WallpaperSnapshot> {
    let mut snapshot = wallpaper::query()?;
    if let Some(p) = wallpaper_override {
        for m in &mut snapshot.monitors {
            m.path = Some(PathBuf::from(p));
        }
    }
    Ok(snapshot)
}

/// Size and last-write time of a wallpaper file (None when it cannot be read).
fn file_stamp(path: &std::path::Path) -> Option<(u64, u64)> {
    use std::os::windows::fs::MetadataExt;
    let meta = std::fs::metadata(path).ok()?;
    Some((meta.file_size(), meta.last_write_time()))
}

/// Everything needed to build one monitor's backdrop. `Send`, so another virtual desktop's
/// wallpaper can be decoded on a worker thread.
#[derive(Clone)]
pub(super) struct MonitorRecipe {
    path: Option<PathBuf>,
    position: WallpaperPosition,
    left: i32,
    top: i32,
    width: i32,
    height: i32,
    /// The bounding box of all monitors, which a Span picture covers.
    span: RECT,
    background: [u8; 3],
    tint: pecofence_render::backdrop::MicaTint,
    downscale: u32,
    decode_divisor: u32,
    /// A capture of the live wallpaper covering this monitor, shown instead of the picture.
    pub(super) live: Option<Arc<Image>>,
    /// Liquid Glass: the blur that frosts a capture (see `show_live`), at this monitor's DPI.
    frost_blur: Option<f32>,
}

impl MonitorRecipe {
    /// Shows `capture` instead of the picture. A capture is a still picture: through clear
    /// glass it would not line up with the video moving around the fence, so Liquid Glass
    /// frosts it like Fluent does, and drops the detail the frost hides.
    pub(super) fn show_live(&mut self, capture: Arc<Image>) {
        if let Some(blur) = self.frost_blur {
            self.tint.blur_sigma_dip = blur;
            self.downscale = 4;
        }
        self.live = Some(capture);
    }

    pub(super) fn rect(&self) -> RECT {
        RECT {
            left: self.left,
            top: self.top,
            right: self.left + self.width,
            bottom: self.top + self.height,
        }
    }

    /// Decode, map, blur and tint: the expensive part (~360 ms for a 4K picture).
    pub(super) fn build_image(&self) -> Result<Image> {
        let decoded;
        let (image, position) = match (&self.live, &self.path) {
            // The capture is this monitor's part of the window already.
            (Some(live), _) => (&**live, WallpaperPosition::Stretch),
            (None, Some(p)) => {
                let (w, h) = (self.width as u32, self.height as u32);
                let span = &self.span;
                let (span_w, span_h) = (
                    (span.right - span.left) as u32,
                    (span.bottom - span.top) as u32,
                );
                let d = match self.position {
                    // One picture pixel is one screen pixel: a smaller decode would shrink it.
                    WallpaperPosition::Center | WallpaperPosition::Tile => {
                        wallpaper::decode_native(
                            p,
                            w,
                            h,
                            self.position == WallpaperPosition::Center,
                        )?
                    }
                    WallpaperPosition::Span => wallpaper::decode_scaled(
                        p,
                        (span_w / self.decode_divisor).max(1),
                        (span_h / self.decode_divisor).max(1),
                    )?,
                    _ => wallpaper::decode_scaled(
                        p,
                        (w / self.decode_divisor).max(1),
                        (h / self.decode_divisor).max(1),
                    )?,
                };
                let picture = Image {
                    width: d.width,
                    height: d.height,
                    bgra: d.bgra,
                };
                if self.position == WallpaperPosition::Span {
                    // This monitor's part, already at the backdrop's size.
                    decoded = pecofence_render::backdrop::map_span(
                        &picture,
                        span_w,
                        span_h,
                        (self.left - span.left) as u32,
                        (self.top - span.top) as u32,
                        w,
                        h,
                        self.downscale,
                        self.background,
                    );
                    (&decoded, WallpaperPosition::Stretch)
                } else {
                    decoded = picture;
                    (&decoded, self.position)
                }
            }
            (None, None) => {
                decoded = Image::solid(1, 1, self.background);
                (&decoded, self.position)
            }
        };
        let MonitorBackdrop { image, .. } = MonitorBackdrop::build(
            image,
            position,
            self.left,
            self.top,
            self.width,
            self.height,
            self.background,
            self.tint,
            self.downscale,
        );
        Ok(image)
    }

    /// Bytes a set with this monitor adds to the backdrop cache (see `BackdropCache`).
    fn estimated_bytes(&self) -> usize {
        let w = (self.width as usize).div_ceil(self.downscale as usize);
        let h = (self.height as usize).div_ceil(self.downscale as usize);
        let full = w * h * 4;
        if self.frost_blur.is_some() {
            // Clear glass: the image the GPU upload takes plus its 8x sampling copy.
            full + w.div_ceil(8) * h.div_ceil(8) * 4
        } else {
            full
        }
    }

    /// The backdrop around an image from [`MonitorRecipe::build_image`]. Clear glass keeps the
    /// half-resolution pixels (a solid colour is monitor-sized too) only until the GPU upload;
    /// contrast sampling uses a copy 8x smaller. Uploading again (device loss) re-decodes.
    pub(super) fn finish(self, image: Image, liquid_glass: bool) -> MonitorBackdrop {
        let backdrop = MonitorBackdrop {
            left: self.left,
            top: self.top,
            width: self.width,
            height: self.height,
            downscale: self.downscale,
            image,
            gpu: None,
        };
        if !liquid_glass {
            return backdrop;
        }
        // A rebuild must reproduce these pixels: a file rewritten in place since is a new
        // wallpaper (the next check replaces the whole set), not this one.
        let stamp = self.path.as_deref().map(file_stamp);
        backdrop.into_gpu_backed(8, move || {
            if self.path.as_deref().map(file_stamp) != stamp {
                tracing::info!("wallpaper file changed; not rebuilding the old set");
                return None;
            }
            match self.build_image() {
                Ok(image) => Some(image),
                Err(error) => {
                    tracing::warn!(%error, "wallpaper rebuild for GPU upload failed");
                    None
                }
            }
        })
    }
}

/// One recipe per live monitor of `snapshot`, with the captures of `live` wallpapers.
pub(super) fn monitor_recipes(
    theme: &Theme,
    snapshot: &wallpaper::WallpaperSnapshot,
    live: &[LiveWallpaper],
) -> Vec<MonitorRecipe> {
    let position = match snapshot.position {
        wallpaper::Position::Center => WallpaperPosition::Center,
        wallpaper::Position::Tile => WallpaperPosition::Tile,
        wallpaper::Position::Stretch => WallpaperPosition::Stretch,
        wallpaper::Position::Fit => WallpaperPosition::Fit,
        wallpaper::Position::Fill => WallpaperPosition::Fill,
        wallpaper::Position::Span => WallpaperPosition::Span,
    };
    let infos = monitors::enumerate();
    // The bounding box of the monitors (not the disconnected outputs, see below).
    let span = snapshot
        .monitors
        .iter()
        .map(|m| m.rect)
        .filter(|r| r.right > r.left && r.bottom > r.top)
        .reduce(|a, b| RECT {
            left: a.left.min(b.left),
            top: a.top.min(b.top),
            right: a.right.max(b.right),
            bottom: a.bottom.max(b.bottom),
        })
        .unwrap_or_default();
    let mut out = Vec::new();
    for m in &snapshot.monitors {
        let w = m.rect.right - m.rect.left;
        let h = m.rect.bottom - m.rect.top;
        // IDesktopWallpaper also lists disconnected outputs with an empty rectangle.
        // They must not become a spurious 1px texture over the live monitor's origin.
        if w <= 0 || h <= 0 {
            continue;
        }
        // Blur is specified in DIPs: scale to this monitor's DPI (200 % → twice the pixels).
        let (cx, cy) = (
            (m.rect.left + m.rect.right) / 2,
            (m.rect.top + m.rect.bottom) / 2,
        );
        let dpi = infos
            .iter()
            .find(|i| {
                cx >= i.bounds.left
                    && cx < i.bounds.right
                    && cy >= i.bounds.top
                    && cy < i.bounds.bottom
            })
            .map(|i| i.dpi)
            .unwrap_or(96)
            .max(96);
        let mut tint = if theme.liquid_glass {
            theme.acrylic_tint()
        } else {
            tuned_tint(theme.acrylic_tint())
        };
        let scale = dpi as f32 / 96.0;
        tint.blur_sigma_dip *= scale;
        let mut recipe = MonitorRecipe {
            path: m.path.clone(),
            position,
            left: m.rect.left,
            top: m.rect.top,
            width: w,
            height: h,
            span,
            background: snapshot.background,
            tint,
            // Clear glass keeps wallpaper detail for refraction, at half the monitor's
            // resolution (a quarter of the texture memory; the GPU scales it up with linear
            // filtering, which the glass shows no sharper). Acrylic discards the detail. A
            // picture scaled to the monitor is decoded at most at the monitor's size (Acrylic:
            // half of it); Center and Tile decode it at its own scale (`build_image`).
            downscale: if theme.liquid_glass { 2 } else { 4 },
            decode_divisor: if theme.liquid_glass { 1 } else { 2 },
            live: None,
            frost_blur: theme.liquid_glass.then_some(
                pecofence_render::backdrop::MicaTint::ACRYLIC_DARK.blur_sigma_dip * scale,
            ),
        };
        if let Some(image) = live
            .iter()
            .find(|l| l.monitor == m.rect)
            .and_then(|l| l.image.clone())
        {
            recipe.show_live(image);
        }
        out.push(recipe);
    }
    out
}

/// `snapshot`'s signature, plus the monitors whose backdrop shows a live wallpaper's capture.
pub(super) fn backdrop_signature(
    snapshot: &wallpaper::WallpaperSnapshot,
    live: &[LiveWallpaper],
) -> String {
    let mut signature = snapshot.signature();
    for m in live.iter().filter(|l| l.image.is_some()).map(|l| l.monitor) {
        signature.push_str(&format!(
            "{LIVE_MARK}{},{},{},{}",
            m.left, m.top, m.right, m.bottom
        ));
    }
    signature
}

/// E_PENDING: the monitor topology or the wallpaper is not ready yet.
fn pending() -> windows_core::Error {
    windows_core::Error::from_hresult(windows_core::HRESULT(0x8000000Au32 as i32))
}

/// Build from the snapshot we fingerprinted, rather than querying a possibly newer desktop.
/// A transient decode failure leaves the last good background on screen and is retried.
fn build_backdrops(
    theme: &Theme,
    snapshot: &wallpaper::WallpaperSnapshot,
    live: &[LiveWallpaper],
) -> Result<Vec<MonitorBackdrop>> {
    let started = std::time::Instant::now();
    let mut out = Vec::new();
    for recipe in monitor_recipes(theme, snapshot, live) {
        let image = recipe.build_image()?;
        out.push(recipe.finish(image, theme.liquid_glass));
    }
    if out.is_empty() {
        return Err(pending());
    }
    tracing::info!(
        position = ?snapshot.position,
        elapsed_ms = started.elapsed().as_millis(),
        count = out.len(),
        "backdrops ready"
    );
    Ok(out)
}

/// All fences share one material. A missing wallpaper or the diagnostic override uses the
/// renderer's solid fallback without introducing a second user-facing material.
fn build_snapshot_backdrops(
    theme: &Theme,
    snapshot: &wallpaper::WallpaperSnapshot,
    live: &[LiveWallpaper],
    signature: &str,
) -> Result<Rc<BackdropSets>> {
    if pecofence_core::brand::var_os("PECOFENCE_SOLID").is_some() {
        return Ok(Rc::new(BackdropSets::default()));
    }
    let backdrops = build_backdrops(theme, snapshot, live)?;
    if signature != backdrop_signature(snapshot, live) {
        // Explorer finished replacing the image while WIC read it. Do not cache that read
        // under the old metadata, or a later desktop round trip could resurrect it.
        return Err(pending());
    }
    Ok(Rc::new(BackdropSets {
        acrylic: Rc::new(backdrops),
    }))
}

/// What the startup worker read and decoded.
struct StartupResult {
    snapshot: wallpaper::WallpaperSnapshot,
    /// `snapshot.signature()` as read right after the query (see `take`).
    signature: String,
    recipes: Vec<MonitorRecipe>,
    images: Vec<Image>,
}

/// How long `StartupBackdrops::finish` waits for Explorer to answer the wallpaper query before
/// the fences go up with the solid backdrop. A responsive Explorer answers within a few ms; at
/// logon or after a large copy it has taken seconds.
const STARTUP_WALLPAPER_WAIT: Duration = Duration::from_millis(150);

/// Shared between the startup worker and the UI thread. One lock covers both fields, so exactly
/// one side acts on the outcome: `finish` takes it when it is already there, otherwise it leaves
/// the control window for the worker to post to.
#[derive(Default)]
struct StartupSlot {
    outcome: Option<std::result::Result<StartupResult, String>>,
    /// The control window (`HWND` as isize) to post `WM_APP_STARTUP_BACKDROPS` to; 0 while
    /// `finish` still waits.
    notify: isize,
}

/// The startup backdrops: the wallpaper query (a COM call into Explorer) and the decode run on
/// a worker thread while the rest of startup runs. `finish` waits for them before the first
/// fence window is created, unless Explorer is slow to answer: the fences then start with the
/// solid backdrop and `App::finish_startup_backdrops` swaps the glass in when it arrives.
pub(super) struct StartupBackdrops {
    slot: Arc<Mutex<StartupSlot>>,
    /// One message when the query has been answered, one when the decode is done.
    stages: std::sync::mpsc::Receiver<()>,
    /// `BackdropCache::generation` when `finish` gave up waiting: a theme or layout change
    /// since makes the late result stale.
    pub(super) generation: u64,
}

impl StartupBackdrops {
    pub(super) fn start(theme: &Theme, wallpaper_override: Option<&str>) -> Self {
        let slot: Arc<Mutex<StartupSlot>> = Arc::default();
        let (stage_tx, stages) = std::sync::mpsc::channel();
        let theme = *theme;
        let wallpaper_override = wallpaper_override.map(str::to_string);
        let work = {
            let slot = slot.clone();
            move || {
                let outcome = pecofence_platform::com::MtaGuard::init().and_then(|_com| {
                    let snapshot = wallpaper_snapshot(wallpaper_override.as_deref());
                    let _ = stage_tx.send(());
                    let snapshot = snapshot?;
                    let signature = snapshot.signature();
                    let recipes = if pecofence_core::brand::var_os("PECOFENCE_SOLID").is_some() {
                        Vec::new()
                    } else {
                        monitor_recipes(&theme, &snapshot, &[])
                    };
                    let images = recipes
                        .iter()
                        .map(MonitorRecipe::build_image)
                        .collect::<Result<Vec<_>>>()?;
                    Ok(StartupResult {
                        snapshot,
                        signature,
                        recipes,
                        images,
                    })
                });
                let notify = match slot.lock() {
                    Ok(mut slot) => {
                        slot.outcome = Some(outcome.map_err(|error| error.to_string()));
                        slot.notify
                    }
                    Err(_) => 0,
                };
                let _ = stage_tx.send(());
                if notify != 0 {
                    window::post_message(
                        HWND(notify as *mut core::ffi::c_void),
                        WM_APP_STARTUP_BACKDROPS,
                        0,
                        0,
                    );
                }
            }
        };
        if let Err(error) = std::thread::Builder::new()
            .name("pecofence-wallpaper-startup".into())
            .spawn(work)
        {
            tracing::warn!(%error, "wallpaper startup thread failed to start");
        }
        Self {
            slot,
            stages,
            generation: 0,
        }
    }

    /// What `build_backdrop_sets` returns, plus the snapshot, from the worker's result. `None`
    /// when Explorer has not answered the query within `STARTUP_WALLPAPER_WAIT`: the worker
    /// then posts `WM_APP_STARTUP_BACKDROPS` to `control` when it is done.
    pub(super) fn finish(
        &mut self,
        theme: &Theme,
        control: HWND,
    ) -> Option<Result<(Rc<BackdropSets>, wallpaper::WallpaperSnapshot, String)>> {
        use std::sync::mpsc::RecvTimeoutError;
        let started = std::time::Instant::now();
        match self.stages.recv_timeout(STARTUP_WALLPAPER_WAIT) {
            Ok(()) => {}
            Err(RecvTimeoutError::Disconnected) => return Some(self.take(theme, started)),
            Err(RecvTimeoutError::Timeout) => {
                let waiting = match self.slot.lock() {
                    Ok(mut slot) if slot.outcome.is_none() => {
                        slot.notify = control.0 as isize;
                        true
                    }
                    _ => false,
                };
                if waiting {
                    tracing::info!(
                        waited_ms = started.elapsed().as_millis(),
                        "wallpaper not answered yet; fences start with the solid backdrop"
                    );
                    return None;
                }
                // The worker finished just now (the lock decides, so it will not post as well).
                return Some(self.take(theme, started));
            }
        }
        // Explorer answered: the decode is waited for as before, so the fences come up with
        // the glass in place.
        let _ = self.stages.recv();
        Some(self.take(theme, started))
    }

    /// Builds the sets from the finished worker's result.
    pub(super) fn take(
        &mut self,
        theme: &Theme,
        started: std::time::Instant,
    ) -> Result<(Rc<BackdropSets>, wallpaper::WallpaperSnapshot, String)> {
        let failed = |message: String| {
            windows_core::Error::new(windows_core::HRESULT(0x8000_4005_u32 as i32), message)
        };
        let result = self
            .slot
            .lock()
            .ok()
            .and_then(|mut slot| slot.outcome.take())
            .ok_or_else(|| failed("wallpaper worker ended without a result".into()))?;
        let StartupResult {
            snapshot,
            signature,
            recipes,
            images,
        } = result.map_err(failed)?;
        if pecofence_core::brand::var_os("PECOFENCE_SOLID").is_some() {
            return Ok((Rc::new(BackdropSets::default()), snapshot, signature));
        }
        let backdrops: Vec<MonitorBackdrop> = recipes
            .into_iter()
            .zip(images)
            .map(|(recipe, image)| recipe.finish(image, theme.liquid_glass))
            .collect();
        if backdrops.is_empty() {
            return Err(pending());
        }
        tracing::info!(
            position = ?snapshot.position,
            waited_ms = started.elapsed().as_millis(),
            count = backdrops.len(),
            "backdrops ready"
        );
        if signature != snapshot.signature() {
            // Explorer finished replacing the image while WIC read it (as in
            // `build_snapshot_backdrops`).
            return Err(pending());
        }
        Ok((
            Rc::new(BackdropSets {
                acrylic: Rc::new(backdrops),
            }),
            snapshot,
            signature,
        ))
    }
}

/// Reads the wallpaper again on a worker thread and asks the control window for a wallpaper
/// check (`WM_APP_WALLPAPER`) when it no longer matches `signature` or cannot be read.
pub(super) fn verify_wallpaper_later(control: HWND, signature: String) {
    let control = control.0 as isize;
    let post = move || {
        window::post_message(
            HWND(control as *mut core::ffi::c_void),
            WM_APP_WALLPAPER,
            0,
            0,
        );
    };
    let spawned = std::thread::Builder::new()
        .name("pecofence-wallpaper-verify".into())
        .spawn(move || {
            let same = pecofence_platform::com::MtaGuard::init()
                .ok()
                .and_then(|_com| wallpaper::signature())
                .is_some_and(|current| current == signature);
            if !same {
                post();
            }
        });
    if spawned.is_err() {
        post();
    }
}

pub(super) fn build_backdrop_sets(
    theme: &Theme,
    wallpaper_override: Option<&str>,
    live: &[LiveWallpaper],
) -> Result<(Rc<BackdropSets>, String)> {
    let snapshot = wallpaper_snapshot(wallpaper_override)?;
    let signature = backdrop_signature(&snapshot, live);
    let backdrops = build_snapshot_backdrops(theme, &snapshot, live, &signature)?;
    Ok((backdrops, signature))
}

/// Another virtual desktop's wallpaper, decoded on a worker thread ahead of a switch there:
/// a cache miss at switch time (a 4K decode) outlasts the switch animation, so the fences
/// would arrive showing the previous desktop's picture.
pub(super) struct PrewarmJob {
    signature: String,
    /// `BackdropCache::generation` and material when the job started.
    generation: u64,
    liquid_glass: bool,
    snapshot: wallpaper::WallpaperSnapshot,
    recipes: Vec<MonitorRecipe>,
    result: Arc<Mutex<Option<std::result::Result<Vec<Image>, String>>>>,
}

/// The other virtual desktops' pictures laid out like `current` (same position, colour and
/// monitors), nearest desktop first since Ctrl+Win+Arrow moves one step. Desktops without a
/// picture of their own, and a picture already listed (in any spelling), are skipped.
fn other_desktop_snapshots(
    current: &wallpaper::WallpaperSnapshot,
    desktops: &[([u8; 16], Option<PathBuf>)],
    current_id: Option<[u8; 16]>,
) -> Vec<wallpaper::WallpaperSnapshot> {
    let here = current_id
        .and_then(|id| desktops.iter().position(|(d, _)| *d == id))
        .unwrap_or(0) as isize;
    let mut order: Vec<(isize, &PathBuf)> = desktops
        .iter()
        .enumerate()
        .filter_map(|(i, (_, path))| Some((i as isize - here, path.as_ref()?)))
        .filter(|(distance, _)| *distance != 0)
        .collect();
    // Nearest first; to the right before to the left at the same distance.
    order.sort_by_key(|(distance, _)| (distance.abs(), *distance < 0));
    let mut seen: Vec<String> = Vec::new();
    let mut out = Vec::new();
    for (_, path) in order {
        let key = path.to_string_lossy().to_lowercase();
        if seen.contains(&key) {
            continue;
        }
        seen.push(key);
        let mut snapshot = current.clone();
        for m in &mut snapshot.monitors {
            if m.rect.right > m.rect.left && m.rect.bottom > m.rect.top {
                m.path = Some(path.clone());
            }
        }
        out.push(snapshot);
    }
    out
}

pub(super) fn backdrop_mode_for(b: pecofence_core::Backdrop) -> BackdropMode {
    match b {
        pecofence_core::Backdrop::Acrylic => BackdropMode::Acrylic,
    }
}

pub(super) fn icon_variant_for(s: &pecofence_core::IconSettings) -> IconVariant {
    IconVariant {
        tint: s.tint_rgb,
        tint_strength: (s.tint_strength.clamp(0.0, 1.0) * 100.0).round() as u8,
        chameleon: s.chameleon,
        shortcut_arrows: s.shortcut_arrows,
    }
}

pub(super) fn fence_style_for(f: &pecofence_core::Fence) -> FenceStyle {
    let a = f.appearance.as_ref();
    let rgb = |c: [u8; 3]| pecofence_render::ColorF::from_rgba8(c[0], c[1], c[2], 0xFF);
    FenceStyle {
        tint: a.and_then(|a| a.tint_rgb).map(rgb),
        tint_title_only: a.is_some_and(|a| a.tint_title_only),
        title_color: a.and_then(|a| a.title_rgb).map(rgb),
        title_size: match a.and_then(|a| a.title_size).unwrap_or_default() {
            TitleSize::Small => 0,
            TitleSize::Normal => 1,
            TitleSize::Large => 2,
            TitleSize::ExtraLarge => 3,
        },
        // Global (标题对齐, 标签栏位置, the count and chevron): the window takes them from
        // `Behavior` at draw time.
        title_align: pecofence_core::TitleAlign::Left,
        tab_rail: 0.0,
        hide_count_and_chevron: false,
    }
}

pub(super) fn shadow_style_for(theme: &Theme) -> ShadowStyle {
    let mut shadow = match theme.mode {
        ThemeMode::Dark => ShadowStyle::DARK,
        ThemeMode::Light => ShadowStyle::LIGHT,
    };
    if theme.liquid_glass {
        shadow.sigma = 12.0;
        shadow.offset_y = 5.0;
    }
    shadow.radius = theme.corner_radius;
    let custom = theme.shadow;
    shadow.opacity = custom.opacity.unwrap_or(shadow.opacity);
    shadow.sigma = custom.blur.unwrap_or(shadow.sigma);
    shadow.offset_y = custom.offset.unwrap_or(shadow.offset_y);
    shadow
}

pub(super) fn tray_icon_image(size: i32, _accent: [u8; 3], _dark: bool) -> Vec<u8> {
    // The product icon: the shipped Nodra icon as 64×64 straight BGRA
    // (`assets/nodra-64.bgra`, rendered full-bleed from Nodra.svg by the icon script),
    // premultiplied once, box-filtered down to the asked size and clipped to the rounded
    // plate (corners of 22 % of the side, transparent outside), so the footprint of the
    // icon is unchanged. The tray and the settings caption ask for 16–48 px at the DPI in
    // play; sizes above the source keep its 64 px. Premultiplied BGRA out.
    const SRC: usize = 64;
    const MARK: &[u8; SRC * SRC * 4] = include_bytes!("../../assets/nodra-64.bgra");
    let dst = size.clamp(8, SRC as i32) as usize;
    let mut plate = [0u8; SRC * SRC * 4];
    for (px, src) in plate.chunks_exact_mut(4).zip(MARK.chunks_exact(4)) {
        let a = src[3] as u32;
        for c in 0..3 {
            px[c] = ((src[c] as u32 * a + 127) / 255) as u8;
        }
        px[3] = src[3];
    }
    let mut out = vec![0u8; dst * dst * 4];
    for y in 0..dst {
        let sy0 = y * SRC / dst;
        let sy1 = ((y + 1) * SRC / dst).max(sy0 + 1).min(SRC);
        for x in 0..dst {
            let sx0 = x * SRC / dst;
            let sx1 = ((x + 1) * SRC / dst).max(sx0 + 1).min(SRC);
            let (mut sum, mut count) = ([0u32; 4], 0u32);
            for sy in sy0..sy1 {
                for sx in sx0..sx1 {
                    let i = (sy * SRC + sx) * 4;
                    for c in 0..4 {
                        sum[c] += plate[i + c] as u32;
                    }
                    count += 1;
                }
            }
            let o = (y * dst + x) * 4;
            for c in 0..4 {
                out[o + c] = (sum[c] / count) as u8;
            }
        }
    }
    // The plate mask: the rounded square the replaced glyph sat on, applied at the output
    // resolution so the edge stays one antialiased pixel wide.
    let (half, radius) = (dst as f32 / 2.0, 0.22 * dst as f32);
    for y in 0..dst {
        for x in 0..dst {
            let dx = (x as f32 + 0.5 - half).abs() - (half - radius);
            let dy = (y as f32 + 0.5 - half).abs() - (half - radius);
            let distance = dx.max(0.0).hypot(dy.max(0.0)) + dx.max(dy).min(0.0) - radius;
            let coverage = (0.5 - distance).clamp(0.0, 1.0);
            if coverage < 1.0 {
                let i = (y * dst + x) * 4;
                for c in 0..4 {
                    out[i + c] = (out[i + c] as f32 * coverage).round() as u8;
                }
            }
        }
    }
    out
}

impl App {
    /// Starts decoding the nearest other virtual desktop's wallpaper that is not cached yet,
    /// if the cache has room for it without evicting a visited desktop.
    pub(super) fn prewarm_wallpapers(&mut self) {
        if self.prewarm.is_some()
            || self.wallpaper_override.is_some()
            || pecofence_core::brand::var_os("PECOFENCE_SOLID").is_some()
        {
            return;
        }
        let Some(current) = self.wallpaper_sig.clone() else {
            return;
        };
        let Ok(snapshot) = wallpaper::query() else {
            return;
        };
        if snapshot.signature() != current {
            // A switch or a wallpaper change in progress: its signal re-arms this.
            return;
        }
        let theme = *self.ctx.theme.borrow();
        let candidates = other_desktop_snapshots(
            &snapshot,
            &wallpaper::desktop_wallpapers(),
            wallpaper::desktop_id(),
        );
        for candidate in candidates {
            if candidate
                .monitors
                .iter()
                .filter_map(|m| m.path.as_deref())
                .any(|p| !p.is_file())
            {
                continue;
            }
            let signature = candidate.signature();
            if signature.eq_ignore_ascii_case(&current) || self.wallpaper_cache.contains(&signature)
            {
                continue;
            }
            let recipes = monitor_recipes(&theme, &candidate, &[]);
            let bytes = recipes.iter().map(MonitorRecipe::estimated_bytes).sum();
            if recipes.is_empty() || !self.wallpaper_cache.has_room(bytes) {
                tracing::debug!(bytes, "no room to prepare another desktop's wallpaper");
                return;
            }
            let result = Arc::new(Mutex::new(None));
            let spawned = {
                let recipes = recipes.clone();
                let result = result.clone();
                let control = self.control.hwnd().0 as isize;
                std::thread::Builder::new()
                    .name("pecofence-wallpaper-prewarm".into())
                    .spawn(move || {
                        let images = pecofence_platform::com::MtaGuard::init()
                            .and_then(|_com| {
                                recipes
                                    .iter()
                                    .map(MonitorRecipe::build_image)
                                    .collect::<Result<Vec<_>>>()
                            })
                            .map_err(|error| error.to_string());
                        if let Ok(mut slot) = result.lock() {
                            *slot = Some(images);
                        }
                        window::post_message(
                            HWND(control as *mut core::ffi::c_void),
                            WM_APP_PREWARM_DONE,
                            0,
                            0,
                        );
                    })
            };
            if let Err(error) = spawned {
                tracing::warn!(%error, "wallpaper prewarm thread failed to start");
                return;
            }
            tracing::debug!(%signature, "preparing another desktop's wallpaper");
            self.prewarm = Some(PrewarmJob {
                signature,
                generation: self.wallpaper_cache.generation(),
                liquid_glass: theme.liquid_glass,
                snapshot: candidate,
                recipes,
                result,
            });
            return;
        }
    }

    /// The startup wallpaper worker finished after the fences went up with the solid backdrop
    /// (Explorer was slow to answer): the glass comes in now, as for a wallpaper change.
    pub(super) fn finish_startup_backdrops(&mut self) {
        let Some(mut job) = self.startup_backdrops.take() else {
            return;
        };
        let control = self.control.hwnd();
        if job.generation != self.wallpaper_cache.generation() || self.wallpaper_sig.is_some() {
            // A theme or layout change, or a wallpaper check, got there first (as in
            // `finish_prewarm`): a read from before it must not be cached or shown.
            tracing::debug!("startup wallpaper arrived late and is stale; discarded");
            if self.wallpaper_sig.is_none() {
                window::post_message(control, WM_APP_WALLPAPER, 0, 0);
            }
            return;
        }
        let theme = *self.ctx.theme.borrow();
        match job.take(&theme, Instant::now()) {
            Ok((backdrops, snapshot, signature)) => {
                self.wallpaper_cache.insert(signature, backdrops);
                self.follow_snapshot(&snapshot, "startup");
                // The registry watchers were up before this snapshot was taken, so only the
                // other desktops are left to prepare (as the normal startup path does).
                window::set_timer(control, TIMER_WALLPAPER_PREWARM, WALLPAPER_PREWARM_DELAY_MS);
            }
            Err(error) => {
                tracing::warn!(%error, "wallpaper unavailable at startup; solid backdrop");
                // Not readable: keep trying as for a signal (as the normal startup path does).
                window::post_message(control, WM_APP_WALLPAPER, 0, 0);
            }
        }
    }

    /// The worker finished: cache the set (uploading clear glass right away, so its pixels
    /// leave process memory) unless the theme, layout or file changed meanwhile, then
    /// prepare the next desktop.
    pub(super) fn finish_prewarm(&mut self) {
        let Some(job) = self.prewarm.take() else {
            return;
        };
        let Some(result) = job.result.lock().ok().and_then(|mut slot| slot.take()) else {
            self.prewarm = Some(job);
            return;
        };
        let images = match result {
            Ok(images) => images,
            Err(error) => {
                tracing::debug!(%error, "another desktop's wallpaper could not be prepared");
                return;
            }
        };
        let liquid_glass = self.ctx.theme.borrow().liquid_glass;
        if job.generation != self.wallpaper_cache.generation()
            || job.liquid_glass != liquid_glass
            || job.snapshot.signature() != job.signature
        {
            tracing::debug!("prepared wallpaper is stale; discarded");
            self.prewarm_wallpapers();
            return;
        }
        let set: Rc<Vec<MonitorBackdrop>> = Rc::new(
            job.recipes
                .into_iter()
                .zip(images)
                .map(|(recipe, image)| recipe.finish(image, liquid_glass))
                .collect(),
        );
        let backdrops = Rc::new(BackdropSets {
            acrylic: set.clone(),
        });
        if !self
            .wallpaper_cache
            .insert_if_room(job.signature, backdrops)
        {
            return;
        }
        if liquid_glass
            && let Err(error) = self
                .ctx
                .bitmaps
                .borrow_mut()
                .preload_wallpaper(&self.ctx.stack, &set)
        {
            // The first draw uploads it instead.
            tracing::debug!(%error, "prepared wallpaper upload deferred");
        }
        tracing::info!("wallpaper prepared for another desktop");
        self.prewarm_wallpapers();
    }

    /// A wallpaper signal or the 5 s poll: follows the Windows wallpaper and the live
    /// wallpapers over it, and captures those that are due.
    pub(super) fn check_wallpaper(&mut self, reason: &str) {
        let Ok(snapshot) = wallpaper_snapshot(self.wallpaper_override.as_deref()) else {
            return;
        };
        self.follow_snapshot(&snapshot, reason);
    }

    /// What a check does once the wallpaper has been read (also run on the startup snapshot,
    /// whose read happened on a worker).
    pub(super) fn follow_snapshot(
        &mut self,
        snapshot: &wallpaper::WallpaperSnapshot,
        reason: &str,
    ) {
        self.detect_live_wallpapers(snapshot);
        self.show_wallpaper(snapshot, reason);
        self.capture_live_wallpapers(LIVE_REFRESH);
    }

    /// Wallpaper-only refresh: reuse a recent desktop's pixels and preserve icon/geometry
    /// caches. Failed reads must not advance the signature, so the next check can retry.
    fn show_wallpaper(&mut self, snapshot: &wallpaper::WallpaperSnapshot, reason: &str) {
        let signature = backdrop_signature(snapshot, &self.live);
        if self.wallpaper_sig.as_ref() == Some(&signature) {
            return;
        }
        // The same files with new contents: the old set can never be shown again. Drop it
        // before inserting the new one so the byte cap does not evict another desktop's set.
        if let Some(old) = self.wallpaper_sig.as_deref()
            && supersedes(old, &signature)
        {
            self.wallpaper_cache.remove(old);
        }
        let started = Instant::now();
        let cached = self.wallpaper_cache.get(&signature);
        let cache_hit = cached.is_some();
        let backdrops = match cached {
            Some(backdrops) => backdrops,
            None => match build_snapshot_backdrops(
                &self.ctx.theme.borrow(),
                snapshot,
                &self.live,
                &signature,
            ) {
                Ok(backdrops) => {
                    self.wallpaper_cache
                        .insert(signature.clone(), backdrops.clone());
                    backdrops
                }
                Err(error) => {
                    tracing::debug!(reason, %error, "wallpaper not ready; retaining last backdrop");
                    return;
                }
            },
        };
        self.wallpaper_sig = Some(signature);
        *self.ctx.backdrops.borrow_mut() = backdrops.clone();
        for window in self.fences.values() {
            window.set_backdrops(backdrops.clone());
        }
        tracing::info!(
            reason,
            cache_hit,
            elapsed_ms = started.elapsed().as_millis(),
            "wallpaper refreshed"
        );
    }

    pub(super) fn on_system_settings_changed(&mut self) {
        self.refresh_language();
        self.ctx
            .motion
            .set_enabled(sysparams::client_area_animation());
        self.ctx
            .behavior
            .wheel_lines
            .set(sysparams::wheel_scroll_lines());
        self.apply_fonts();
        // Any broadcast that reaches us after the work area moved (taskbar, DPI, resolution
        // races) must re-layout, or every later set_fence_bounds normalizes against a stale
        // work area and the saved geometry drifts by the taskbar height. Once the monitors
        // settled, like a display change.
        let fresh = work_areas();
        if fresh != self.state.work_areas {
            tracing::info!("work areas changed behind a settings broadcast; re-laying out");
            window::set_timer(self.control.hwnd(), TIMER_WORKAREA, DISPLAY_SETTLE_MS);
            return;
        }
        self.refresh_visuals(false);
    }

    /// Icon labels follow the desktop's icon-title font (`SPI_GETICONTITLELOGFONT` times the
    /// Accessibility text-size factor, both re-read on WM_SETTINGCHANGE) unless the custom
    /// theme names its own, and titles the theme's title font. When a font changed, every
    /// fence refits its labels and re-lays out its grid, then settles its auto height.
    pub(super) fn apply_fonts(&mut self) {
        let fonts = self
            .custom_theme
            .as_ref()
            .map(|c| c.fonts.clone())
            .unwrap_or_default();
        let titles = self
            .ctx
            .chrome
            .set_title_font(fonts.title_family.as_deref(), fonts.title_weight)
            .unwrap_or(false);
        let system = sysparams::icon_title_font();
        let text_scale = sysparams::text_scale_percent() as f32 / 100.0;
        let family = fonts
            .label_family
            .clone()
            .or_else(|| system.as_ref().map(|f| f.family.clone()));
        let labels = family.as_ref().is_some_and(|family| {
            let size = fonts
                .label_size
                .map(|s| s * text_scale)
                .or(system.as_ref().map(|f| f.size_dip))
                .unwrap_or(12.0 * text_scale);
            let weight = fonts
                .label_weight
                .or(system.as_ref().map(|f| f.weight))
                .unwrap_or(400);
            self.ctx
                .chrome
                .set_icon_title_font(family, size, pecofence_render::FontWeight(weight))
                .unwrap_or(false)
        });
        if !titles && !labels {
            return;
        }
        tracing::info!(label = ?family, title = ?fonts.title_family, "fonts changed");
        let ids: Vec<FenceId> = self.fences.keys().copied().collect();
        for id in ids {
            if let Some(w) = self.fences.get(&id) {
                w.on_icon_font_changed();
            }
            self.apply_auto_height(id);
        }
    }

    /// Watches the `themes` folder once it exists; a watcher ends when its folder goes away.
    pub(super) fn sync_theme_watcher(&mut self) {
        if self.theme_watcher.as_ref().is_some_and(|w| w.is_running()) {
            return;
        }
        self.theme_watcher = None;
        let dir = self.state.themes_dir();
        if !dir.is_dir() {
            return;
        }
        let control = self.control.hwnd().0 as isize;
        let watcher = DirWatcher::start(&dir, move |_| {
            window::post_message(
                HWND(control as *mut core::ffi::c_void),
                WM_APP_THEMES_CHANGED,
                0,
                0,
            );
        });
        match watcher {
            Ok(w) => self.theme_watcher = Some(w),
            Err(e) => tracing::warn!(dir = %dir.display(), error = %e, "themes watcher failed"),
        }
    }

    /// A theme file was saved, added or removed: the fences take the chosen file as it is now,
    /// and Settings lists the folder again.
    pub(super) fn on_themes_changed(&mut self) {
        self.refresh_visuals(false);
        self.push_settings_state();
    }

    pub(super) fn refresh_visuals(&mut self, force: bool) {
        let mode = self.theme_override.unwrap_or_else(|| {
            pick_theme_mode(
                self.state.config.settings.theme,
                &Args {
                    light: false,
                    dark: false,
                    wallpaper_override: None,
                    portable: false,
                    no_hide_icons: false,
                    exit_after_ms: None,
                    dump_stats: false,
                    open_settings: false,
                    portal: None,
                    test_script: None,
                    instance: None,
                },
            )
        });
        let accent = systheme::accent_palette();
        let accent_changed = accent != self.accent;
        let loaded = load_custom_theme(&self.state);
        self.custom_theme_error = loaded.as_ref().err().cloned();
        let custom = loaded.ok().flatten();
        let style = custom
            .as_ref()
            .map_or(self.state.config.settings.theme_style, |c| c.base);
        let style_changed = self.ctx.theme.borrow().liquid_glass
            != (style == pecofence_core::ThemeStyle::LiquidGlass)
            || custom != self.custom_theme;
        if mode == self.theme_mode && !style_changed && !accent_changed && !force {
            return;
        }
        let theme_changed = mode != self.theme_mode || style_changed;
        let theme = theme_for(mode, style, custom.as_ref(), accent.as_ref());
        self.custom_theme = custom;
        if style_changed {
            // Before the fences take the theme, so their title rows lay out in its font.
            self.apply_fonts();
        }
        // The wallpaper sets are accent-independent and expensive: rebuild them only for a
        // mode change (or a forced refresh), not for a Settings › Colours retint.
        let backdrops = if theme_changed || force {
            // Theme/DPI/layout changes invalidate cached material recipes and coordinates.
            self.wallpaper_cache.clear();
            window::set_timer(
                self.control.hwnd(),
                TIMER_WALLPAPER_PREWARM,
                WALLPAPER_PREWARM_DELAY_MS,
            );
            match build_backdrop_sets(&theme, self.wallpaper_override.as_deref(), &self.live) {
                Ok((backdrops, signature)) => {
                    self.wallpaper_cache
                        .insert(signature.clone(), backdrops.clone());
                    self.wallpaper_sig = Some(signature);
                    backdrops
                }
                Err(error) => {
                    tracing::warn!(%error, "backdrop refresh deferred until wallpaper is readable");
                    self.wallpaper_sig = None;
                    window::post_message(self.control.hwnd(), WM_APP_WALLPAPER, 0, 0);
                    self.ctx.backdrops.borrow().clone()
                }
            }
        } else {
            self.ctx.backdrops.borrow().clone()
        };
        if mode != self.theme_mode {
            tray::set_dark_menus(mode == ThemeMode::Dark);
        }
        self.theme_mode = mode;
        self.accent = accent;
        *self.ctx.theme.borrow_mut() = theme;
        *self.ctx.backdrops.borrow_mut() = backdrops.clone();
        // Icon bitmaps are accent-independent: an accent-only change (Settings > Colours)
        // keeps them; a mode change or a forced refresh re-extracts them.
        if theme_changed || force {
            // Wallpaper uploads follow their backdrop set: a rebuilt set uploads afresh.
            self.ctx.bitmaps.borrow_mut().clear_keyed();
        }
        let shadow = shadow_style_for(&theme);
        self.ctx.shadow_style.set(shadow);
        if let Some(h) = &self.settings {
            if theme_changed {
                h.set_theme(mode, theme.liquid_glass);
            }
            self.push_settings_state();
        }
        for w in self.fences.values() {
            w.set_theme(theme, backdrops.clone(), shadow);
        }
        // Leaving Liquid Glass stops the draws that would otherwise release old textures.
        self.ctx.bitmaps.borrow_mut().prune_wallpapers();
        if style_changed {
            // Liquid Glass needs about 60 MB more GPU memory than Fluent: the next idle point
            // reads the new style's baseline instead of rebuilding the render stack for it.
            self.gpu_baseline = None;
        }
        tracing::info!(?mode, ?style, accent = ?accent.map(|a| a.accent), "theme refreshed");
    }

    /// Global icon tint / chameleon / shortcut arrows changed: flush the caches and let icons
    /// reload processed.
    pub(super) fn apply_icon_variant(&mut self) {
        let variant = icon_variant_for(&self.state.config.settings.icons);
        if self.ctx.icons.borrow_mut().set_variant(variant) {
            self.ctx.bitmaps.borrow_mut().clear_keyed();
            for w in self.fences.values() {
                w.drop_icons();
            }
        }
    }
}

#[cfg(test)]
mod prewarm_tests {
    use super::other_desktop_snapshots;
    use pecofence_platform::RECT;
    use pecofence_platform::wallpaper::{MonitorWallpaper, Position, WallpaperSnapshot};
    use std::path::PathBuf;

    #[test]
    fn other_desktops_nearest_first_each_picture_once() {
        let rect = |right| RECT {
            left: 0,
            top: 0,
            right,
            bottom: 10,
        };
        let current = WallpaperSnapshot {
            position: Position::Fill,
            background: [0, 0, 0],
            monitors: vec![
                MonitorWallpaper {
                    monitor_id: "live".into(),
                    rect: rect(10),
                    path: Some("C:/here.jpg".into()),
                },
                // Disconnected output: stays without a picture.
                MonitorWallpaper {
                    monitor_id: "gone".into(),
                    rect: rect(0),
                    path: None,
                },
            ],
        };
        let desk = |n: u8, path: Option<&str>| ([n; 16], path.map(PathBuf::from));
        let desktops = [
            desk(0, Some("C:/a.jpg")),
            desk(1, Some("C:/b.jpg")),
            desk(2, Some("C:/here.jpg")),
            desk(3, None),
            desk(4, Some("C:/A.JPG")),
            desk(5, Some("C:/c.jpg")),
        ];
        let paths: Vec<Vec<Option<PathBuf>>> =
            other_desktop_snapshots(&current, &desktops, Some([2; 16]))
                .into_iter()
                .map(|s| s.monitors.into_iter().map(|m| m.path).collect())
                .collect();
        let p = |s: &str| Some(PathBuf::from(s));
        assert_eq!(
            paths,
            vec![
                // The current desktop (2) and desktop 3 (no picture of its own) are skipped;
                // desktop 4's picture is desktop 0's in another spelling, listed once.
                vec![p("C:/b.jpg"), None],
                vec![p("C:/A.JPG"), None],
                vec![p("C:/c.jpg"), None],
            ]
        );
    }
}

#[cfg(test)]
mod tray_icon_tests {
    use super::tray_icon_image;

    /// Premultiplied, with the rounded plate of the replaced glyph: transparent corners, an
    /// opaque centre (the picture is fully opaque).
    #[test]
    fn tray_icon_is_premultiplied_with_rounded_corners() {
        for size in [16, 20, 24, 32, 48] {
            let px = tray_icon_image(size, [0, 0, 0], true);
            assert_eq!(px.len(), (size * size * 4) as usize);
            assert!(px.chunks(4).any(|c| c[3] > 0), "empty mark at {size}");
            for c in px.chunks(4) {
                assert!(
                    c[0] <= c[3] && c[1] <= c[3] && c[2] <= c[3],
                    "not premultiplied"
                );
            }
            assert!(
                px[3] < 40,
                "corner pixel must be (nearly) transparent at {size}"
            );
            let centre = (((size / 2) * size + size / 2) * 4) as usize;
            assert_eq!(px[centre + 3], 255, "plate must be opaque at {size}");
        }
    }

    /// Writes raw BGRA dumps for a visual check: `cargo test -p pecofence tray_icon_dump -- --ignored`.
    #[test]
    #[ignore]
    fn tray_icon_dump() {
        for size in [16, 20, 24, 32, 48, 64] {
            let px = tray_icon_image(size, [0, 0, 0], true);
            std::fs::write(format!("../../.cache/tray-{size}.bgra"), px).unwrap();
        }
    }
}

#[cfg(test)]
mod example_theme_tests {
    use super::{CustomTheme, example_themes};

    /// Every example loads, names no font (a missing font would refuse the theme) and gets a
    /// file name of its own in every language.
    #[test]
    fn example_themes_load_with_distinct_names() {
        for &language in pecofence_core::i18n::SUPPORTED {
            let themes = example_themes(language);
            for (name, text) in themes {
                let theme = CustomTheme::parse(text).unwrap_or_else(|e| panic!("{name}: {e}"));
                assert_eq!(theme.fonts, Default::default(), "{name}");
                assert!(!name.contains(['/', '\\', ':', '*', '?', '"', '<', '>', '|']));
            }
            let mut names: Vec<_> = themes.iter().map(|(n, _)| *n).collect();
            names.sort();
            names.dedup();
            assert_eq!(names.len(), 10, "{language:?}");
        }
    }
}
