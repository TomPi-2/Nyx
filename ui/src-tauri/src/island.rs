//! Ventanas flotantes de la isla, arriba en el centro del monitor donde está el ratón.
//! Nunca toman el foco y se ocultan del todo en reposo, para no quedarse encima de un juego
//! cuando no hace falta (SPEC sección 11).
//!
//! Son dos (decisión 2026-11-10):
//! - `island`: la forma de Nyx. No captura la pantalla, así que sale siempre en capturas y
//!   directos.
//! - `panels`: los paneles (respuesta, confirmación, deshacer, aviso) sobre el motor de
//!   cristal, debajo de la forma con un hueco fijo. En Alto y Medio el motor la excluye de
//!   las capturas (si no, el cristal se vería a sí mismo).
//!
//! Los comandos actúan sobre la ventana que los llama.

use std::collections::HashMap;
use std::sync::atomic::{AtomicBool, Ordering};
use std::sync::{Arc, Mutex};
use std::time::Duration;

use tauri::{AppHandle, Manager, Runtime, State, WebviewUrl, WebviewWindow, WebviewWindowBuilder};

use crate::win32;

pub const LABEL: &str = "island";
pub const PANELS: &str = "panels";
/// Tamaño inicial; cada página pide el suyo (island_set_size).
const WIDTH: f64 = 600.0;
const HEIGHT: f64 = 300.0;
/// Frecuencia con la que se sigue al ratón entre monitores mientras la ventana es visible.
const FOLLOW_INTERVAL: Duration = Duration::from_millis(150);
/// Con botones, se mira dónde está el ratón con esta frecuencia (debe sentirse inmediato).
const HOVER_INTERVAL: Duration = Duration::from_millis(30);

#[derive(Default)]
pub struct OverlayState {
    visible: AtomicBool,
    /// Botones visibles, en píxeles CSS de la ventana: solo ahí la ventana recibe clics.
    hit_rects: Mutex<Vec<[f64; 4]>>,
    /// Tamaño (px CSS) y distancia desde arriba del monitor (px CSS).
    geometry: Mutex<Geometry>,
}

#[derive(Clone, Copy)]
struct Geometry {
    width: f64,
    height: f64,
    top: f64,
}

impl Default for Geometry {
    fn default() -> Self {
        Geometry {
            width: WIDTH,
            height: HEIGHT,
            top: 0.0,
        }
    }
}

/// Estado de cada ventana flotante, por etiqueta.
#[derive(Default)]
pub struct Overlays(Mutex<HashMap<String, Arc<OverlayState>>>);

impl Overlays {
    fn get(&self, label: &str) -> Option<Arc<OverlayState>> {
        self.0.lock().ok()?.get(label).cloned()
    }
}

pub fn create(app: &AppHandle) -> tauri::Result<()> {
    app.manage(Overlays::default());
    create_overlay(app, LABEL, "island")?;
    create_overlay(app, PANELS, "panels")?;
    Ok(())
}

fn create_overlay(app: &AppHandle, label: &str, route: &str) -> tauri::Result<()> {
    let window = WebviewWindowBuilder::new(app, label, WebviewUrl::App(route.into()))
        .title("Nyx")
        .inner_size(WIDTH, HEIGHT)
        .transparent(true)
        .decorations(false)
        .shadow(false)
        .always_on_top(true)
        .skip_taskbar(true)
        .resizable(false)
        .focused(false)
        // Para tao también: si alguna vez reescribe los estilos, que no quite NOACTIVATE.
        .focusable(false)
        .visible(false)
        .build()?;
    if let Some(hwnd) = win32::hwnd(&window) {
        win32::make_non_activating(hwnd);
        win32::remove_border(hwnd);
        // Atraviesa los clics salvo con el ratón encima de un botón (ver hover).
        win32::set_click_through(hwnd, true);
    }

    let state = Arc::new(OverlayState::default());
    if let Ok(mut map) = app.state::<Overlays>().0.lock() {
        map.insert(label.to_string(), state.clone());
    }
    tauri::async_runtime::spawn(follow_cursor(window.clone(), state.clone()));
    tauri::async_runtime::spawn(hover(window, state));
    Ok(())
}

/// La página informa de dónde están los botones (vacío = no hay).
#[tauri::command]
pub fn island_set_hit_rects<R: Runtime>(
    window: WebviewWindow<R>,
    overlays: State<'_, Overlays>,
    rects: Vec<[f64; 4]>,
) {
    if let Some(state) = overlays.get(window.label())
        && let Ok(mut current) = state.hit_rects.lock()
    {
        *current = rects;
    }
}

