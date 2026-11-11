//! Hilo del motor de cristal: un solo hilo para la GPU, la composición y la captura.
//!
//! En reposo (ninguna lámina) duerme sin despertarse. Con láminas visibles:
//! - redibuja a la frecuencia de la pantalla solo mientras el borde se mueve o la ventana
//!   se está arrastrando;
//! - repite el desenfoque solo cuando llega una captura nueva (máximo 30 Hz);
//! - si no pasa nada, mira cada poco si la ventana se ha movido u ocultado.

use std::f64::consts::TAU;
use std::sync::Arc;
use std::sync::mpsc::{Receiver, TryRecvError};
use std::time::{Duration, Instant};

use serde::Serialize;
use tauri::{AppHandle, Emitter};
use windows::UI::Composition::Compositor;
use windows::Win32::Foundation::{HWND, POINT, RECT};
use windows::Win32::Graphics::Dwm::DwmFlush;
use windows::Win32::Graphics::Gdi::{
    ClientToScreen, HMONITOR, MONITOR_DEFAULTTONEAREST, MonitorFromWindow,
};
use windows::Win32::System::Threading::INFINITE;
use windows::Win32::System::WinRT::{
    CreateDispatcherQueueController, DQTAT_COM_NONE, DQTYPE_THREAD_CURRENT, DispatcherQueueOptions,
    RO_INIT_SINGLETHREADED, RoInitialize,
};
use windows::Win32::UI::HiDpi::GetDpiForWindow;
use windows::Win32::UI::WindowsAndMessaging::{
    DispatchMessageW, GetClientRect, IsIconic, IsWindow, IsWindowVisible, MSG, MWMO_INPUTAVAILABLE,
    MsgWaitForMultipleObjectsEx, PM_REMOVE, PeekMessageW, QS_ALLINPUT, SetWindowDisplayAffinity,
    TranslateMessage, WDA_EXCLUDEFROMCAPTURE, WDA_NONE,
};

use super::capture::MonitorCapture;
use super::compositor::Layers;
use super::occlusion;
use super::quality::{self, Level, Limits, Motion, Preference, SystemState};
use super::renderer::{GlassParams, Gpu, MAX_SHAPES, Mode, Targets};
use super::{GlassOptions, Shape, Wake};

pub enum Cmd {
    Attach {
        label: String,
        hwnd: isize,
        options: GlassOptions,
    },
    Options {
        label: String,
        options: GlassOptions,
    },
    Shapes {
        label: String,
        shapes: Vec<Shape>,
    },
    Poke {
        label: String,
    },
    Detach {
        label: String,
    },
    Game(bool),
}

/// Lo que ve la interfaz (galería de ejemplos y, más adelante, Ajustes).
#[derive(Clone, Debug, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct Stats {
    pub requested: Preference,
    pub effective: Level,
    pub reason: Option<&'static str>,
    /// Fotogramas dibujados por segundo en esta ventana (0 si está quieta).
    pub fps: f32,
    /// Tiempo de GPU por fotograma (todas las ventanas), en ms.
    pub gpu_ms: Option<f32>,
    /// Carga aproximada de GPU del motor: ms por fotograma × fotogramas por segundo.
    pub gpu_load: Option<f32>,
    /// Capturas nuevas por segundo (solo cambia lo de detrás).
    pub capture_fps: Option<f32>,
    pub adapter: String,
    pub animating: bool,
    /// El motor no puede dibujar en esta ventana: la interfaz usa el tinte de CSS.
    pub failed: Option<String>,
}

const STATS_EVERY: Duration = Duration::from_millis(500);
const SYSTEM_EVERY: Duration = Duration::from_secs(2);
/// Sin animación, cada cuánto se mira si la ventana se ha movido u ocultado.
const IDLE_POLL_MS: u32 = 100;
/// Cada cuánto se mira si otras ventanas tapan del todo a una ventana con cristal.
const OCCLUSION_EVERY: Duration = Duration::from_millis(250);
/// Cuánto sigue viva una captura que ya nadie necesita.
const CAPTURE_LINGER: Duration = Duration::from_secs(2);
/// Mientras se arrastra una ventana se redibuja a la frecuencia de la pantalla.
const MOVING_FOR: Duration = Duration::from_millis(400);
/// Una vuelta completa del ruido del borde a velocidad 1 (s).
const LOOP_S: f64 = 9.0;
/// Al interactuar, cuánto sigue ondulando antes de frenarse (s).
const POKE_FOR: Duration = Duration::from_millis(2500);
/// Si cada fotograma tarda en la GPU más que esto (la mitad de un fotograma a 60 Hz)
/// durante unos segundos, se baja un nivel.
const GPU_SLOW_MS: f32 = 8.0;
const GPU_SLOW_FOR: Duration = Duration::from_secs(5);
/// El borde líquido se mueve despacio: a 30 fotogramas por segundo no se nota la diferencia
/// y cuesta la mitad. Al arrastrar la ventana se sigue redibujando a la frecuencia de la pantalla.
const ANIM_INTERVAL: Duration = Duration::from_millis(33);

