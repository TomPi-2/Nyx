//! La isla: ventana pequeña, transparente y siempre encima, centrada arriba en el monitor
//! donde está el ratón. Nunca toma el foco y se oculta del todo en reposo, para no
//! quedarse encima de un juego cuando no hace falta.

use std::sync::Arc;
use std::sync::atomic::{AtomicBool, Ordering};
use std::time::Duration;

use tauri::{AppHandle, Manager, Runtime, State, WebviewUrl, WebviewWindow, WebviewWindowBuilder};

use crate::win32;

pub const LABEL: &str = "island";
/// Tamaño lógico de la ventana: burbuja máxima (520 px) + margen para la sombra.
const WIDTH: f64 = 600.0;
const HEIGHT: f64 = 240.0;
/// Frecuencia con la que se sigue al ratón entre monitores mientras la isla es visible.
const FOLLOW_INTERVAL: Duration = Duration::from_millis(150);

#[derive(Default)]
pub struct IslandState {
    visible: AtomicBool,
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
        .visible(false)
        .build()?;
    // Fase 1: la isla aún no tiene botones, así que los clics siempre la atraviesan.
    window.set_ignore_cursor_events(true)?;
    if let Some(hwnd) = win32::hwnd(&window) {
        win32::make_non_activating(hwnd);
        win32::remove_border(hwnd);
    }

    let state = Arc::new(IslandState::default());
    app.manage(state.clone());
    tauri::async_runtime::spawn(follow_cursor(window, state));
    Ok(())
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
