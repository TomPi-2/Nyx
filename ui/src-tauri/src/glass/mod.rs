//! Motor gráfico de cristal (docs/INSTALADOR-Y-MOTOR-GRAFICO.md, apartado 2).
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
pub mod gallery;
mod occlusion;
pub mod quality;
mod renderer;

use std::sync::Arc;
use std::sync::mpsc::{Sender, channel};

use serde::Deserialize;
use tauri::{AppHandle, Manager, Runtime, State, WebviewWindow};
use windows::Win32::Foundation::{CloseHandle, HANDLE};
use windows::Win32::System::Threading::{CreateEventW, SetEvent};
use windows::core::PCWSTR;

use crate::win32;
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

/// La ventana empieza a usar el cristal. Las estadísticas llegan en el evento `glass-stats`.
#[tauri::command]
pub fn glass_attach<R: Runtime>(
    window: WebviewWindow<R>,
    engine: State<'_, Engine>,
    options: GlassOptions,
) -> Result<(), String> {
    let hwnd = win32::hwnd(&window).ok_or("ventana sin HWND")?;
    engine.send(Cmd::Attach {
        label: window.label().to_string(),
        hwnd: hwnd.0 as isize,
        options,
    });
    Ok(())
}

#[tauri::command]
pub fn glass_set_options<R: Runtime>(
    window: WebviewWindow<R>,
    engine: State<'_, Engine>,
    options: GlassOptions,
) {
    engine.send(Cmd::Options {
        label: window.label().to_string(),
        options,
    });
}

#[tauri::command]
pub fn glass_set_shapes<R: Runtime>(
    window: WebviewWindow<R>,
    engine: State<'_, Engine>,
    shapes: Vec<Shape>,
) {
    engine.send(Cmd::Shapes {
        label: window.label().to_string(),
        shapes,
    });
}

/// Interacción (aparecer, pasar el ratón, pulsar): en el modo «al interactuar» el borde
/// ondula un rato.
#[tauri::command]
pub fn glass_poke<R: Runtime>(window: WebviewWindow<R>, engine: State<'_, Engine>) {
    engine.send(Cmd::Poke {
        label: window.label().to_string(),
    });
}

#[tauri::command]
pub fn glass_detach<R: Runtime>(window: WebviewWindow<R>, engine: State<'_, Engine>) {
    engine.send(Cmd::Detach {
        label: window.label().to_string(),
    });
}

/// Partida en curso (SPEC sección 9): nunca se captura la pantalla con un juego abierto.
/// De momento lo usa la galería para simularlo; en 5c lo enviará el modo partida.
#[tauri::command]
pub fn glass_set_game(engine: State<'_, Engine>, active: bool) {
    engine.send(Cmd::Game(active));
}