pub fn run(rx: Receiver<Cmd>, wake: Arc<Wake>, app: AppHandle) {
    // La composición de Windows necesita WinRT y una cola de mensajes en este hilo.
    // SAFETY: inicialización por hilo; se hace una sola vez al empezar.
    if let Err(err) = unsafe { RoInitialize(RO_INIT_SINGLETHREADED) } {
        eprintln!("[nyx] cristal: RoInitialize: {err}");
    }
    let options = DispatcherQueueOptions {
        dwSize: size_of::<DispatcherQueueOptions>() as u32,
        threadType: DQTYPE_THREAD_CURRENT,
        apartmentType: DQTAT_COM_NONE,
    };
    // SAFETY: crea la cola de este hilo; se mantiene viva hasta salir de run().
    let _queue = match unsafe { CreateDispatcherQueueController(options) } {
        Ok(q) => Some(q),
        Err(err) => {
            eprintln!("[nyx] cristal: sin DispatcherQueue: {err}");
            None
        }
    };

    let mut engine = Engine::new(app, wake.clone());
    loop {
        pump_messages();
        loop {
            match rx.try_recv() {
                Ok(cmd) => engine.handle(cmd),
                Err(TryRecvError::Empty) => break,
                Err(TryRecvError::Disconnected) => return,
            }
        }
        match engine.tick() {
            Next::Frame => {
                // Espera a la siguiente composición de Windows (ritmo de la pantalla).
                // SAFETY: sin parámetros.
                if unsafe { DwmFlush() }.is_err() {
                    std::thread::sleep(Duration::from_millis(16));
                }
            }
            Next::Wait(ms) => {
                // SAFETY: el evento sigue vivo mientras exista `wake`.
                unsafe {
                    MsgWaitForMultipleObjectsEx(
                        Some(&[wake.handle()]),
                        ms,
                        QS_ALLINPUT,
                        MWMO_INPUTAVAILABLE,
                    );
                }
            }
        }
    }
}

fn pump_messages() {
    let mut msg = MSG::default();
    // SAFETY: bucle de mensajes estándar del hilo actual.
    unsafe {
        while PeekMessageW(&mut msg, None, 0, 0, PM_REMOVE).as_bool() {
            let _ = TranslateMessage(&msg);
            DispatchMessageW(&msg);
        }
    }
}

enum Next {
    Frame,
    Wait(u32),
}

struct Surface {
    label: String,
    hwnd: HWND,
    options: GlassOptions,
    shapes: Vec<Shape>,
    // `layers` antes que `targets`: el árbol de composición se suelta primero.
    layers: Layers,
    targets: Targets,
    scale: f32,
    /// Área cliente en coordenadas de pantalla (píxeles físicos).
    client: RECT,
    monitor: HMONITOR,
    visible: bool,
    /// Tapada del todo por otras ventanas (occlusion.rs): no se dibuja ni se captura.
    covered: bool,
    covered_at: Option<Instant>,
    effective: Level,
    /// El nivel ya se ha aplicado al menos una vez (exclusión de la captura).
    applied: bool,
    reason: Option<&'static str>,
    limits: Limits,
    excluded: Option<bool>,
    phase: f64,
    energy: f32,
    poke_until: Instant,
    moved_at: Option<Instant>,
    /// Último fotograma dibujado por el movimiento del borde (tope de 30 por segundo).
    anim_at: Instant,
    has_backdrop: bool,
    needs_blur: bool,
    needs_draw: bool,
    frames: u32,
    seed: f32,
}

