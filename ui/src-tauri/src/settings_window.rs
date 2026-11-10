//! Ventana de Ajustes (SPEC sección 13): la única ventana clásica de Nyx.
//!
//! Toma el foco, sale en la barra de tareas y en Alt+Tab, se mueve libremente y se puede
//! redimensionar (880 × 600 por defecto, mínimo 720 × 480). Sin bordes ni barra de título
//! del sistema: el fondo es el motor de cristal y la barra de título es propia.
//! Recuerda posición, tamaño y monitor en %LOCALAPPDATA%\Nyx\settings-window.json.

use std::path::PathBuf;

use serde::{Deserialize, Serialize};
use tauri::{
    AppHandle, Emitter, Manager, PhysicalPosition, PhysicalSize, WebviewUrl, WebviewWindow,
    WebviewWindowBuilder, WindowEvent,
};

use crate::win32;

pub const LABEL: &str = "settings";
const WIDTH: f64 = 880.0;
const HEIGHT: f64 = 600.0;
const MIN_WIDTH: f64 = 720.0;
const MIN_HEIGHT: f64 = 480.0;

/// Posición y tamaño en píxeles físicos.
#[derive(Clone, Copy, Debug, Deserialize, Serialize)]
struct Geometry {
    x: i32,
    y: i32,
    width: u32,
    height: u32,
}

/// Abre Ajustes o, si ya está abierta, la trae al frente.
pub fn open(app: &AppHandle) {
    open_at(app, None);
}

/// Igual, en una sección concreta («abre tus ajustes del modo partida»).
pub fn open_at(app: &AppHandle, section: Option<&str>) {
    if let Some(window) = app.get_webview_window(LABEL) {
        let _ = window.unminimize();
        let _ = window.show();
        let _ = window.set_focus();
        if let Some(section) = section {
            let _ = window.emit_to(LABEL, "settings://section", section);
        }
        return;
    }
    if let Err(err) = create(app, section) {
        eprintln!("[nyx] ventana de Ajustes: {err}");
    }
}

/// La isla lo pide cuando el núcleo dice «abre tus ajustes» (herramienta open_nyx_settings).
/// Asíncrono: crear una ventana desde un comando síncrono bloquea Tauri en Windows.
#[tauri::command]
pub async fn settings_open(app: AppHandle, section: Option<String>) {
    let section = section.filter(|s| matches!(s.as_str(), "apariencia" | "respuestas" | "partida"));
    open_at(&app, section.as_deref());
}

fn create(app: &AppHandle, section: Option<&str>) -> tauri::Result<()> {
    // Una ventana nueva aún no escucha eventos: la sección va en la dirección.
    let url = match section {
        Some(s) => format!("settings?section={s}"),
        None => "settings".to_string(),
    };
    let window = WebviewWindowBuilder::new(app, LABEL, WebviewUrl::App(url.into()))
        .title("Ajustes de Nyx")
        .inner_size(WIDTH, HEIGHT)
        .min_inner_size(MIN_WIDTH, MIN_HEIGHT)
        .transparent(true)
        .decorations(false)
        .shadow(false)
        .resizable(true)
        .visible(false)
        .build()?;
    if let Some(hwnd) = win32::hwnd(&window) {
        win32::remove_border(hwnd);
    }
    match load().filter(|g| on_some_monitor(&window, g)) {
        Some(g) => {
            window.set_size(PhysicalSize::new(g.width, g.height))?;
            window.set_position(PhysicalPosition::new(g.x, g.y))?;
        }
        None => center_on_cursor_monitor(&window)?,
    }
    let saver = window.clone();
    window.on_window_event(move |event| {
        if matches!(event, WindowEvent::CloseRequested { .. }) {
            save(&saver);
        }
    });
    window.show()?;
    window.set_focus()?;
    Ok(())
}

fn center_on_cursor_monitor(window: &WebviewWindow) -> tauri::Result<()> {
    let Some(m) = win32::cursor_monitor() else {
        return Ok(());
    };
    let w = (WIDTH * m.scale).round() as i32;
    let h = (HEIGHT * m.scale).round() as i32;
    window.set_position(PhysicalPosition::new(
        m.left + (m.width - w) / 2,
        m.top + (m.height - h) / 2,
    ))
}

/// ¿Se ve al menos un trozo de la barra de título en algún monitor? (Si se desconectó el
/// monitor donde estaba, se vuelve a centrar.)
fn on_some_monitor(window: &WebviewWindow, g: &Geometry) -> bool {
    let Ok(monitors) = window.available_monitors() else {
        return false;
    };
    monitors.iter().any(|m| {
        let (p, s) = (m.position(), m.size());
        let (right, bottom) = (p.x + s.width as i32, p.y + s.height as i32);
        g.x + 100 < right && g.x + g.width as i32 - 100 > p.x && g.y >= p.y && g.y + 40 < bottom
    })
}

fn path() -> Option<PathBuf> {
    let base = std::env::var_os("LOCALAPPDATA")?;
    Some(PathBuf::from(base).join("Nyx").join("settings-window.json"))
}

fn load() -> Option<Geometry> {
    let text = std::fs::read_to_string(path()?).ok()?;
    serde_json::from_str(&text).ok()
}

fn save(window: &WebviewWindow) {
    // Maximizada o minimizada no se guarda: se recuerda el tamaño normal.
    if window.is_maximized().unwrap_or(false) || window.is_minimized().unwrap_or(false) {
        return;
    }
    let (Ok(pos), Ok(size), Some(path)) = (window.outer_position(), window.inner_size(), path())
    else {
        return;
    };
    let g = Geometry {
        x: pos.x,
        y: pos.y,
        width: size.width,
        height: size.height,
    };
    if let (Some(dir), Ok(text)) = (path.parent(), serde_json::to_string(&g)) {
        let _ = std::fs::create_dir_all(dir);
        let _ = std::fs::write(path, text);
    }
}
