//! Motor gráfico de cristal de Nyx (docs/INSTALADOR-Y-MOTOR-GRAFICO.md, apartado 2).
//!
//! Crate compartido (9.08): lo usan la app (`ui/src-tauri`) y el instalador (`installer/`).
//! Cada una define sus órdenes de Tauri (`glass_attach`…) como envoltorios de `Engine`.
//!
//! Dibuja los fondos de los paneles (burbujas, Ajustes, instalador) detrás de la WebView:
//! cristal en tiempo real con lo que hay detrás, silueta líquida sin bordes y niveles de
//! calidad que bajan solos (partida, batería, transparencias desactivadas…).
//!
//! La interfaz registra la ventana (`glass_attach`) y le pasa las formas de sus paneles en
//! píxeles CSS (`glass_set_shapes`); el resto ocurre en un hilo propio (engine.rs).
//!
//! Sustituye a la prueba de cristal de la fase 1 (Acrylic descartado: ver SPEC sección 11).

mod capture;
mod compositor;
mod engine;
mod occlusion;
pub mod quality;
mod renderer;

use std::sync::Arc;
use std::sync::mpsc::{Sender, channel};

use serde::Deserialize;
use tauri::{AppHandle, Manager, Runtime, WebviewWindow};
use windows::Win32::Foundation::{CloseHandle, HANDLE};
use windows::Win32::System::Threading::{CreateEventW, SetEvent};
use windows::core::PCWSTR;

use engine::Cmd;
pub use quality::{Motion, Preference};

/// Opciones de una ventana con cristal (camelCase desde la interfaz).
#[derive(Clone, Debug, Deserialize)]
#[serde(rename_all = "camelCase", default)]
pub struct GlassOptions {
    /// Auto o un nivel concreto (en partida se pasa a Bajo sin excepción).
    pub quality: Preference,
    pub motion: Motion,
    /// Amplitud del borde líquido (px CSS).
    pub amplitude: f32,
    /// Velocidad de la ondulación (1 = normal).
    pub speed: f32,
    /// Cantidad de desenfoque (0–1).
    pub blur: f32,
    /// Opacidad del tinte gris sobre el cristal (0–1).
    pub tint: f32,
    /// Desplazamiento máximo de la refracción junto al borde (px CSS).
    pub refraction: f32,
    pub saturation: f32,
    pub specular: f32,
    pub shadow: f32,
    /// Tema oscuro de Windows.
    pub dark: bool,
    /// Tinte de los paneles elegido en Apariencia (0–255) para cada tema; None = gris.
    pub tint_dark: Option<[u8; 3]>,
    pub tint_light: Option<[u8; 3]>,
    /// Opacidad del tinte en el nivel Bajo (sin desenfoque, lo de detrás se ve nítido: tiene
    /// que tapar lo bastante para leer). Ajustes, con mucho texto, la sube más.
    pub low_opacity: f32,
}

impl Default for GlassOptions {
    fn default() -> Self {
        GlassOptions {
            quality: Preference::Auto,
            motion: Motion::Siempre,
            amplitude: 3.5,
            speed: 1.0,
            blur: 0.6,
            tint: 0.45,
            refraction: 10.0,
            saturation: 1.15,
            specular: 0.35,
            shadow: 0.4,
            dark: true,
            tint_dark: None,
            tint_light: None,
            low_opacity: 0.92,
        }
    }
}

/// Un panel: rectángulo en píxeles CSS relativo a la ventana.
#[derive(Clone, Copy, Debug, Deserialize)]
pub struct Shape {
    pub x: f32,
    pub y: f32,
    pub w: f32,
    pub h: f32,
    pub radius: f32,
    /// Amplitud relativa del borde líquido de este panel (1 = la de las opciones).
    #[serde(default = "one")]
    pub wobble: f32,
    /// Grosor del anillo (px CSS): con más de 0 solo se dibuja esa franja junto al borde
    /// (la onda de «Nyx lista», 9.04). 0 = el panel entero.
    #[serde(default)]
    pub ring: f32,
}