struct Engine {
    app: AppHandle,
    wake: Arc<Wake>,
    gpu: Option<Gpu>,
    gpu_error: Option<String>,
    compositor: Option<Compositor>,
    surfaces: Vec<Surface>,
    captures: Vec<MonitorCapture>,
    game: bool,
    sys: SystemState,
    sys_at: Instant,
    last_tick: Instant,
    stats_at: Instant,
    frames: u32,
    gpu_ms: Option<f32>,
    slow_since: Option<Instant>,
}

impl Engine {
    fn new(app: AppHandle, wake: Arc<Wake>) -> Engine {
        let now = Instant::now();
        Engine {
            app,
            wake,
            gpu: None,
            gpu_error: None,
            compositor: None,
            surfaces: Vec::new(),
            captures: Vec::new(),
            game: false,
            sys: quality::read_system(false),
            sys_at: now,
            last_tick: now,
            stats_at: now,
            frames: 0,
            gpu_ms: None,
            slow_since: None,
        }
    }

    fn handle(&mut self, cmd: Cmd) {
        match cmd {
            Cmd::Attach {
                label,
                hwnd,
                options,
            } => {
                // Una ventana solo puede tener un árbol: se suelta el anterior primero.
                self.surfaces.retain(|s| s.label != label);
                let hwnd = HWND(hwnd as *mut _);
                if let Err(err) = self.attach(label.clone(), hwnd, options.clone()) {
                    eprintln!("[nyx] cristal: no se pudo preparar «{label}»: {err}");
                    let failed = Stats {
                        requested: options.quality,
                        effective: Level::Bajo,
                        reason: None,
                        fps: 0.0,
                        gpu_ms: None,
                        gpu_load: None,
                        capture_fps: None,
                        adapter: self.adapter(),
                        animating: false,
                        failed: Some(err.message()),
                    };
                    let _ = self.app.emit_to(label.as_str(), "glass-stats", failed);
                }
            }
            Cmd::Options { label, options } => {
                if let Some(s) = self.surface(&label) {
                    s.options = options;
                    // El usuario ha cambiado algo: se vuelve a intentar todo lo que falló o
                    // se bajó (GPU, captura).
                    s.limits = Limits::default();
                    s.poke_until = Instant::now() + POKE_FOR;
                    s.needs_blur = true;
                    s.needs_draw = true;
                }
            }
            Cmd::Shapes { label, shapes } => {
                if let Some(s) = self.surface(&label) {
                    s.shapes = shapes;
                    s.shapes.truncate(MAX_SHAPES);
                    s.needs_draw = true;
                }
            }
            Cmd::Poke { label } => {
                if let Some(s) = self.surface(&label) {
                    s.poke_until = Instant::now() + POKE_FOR;
                }
            }
            Cmd::Detach { label } => self.surfaces.retain(|s| s.label != label),
            Cmd::Game(on) => {
                self.game = on;
                self.sys = quality::read_system(on);
            }
        }
    }

    fn surface(&mut self, label: &str) -> Option<&mut Surface> {
        self.surfaces.iter_mut().find(|s| s.label == label)
    }

    fn adapter(&self) -> String {
        self.gpu
            .as_ref()
            .map(|g| g.adapter.clone())
            .unwrap_or_default()
    }

    fn attach(
        &mut self,
        label: String,
        hwnd: HWND,
        options: GlassOptions,
    ) -> windows::core::Result<()> {
        if self.gpu.is_none() {
            match Gpu::new() {
                Ok(gpu) => self.gpu = Some(gpu),
                Err(err) => {
                    self.gpu_error = Some(err.message());
                    return Err(err);
                }
            }
        }
        if self.compositor.is_none() {
            self.compositor = Some(Compositor::new()?);
        }
        let (Some(gpu), Some(compositor)) = (&self.gpu, &self.compositor) else {
            return Err(super::renderer::fail("sin GPU"));
        };
        let client = client_rect(hwnd);
        let size = rect_size(&client);
        let targets = gpu.new_targets(size.0, size.1)?;
        let layers = Layers::new(compositor, hwnd, &targets.swapchain, size)?;
        let now = Instant::now();
        let seed = (self.surfaces.len() as f32) * 17.0 + 3.0;
        self.surfaces.push(Surface {
            label,
            hwnd,
            options,
            shapes: Vec::new(),
            layers,
            targets,
            scale: dpi_scale(hwnd),
            client,
            // SAFETY: ventana viva.
            monitor: unsafe { MonitorFromWindow(hwnd, MONITOR_DEFAULTTONEAREST) },
            visible: false,
            covered: false,
            covered_at: None,
            // Se aplica de verdad en el primer tick (applied = false).
            effective: Level::Bajo,
            applied: false,
            reason: None,
            limits: Limits::default(),
            excluded: None,
            phase: 0.0,
            energy: 0.0,
            // Al aparecer, ondula un poco aunque el modo sea «al interactuar».
            poke_until: now + POKE_FOR,
            moved_at: None,
            anim_at: now,
            has_backdrop: false,
            needs_blur: true,
            needs_draw: true,
            frames: 0,
            seed,
        });
        Ok(())
    }

