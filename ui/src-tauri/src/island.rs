//! Ventanas flotantes de la isla, arriba en el centro del monitor que toque (monitors.rs).
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
//! Un solo coordinador decide el monitor para las dos, así siempre van juntas. Si hay que
//! cambiar de monitor estando visibles y la animación está activada, les avisa
//! («overlay://move»: "out"), espera a que se encojan, las mueve y les vuelve a avisar ("in").
//!
//! Los comandos actúan sobre la ventana que los llama.

use std::collections::HashMap;
use std::sync::atomic::{AtomicBool, Ordering};
use std::sync::{Arc, Mutex};
use std::time::Duration;

use tauri::{
    AppHandle, Emitter, Manager, Runtime, State, WebviewUrl, WebviewWindow, WebviewWindowBuilder,
};
use tokio::sync::Notify;

use crate::monitors::{self, Policy};
use crate::win32::{self, MonitorArea};

pub const LABEL: &str = "island";
pub const PANELS: &str = "panels";
const OVERLAYS: [&str; 2] = [LABEL, PANELS];
/// Tamaño inicial; cada página pide el suyo (island_set_size).
const WIDTH: f64 = 600.0;
const HEIGHT: f64 = 300.0;
/// Cada cuánto se mira si hay que cambiar de monitor (el ratón ha pasado a otro…).
const FOLLOW_INTERVAL: Duration = Duration::from_millis(150);
/// Con botones, se mira dónde está el ratón con esta frecuencia (debe sentirse inmediato).
const HOVER_INTERVAL: Duration = Duration::from_millis(30);
/// Lo que tardan en encogerse antes de cambiar de monitor (app.css, «nyx-move-out»).
const MOVE_OUT: Duration = Duration::from_millis(130);
pub const MOVE_EVENT: &str = "overlay://move";

#[derive(Default)]
pub struct OverlayState {
    /// La página quiere verse.
    visible: AtomicBool,
    /// Se ve de verdad (en partida puede no haber monitor donde ponerla).
    shown: AtomicBool,
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

/// Estado de las ventanas flotantes y del monitor donde están.
#[derive(Default)]
pub struct Overlays {
    windows: Mutex<HashMap<String, Arc<OverlayState>>>,
    policy: Mutex<Policy>,
    /// Monitor donde están ahora (dispositivo); None = en ninguno (partida sin monitor libre).
    current: Mutex<Option<String>>,
    /// Para mirar enseguida si hay que cambiar (ajustes o partida nuevos).
    changed: Notify,
}

impl Overlays {
    fn get(&self, label: &str) -> Option<Arc<OverlayState>> {
        self.windows.lock().ok()?.get(label).cloned()
    }

    fn policy(&self) -> Policy {
        self.policy.lock().map(|p| p.clone()).unwrap_or_default()
    }

    fn current(&self) -> Option<String> {
        self.current.lock().ok().and_then(|c| c.clone())
    }

