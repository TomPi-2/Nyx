//! La isla: ventana pequeña, transparente y siempre encima, centrada arriba en el monitor
//! donde está el ratón. Nunca toma el foco y se oculta del todo en reposo, para no
//! quedarse encima de un juego cuando no hace falta.

use std::sync::atomic::{AtomicBool, Ordering};
use std::sync::{Arc, Mutex};
use std::time::Duration;

use tauri::{AppHandle, Manager, Runtime, State, WebviewUrl, WebviewWindow, WebviewWindowBuilder};

use crate::win32;

pub const LABEL: &str = "island";
/// Tamaño lógico de la ventana: burbuja máxima (520 px) + margen para la sombra.
const WIDTH: f64 = 600.0;
const HEIGHT: f64 = 240.0;
/// Frecuencia con la que se sigue al ratón entre monitores mientras la isla es visible.
const FOLLOW_INTERVAL: Duration = Duration::from_millis(150);

/// Con botones, se mira dónde está el ratón con esta frecuencia (debe sentirse inmediato).
const HOVER_INTERVAL: Duration = Duration::from_millis(30);

#[derive(Default)]
pub struct IslandState {
    visible: AtomicBool,
    /// Botones visibles, en píxeles CSS de la ventana: solo ahí la isla recibe clics.
    hit_rects: Mutex<Vec<[f64; 4]>>,
}

pub fn create(app: &AppHandle) -> tauri::Result<()> {
    let window = WebviewWindowBuilder::new(app, LABEL, WebviewUrl::App("island".into()))
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

    let state = Arc::new(IslandState::default());
    app.manage(state.clone());
    tauri::async_runtime::spawn(follow_cursor(window.clone(), state.clone()));
    tauri::async_runtime::spawn(hover(window, state));
    Ok(())
}

/// La página informa de dónde están los botones (vacío = no hay).
#[tauri::command]
pub fn island_set_hit_rects(state: State<'_, Arc<IslandState>>, rects: Vec<[f64; 4]>) {
    if let Ok(mut current) = state.hit_rects.lock() {
        *current = rects;
    }
}

/// SPEC sección 11: la isla deja pasar los clics a lo de debajo salvo cuando el ratón está
/// encima de un botón. Mientras deja pasar los clics la página no recibe el ratón, así que
/// la posición se mira desde aquí.
async fn hover<R: Runtime>(window: WebviewWindow<R>, state: Arc<IslandState>) {
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
    state: State<'_, Arc<IslandState>>,
    visible: bool,
) {
    let Some(hwnd) = win32::hwnd(&window) else {
        return;
    };
    state.visible.store(visible, Ordering::Relaxed);
    if visible {
        place(&window);
        win32::show_no_activate(hwnd);
    } else {
        win32::hide(hwnd);
    }
}

async fn follow_cursor<R: Runtime>(window: WebviewWindow<R>, state: Arc<IslandState>) {
    let mut last = None;
    loop {
        tokio::time::sleep(FOLLOW_INTERVAL).await;
        if !state.visible.load(Ordering::Relaxed) {
            last = None;
            continue;
        }
        let monitor = win32::cursor_monitor();
        if monitor != last {
            place(&window);
            last = monitor;
        }
    }
}

fn place<R: Runtime>(window: &WebviewWindow<R>) {
    place_top_center(window, WIDTH, HEIGHT);
}

/// Centra la ventana arriba del monitor del ratón. Se recalcula cada vez, así que los
/// cambios de monitores, resolución o escala se aplican sin reiniciar.
pub fn place_top_center<R: Runtime>(window: &WebviewWindow<R>, width: f64, height: f64) {
    let (Some(hwnd), Some(m)) = (win32::hwnd(window), win32::cursor_monitor()) else {
        return;
    };
    let width = (width * m.scale).round() as i32;
    let height = (height * m.scale).round() as i32;
    let x = m.left + (m.width - width) / 2;
    win32::place_topmost(hwnd, x, m.top, width, height);
}