    fn tick(&mut self) -> Next {
        let now = Instant::now();
        let dt = now.duration_since(self.last_tick).as_secs_f64().min(0.1);
        self.last_tick = now;
        if now.duration_since(self.sys_at) >= SYSTEM_EVERY {
            self.sys = quality::read_system(self.game);
            self.sys_at = now;
        }
        // Ventanas cerradas sin avisar (por ejemplo, al cerrar la galería).
        // SAFETY: IsWindow solo consulta.
        self.surfaces
            .retain(|s| unsafe { IsWindow(Some(s.hwnd)) }.as_bool());
        if self.surfaces.is_empty() {
            self.captures.clear();
            return Next::Wait(INFINITE);
        }

        self.update_surfaces(now, dt);
        self.update_captures();

        let Some(gpu) = self.gpu.as_mut() else {
            return Next::Wait(IDLE_POLL_MS);
        };
        // Solo se mide (y se cuenta) cuando hay algo que dibujar: los fotogramas vacíos
        // bajarían la media de forma engañosa.
        let work = self
            .surfaces
            .iter()
            .any(|s| s.visible && (s.needs_draw || (s.needs_blur && s.effective.captures())));
        if work {
            gpu.begin_frame();
        }
        let mut drew = false;
        for s in self.surfaces.iter_mut().filter(|s| s.visible) {
            if s.effective.captures() && s.needs_blur {
                let capture = self.captures.iter().find(|c| c.monitor == s.monitor);
                if let Some((texture, size)) = capture.and_then(|c| c.texture()) {
                    let origin = capture.map(|c| c.origin).unwrap_or_default();
                    gpu.copy_backdrop(
                        &s.targets,
                        texture,
                        size,
                        s.client.left - origin.0,
                        s.client.top - origin.1,
                    );
                    let blur = s.options.blur.clamp(0.0, 1.0);
                    gpu.blur(
                        &s.targets,
                        2 + (blur * 3.0).round() as usize,
                        1.0 + blur * 1.5,
                    );
                    s.has_backdrop = true;
                    s.needs_blur = false;
                    s.needs_draw = true;
                }
            }
            if s.needs_draw {
                let params = params(s);
                if let Err(err) = gpu.draw_glass(&s.targets, &params) {
                    eprintln!("[nyx] cristal: al dibujar «{}»: {err}", s.label);
                }
                s.needs_draw = false;
                s.frames += 1;
                drew = true;
            }
        }
        if work && let Some(ms) = gpu.end_frame() {
            self.gpu_ms = Some(ms);
        }
        if drew {
            self.frames += 1;
        }

        if now.duration_since(self.stats_at) >= STATS_EVERY {
            self.emit_stats(now);
        }

        let busy = self.surfaces.iter().any(|s| {
            s.visible
                && (s.energy > 0.0
                    || s.moved_at
                        .is_some_and(|t| now.duration_since(t) < MOVING_FOR))
        });
        if busy {
            Next::Frame
        } else {
            Next::Wait(IDLE_POLL_MS)
        }
    }