    fn set_current(&self, device: Option<String>) {
        if let Ok(mut c) = self.current.lock() {
            *c = device;
        }
    }
}

/// Monitor donde debería estar Nyx ahora mismo (o None si en ninguno).
fn target(overlays: &Overlays) -> Option<win32::Monitor> {
    let monitors = win32::monitors();
    let cursor = win32::cursor_device();
    let index = monitors::choose(&overlays.policy(), &monitors, cursor.as_deref())?;
    monitors.into_iter().nth(index)
}

/// Área del monitor actual de la isla (para el campo de texto: aparece en el mismo sitio).
pub fn current_area(app: &AppHandle) -> Option<MonitorArea> {
    let overlays = app.try_state::<Overlays>()?;
    let current = overlays.current();
    let monitors = win32::monitors();
    current
        .and_then(|d| monitors.iter().find(|m| m.device == d).map(|m| m.area))
        .or_else(|| target(&overlays).map(|m| m.area))
}

pub fn create(app: &AppHandle) -> tauri::Result<()> {
    app.manage(Overlays::default());
    create_overlay(app, LABEL, "island")?;
    create_overlay(app, PANELS, "panels")?;
    tauri::async_runtime::spawn(follow(app.clone()));
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
    if let Ok(mut map) = app.state::<Overlays>().windows.lock() {
        map.insert(label.to_string(), state.clone());
    }
    tauri::async_runtime::spawn(hover(window, state));
    Ok(())
}

/// La isla manda la política de monitores (ajustes y partida) cada vez que cambia.
#[tauri::command]
pub fn overlay_policy(overlays: State<'_, Overlays>, policy: Policy) {
    if let Ok(mut current) = overlays.policy.lock() {
        *current = policy;
    }
    overlays.changed.notify_one();
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
        let shown = state.shown.load(Ordering::Relaxed);
        if let Some(hwnd) = win32::hwnd(&window) {
            let want = rects.is_empty() || !shown || !win32::cursor_in(hwnd, &rects);
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
    let Some(state) = overlays.get(window.label()) else {
        return;
    };
    state.visible.store(visible, Ordering::Relaxed);
    if !visible {
        if let Some(hwnd) = win32::hwnd(&window) {
            win32::hide(hwnd);
        }
        state.shown.store(false, Ordering::Relaxed);
        return;
    }
    // Donde estén las demás o, si no hay ninguna a la vista, donde toque ahora.
    let any_shown = OVERLAYS
        .iter()
        .filter(|l| **l != window.label())
        .filter_map(|l| overlays.get(l))
        .any(|s| s.shown.load(Ordering::Relaxed));
    let device = if any_shown {
        overlays.current()
    } else {
        let t = target(&overlays).map(|m| m.device);
        overlays.set_current(t.clone());
        t
    };
    if let Some(area) = device.and_then(|d| area_of(&d)) {
        show(&window, &state, area);
    }
    overlays.changed.notify_one();
}

fn area_of(device: &str) -> Option<MonitorArea> {
    win32::monitors()
        .into_iter()
        .find(|m| m.device == device)
        .map(|m| m.area)
}

fn show<R: Runtime>(window: &WebviewWindow<R>, state: &OverlayState, area: MonitorArea) {
    place(window, state, area);
    if let Some(hwnd) = win32::hwnd(window) {
        win32::show_no_activate(hwnd);
    }
    state.shown.store(true, Ordering::Relaxed);
}

fn place<R: Runtime>(window: &WebviewWindow<R>, state: &OverlayState, area: MonitorArea) {
    let g = state.geometry.lock().map(|g| *g).unwrap_or_default();
    place_top_center_at(window, area, g.width, g.height, g.top);
}

/// Un solo coordinador para las dos ventanas: decide el monitor y las mueve juntas.
async fn follow(app: AppHandle) {
    let overlays = app.state::<Overlays>();
    loop {
        tokio::select! {
            _ = tokio::time::sleep(FOLLOW_INTERVAL) => {}
            _ = overlays.changed.notified() => {}
        }
        let wanted: Vec<(WebviewWindow, Arc<OverlayState>)> = OVERLAYS
            .iter()
            .filter_map(|l| Some((app.get_webview_window(l)?, overlays.get(l)?)))
            .filter(|(_, s)| s.visible.load(Ordering::Relaxed))
            .collect();
        if wanted.is_empty() {
            continue; // en reposo no hay nada que mover (al mostrarse se elige el monitor)
        }
        let next = target(&overlays);
        let next_device = next.as_ref().map(|m| m.device.clone());
        let current = overlays.current();
        let all_shown = wanted.iter().all(|(_, s)| s.shown.load(Ordering::Relaxed));
        if next_device == current && all_shown {
            continue;
        }
        let Some(monitor) = next else {
            // En partida sin monitor libre: se ocultan, pero siguen queriendo verse.
            for (window, state) in &wanted {
                if let Some(hwnd) = win32::hwnd(window) {
                    win32::hide(hwnd);
                }
                state.shown.store(false, Ordering::Relaxed);
            }
            overlays.set_current(None);
            continue;
        };
        let moving = current.is_some() && next_device != current;
        let animate = moving
            && overlays.policy().transition
            && wanted.iter().any(|(_, s)| s.shown.load(Ordering::Relaxed));
        if animate {
            for label in OVERLAYS {
                let _ = app.emit_to(label, MOVE_EVENT, "out");
            }
            tokio::time::sleep(MOVE_OUT).await;
        }
        overlays.set_current(next_device);
        for (window, state) in &wanted {
            show(window, state, monitor.area);
        }
        if animate {
            for label in OVERLAYS {
                let _ = app.emit_to(label, MOVE_EVENT, "in");
            }
        }
    }
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
    if state.shown.load(Ordering::Relaxed)
        && let Some(area) = overlays.current().and_then(|d| area_of(&d))
    {
        place(&window, &state, area);
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

/// Centra la ventana arriba de un monitor. Se recalcula cada vez, así que los cambios de
/// monitores, resolución o escala se aplican sin reiniciar.
pub fn place_top_center_at<R: Runtime>(
    window: &WebviewWindow<R>,
    m: MonitorArea,
    width: f64,
    height: f64,
    top: f64,
) {
    let Some(hwnd) = win32::hwnd(window) else {
        return;
    };
    let width = (width * m.scale).round() as i32;
    let height = (height * m.scale).round() as i32;
    let x = m.left + (m.width - width) / 2;
    let y = m.top + (top * m.scale).round() as i32;
    win32::place_topmost(hwnd, x, y, width, height);
}