fn one() -> f32 {
    1.0
}

/// Evento de Windows para despertar al hilo del motor.
pub struct Wake(HANDLE);

// SAFETY: un evento de Windows se puede señalar desde cualquier hilo.
unsafe impl Send for Wake {}
// SAFETY: ídem; solo se usa con SetEvent y en esperas.
unsafe impl Sync for Wake {}

impl Wake {
    fn new() -> windows::core::Result<Wake> {
        // SAFETY: evento anónimo de reinicio automático.
        let handle = unsafe { CreateEventW(None, false, false, PCWSTR::null())? };
        Ok(Wake(handle))
    }

    pub fn set(&self) {
        // SAFETY: el evento vive tanto como este objeto.
        let _ = unsafe { SetEvent(self.0) };
    }

    pub fn handle(&self) -> HANDLE {
        self.0
    }
}

impl Drop for Wake {
    fn drop(&mut self) {
        // SAFETY: evento propio, se cierra una vez.
        let _ = unsafe { CloseHandle(self.0) };
    }
}

/// Acceso al hilo del motor (estado de Tauri).
pub struct Engine {
    tx: Sender<Cmd>,
    wake: Arc<Wake>,
}

impl Engine {
    fn send(&self, cmd: Cmd) {
        let _ = self.tx.send(cmd);
        self.wake.set();
    }

    /// La ventana empieza a usar el cristal. Las estadísticas llegan en el evento
    /// `glass-stats`.
    pub fn attach<R: Runtime>(
        &self,
        window: &WebviewWindow<R>,
        options: GlassOptions,
    ) -> Result<(), String> {
        let hwnd = hwnd(window).ok_or("ventana sin HWND")?;
        self.send(Cmd::Attach {
            label: window.label().to_string(),
            hwnd: hwnd.0 as isize,
            options,
        });
        Ok(())
    }

    pub fn set_options(&self, label: &str, options: GlassOptions) {
        self.send(Cmd::Options {
            label: label.to_string(),
            options,
        });
    }

    pub fn set_shapes(&self, label: &str, shapes: Vec<Shape>) {
        self.send(Cmd::Shapes {
            label: label.to_string(),
            shapes,
        });
    }

    /// Interacción (aparecer, pasar el ratón, pulsar): en el modo «al interactuar» el borde
    /// ondula un rato.
    pub fn poke(&self, label: &str) {
        self.send(Cmd::Poke {
            label: label.to_string(),
        });
    }

    pub fn detach(&self, label: &str) {
        self.send(Cmd::Detach {
            label: label.to_string(),
        });
    }

    /// Partida en curso (SPEC sección 9): nunca se captura la pantalla con un juego abierto.
    pub fn set_game(&self, active: bool) {
        self.send(Cmd::Game(active));
    }
}

/// El HWND de una ventana de Tauri.
fn hwnd<R: Runtime>(window: &WebviewWindow<R>) -> Option<windows::Win32::Foundation::HWND> {
    use raw_window_handle::{HasWindowHandle, RawWindowHandle};
    let handle = window.window_handle().ok()?;
    match handle.as_raw() {
        RawWindowHandle::Win32(h) => Some(windows::Win32::Foundation::HWND(h.hwnd.get() as *mut _)),
        _ => None,
    }
}

/// Arranca el hilo del motor. No toca la GPU hasta que una ventana lo usa.
pub fn init(app: &AppHandle) {
    let wake = match Wake::new() {
        Ok(w) => Arc::new(w),
        Err(err) => {
            eprintln!("[nyx] cristal: sin evento: {err}");
            return;
        }
    };
    let (tx, rx) = channel();
    let thread_wake = wake.clone();
    let handle = app.clone();
    let spawned = std::thread::Builder::new()
        .name("nyx-cristal".into())
        .spawn(move || engine::run(rx, thread_wake, handle));
    if let Err(err) = spawned {
        eprintln!("[nyx] cristal: no se pudo arrancar el hilo: {err}");
        return;
    }
    app.manage(Engine { tx, wake });
}