    fn update_surfaces(&mut self, now: Instant, dt: f64) {
        let sys = self.sys;
        for s in &mut self.surfaces {
            let was_visible = s.visible;
            // SAFETY: consultas sobre una ventana viva.
            let shown = unsafe { IsWindowVisible(s.hwnd).as_bool() && !IsIconic(s.hwnd).as_bool() };
            if shown
                && s.covered_at
                    .is_none_or(|t| now.duration_since(t) >= OCCLUSION_EVERY)
            {
                let cover = occlusion::covering(s.hwnd, &client_rect(s.hwnd));
                if cover.is_some() != s.covered {
                    log_cover(&s.label, cover);
                }
                s.covered = cover.is_some();
                s.covered_at = Some(now);
            }
            s.visible = shown && !s.covered;
            if !s.visible {
                // Se conserva la última imagen desenfocada: al volver a verse (restaurar tras
                // minimizar, dejar de estar tapada) se dibuja con ella al momento y se renueva
                // en cuanto llega la captura. Si se olvidara, el primer fotograma saldría con
                // el tinte casi opaco y se vería un destello.
                continue;
            }
            if !was_visible {
                // Vuelve a verse: se redibuja ya y luego con lo que haya detrás ahora.
                s.needs_blur = true;
                s.needs_draw = true;
            }
            s.scale = dpi_scale(s.hwnd);

            // Tamaño y posición de la ventana.
            let client = client_rect(s.hwnd);
            let size = rect_size(&client);
            if size != rect_size(&s.client) {
                if let Some(gpu) = &self.gpu
                    && let Err(err) = gpu.resize_targets(&mut s.targets, size.0, size.1)
                {
                    eprintln!("[nyx] cristal: al redimensionar «{}»: {err}", s.label);
                }
                let _ = s.layers.set_size(size);
                s.needs_blur = true;
                s.needs_draw = true;
            }
            if client.left != s.client.left || client.top != s.client.top {
                s.moved_at = Some(now);
                s.needs_blur = true;
            }
            s.client = client;
            // SAFETY: ventana viva.
            s.monitor = unsafe { MonitorFromWindow(s.hwnd, MONITOR_DEFAULTTONEAREST) };

            // Nivel efectivo.
            let (level, reason) = quality::effective(s.options.quality, &sys, &s.limits);
            if !s.applied || level != s.effective {
                apply_level(&self.app, s, level);
            }
            s.reason = reason;

            // Movimiento del borde: la «energía» acelera y frena con suavidad.
            let allowed = quality::motion_allowed(s.options.motion, &sys);
            let target = match (allowed, s.options.motion) {
                (false, _) | (_, Motion::Quieto) => 0.0,
                (true, Motion::Siempre) => 1.0,
                (true, Motion::Interaccion) => {
                    if now < s.poke_until {
                        1.0
                    } else {
                        0.0
                    }
                }
            };
            s.energy += (target - s.energy) * (dt as f32 * 2.5).min(1.0);
            if target == 0.0 && s.energy < 0.02 {
                s.energy = 0.0;
            }
            if s.energy > 0.0 {
                s.phase += dt * f64::from(s.options.speed.max(0.0)) * f64::from(s.energy);
                if now.duration_since(s.anim_at) >= ANIM_INTERVAL {
                    s.anim_at = now;
                    s.needs_draw = true;
                }
            }
        }
    }

    /// Abre las capturas que hacen falta, cierra las demás y recoge los fotogramas nuevos.
    fn update_captures(&mut self) {
        let wanted: Vec<HMONITOR> = self
            .surfaces
            .iter()
            .filter(|s| s.visible && s.effective.captures())
            .map(|s| s.monitor)
            .collect();
        // Una captura que ya nadie necesita sigue viva un momento: si la ventana vuelve enseguida
        // (minimizar y restaurar, una burbuja tras otra), no hay que volver a arrancarla.
        let now = Instant::now();
        for c in &mut self.captures {
            if wanted.contains(&c.monitor) {
                c.needed_at = now;
            }
        }
        self.captures
            .retain(|c| now.duration_since(c.needed_at) < CAPTURE_LINGER);
        let Some(gpu) = &self.gpu else {
            return;
        };
        for monitor in wanted {
            if self.captures.iter().any(|c| c.monitor == monitor) {
                continue;
            }
            match MonitorCapture::start(monitor, &gpu.winrt_device, self.wake.clone()) {
                Ok(c) => self.captures.push(c),
                Err(err) => {
                    eprintln!("[nyx] cristal: captura no disponible: {err}");
                    for s in self.surfaces.iter_mut().filter(|s| s.monitor == monitor) {
                        s.limits.capture_failed = true;
                    }
                }
            }
        }
        for c in &mut self.captures {
            match c.poll(&gpu.winrt_device) {
                Ok(true) => {
                    for s in self.surfaces.iter_mut().filter(|s| s.monitor == c.monitor) {
                        s.needs_blur = true;
                    }
                }
                Ok(false) => {}
                Err(err) => eprintln!("[nyx] cristal: al leer la captura: {err}"),
            }
        }
    }

