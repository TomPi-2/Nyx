//! Galería de ejemplos del motor de cristal (bandeja → «Motor gráfico (ejemplos)»).
//!
//! - `glass-gallery`: ventana normal, con foco, como será Ajustes. Paneles de muestra y
//!   controles para cambiar el nivel, el borde y los parámetros viendo el coste en directo.
//! - `glass-bubble`: burbuja en una ventana que nunca toma el foco y deja pasar los clics,
//!   arriba en el centro, como la isla. Es el caso en el que el Acrylic de Windows fallaba.
//!
//! NYX_GLASS=1 abre la galería al arrancar.

use tauri::{AppHandle, Manager, WebviewUrl, WebviewWindowBuilder};

use crate::win32;

const GALLERY: &str = "glass-gallery";
const BUBBLE: &str = "glass-bubble";
const GALLERY_SIZE: (f64, f64) = (1040.0, 720.0);
const BUBBLE_SIZE: (f64, f64) = (620.0, 260.0);

pub fn toggle(app: &AppHandle) {
    if let Some(window) = app.get_webview_window(GALLERY) {
        let _ = window.close();
        close_bubble(app);
    } else if let Err(err) = open_gallery(app) {
        eprintln!("[nyx] galería del cristal: {err}");
    }
}

fn open_gallery(app: &AppHandle) -> tauri::Result<()> {
    let Some(m) = win32::cursor_monitor() else {
        return Ok(());
    };
    let (w, h) = GALLERY_SIZE;
    let window = WebviewWindowBuilder::new(app, GALLERY, WebviewUrl::App("motor".into()))
        .title("Nyx · motor gráfico")
        .inner_size(w, h)
        .transparent(true)
        .decorations(false)
        .shadow(false)
        .resizable(false)
        .visible(false)
        .build()?;
    if let Some(hwnd) = win32::hwnd(&window) {
        win32::remove_border(hwnd);
        let pw = (w * m.scale).round() as i32;
        let ph = (h * m.scale).round() as i32;
        let x = m.left + (m.width - pw) / 2;
        let y = m.top + (m.height - ph) / 2;
        window.set_position(tauri::PhysicalPosition::new(x, y))?;
    }
    window.show()?;
    window.set_focus()?;
    Ok(())
}

fn close_bubble(app: &AppHandle) {
    if let Some(window) = app.get_webview_window(BUBBLE) {
        let _ = window.close();
    }
}

fn open_bubble(app: &AppHandle) -> tauri::Result<()> {
    let (w, h) = BUBBLE_SIZE;
    let window = WebviewWindowBuilder::new(app, BUBBLE, WebviewUrl::App("motor/burbuja".into()))
        .title("Nyx · burbuja de prueba")
        .inner_size(w, h)
        .transparent(true)
        .decorations(false)
        .shadow(false)
        .always_on_top(true)
        .skip_taskbar(true)
        .resizable(false)
        .focused(false)
        .focusable(false)
        .visible(false)
        .build()?;
    if let (Some(hwnd), Some(m)) = (win32::hwnd(&window), win32::cursor_monitor()) {
        win32::make_non_activating(hwnd);
        win32::remove_border(hwnd);
        win32::set_click_through(hwnd, true);
        // Arriba en el centro como la isla, un poco más abajo para no taparla.
        let pw = (w * m.scale).round() as i32;
        let ph = (h * m.scale).round() as i32;
        let x = m.left + (m.width - pw) / 2;
        let y = m.top + (120.0 * m.scale).round() as i32;
        win32::place_topmost(hwnd, x, y, pw, ph);
        win32::show_no_activate(hwnd);
    }
    Ok(())
}

/// La galería abre y cierra la burbuja sin foco. Asíncrono: crear una ventana desde un
/// comando síncrono bloquea Tauri en Windows.
#[tauri::command]
pub async fn glass_toggle_bubble(app: AppHandle) -> bool {
    if app.get_webview_window(BUBBLE).is_some() {
        close_bubble(&app);
        false
    } else if let Err(err) = open_bubble(&app) {
        eprintln!("[nyx] burbuja de prueba: {err}");
        false
    } else {
        true
    }
}

/// Cierra la galería (botón de la propia galería).
#[tauri::command]
pub fn glass_close_gallery(app: AppHandle) {
    if let Some(window) = app.get_webview_window(GALLERY) {
        let _ = window.close();
    }
    close_bubble(&app);
}
