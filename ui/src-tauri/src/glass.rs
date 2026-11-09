//! Prueba de cristal de la fase 1 (SPEC sección 11).
//!
//! Primera ronda (2026-11-09): el Acrylic de Windows 11 se ve sólido en ventanas que
//! nunca toman el foco, actualiza lo de detrás con ~2 s de retraso y recortarlo con una
//! región deja bordes en escalones. Queda descartado: la isla usa un tinte gris
//! translúcido (84 %) dibujado en CSS, que Windows compone en el mismo fotograma.
//!
//! La ventana muestra ese estilo final para revisar la paleta sobre fondos reales;
//! queda encima y deja pasar los clics. NYX_GLASS_TEST=1 la abre al arrancar.

use tauri::{AppHandle, Manager, WebviewUrl, WebviewWindowBuilder};

use crate::win32;

const LABEL: &str = "glass-test";
const WIDTH: f64 = 640.0;
const HEIGHT: f64 = 560.0;

pub fn toggle(app: &AppHandle) {
    if let Some(window) = app.get_webview_window(LABEL) {
        let _ = window.close();
    } else if let Err(err) = open(app) {
        eprintln!("[nyx] prueba de cristal: {err}");
    }
}

fn open(app: &AppHandle) -> tauri::Result<()> {
    let Some(m) = win32::cursor_monitor() else {
        return Ok(());
    };
    let window = WebviewWindowBuilder::new(app, LABEL, WebviewUrl::App("glass".into()))
        .title("Nyx · prueba de cristal")
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
    window.set_ignore_cursor_events(true)?;

    if let Some(hwnd) = win32::hwnd(&window) {
        win32::make_non_activating(hwnd);
        win32::remove_border(hwnd);
        let w = (WIDTH * m.scale).round() as i32;
        let h = (HEIGHT * m.scale).round() as i32;
        let x = m.left + (m.width - w) / 2;
        let y = m.top + (m.height - h) / 2;
        win32::place_topmost(hwnd, x, y, w, h);
        win32::show_no_activate(hwnd);
    }
    Ok(())
}