    fn emit_stats(&mut self, now: Instant) {
        let secs = now.duration_since(self.stats_at).as_secs_f32().max(0.001);
        self.stats_at = now;
        let engine_fps = self.frames as f32 / secs;
        self.frames = 0;
        let load = self.gpu_ms.map(|ms| ms * engine_fps / 10.0);

        // GPU que no llega de verdad (cada fotograma tarda más de lo que hay disponible): se
        // baja un solo nivel en las ventanas que capturan, hasta que el usuario cambie algo.
        // La carga en % solo se muestra: con otras apps usando la GPU sale inflada.
        if self.gpu_ms.is_some_and(|ms| ms > GPU_SLOW_MS) {
            let since = *self.slow_since.get_or_insert(now);
            if now.duration_since(since) >= GPU_SLOW_FOR {
                for s in self.surfaces.iter_mut().filter(|s| {
                    s.options.quality == Preference::Auto
                        && s.effective.captures()
                        && s.limits.gpu_cap.is_none()
                }) {
                    s.limits.gpu_cap = Some(s.effective.lower());
                }
                self.slow_since = None;
            }
        } else {
            self.slow_since = None;
        }

        let adapter = self.adapter();
        for s in &mut self.surfaces {
            let capture_fps = s
                .effective
                .captures()
                .then(|| self.captures.iter().find(|c| c.monitor == s.monitor))
                .flatten()
                .map(|c| c.frames as f32 / secs);
            let stats = Stats {
                requested: s.options.quality,
                effective: s.effective,
                reason: s.reason,
                fps: s.frames as f32 / secs,
                gpu_ms: self.gpu_ms,
                gpu_load: load,
                capture_fps,
                adapter: adapter.clone(),
                animating: s.energy > 0.0,
                failed: None,
            };
            s.frames = 0;
            let _ = self.app.emit_to(s.label.as_str(), "glass-stats", stats);
        }
        for c in &mut self.captures {
            c.frames = 0;
        }
    }
}

/// Cambia de nivel. La ventana se excluye de la captura de pantalla solo cuando captura
/// (si no, se vería a sí misma); en Bajo, Nyx sigue saliendo en capturas y directos.
fn apply_level(app: &AppHandle, s: &mut Surface, level: Level) {
    s.effective = level;
    s.applied = true;
    let exclude = level.captures();
    if s.excluded != Some(exclude) {
        s.excluded = Some(exclude);
        let hwnd = s.hwnd.0 as isize;
        // La afinidad se cambia desde el hilo dueño de la ventana.
        let _ = app.run_on_main_thread(move || {
            let affinity = if exclude {
                WDA_EXCLUDEFROMCAPTURE
            } else {
                WDA_NONE
            };
            // SAFETY: ventana viva de este proceso.
            if let Err(err) = unsafe { SetWindowDisplayAffinity(HWND(hwnd as *mut _), affinity) } {
                eprintln!("[nyx] cristal: SetWindowDisplayAffinity: {err}");
            }
        });
    }
    s.has_backdrop = false;
    s.needs_blur = true;
    s.needs_draw = true;
}

/// Color y opacidad del tinte según el tema y el modo.
fn tint(o: &GlassOptions, mode: Mode) -> ([f32; 3], f32) {
    let low = o.low_opacity.clamp(0.5, 1.0);
    // Tinte elegido en Apariencia (con su versión para el tema actual).
    let chosen = if o.dark { o.tint_dark } else { o.tint_light };
    if let Some([r, g, b]) = chosen {
        let rgb = [
            f32::from(r) / 255.0,
            f32::from(g) / 255.0,
            f32::from(b) / 255.0,
        ];
        let alpha = if mode == Mode::Tint { low } else { o.tint };
        return (rgb, alpha);
    }
    match (mode, o.dark) {
        // Bajo: el mismo tinte que el respaldo de CSS (theme/nyx.ts), con la opacidad de la
        // ventana (92 %; Ajustes, 97 %).
        (Mode::Tint, true) => ([36.0 / 255.0, 36.0 / 255.0, 38.0 / 255.0], low),
        (Mode::Tint, false) => ([242.0 / 255.0, 242.0 / 255.0, 247.0 / 255.0], low),
        (_, true) => ([28.0 / 255.0, 28.0 / 255.0, 30.0 / 255.0], o.tint),
        (_, false) => ([242.0 / 255.0, 242.0 / 255.0, 247.0 / 255.0], o.tint),
    }
}