/// SPEC sección 11: deja pasar los clics a lo de debajo salvo cuando el ratón está encima de
/// un botón. Mientras deja pasar los clics la página no recibe el ratón, así que la posición
/// se mira desde aquí.
async fn hover<R: Runtime>(window: WebviewWindow<R>, state: Arc<OverlayState>) {
    let mut through = true;
    loop {
        let rects = state
            .hit_rects
            .lock()
            .map(|r| r.clone())
            .unwrap_or_default();
        let visible = state.visible.load(Ordering::Relaxed);
        if let Some(hwnd) = win32::hwnd(&window) {
            let want = rects.is_empty() || !visible || !win32::cursor_in(hwnd, &rects);
            if want != through {
                win32::set_click_through(hwnd, want);
                through = want;
            }
        }
        let wait = if rects.is_empty() {
            FOLLOW_INTERVAL
        } else {
            HOVER_INTERVAL
        };
        tokio::time::sleep(wait).await;
    }
}

/// La interfaz la muestra al salir de reposo y la oculta al terminar su animación de salida.
#[tauri::command]
pub fn island_set_visible<R: Runtime>(
    window: WebviewWindow<R>,
    overlays: State<'_, Overlays>,
    visible: bool,
) {
    let (Some(hwnd), Some(state)) = (win32::hwnd(&window), overlays.get(window.label())) else {
        return;
    };
    state.visible.store(visible, Ordering::Relaxed);
    if visible {
        place(&window, &state);
        win32::show_no_activate(hwnd);
    } else {
        win32::hide(hwnd);
    }
}

async fn follow_cursor<R: Runtime>(window: WebviewWindow<R>, state: Arc<OverlayState>) {
    let mut last = None;
    loop {
        tokio::time::sleep(FOLLOW_INTERVAL).await;
        if !state.visible.load(Ordering::Relaxed) {
            last = None;
            continue;
        }
        let monitor = win32::cursor_monitor();
        if monitor != last {
            place(&window, &state);
            last = monitor;
        }
    }
}

fn place<R: Runtime>(window: &WebviewWindow<R>, state: &OverlayState) {
    let g = state.geometry.lock().map(|g| *g).unwrap_or_default();
    place_top_center_at(window, g.width, g.height, g.top);
}

/// Cada página pide su tamaño y a qué distancia de arriba del monitor va (px CSS): la forma
/// arriba del todo y los paneles debajo, con el hueco fijo (overlay/panels/layout.ts).
#[tauri::command]
pub fn island_set_size<R: Runtime>(
    window: WebviewWindow<R>,
    overlays: State<'_, Overlays>,
    width: f64,
    height: f64,
    top: Option<f64>,
) {
    let Some(state) = overlays.get(window.label()) else {
        return;
    };
    if let Ok(mut g) = state.geometry.lock() {
        *g = Geometry {
            width: width.clamp(120.0, 1200.0),
            height: height.clamp(80.0, 1000.0),
            top: top.unwrap_or(0.0).clamp(0.0, 800.0),
        };
    }
    if state.visible.load(Ordering::Relaxed) {
        place(&window, &state);
    }
}

/// Luminancia (0–1) alrededor de la forma, para pasar de blanco a gris sobre fondos claros.
#[tauri::command]
pub fn island_backdrop_luma<R: Runtime>(
    window: WebviewWindow<R>,
    cx: f64,
    cy: f64,
    radius: f64,
) -> Option<f64> {
    win32::ring_luma(win32::hwnd(&window)?, cx, cy, radius)
}

/// Centra la ventana arriba del monitor del ratón. Se recalcula cada vez, así que los
/// cambios de monitores, resolución o escala se aplican sin reiniciar.
pub fn place_top_center<R: Runtime>(window: &WebviewWindow<R>, width: f64, height: f64) {
    place_top_center_at(window, width, height, 0.0);
}

fn place_top_center_at<R: Runtime>(window: &WebviewWindow<R>, width: f64, height: f64, top: f64) {
    let (Some(hwnd), Some(m)) = (win32::hwnd(window), win32::cursor_monitor()) else {
        return;
    };
    let width = (width * m.scale).round() as i32;
    let height = (height * m.scale).round() as i32;
    let x = m.left + (m.width - width) / 2;
    let y = m.top + (top * m.scale).round() as i32;
    win32::place_topmost(hwnd, x, y, width, height);
}