fn params(s: &Surface) -> GlassParams {
    let o = &s.options;
    let mode = match s.effective {
        Level::Bajo => Mode::Tint,
        // Hasta que llega la primera captura, el tinte (nada de fondos negros).
        _ if !s.has_backdrop => Mode::Tint,
        Level::Medio => Mode::Blur,
        Level::Alto => Mode::Glass,
    };
    let (rgb, alpha) = tint(o, mode);
    let k = s.scale;
    let angle = (s.phase / LOOP_S) * TAU;
    let mut p = GlassParams {
        size: [s.targets.width as f32, s.targets.height as f32],
        loop_phase: [angle.cos() as f32, angle.sin() as f32],
        amp: o.amplitude.max(0.0) * k,
        wave: 150.0 * k,
        mode: mode as u32,
        count: s.shapes.len().min(MAX_SHAPES) as u32,
        tint: [rgb[0], rgb[1], rgb[2], alpha.clamp(0.0, 1.0)],
        refraction: o.refraction.max(0.0) * k,
        band: 18.0 * k,
        specular: o.specular.max(0.0),
        grain: 0.012,
        saturation: o.saturation.max(0.0),
        shadow: o.shadow.clamp(0.0, 1.0),
        scale: k,
        sheen: if o.dark { 0.035 } else { 0.09 },
        seed: s.seed,
        ..GlassParams::default()
    };
    for (i, shape) in s.shapes.iter().take(MAX_SHAPES).enumerate() {
        let (hw, hh) = (shape.w * 0.5 * k, shape.h * 0.5 * k);
        p.rects[i] = [shape.x * k + hw, shape.y * k + hh, hw, hh];
        p.params[i] = [shape.radius * k, shape.wobble.clamp(0.0, 2.0), 0.0, 0.0];
    }
    p
}

/// Área cliente en coordenadas de pantalla.
fn client_rect(hwnd: HWND) -> RECT {
    let mut rect = RECT::default();
    let mut origin = POINT::default();
    // SAFETY: consultas sobre una ventana viva; variables locales.
    unsafe {
        let _ = GetClientRect(hwnd, &mut rect);
        let _ = ClientToScreen(hwnd, &mut origin);
    }
    RECT {
        left: origin.x,
        top: origin.y,
        right: origin.x + rect.right,
        bottom: origin.y + rect.bottom,
    }
}

fn rect_size(r: &RECT) -> (u32, u32) {
    (
        (r.right - r.left).max(1) as u32,
        (r.bottom - r.top).max(1) as u32,
    )
}

fn dpi_scale(hwnd: HWND) -> f32 {
    // SAFETY: consulta sobre una ventana viva.
    unsafe { GetDpiForWindow(hwnd) }.max(96) as f32 / 96.0
}

/// Apunta en %LOCALAPPDATA%\Nyx\logs\glass.log cuándo una ventana queda tapada (y por
/// cuál) o vuelve a verse. Si un panel sale sin cristal, ahí se ve el motivo.
fn log_cover(label: &str, cover: Option<HWND>) {
    use std::io::Write;
    let Some(base) = std::env::var_os("LOCALAPPDATA") else {
        return;
    };
    let dir = std::path::PathBuf::from(base).join("Nyx").join("logs");
    let _ = std::fs::create_dir_all(&dir);
    let line = match cover {
        Some(h) => format!("{label}: tapada por {}", occlusion::describe(h)),
        None => format!("{label}: se ve"),
    };
    let secs = std::time::SystemTime::now()
        .duration_since(std::time::UNIX_EPOCH)
        .map(|d| d.as_secs())
        .unwrap_or_default();
    if let Ok(mut f) = std::fs::OpenOptions::new()
        .create(true)
        .append(true)
        .open(dir.join("glass.log"))
    {
        let _ = writeln!(f, "{secs} {line}");
    }
}
